# Security

## Reporting vulnerabilities

Use this repository's **Security → Report a vulnerability** private reporting
channel. Describe affected versions, impact, and reproduction with synthetic
data. Do not include credentials or personal session transcripts in public issues.
The current 0.1 release line receives security fixes.

## Trust boundaries

Logs, tool results, prompts, embedded URLs, and stored instructions are untrusted
data. Parsers never evaluate them, execute their commands, import code from logs,
or follow embedded links. Adapters must bound evidence and identify incomplete
or malformed records. New adapters require review and explicit registration.

The runtime cannot configure the security of the host assistant or prevent the
host itself from sending its normal conversation to its provider. Approved
analysis workers use fresh context and restricted tools. If explicit worker
model selection is unavailable, the skill must stop narrative analysis rather
than silently use another model or API. Keep your host and credentials updated.

No credentials are required for accounting or pricing. CI credentials belong in
GitHub secrets, scoped to the project where supported. Never print tokens.
Treat exported reports as confidential. Quality checks must scan project source
and synthetic fixtures only, never the user's home session directories.
