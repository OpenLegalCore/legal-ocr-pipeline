# Minimal Vertex PDF OCR

This project transcribes one scanned PDF into page-oriented text with a small,
resumable Vertex AI pipeline. Successful page responses are validated and
checkpointed before the final document is published.

## Installation

Create a virtual environment and install the pinned direct dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --requirement requirements.txt
```

Poppler must provide `pdftoppm` on `PATH`.

## Google ADC

Authenticate with Google Application Default Credentials and select the Vertex
project locally:

```bash
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT="your-project-id"
```

Never store credentials in this repository.

## Run

The CLI accepts exactly one input PDF and one output directory:

```bash
python vertex_parallel_pdf_ocr.py input.pdf output-directory
```

## Outputs and resume

The output directory contains:

- `checkpoints/page-NNNNNN.txt`: validated per-page responses;
- `metrics.json`: compact campaign metrics;
- `ocr.txt`: published only after every PDF page succeeds.

Rerun the same command with the same output directory to resume. Valid existing
page checkpoints are not sent to the provider again.

## Locked FAST configuration

- Vertex API `v1`, location `eu`;
- model `gemini-3.5-flash-lite`;
- JPEG at 150 DPI and quality 95;
- concurrency 16;
- at most three attempts per page;
- at most 180 provider calls per campaign;
- exact terminal sentinel validation and streaming TTFT metrics.

## Legal verification

OCR is not authoritative evidence. Critical legal facts, names, dates, amounts,
deadlines, citations, and operative wording must be checked against the original
PDF before use.

## Manual OCR review

Run OCR to completion first, then build a private offline review package from
the source PDF and its final `ocr.txt`:

```bash
python build_manual_review.py \
  --pdf /path/document.pdf \
  --ocr /path/ocr.txt \
  --output /path/manual-review \
  --include-pages 5,8-10
```

The output must be a new or empty directory. Open its `index.html` locally;
no server or network connection is required. Progress is stored in browser
`localStorage` and can be imported or exported as JSON.

`SAMPLE_PASS` requires explicit reviewer confirmation and `PASS` or retained
`MINOR` status on every mandatory page. `FULL_PASS` requires confirmation and
`PASS` or `MINOR` on every page. Any `ISSUE` produces `FAIL`; `UNCERTAIN` and
unreviewed required pages prevent completion. These are reviewer decisions,
not automatic OCR quality judgments.

Review packages contain sensitive page images and OCR text. Keep generated
packages and `manual-review-result.json` private and never commit them.

## Offline verification

```bash
python -m py_compile vertex_parallel_pdf_ocr.py test_vertex_parallel_pdf_ocr.py build_manual_review.py test_manual_review.py
python -m unittest discover -v
git diff --check
```

PDFs, OCR text, metrics, checkpoints, rendered pages, and credentials are
confidential local artifacts and must not be committed.
