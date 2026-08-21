## Purpose

Describe the problem and the smallest change that solves it.

## Behavior and risk

- What behavior changes?
- What privacy, security, reliability, or compatibility assumptions change?
- Does this change the model, prompt, rendering, concurrency, retry policy, or
  request cap? If yes, link the new evidence plan or record.

## Verification

- [ ] `python -m py_compile vertex_parallel_pdf_ocr.py test_vertex_parallel_pdf_ocr.py build_manual_review.py test_manual_review.py`
- [ ] `python -m unittest discover -v`
- [ ] `git diff --check`
- [ ] Tests use mocks or synthetic data and make no provider calls.
- [ ] Documentation is updated where user-visible behavior changed.

## Privacy and contribution rights

- [ ] This pull request contains no private PDF, OCR text, page image,
      checkpoint, credential, project ID, token, provider log, or personal data.
- [ ] I have the right to submit this contribution under Apache-2.0.
- [ ] I have read `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md`.
