"""Offline tests for the universal manual OCR review builder."""

from __future__ import annotations

import hashlib
import json
import stat
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfWriter

import build_manual_review as review


CORE_SHA256 = "db1e966a0ba3fdb7264bd69adf155becd2772f01825c946b8a9da87bc2fc7e6d"


def make_pdf(path: Path, pages: int) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    with path.open("wb") as stream:
        writer.write(stream)


def make_ocr(bodies: list[str]) -> str:
    return "\n\n".join(
        f"=== PAGE {page} ===\n{body}\n=== END PAGE {page} ==="
        for page, body in enumerate(bodies, 1)
    ) + "\n"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ManualReviewTests(unittest.TestCase):
    def test_generates_private_offline_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf, ocr, output = root / "input.pdf", root / "ocr.txt", root / "manual-review"
            make_pdf(pdf, 3)
            ocr.write_text(make_ocr(["alpha", "</script><img src=x onerror=alert(1)>", "[NO TEXT]"]))
            output.mkdir()

            review.build_package(pdf, ocr, output, {2})

            images = sorted((output / "pages").glob("*.jpg"))
            self.assertEqual([path.name for path in images], ["page-0001.jpg", "page-0002.jpg", "page-0003.jpg"])
            self.assertTrue(all(path.read_bytes().startswith(b"\xff\xd8") for path in images))
            self.assertTrue(all(path.read_bytes().endswith(b"\xff\xd9") for path in images))
            manifest = json.loads((output / "render-manifest.json").read_text())
            self.assertEqual(manifest["pdf"], {"sha256": digest(pdf), "size": pdf.stat().st_size})
            self.assertEqual(manifest["ocr"], {"sha256": digest(ocr), "size": ocr.stat().st_size})
            self.assertEqual(manifest["index_html"]["sha256"], digest(output / "index.html"))
            for item, image in zip(manifest["pages"], images):
                self.assertEqual((item["sha256"], item["size"]), (digest(image), image.stat().st_size))
            html = (output / "index.html").read_text()
            self.assertEqual(html.count("</script>"), 1)
            self.assertIn(r"\u003c/script\u003e", html)
            self.assertNotIn("<img src=x", html)
            self.assertNotIn("innerHTML", html)
            self.assertIn("textContent = PAGE_DATA", html)
            self.assertIn('loading="lazy"', html)
            for field in ("schema_version", "pdf_sha256", "ocr_sha256", "reviewed_pages", "minor_count", "reviewer_confirmed", "final_status"):
                self.assertIn(field, html)
            self.assertIn("<option>MINOR</option>", html)
            self.assertIn("status:review.status, note:review.note", html)
            self.assertIn('minor_count:pages.filter(page => page.status === "MINOR").length', html)
            self.assertNotIn("http://", html)
            self.assertNotIn("https://", html)
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE((output / "pages").stat().st_mode), 0o700)
            self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in output.rglob("*") if path.is_file()))

    def test_confirmation_values_are_fail_closed(self) -> None:
        template = Path(__file__).with_name("manual_review_template.html").read_text(encoding="utf-8")
        self.assertIn("confirmed:value.confirmed === true", template)
        self.assertIn('typeof value.reviewer_confirmed !== "boolean"', template)
        self.assertIn("confirmed:value.reviewer_confirmed", template)
        self.assertNotIn("Boolean(value.confirmed)", template)
        self.assertNotIn("Boolean(value.reviewer_confirmed)", template)

    def test_mandatory_selection_is_deterministic(self) -> None:
        pages = ["x" * page for page in range(1, 21)]
        pages[3], pages[4] = "[NO TEXT]", "[ILLEGIBLE]"
        even = {round(index * 19 / 9) + 1 for index in range(10)}
        expected = {1, 2, 3, 18, 19, 20, 4, 5, 6, 7, 16, 17, *even}
        first = review.mandatory_pages(pages, {7})
        self.assertEqual(first, sorted(expected))
        self.assertEqual(first, review.mandatory_pages(pages, {7}))

    def test_include_pages_supports_singletons_and_ranges(self) -> None:
        self.assertEqual(review.parse_include_pages("5,8-10"), {5, 8, 9, 10})
        with self.assertRaises(ValueError):
            review.parse_include_pages("10-8")
        with self.assertRaises(ValueError):
            review.mandatory_pages(["one", "two"], {3})
        self.assertIn(181, review.mandatory_pages(["text"] * 181))

    def test_rejects_malformed_ocr_structures(self) -> None:
        malformed = {
            "missing": "=== PAGE 1 ===\none\n=== END PAGE 1 ===\n\n=== PAGE 3 ===\nthree\n=== END PAGE 3 ===\n",
            "duplicate": "=== PAGE 1 ===\none\n=== END PAGE 1 ===\n\n=== PAGE 1 ===\nagain\n=== END PAGE 1 ===\n",
            "truncated": "=== PAGE 1 ===\npartial\n",
            "wrong order": "=== PAGE 2 ===\ntwo\n=== END PAGE 2 ===\n",
            "empty": "=== PAGE 1 ===\n\n=== END PAGE 1 ===\n",
        }
        for name, text in malformed.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                review.parse_ocr(text)

    def test_rejects_page_mismatch_and_nonempty_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf, ocr, output = root / "input.pdf", root / "ocr.txt", root / "review"
            make_pdf(pdf, 2)
            ocr.write_text(make_ocr(["one"]))
            with self.assertRaises(ValueError):
                review.build_package(pdf, ocr, output)
            ocr.write_text(make_ocr(["one", "two"]))
            output.mkdir()
            (output / "keep.txt").write_text("keep")
            with self.assertRaises(ValueError):
                review.build_package(pdf, ocr, output)
            self.assertEqual((output / "keep.txt").read_text(), "keep")

    def test_review_final_status_rules(self) -> None:
        mandatory = [1, 2]
        self.assertEqual(review.review_final_status(["PASS"] * 4, mandatory, False), "IN_PROGRESS")
        self.assertEqual(review.review_final_status(["PASS"] * 4, mandatory, True), "FULL_PASS")
        self.assertEqual(review.review_final_status(["PASS", "MINOR", "UNREVIEWED", "UNREVIEWED"], mandatory, True), "SAMPLE_PASS")
        retained = ["PASS", "MINOR", "PASS", "MINOR"]
        self.assertEqual(review.review_final_status(retained, mandatory, True), "FULL_PASS")
        self.assertEqual(retained, ["PASS", "MINOR", "PASS", "MINOR"])
        self.assertEqual(review.review_final_status(["PASS", "MINOR", "PASS", "MINOR"], mandatory, False), "IN_PROGRESS")
        self.assertEqual(review.review_final_status(["PASS", "PASS", "UNREVIEWED", "UNCERTAIN"], mandatory, True), "IN_PROGRESS")
        self.assertEqual(review.review_final_status(["PASS", "UNCERTAIN", "PASS", "PASS"], mandatory, True), "IN_PROGRESS")
        self.assertEqual(review.review_final_status(["PASS", "UNREVIEWED", "PASS", "PASS"], mandatory, True), "IN_PROGRESS")
        self.assertEqual(review.review_final_status(["PASS", "PASS", "ISSUE", "PASS"], mandatory, True), "FAIL")
        template = Path(review.__file__).with_name("manual_review_template.html").read_text()
        for status in ("IN_PROGRESS", "SAMPLE_PASS", "FULL_PASS", "FAIL"):
            self.assertIn(f'return "{status}"', template)

    def test_vertex_core_sha_is_unchanged(self) -> None:
        self.assertEqual(digest(Path(review.__file__).with_name("vertex_parallel_pdf_ocr.py")), CORE_SHA256)


if __name__ == "__main__":
    unittest.main()
