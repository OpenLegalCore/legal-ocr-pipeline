# Recorded acceptance: 174-page legal PDF

## Status

This document records the accepted private production run and its associated
manual review. It turns the elapsed-time claim into a bounded technical record.
The source PDF, OCR output, metrics, review package, project identifier, and
artifact hashes remain private and are not distributed with this repository.

This record describes one run of one document. It must not be generalized into
a universal performance or accuracy guarantee.

## Required measurement fields

| Field | Recorded value |
|---|---|
| Measurement date | 2026-08-16. The local time of day and timezone were not retained in the accepted public record. |
| Model and provider | `gemini-3.5-flash-lite` through Google Vertex AI, API `v1`, location `eu` |
| Pages and rendering | 174 PDF pages; JPEG at 150 DPI and quality 95 |
| Concurrency | 16 page tasks |
| Retries | 0; 174 requests produced 174 accepted page checkpoints |
| External elapsed time | **45.23 seconds** process wall time |
| Internal elapsed time | `metrics.json` recorded `wall_seconds = 44.988` |
| Execution path | Local Linux workstation; `python vertex_parallel_pdf_ocr.py <private-input.pdf> <private-output-directory>`; local `pdftoppm` rendering; ADC-authenticated Vertex AI calls; local checkpoints and final files. The run was not executed in GitHub Actions or a container. |
| Review method | Private offline side-by-side visual review using the repository's generated manual-review package and a deterministic 40-page mandatory sample |
| Review result | `SAMPLE_PASS`: 39 `PASS`, 1 retained `MINOR`, 0 `ISSUE`, 0 `UNCERTAIN` among the 40 mandatory pages |

## Exact measured intervals

The two elapsed-time values measure different boundaries and must not be
substituted for each other.

### External process wall time: 45.23 seconds

The external timer started immediately before launching:

```text
python vertex_parallel_pdf_ocr.py <private-input.pdf> <private-output-directory>
```

It stopped when the process exited. It therefore includes interpreter startup,
imports, CLI parsing, the complete `run_ocr()` call, final `ocr.txt` and
`metrics.json` writes, and process shutdown.

### Internal `run_ocr()` wall time: 44.988 seconds

The internal monotonic timer starts on entry to `run_ocr()`, before input-path
validation, output-directory setup, PDF page counting, and checkpoint discovery.
It includes provider creation, page rendering, all provider calls, validation,
checkpoint writes, provider close, and the final checkpoint revalidation pass.

The internal value is captured while constructing the metrics object. It does
**not** include the subsequent final `ocr.txt` write or the `metrics.json` write.

The external 45.23-second value is therefore the appropriate end-to-end CLI
claim. The internal 44.988-second value is useful for implementation-level
comparison.

## Review method

The review was performed locally in a browser with no server or network
connection. The reviewer compared rendered source pages and OCR text side by
side. Completion required an explicit reviewer confirmation.

The mandatory set was the deterministic, de-duplicated union of:

- fixed boundary and known-interest pages;
- all pages classified as no-text;
- pages containing illegible markers;
- the five shortest nonblank OCR pages;
- the five longest OCR pages;
- ten pages selected with the review tool's fixed random seed.

The resulting 40 mandatory page numbers were:

```text
1, 2, 3, 4, 11, 20, 28, 32, 34, 36, 38, 42, 46, 47, 50, 56, 68, 70,
72, 74, 90, 96, 103, 110, 120, 121, 122, 150, 157, 158, 159, 162, 164,
165, 166, 168, 169, 170, 172, 174
```

Page 150 retained one `MINOR` name transcription variant. The reviewer judged
it legally immaterial. No mandatory page contained a substantive or legally
material issue.

## Limitations

- This was one accepted run, not a repeated statistical benchmark. No variance,
  confidence interval, cold/warm comparison, or throughput distribution was
  recorded.
- The private source was one 174-page image-based legal filing containing
  printed and graphic text, stamps, handwritten elements, and 18 no-text pages.
  It is not representative of every language, scan quality, layout, or document
  type.
- `SAMPLE_PASS` covers the deterministic 40-page sample, not all 174 pages.
- The review used human categorical judgments; it did not produce character or
  word error rates (CER/WER).
- One retained `MINOR` variance means the result is not evidence of literal
  100% transcription identity.
- Exact workstation hardware, Python version, Poppler version, dependency
  runtime versions, time of day, and network conditions were not retained in
  this public record. Pinned direct dependency versions are visible in
  `requirements.txt`, but the record does not prove those exact installed
  versions for this historical run.
- The confidential source and output are not publicly reproducible. Their
  hashes and the private evidence package must remain under maintainer control.
- Provider load, quotas, model revisions, regional routing, network latency, and
  pricing can change. A later run may produce different timing or text.
- Concurrency 16 is the configuration that passed this acceptance campaign. No
  controlled greater-than-16 sweep was accepted under identical conditions, so
  this record does not support a claim that a higher value would be faster or as
  reliable.
- The code rejects incomplete page responses with its terminal sentinel check,
  but that mechanism validates response completeness, not transcription truth.

## Rules for future benchmark claims

A new public performance or quality claim should create a new evidence record
rather than overwrite this one. At minimum, retain:

1. measurement date and exact code revision;
2. provider, model, API version, and region;
3. document characterization, page count, DPI, and image settings;
4. concurrency, attempt limit, request cap, requests, retries, and failures;
5. exact internal and external interval boundaries;
6. execution environment and dependency versions;
7. a hash-linked private input, output, metrics file, and review result;
8. review selection method, reviewed page count, result counts, and reviewer
   confirmation;
9. known limitations and deviations from the accepted configuration.
