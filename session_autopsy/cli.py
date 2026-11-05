"""Composition root and command delivery; native inference stays with the host."""
import argparse
import json
import os
from pathlib import Path
import sys

from session_autopsy.adapters.claude import ClaudeSource
from session_autopsy.adapters.codex import CodexSource
from session_autopsy.adapters.local import PrivateEvidenceStore, export_report
from session_autopsy.adapters.picker import choose
from session_autopsy.adapters.presentation import render, session_rows
from session_autopsy.adapters.prices import OfficialPrices
from session_autopsy.application.advisory import prepare_analysis
from session_autopsy.application.sessions import SessionService, filtered_sessions


def parser():
    result = argparse.ArgumentParser(description="Local session accounting; optional bounded native-host analysis")
    result.add_argument("command", choices=("list", "pick", "tokens", "postmortem", "improve", "prices", "install"), nargs="?", default="list")
    result.add_argument("selector", nargs="?")
    result.add_argument("--harness", choices=("claude", "codex"))
    result.add_argument("--claude-root", type=Path, default=Path.home() / ".claude/projects")
    result.add_argument("--codex-root", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "sessions")
    for flag in ("since", "until", "cwd", "query", "timezone"):
        result.add_argument("--" + flag)
    result.add_argument("--limit", type=int, default=20)
    result.add_argument("--format", choices=("text", "markdown", "json"), default="text")
    result.add_argument("--output", type=Path)
    result.add_argument("--prices-file", type=Path)
    result.add_argument("--offline", action="store_true")
    result.add_argument("--host", choices=("claude", "codex", "both"))
    result.add_argument("--deep", action="store_true")
    result.add_argument("--effort", choices=("medium", "high"))
    return result


def install(host):
    if host not in ("claude", "codex", "both"):
        raise ValueError("Installation requires --host claude, codex, or both")
    root = Path(__file__).resolve().parents[1]
    if not (root / "SKILL.md").exists():
        raise ValueError("Skill installation requires the source checkout; install from its launcher")
    destinations = []
    if host in ("claude", "both"):
        destinations.append(Path.home() / ".claude/skills/session-autopsy")
    if host in ("codex", "both"):
        destinations.append(Path.home() / ".agents/skills/session-autopsy")
    for destination in destinations:
        if (destination.exists() or destination.is_symlink()) and destination.resolve() != root:
            raise ValueError(f"Installation destination already exists: {destination}")
    for destination in destinations:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.is_symlink():
            destination.symlink_to(root, target_is_directory=True)
    return {"installed": [str(p) for p in destinations]}


def run(args):
    if args.command == "install":
        return install(args.host)
    prices = OfficialPrices(args.prices_file)
    if args.command == "prices":
        return prices.load(args.offline, refresh=args.selector == "refresh")
    service = SessionService([(ClaudeSource(), args.claude_root), (CodexSource(), args.codex_root)])
    sessions, warnings = service.discover()
    filtered = filtered_sessions(sessions, args.harness, args.since, args.until, args.cwd, args.query)
    if args.limit < 1:
        raise ValueError("Limit must be positive")
    rows = session_rows(filtered[:args.limit], args.timezone)
    if args.command == "list":
        for warning in warnings:
            print(warning, file=sys.stderr)
        return rows
    if args.command == "pick":
        return {"selected": choose(rows)}
    selector = resolve_selector(args.selector, rows)
    candidates = filtered if selector == "latest" else [s for s in sessions if not args.harness or s.harness == args.harness]
    selected = service.select(candidates, selector)
    report, family = service.report(sessions, selected, prices.load(args.offline))
    report["warnings"].extend(warnings + prices.warnings)
    if args.command in ("postmortem", "improve"):
        if args.host not in ("claude", "codex"):
            raise ValueError("Analysis preparation requires --host claude or codex")
        packet = prepare_analysis(report, family, args.command, args.host, args.deep, args.effort)
        path = PrivateEvidenceStore().save(json.dumps(packet, ensure_ascii=False))
        return {"evidence_file": str(path), "analysis_request": packet,
                "status": "Prepared evidence; the native host must run the approved worker"}
    return report


def resolve_selector(selector, rows):
    if selector == "current":
        selector = os.environ.get("CLAUDE_SESSION_ID") or os.environ.get("CODEX_THREAD_ID")
        if not selector:
            raise ValueError("Current session ID unavailable; select an explicit ID")
    if not selector:
        selector = choose(rows)
    return selector


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        value = run(args)
        output = render(value, args.format)
        if args.output:
            destination = export_report(args.output, output + "\n")
            print(f"Saved {destination}")
        else:
            print(output)
        return 0
    except (OSError, ValueError, ArithmeticError) as exc:
        print(f"session-autopsy: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
