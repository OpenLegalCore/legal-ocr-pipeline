#!/usr/bin/env python3
"""Small, resumable page-by-page PDF OCR runner for Vertex AI."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Awaitable, Callable


MODEL = "gemini-3.5-flash-lite"
LOCATION = "eu"
API_VERSION = "v1"
DPI = 150
JPEG_QUALITY = 95
CONCURRENCY = 16
MAX_ATTEMPTS = 3
MAX_REQUESTS = 180


class PageValidationError(ValueError):
    """The provider response is not a complete page transcription."""


def page_sentinel(page: int) -> str:
    return f"[[END_OF_PAGE_{page}]]"


def page_prompt(page: int) -> str:
    marker = page_sentinel(page)
    return (
        "Transcribe every visible word on this single PDF page in reading order. "
        "Preserve paragraphs and represent tables as readable plain text. "
        "Use [ILLEGIBLE] where text cannot be read and [NO TEXT] for a blank page. "
        "Do not explain or summarize. End with this exact marker on its own line: "
        f"{marker}"
    )


def validate_page_response(text: str, page: int) -> str:
    """Return page text only when the exact terminal sentinel is present."""

    if not isinstance(text, str):
        raise PageValidationError("response is not text")
    marker = page_sentinel(page)
    stripped = text.rstrip()
    lines = stripped.splitlines()
    if not lines or lines[-1] != marker:
        raise PageValidationError("missing terminal sentinel")
    body = "\n".join(lines[:-1]).strip()
    if marker in body:
        raise PageValidationError("sentinel appears before the end")
    if not body:
        raise PageValidationError("empty page transcription")
    return body


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


class Checkpoints:
    def __init__(self, output_dir: Path) -> None:
        self.directory = output_dir / "checkpoints"

    def path(self, page: int) -> Path:
        return self.directory / f"page-{page:06d}.txt"

    def load(self, page: int) -> str | None:
        path = self.path(page)
        if not path.is_file():
            return None
        try:
            return validate_page_response(path.read_text(encoding="utf-8"), page)
        except (OSError, UnicodeError, PageValidationError):
            return None

    def save(self, page: int, response: str) -> None:
        validate_page_response(response, page)
        atomic_write_text(self.path(page), response.rstrip() + "\n")


def pdf_page_count(pdf_path: Path) -> int:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is required") from exc
    count = len(PdfReader(str(pdf_path)).pages)
    if count < 1:
        raise ValueError("PDF has no pages")
    return count


async def render_page(pdf_path: Path, page: int) -> bytes:
    """Render one page to JPEG with the fixed OCR settings."""

    command = [
        "pdftoppm",
        "-f",
        str(page),
        "-l",
        str(page),
        "-singlefile",
        "-jpeg",
        "-r",
        str(DPI),
        "-jpegopt",
        f"quality={JPEG_QUALITY}",
        str(pdf_path),
    ]
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        data, _ = await process.communicate()
    except OSError as exc:
        raise RuntimeError(f"could not render page {page}") from exc
    if process.returncode:
        raise RuntimeError(f"could not render page {page}")
    if not data:
        raise RuntimeError(f"renderer produced an empty page {page}")
    return data


class VertexProvider:
    """Minimal Google Gen AI client configured only for Vertex v1 in eu."""

    def __init__(self, project: str) -> None:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError("google-genai is required") from exc
        self._types = types
        self._client = genai.Client(
            vertexai=True,
            project=project,
            location=LOCATION,
            http_options=types.HttpOptions(api_version=API_VERSION),
        )

    @classmethod
    def from_environment(cls) -> "VertexProvider":
        project = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
        if not project:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT is required")
        return cls(project)

    async def generate(self, page: int, jpeg: bytes) -> tuple[str, float | None]:
        part = self._types.Part.from_bytes(data=jpeg, mime_type="image/jpeg")
        started = time.perf_counter()
        stream = await self._client.aio.models.generate_content_stream(
            model=MODEL,
            contents=[part, page_prompt(page)],
            config=self._types.GenerateContentConfig(temperature=0),
        )
        chunks: list[str] = []
        ttft: float | None = None
        async for response in stream:
            text = response.text or ""
            if text and ttft is None:
                ttft = time.perf_counter() - started
            chunks.append(text)
        return "".join(chunks), ttft

    async def close(self) -> None:
        await self._client.aio.aclose()


def assemble_ocr(pages: dict[int, str]) -> str:
    sections = [
        f"=== PAGE {page} ===\n{pages[page]}\n=== END PAGE {page} ==="
        for page in sorted(pages)
    ]
    return "\n\n".join(sections) + "\n"


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return round(ordered[index], 3)


async def run_ocr(
    pdf_path: Path,
    output_dir: Path,
    provider: Any | None = None,
    *,
    count_pages: Callable[[Path], int] = pdf_page_count,
    renderer: Callable[[Path, int], Awaitable[bytes]] = render_page,
) -> dict[str, object]:
    """OCR a PDF and return the short metrics document."""

    started = time.perf_counter()
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    if not pdf_path.is_file() or pdf_path.suffix.lower() != ".pdf":
        raise ValueError("input must be one existing PDF")
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError("output path must be a directory")
    output_dir.mkdir(parents=True, exist_ok=True)

    total_pages = count_pages(pdf_path)
    if total_pages > MAX_REQUESTS:
        raise ValueError(f"PDF exceeds the {MAX_REQUESTS}-request campaign limit")
    checkpoints = Checkpoints(output_dir)
    completed = {
        page: body
        for page in range(1, total_pages + 1)
        if (body := checkpoints.load(page)) is not None
    }
    resumed = len(completed)
    pending = [page for page in range(1, total_pages + 1) if page not in completed]
    requests = 0
    retries = 0
    first_attempts_remaining = len(pending)
    ttfts: list[float] = []
    failed: list[int] = []
    created_provider = False
    semaphore = asyncio.Semaphore(CONCURRENCY)

    if pending and provider is None:
        provider = VertexProvider.from_environment()
        created_provider = True

    async def process(page: int) -> None:
        nonlocal first_attempts_remaining, requests, retries
        async with semaphore:
            try:
                jpeg = await renderer(pdf_path, page)
            except Exception:
                first_attempts_remaining -= 1
                failed.append(page)
                return
            for attempt in range(1, MAX_ATTEMPTS + 1):
                if attempt == 1:
                    first_attempts_remaining -= 1
                elif requests + first_attempts_remaining >= MAX_REQUESTS:
                    failed.append(page)
                    return
                requests += 1
                if attempt > 1:
                    retries += 1
                try:
                    response, ttft = await provider.generate(page, jpeg)
                    if ttft is not None:
                        ttfts.append(ttft)
                    body = validate_page_response(response, page)
                    checkpoints.save(page, response)
                    completed[page] = body
                    return
                except Exception:
                    if attempt == MAX_ATTEMPTS:
                        failed.append(page)

    try:
        await asyncio.gather(*(process(page) for page in pending))
    finally:
        if created_provider:
            await provider.close()

    verified = {
        page: body
        for page in range(1, total_pages + 1)
        if (body := checkpoints.load(page)) is not None
    }
    failed = sorted(set(range(1, total_pages + 1)) - set(verified))
    metrics: dict[str, object] = {
        "model": MODEL,
        "pages": total_pages,
        "resumed": resumed,
        "succeeded": len(verified),
        "failed": failed,
        "requests": requests,
        "retries": retries,
        "wall_seconds": round(time.perf_counter() - started, 3),
        "ttft_p50_seconds": percentile(ttfts, 0.50),
        "ttft_p95_seconds": percentile(ttfts, 0.95),
    }
    if len(verified) == total_pages:
        atomic_write_text(output_dir / "ocr.txt", assemble_ocr(verified))
    atomic_write_text(
        output_dir / "metrics.json",
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
    )
    return metrics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="one input PDF")
    parser.add_argument("output_dir", type=Path, help="one output directory")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        metrics = asyncio.run(run_ocr(args.pdf, args.output_dir))
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"OCR failed: {exc}", file=sys.stderr)
        return 1
    if metrics["failed"]:
        print(f"OCR incomplete; failed pages: {metrics['failed']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
