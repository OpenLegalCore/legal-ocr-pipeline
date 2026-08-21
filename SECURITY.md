# Security policy

## Supported versions

Until versioned maintenance branches are announced, security fixes apply to the
latest revision on the default branch. Older commits and tags are not supported
separately.

## Reporting a vulnerability

Do **not** open a public issue for a suspected vulnerability.

Use GitHub's private **Report a vulnerability** channel:

<https://github.com/OpenLegalCore/legal-ocr-pipeline/security/advisories/new>

If GitHub does not present a private reporting form, open a public issue titled
`Private security contact requested` without including technical details,
documents, credentials, identifiers, logs, or personal data. A maintainer will
establish a private channel.

Include only information needed to assess the problem:

- affected revision and environment;
- impact and realistic attack path;
- minimal reproduction using synthetic data;
- suggested mitigation, if known.

Never send a real legal document, OCR output, Google Cloud credential, project
identifier, access token, or unredacted provider log.

Maintainers will acknowledge reports as soon as practical, investigate them
privately, and coordinate remediation and disclosure according to severity and
available capacity. This project currently offers no fixed response-time SLA or
bug bounty.

## Security boundaries

The pipeline sends rendered page images to Google Vertex AI. Operators are
responsible for Google Cloud IAM, credentials, quotas, logging, contractual
terms, data governance, and all legal or professional obligations governing the
documents they process.

Provider outages, account compromise outside this repository, model accuracy,
prompt injection contained in a source document, and incorrect legal reliance on
OCR output are operational risks that callers must assess. Reports are still
welcome when repository behavior unexpectedly exposes data, bypasses validation,
breaks execution bounds, or mishandles local artifacts.
