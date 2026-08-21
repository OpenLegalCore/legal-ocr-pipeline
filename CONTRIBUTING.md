# Contributing to OpenLegalCore Legal OCR Pipeline

Thank you for helping improve a small, evidence-oriented legal OCR component.
Contributions are welcome when they preserve the project's narrow scope,
fail-closed behavior, privacy posture, and testability.

## Before opening an issue or pull request

- Search existing issues and pull requests first.
- Never upload or paste private PDFs, page images, OCR text, checkpoints,
  credentials, project IDs, access tokens, or provider request/response logs.
- Reduce reproductions to synthetic or clearly licensed public material.
- Use GitHub's private vulnerability reporting path for security problems; see
  [SECURITY.md](SECURITY.md).
- For a substantial behavior or interface change, open an issue before writing
  the implementation so scope and evidence requirements can be agreed first.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --requirement requirements.txt
```

Poppler must provide `pdftoppm` on `PATH`. On Debian or Ubuntu, install the
`poppler-utils` package.

## Required checks

Run all checks before submitting a pull request:

```bash
python -m py_compile \
  vertex_parallel_pdf_ocr.py \
  test_vertex_parallel_pdf_ocr.py \
  build_manual_review.py \
  test_manual_review.py
python -m unittest discover -v
git diff --check
```

The tests must remain offline. Do not add CI steps that require Google
credentials, provider calls, private documents, or billable resources.

## Change expectations

- Keep the implementation small and understandable.
- Preserve atomic writes, checkpoint revalidation, exact terminal sentinel
  validation, deterministic output order, and bounded provider calls.
- Add or update offline tests for behavior changes.
- Do not silently change the accepted model, rendering settings, concurrency,
  retry policy, or request cap.
- Treat a configuration or prompt change as a new operating configuration. A
  public speed or quality claim for it needs a separate evidence record.
- Keep generated artifacts and customer or case data out of the repository.
- Update user-facing documentation when behavior, setup, outputs, or limitations
  change.

## Pull requests

Keep each pull request focused. The description should state:

1. what changed and why;
2. the behavior and risk affected;
3. the offline tests run;
4. whether the accepted configuration or benchmark claim changed;
5. whether any data-handling or security assumption changed.

The repository uses maintainer review. Approval is not guaranteed merely because
a change is technically correct; scope, maintainability, privacy, and evidence
quality also matter.

## Contribution license

The project is licensed under the Apache License 2.0. Consistent with section 5
of that license, unless you explicitly state otherwise, a contribution
intentionally submitted for inclusion in the project is submitted under
Apache-2.0 without additional terms. No separate contributor license agreement
is required at this stage.

Do not submit code or content that you do not have the right to license.
