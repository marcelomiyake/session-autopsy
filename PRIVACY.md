# Privacy

Discovery and token/cost accounting run locally against user-selected roots.
The tool reads transcripts, initial prompts, directories, timestamps, model and
effort settings, usage counters, compaction markers, and tool events. Source
files are never modified. Local report exports can contain confidential text.

Analysis is optional. A bounded evidence packet, including selected excerpts,
is passed to a native worker within the invoking Claude Code or Codex provider.
That provider receives the packet under your existing account and its policies.
The coordinator also consumes tokens under the model selected in your host.
This is not offline AI analysis. The application has no direct model API client.

The runtime's only HTTP requests fetch fixed public pricing/documentation paths
on `platform.claude.com`, `code.claude.com`, `developers.openai.com`, and
`learn.chatgpt.com`. They carry no session-derived queries, request bodies,
authentication, or cookies. Servers see normal connection metadata, including
your IP address. Redirects outside the fixed allowlist are rejected. Offline mode
uses local snapshots. Cached prices show their verification date.

Private runtime files live in the user's cache directory with restrictive
permissions. They remain until the user removes them. Explicit exports live at
the selected path. No telemetry, automatic report uploads, remote storage, or
third-party model routing is included.

Development is separate: GitHub stores project code and branding assets;
SonarCloud receives project source and synthetic test results. Image generation
receives only a generic branding prompt. Personal sessions, evidence packets,
private caches, and credentials are excluded from these services and commits.
