"""Small offline tests for the resumable Vertex PDF OCR runner."""

from __future__ import annotations

import asyncio
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pypdf import PdfWriter

import vertex_parallel_pdf_ocr as ocr


def response(page: int, body: str) -> str:
    return f"{body}\n{ocr.page_sentinel(page)}"


class MockProvider:
    def __init__(self, replies: dict[int, list[object]]) -> None:
        self.replies = {page: list(values) for page, values in replies.items()}
        self.calls: list[int] = []

    async def generate(self, page: int, jpeg: bytes) -> tuple[str, float]:
        self.calls.append(page)
        value = self.replies[page].pop(0)
        if isinstance(value, Exception):
            raise value
        return str(value), 0.01


async def fake_renderer(pdf: Path, page: int) -> bytes:
    return f"jpeg-{page}".encode()


class OfflineOcrTests(unittest.TestCase):
    def run_case(
        self,
        root: Path,
        provider: MockProvider,
        pages: int,
    ) -> dict[str, object]:
        pdf = root / "input.pdf"
        with mock.patch.object(Path, "is_file", return_value=True):
            return asyncio.run(
                ocr.run_ocr(
                    pdf,
                    root / "output",
                    provider,
                    count_pages=lambda _: pages,
                    renderer=fake_renderer,
                )
            )

    def test_resume_does_not_resend_successful_page(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            ocr.Checkpoints(output).save(1, response(1, "already done"))
            provider = MockProvider(
                {2: [response(2, "second")], 3: [response(3, "third")]}
            )

            metrics = self.run_case(root, provider, 3)

            self.assertEqual(provider.calls, [2, 3])
            self.assertEqual(metrics["resumed"], 1)
            self.assertEqual(metrics["failed"], [])

    def test_retry_stops_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider = MockProvider(
                {1: [RuntimeError("temporary"), "no sentinel", response(1, "ok")]}
            )

            metrics = self.run_case(root, provider, 1)

            self.assertEqual(provider.calls, [1, 1, 1])
            self.assertEqual(metrics["requests"], 3)
            self.assertEqual(metrics["retries"], 2)
            self.assertTrue((root / "output" / "ocr.txt").exists())

    def test_missing_sentinel_never_publishes_ocr(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider = MockProvider({1: ["partial", "partial", "partial"]})

            metrics = self.run_case(root, provider, 1)

            self.assertEqual(metrics["failed"], [1])
            self.assertEqual(provider.calls, [1, 1, 1])
            self.assertFalse((root / "output" / "ocr.txt").exists())
            stored = json.loads((root / "output" / "metrics.json").read_text())
            self.assertEqual(stored["failed"], [1])

    def test_final_ocr_is_assembled_in_page_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider = MockProvider(
                {1: [response(1, "one")], 2: [response(2, "two")]}
            )

            self.run_case(root, provider, 2)

            text = (root / "output" / "ocr.txt").read_text()
            self.assertEqual(
                text,
                "=== PAGE 1 ===\none\n=== END PAGE 1 ===\n\n"
                "=== PAGE 2 ===\ntwo\n=== END PAGE 2 ===\n",
            )

    def test_campaign_never_exceeds_180_provider_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider = MockProvider(
                {page: ["invalid"] * 3 for page in range(1, 175)}
            )

            metrics = self.run_case(root, provider, 174)

            self.assertEqual(metrics["requests"], 180)
            self.assertEqual(len(provider.calls), 180)
            self.assertFalse((root / "output" / "ocr.txt").exists())

    def test_real_pdftoppm_returns_jpeg_on_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / "synthetic.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=72, height=72)
            with pdf.open("wb") as stream:
                writer.write(stream)

            rendered = asyncio.run(ocr.render_page(pdf, 1))

            self.assertTrue(rendered)
            self.assertTrue(rendered.startswith(b"\xff\xd8"))
            self.assertFalse((Path.cwd() / "-.jpg").exists())

    @unittest.skipUnless(os.name == "posix", "POSIX mode check")
    def test_output_directories_are_owner_only_on_posix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            checkpoints = output / "checkpoints"
            checkpoints.mkdir(parents=True)
            output.chmod(0o755)
            checkpoints.chmod(0o755)
            provider = MockProvider({1: [response(1, "one")]})

            self.run_case(root, provider, 1)

            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(checkpoints.stat().st_mode), 0o700)

    @unittest.skipUnless(os.name == "posix", "POSIX mode check")
    def test_private_artifacts_are_owner_only_on_posix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider = MockProvider({1: [response(1, "one")]})

            self.run_case(root, provider, 1)

            output = root / "output"
            private_files = [
                output / "checkpoints" / "page-000001.txt",
                output / "ocr.txt",
                output / "metrics.json",
            ]
            for path in private_files:
                with self.subTest(path=path):
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(list(output.rglob(".*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
