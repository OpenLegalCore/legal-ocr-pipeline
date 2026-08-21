#!/usr/bin/env python3
"""Build a private, offline visual review package for completed PDF OCR."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Iterable

from vertex_parallel_pdf_ocr import pdf_page_count, render_page


RESULT_SCHEMA = "manual-ocr-review-result"
RESULT_SCHEMA_VERSION = 1
START = re.compile(r"=== PAGE ([1-9][0-9]*) ===")
END = re.compile(r"=== END PAGE ([1-9][0-9]*) ===")
TEMPLATE_TOKENS = re.compile(r"@@(PAGE_DATA|MANDATORY|PDF_SHA|OCR_SHA|PAGE_COUNT)@@")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_ocr(text: str) -> list[str]:
    """Parse the exact page-oriented format emitted by assemble_ocr."""

    lines = text.splitlines()
    pages: list[str] = []
    index = 0
    expected = 1
    while index < len(lines):
        start = START.fullmatch(lines[index])
        if not start or int(start.group(1)) != expected:
            raise ValueError(f"expected start marker for page {expected}")
        index += 1
        body: list[str] = []
        while index < len(lines) and not END.fullmatch(lines[index]):
            if START.fullmatch(lines[index]):
                raise ValueError(f"nested or duplicate page marker at page {expected}")
            body.append(lines[index])
            index += 1
        if index == len(lines):
            raise ValueError(f"missing end marker for page {expected}")
        end = END.fullmatch(lines[index])
        if not end or int(end.group(1)) != expected:
            raise ValueError(f"wrong end marker for page {expected}")
        content = "\n".join(body).strip()
        if not content:
            raise ValueError(f"empty OCR block for page {expected}")
        pages.append(content)
        expected += 1
        index += 1
        if index < len(lines):
            if lines[index] != "":
                raise ValueError("page blocks must be separated by a blank line")
            index += 1
    if not pages:
        raise ValueError("OCR contains no page blocks")
    return pages


def parse_include_pages(value: str | None) -> set[int]:
    pages: set[int] = set()
    if value is None:
        return pages
    if not value.strip():
        raise ValueError("--include-pages cannot be empty")
    for item in value.split(","):
        item = item.strip()
        if re.fullmatch(r"[1-9][0-9]*", item):
            pages.add(int(item))
            continue
        match = re.fullmatch(r"([1-9][0-9]*)-([1-9][0-9]*)", item)
        if not match or int(match.group(1)) > int(match.group(2)):
            raise ValueError(f"invalid page selection: {item}")
        pages.update(range(int(match.group(1)), int(match.group(2)) + 1))
    return pages


def evenly_spaced(page_count: int) -> set[int]:
    count = min(10, page_count)
    if count == 1:
        return {1}
    return {round(index * (page_count - 1) / (count - 1)) + 1 for index in range(count)}


def mandatory_pages(pages: list[str], included: Iterable[int] = ()) -> list[int]:
    count = len(pages)
    mandatory = set(range(1, min(3, count) + 1))
    mandatory.update(range(max(1, count - 2), count + 1))
    mandatory.update(page for page, text in enumerate(pages, 1) if "[NO TEXT]" in text)
    mandatory.update(page for page, text in enumerate(pages, 1) if "[ILLEGIBLE]" in text)
    nonblank = [
        (page, text) for page, text in enumerate(pages, 1) if text.strip() != "[NO TEXT]"
    ]
    mandatory.update(page for page, _ in sorted(nonblank, key=lambda item: (len(item[1]), item[0]))[:5])
    mandatory.update(page for page, _ in sorted(nonblank, key=lambda item: (-len(item[1]), item[0]))[:5])
    mandatory.update(evenly_spaced(count))
    mandatory.update(included)
    if any(page < 1 or page > count for page in mandatory):
        raise ValueError("included page is outside the document")
    return sorted(mandatory)


def review_final_status(statuses: list[str], mandatory: Iterable[int], confirmed: bool) -> str:
    if "ISSUE" in statuses:
        return "FAIL"
    if not confirmed or "UNCERTAIN" in statuses:
        return "IN_PROGRESS"
    if all(status in {"PASS", "MINOR"} for status in statuses):
        return "FULL_PASS"
    if all(statuses[page - 1] in {"PASS", "MINOR"} for page in mandatory):
        return "SAMPLE_PASS"
    return "IN_PROGRESS"


def script_json(value: object) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return (
        text.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def build_html(pages: list[str], mandatory: list[int], pdf_hash: str, ocr_hash: str) -> str:
    template = Path(__file__).resolve().with_name("manual_review_template.html").read_text(encoding="utf-8")
    values = {
        "PAGE_DATA": script_json(pages),
        "MANDATORY": script_json(mandatory),
        "PDF_SHA": script_json(pdf_hash),
        "OCR_SHA": script_json(ocr_hash),
        "PAGE_COUNT": str(len(pages)),
    }
    rendered = TEMPLATE_TOKENS.sub(lambda match: values[match.group(1)], template)
    if TEMPLATE_TOKENS.search(rendered):
        raise RuntimeError("unresolved HTML template token")
    return rendered


async def render_pages(pdf: Path, output: Path, count: int) -> list[dict[str, object]]:
    semaphore = asyncio.Semaphore(8)
    width = max(4, len(str(count)))

    async def one(page: int) -> dict[str, object]:
        async with semaphore:
            data = await render_page(pdf, page)
        if not (data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9")):
            raise RuntimeError(f"page {page} did not render as a complete JPEG")
        relative = Path("pages") / f"page-{page:0{width}d}.jpg"
        target = output / relative
        target.write_bytes(data)
        target.chmod(0o600)
        return {"page": page, "path": relative.as_posix(), "sha256": sha256(target), "size": len(data)}

    return list(await asyncio.gather(*(one(page) for page in range(1, count + 1))))


def build_package(pdf: Path, ocr: Path, output: Path, include: Iterable[int] = ()) -> None:
    pdf, ocr, output = Path(pdf), Path(ocr), Path(output)
    if not pdf.is_file() or pdf.suffix.lower() != ".pdf" or not ocr.is_file():
        raise ValueError("--pdf and --ocr must be existing files")
    pages = parse_ocr(ocr.read_text(encoding="utf-8"))
    count = pdf_page_count(pdf)
    if len(pages) != count:
        raise ValueError(f"PDF has {count} pages but OCR has {len(pages)}")
    selected = mandatory_pages(pages, include)
    if output.exists():
        if not output.is_dir() or any(output.iterdir()):
            raise ValueError("output must be a new or empty directory")
    else:
        output.mkdir(parents=True, mode=0o700)
    output.chmod(0o700)
    page_dir = output / "pages"
    page_dir.mkdir(mode=0o700)
    pdf_hash, ocr_hash = sha256(pdf), sha256(ocr)
    rendered = asyncio.run(render_pages(pdf, output, count))
    index = output / "index.html"
    index.write_text(build_html(pages, selected, pdf_hash, ocr_hash), encoding="utf-8")
    index.chmod(0o600)
    manifest = {
        "schema": "manual-review-render-manifest-v1",
        "pdf": {"sha256": pdf_hash, "size": pdf.stat().st_size},
        "ocr": {"sha256": ocr_hash, "size": ocr.stat().st_size},
        "index_html": {"path": "index.html", "sha256": sha256(index), "size": index.stat().st_size},
        "pages": rendered,
    }
    manifest_path = output / "render-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    manifest_path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--ocr", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--include-pages")
    args = parser.parse_args()
    try:
        build_package(args.pdf, args.ocr, args.output, parse_include_pages(args.include_pages))
    except (OSError, UnicodeError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
