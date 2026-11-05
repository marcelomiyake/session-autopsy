# Session Autopsy guide

Session Autopsy explains where the tokens and money in a Claude Code or Codex
session went. It reads the session logs already on your machine, removes
duplicate usage records, prices each request at current public API rates, and
reports usage by model, effort, agent, and context compaction. On request, it
also prepares a bounded evidence packet so your own assistant can explain an
expensive session or suggest improvements.

It is for developers who want to understand or reduce the cost of their agent
sessions. It does not change sessions, settings, or your assistant's behavior.

## How it works

1. **Discover.** It lists sessions under `~/.claude/projects` and
   `$CODEX_HOME/sessions` (normally `~/.codex/sessions`), or under the folders
   you pass with `--claude-root` and `--codex-root`.
2. **Read.** It reads the selected session and its subagents line by line. Log
   files are opened read-only, and instructions inside them are treated as data.
3. **Account.** Each request is counted once. Input is uncached tokens plus cache
   reads and cache writes. Reasoning is part of output. Counters a log does not
   record stay unknown rather than zero.
4. **Price.** Requests are priced from official pricing pages, refreshed at most
   once a day, with a bundled snapshot as fallback. `--offline` uses the snapshot.
5. **Report.** You get a text, Markdown, or JSON report.
6. **Analyze (optional).** `postmortem` and `improve` write a bounded evidence
   packet to your private cache. The skill hands it to one fresh-context worker
   on the assistant you are already using: Claude Haiku 5.5 or GPT-6 Luna at
   medium effort, or Claude Sonnet 5.5 or GPT-6.1 Sol at high effort with `--deep`.

## Install, update, and remove

Install from the plugin directory, or with Claude Code 2.1.275 or later:

```sh
/plugin install session-autopsy --marketplace marcelomiyake/session-autopsy
```

In Codex:

```sh
codex plugin marketplace add marcelomiyake/session-autopsy
codex plugin add session-autopsy@session-autopsy
```

Start a new session after installing. Plugin updates arrive through the
directory or marketplace. Remove the plugin with
`claude plugin uninstall session-autopsy@session-autopsy` or
`codex plugin remove session-autopsy@session-autopsy`. For a terminal-only
command, run `uv tool install git+https://github.com/marcelomiyake/session-autopsy`.

## Example prompts

| Ask your assistant | What happens |
| --- | --- |
| `/session-autopsy:session-autopsy tokens` | Lists recent sessions, asks which one, and reports its tokens and estimated cost |
| "Use session-autopsy to show the token usage and cost of my latest Codex session" | Reports the newest Codex session without asking for a selection |
| `/session-autopsy:session-autopsy postmortem 4f2c` | Explains which requests, agents, and compactions made session `4f2c…` expensive |
| `/session-autopsy:session-autopsy improve 4f2c` | Suggests concrete changes, such as delegation or context hygiene, grounded in that session's evidence |
| "List my Claude Code sessions from last week in the checkout folder" | Filters the list with `--harness claude`, `--since`, and `--cwd` |

In Codex, use `$session-autopsy` in place of the slash command.

## Reading a report

| Section | Meaning |
| --- | --- |
| Summary | Requests, estimated API cost, compactions, and when prices were verified |
| Usage by model | Requests and tokens per model and effort, with a total row |
| Agents | The main session and its subagents, nested under their parent |
| Compactions | When the context was compacted, by what trigger, and the token counts before and after |
| Recorded summaries | Totals the harness wrote itself; shown for comparison, never added to usage |
| Summary reconciliation | Differences between recorded summaries and counted requests |
| Notes | How costs were estimated, plus any warnings about incomplete logs |

In the tables, `unknown` means the log did not record that counter. A cost such
as `$0.12–$0.15` is a range, for example when the cache lifetime was not
recorded. `≥$0.12` is a lower bound: some requests could not be priced, for
example because their model has no published price. Costs are estimates at current API rates. They are not subscription
charges or historical invoices.

The [plugin README](../plugins/session-autopsy/README.md) lists every mode and option.

## Troubleshooting

| Message or symptom | What to do |
| --- | --- |
| `No root sessions found` | Check that the harness has saved a session. If your logs live elsewhere, pass `--claude-root` or `--codex-root`, or set `CODEX_HOME`. |
| `Select a session ID, unique prefix, path, or explicit latest` | Pass a session from `list`, or `latest`. The tool never picks the latest session silently. |
| `Session selector matched N sessions` | Use more characters of the ID, or the full path. |
| `Current session ID unavailable` | The host did not expose its session ID. Select the session from `list` instead. |
| `No sessions matched` | Relax `--since`, `--until`, `--cwd`, `--query`, or `--harness`. |
| `Unknown timezone` | Use an IANA name such as `America/Sao_Paulo`. |
| `Pricing refresh failed; last-good snapshot retained` | You are offline or a pricing page changed. The report still works with the dated snapshot; check "Prices verified". |
| Cost shows `unpriced` or `≥` | The model has no published price in the snapshot. Run `prices refresh` later, or pass `--prices-file` with a validated snapshot. |
| `Output must be a simple filename inside ./reports` | Pass a plain name such as `--output report.md`, then move the file yourself. |
| Analysis stops and returns a packet path | Your host cannot start a worker on the approved model. Open the packet with the approved model yourself, as the skill explains. |
| The skill does not appear | Start a new session after installing, and do not install both the plugin and a linked checkout. |

## Data and privacy

Accounting and pricing run on your machine. The only network requests are GETs
for fixed public pricing and documentation pages; they carry no session data,
and `--offline` disables them. Optional analysis sends a bounded packet only to
the assistant provider you are already using. There is no telemetry. See the
[privacy policy](../PRIVACY.md) and the [terms of service](../TERMS.md).

## Support

Report bugs and ask questions in
[GitHub issues](https://github.com/marcelomiyake/session-autopsy/issues), using
synthetic examples instead of real transcripts. Report vulnerabilities privately
as described in [SECURITY.md](../SECURITY.md).
