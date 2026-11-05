# Session Autopsy

Local session analytics for Claude Code and Codex: tokens, API cost estimates,
agent models, context compactions, and optimization advice. Accounting runs on
your machine against the session logs you select, and never modifies them.

## Install

Install from the plugin directory, or in one step with Claude Code 2.1.275 or later:

```sh
/plugin install session-autopsy --marketplace marcelomiyake/session-autopsy
```

In Codex, run `codex plugin marketplace add marcelomiyake/session-autopsy`, then
`codex plugin add session-autopsy@session-autopsy`. Start a new session afterward.

## Use

In Claude Code use `/session-autopsy tokens <id>`; in Codex use
`$session-autopsy improve <id>`. Plugin installs namespace the skill as
`session-autopsy:session-autopsy`, for example
`/session-autopsy:session-autopsy tokens <id>`. No selector means a chat list in the skill or an
interactive picker in the terminal. Select an ID, unique prefix, full path,
explicit `latest`, or `current` if the host exposes its session ID. Child agents
appear in their parent report and can also be selected by agent ID or path.

The launcher is self-contained and needs no packages. From this folder:

```sh
python3 skills/session-autopsy/scripts/autopsy.py list --format json
python3 skills/session-autopsy/scripts/autopsy.py tokens latest --harness codex --offline
```

| Mode | Result |
| --- | --- |
| `list` | Recent sessions with IDs, times, initial folder and prompt |
| `pick` | Searchable terminal picker with numbered fallback |
| `tokens <session>` | Usage, current API cost estimate, models/efforts, agents, compactions |
| `postmortem <session> --host codex` | Bounded evidence for native-host explanation |
| `improve <session> --host claude` | Bounded evidence for native-host optimization advice |
| `prices refresh` | Fetch and validate current official pricing |

Filter with `--harness claude|codex`, `--since YYYY-MM-DD`, `--until YYYY-MM-DD`,
`--cwd`, `--query`, `--limit`, and `--timezone America/Sao_Paulo`. Override session
locations using `--claude-root` and `--codex-root`. Default locations are
`~/.claude/projects` and `$CODEX_HOME/sessions` (normally `~/.codex/sessions`).
Use `--format json|markdown|text` and `--output report.json` to export into
`./reports`. Output accepts a simple filename with `.json`, `.md`, or `.txt`;
directory traversal and writing outside that folder are rejected. Move an export
explicitly afterward if needed. Reports are ignored by Git and created mode 0600.

## Accounting and analysis limits

Reported usage counts come from logs, with duplicates removed. Input includes
uncached tokens plus cache reads and writes; reasoning is part of output. Prices
are refreshed after 24 hours from official Markdown tables, with a bundled
baseline and last-good cache. Use `--offline` to disable refresh or
`--prices-file path.json` for a validated custom snapshot. Dollar amounts are
estimates at current API rates, not subscription charges or historical invoices.
Unknown models/tariffs are unpriced; unknown cache lifetimes produce ranges.
Aggregate native summaries may include background calls absent from request
records. They are displayed separately and never added to overlapping usage.
Referenced Codex history outside a rollout is flagged as incomplete.

The CLI prepares analysis evidence; it does not itself invoke an AI service.
The skill dispatches a native fresh-context worker on the invoking provider:
Haiku 5.5 or GPT-6 Luna at medium effort. Explicit `--deep` uses Sonnet 5.5 or
GPT-6.1 Sol at high effort; `--effort high` raises effort on the selected model.
No automatic escalation or cross-provider fallback is provided. The coordinator
still consumes tokens under the host's current model. If explicit native model
selection is unavailable, the skill returns the packet path and stops narrative
analysis. See [the analysis reference](skills/session-autopsy/references/analysis.md) for delegation
examples and evidence requirements.

## Data it sends

Session evidence stays local except for the bounded packet deliberately passed
to your invoking assistant provider. The only HTTP requests are GETs for fixed
public pricing and documentation pages on `platform.claude.com`, `code.claude.com`,
`developers.openai.com`, and `learn.chatgpt.com`; they carry no session data,
authentication, or cookies, and `--offline` disables them. There is no telemetry.
Full details are in the
[privacy policy](https://github.com/marcelomiyake/session-autopsy/blob/main/PRIVACY.md).

The [guide](https://github.com/marcelomiyake/session-autopsy/blob/main/docs/guide.md) has example prompts, an explanation of
each report section, and troubleshooting. Use is subject to the
[terms of service](https://github.com/marcelomiyake/session-autopsy/blob/main/TERMS.md). Report problems in
[GitHub issues](https://github.com/marcelomiyake/session-autopsy/issues).
