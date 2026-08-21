# OpenLegalCore Legal OCR Pipeline

[![CI](https://github.com/OpenLegalCore/legal-ocr-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/OpenLegalCore/legal-ocr-pipeline/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

**A small, auditable, and resumable OCR building block for legal-document workflows.**

The pipeline transcribes one image-based PDF into page-oriented plain text with
Gemini on Google Vertex AI. It renders and submits pages independently, validates
every response, checkpoints completed pages, and publishes the combined OCR only
after every page succeeds.

This repository is the first public component of OpenLegalCore: *building the
open-source legal-tech engine*. It can be embedded in document-processing
workflows or user interfaces, including Open WebUI-based systems, but it does
not ship a web service, an Open WebUI connector, or a legal-decision system.

## Why this pipeline

- **Fail-closed output:** a terminal page sentinel must validate before a page is
  accepted, and `ocr.txt` is withheld if any page fails.
- **Safe resume:** validated page checkpoints are reused and are not resent to
  the provider.
- **Bounded execution:** concurrency, attempts, and campaign calls are fixed and
  covered by offline tests.
- **Private review tooling:** the generated side-by-side review package works
  locally without a server or network connection.
- **Minimal surface:** two pinned Python dependencies and one required system
  command, `pdftoppm`.

## Requirements

- Python 3.10 or newer; CI verifies Python 3.12;
- Poppler with `pdftoppm` available on `PATH`;
- a Google Cloud project with Vertex AI access to the configured model;
- Google Application Default Credentials (ADC).

On Debian or Ubuntu, Poppler is available as `poppler-utils`.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --requirement requirements.txt
```

Authenticate locally and select the Google Cloud project:

```bash
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT="your-project-id"
```

See Google's documentation for [Application Default
Credentials](https://cloud.google.com/docs/authentication/provide-credentials-adc)
and the [Vertex AI Google Gen AI SDK image
example](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/samples/googlegenaisdk-textgen-with-txt-img).
Never store credentials in this repository.

## Run

The CLI accepts exactly one input PDF and one output directory:

```bash
python vertex_parallel_pdf_ocr.py input.pdf output-directory
```

The output directory contains:

- `checkpoints/page-NNNNNN.txt` — validated per-page provider responses;
- `metrics.json` — compact campaign metrics;
- `ocr.txt` — combined page-oriented text, written only after every page passes.

Run the same command again with the same output directory to resume. A valid
checkpoint is revalidated locally and is not sent to Vertex AI again.

## Data flow and privacy

1. `pdftoppm` renders each PDF page to JPEG bytes locally.
2. The process sends each page image and the transcription prompt to Vertex AI.
3. Validated provider responses are stored as local checkpoints.
4. When all pages are present, the process writes `ocr.txt` and `metrics.json`
   locally.

Input pages therefore leave the local machine and are processed by Google Cloud.
Before using the pipeline with confidential or regulated documents, verify your
Google Cloud configuration, contractual terms, access controls, retention rules,
and applicable professional or legal obligations. The repository does not make
data-residency, confidentiality, or regulatory-compliance guarantees.

PDFs, OCR text, metrics, checkpoints, rendered pages, review packages, and
credentials are confidential local artifacts. The supplied `.gitignore` excludes
their common names and formats, but the operator remains responsible for
preventing disclosure.

## Accepted configuration

The current constants intentionally preserve the reviewed configuration:

| Setting | Value |
|---|---:|
| Provider | Google Vertex AI, API `v1`, location `eu` |
| Model | `gemini-3.5-flash-lite` |
| Page rendering | JPEG, 150 DPI, quality 95 |
| Concurrency | 16 pages |
| Maximum attempts | 3 per page |
| Campaign call cap | 180 provider calls |
| Generation temperature | 0 |

These are code constants rather than CLI tuning flags. Changes to them create a
new operating configuration and should be supported by tests and a new evidence
record. Concurrency 16 is the accepted setting; this project does not claim that
it is universally optimal for every quota, network, document, or model version.

## Recorded acceptance result

On 2026-08-16, the accepted configuration processed a private 174-page
image-based legal filing at 150 DPI in **45.23 seconds external process wall
time**. The run made 174 successful provider calls with zero retries and no
failed pages. Its internal `run_ocr()` interval was 44.988 seconds.

A deterministic 40-page offline manual sample completed with `SAMPLE_PASS`:
39 pages were marked `PASS`, one page retained a legally immaterial `MINOR`
transcription variance, and no page was marked `ISSUE` or `UNCERTAIN`.

This is a single-document acceptance result, not a universal speed or accuracy
guarantee. It is not a CER/WER measurement and it is not evidence of literal
100% transcription accuracy. The exact intervals, review method, execution path,
and limitations are recorded in [docs/RECORDED_ACCEPTANCE.md](docs/RECORDED_ACCEPTANCE.md).

## Manual OCR review

Run OCR to completion, then build a private offline review package from the
source PDF and its final `ocr.txt`:

```bash
python build_manual_review.py \
  --pdf /path/document.pdf \
  --ocr /path/ocr.txt \
  --output /path/manual-review \
  --include-pages 5,8-10
```

The output must be a new or empty directory. Open its `index.html` locally; no
server or network connection is required. Progress is stored in browser
`localStorage` and can be exported to or imported from JSON.

`SAMPLE_PASS` requires explicit reviewer confirmation and `PASS` or retained
`MINOR` status on every mandatory page. `FULL_PASS` requires confirmation and
`PASS` or `MINOR` on every page. Any `ISSUE` produces `FAIL`; `UNCERTAIN` and
unreviewed required pages prevent completion. These are reviewer decisions, not
automatic OCR quality judgments.

Review packages contain page images and OCR text. Keep generated packages and
`manual-review-result.json` private and never commit them.

## Offline verification

The test suite uses mock provider responses and a synthetic PDF. It makes no
Vertex AI or other provider calls.

```bash
python -m py_compile \
  vertex_parallel_pdf_ocr.py \
  test_vertex_parallel_pdf_ocr.py \
  build_manual_review.py \
  test_manual_review.py
python -m unittest discover -v
git diff --check
```

GitHub Actions runs the compile and unit-test checks plus a whole-tree text
hygiene check. CI never needs Google credentials and makes no provider calls.

## Scope and limitations

- The pipeline performs transcription, not legal analysis or verification.
- OCR is not authoritative evidence. Check names, dates, amounts, deadlines,
  citations, handwriting, and operative wording against the original PDF.
- Provider availability, quotas, model behavior, latency, and pricing are outside
  this repository's control and can change.
- The fixed 180-call cap means a new run cannot accept a PDF over 180 pages.
- The output is plain text with page boundaries; it does not preserve a complete
  visual layout or provide structured legal facts.
- There is no packaged library API, hosted service, container image, or graphical
  application in this release.

## Contributing and security

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening an issue or pull request.
Never attach private documents, OCR output, credentials, or provider identifiers.
Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).
Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

Copyright 2026 Rajko Majcen.

Licensed under the [Apache License 2.0](LICENSE). Preserve the attribution in
[NOTICE](NOTICE) when redistributing the work. Apache-2.0 does not grant rights
to OpenLegalCore names or marks except for reasonable attribution as described
by the license.
