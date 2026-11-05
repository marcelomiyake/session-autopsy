"""An optional curses picker with a plain numbered fallback."""
import sys


def choose(rows):
    if not rows:
        raise ValueError("No sessions matched")
    if sys.stdin.isatty() and sys.stdout.isatty():
        selected = _interactive(rows)
        if selected is not None:
            return selected
    for i, row in enumerate(rows, 1):
        print(f"{i}. {row['started']} {row['cwd']} {row['initial_prompt'][:80]}", file=sys.stderr)
    try:
        selected = int(input("Session number: "))
        if not 1 <= selected <= len(rows):
            raise ValueError("Session number is out of range")
        return rows[selected - 1]["path"]
    except (EOFError, KeyboardInterrupt) as exc:
        raise ValueError("Selection canceled; pass an explicit session ID") from exc


def _interactive(rows):
    try:
        import curses
    except ImportError:
        return None
    try:
        return curses.wrapper(lambda screen: _screen(screen, rows, curses))
    except curses.error:
        return None


def _screen(screen, rows, curses):
    query, selected = "", 0
    while True:
        matching = [r for r in rows if query.lower() in " ".join(str(v) for v in r.values()).lower()]
        selected = min(selected, max(0, len(matching) - 1))
        height, width = screen.getmaxyx()
        screen.erase()
        screen.addnstr(0, 0, "Search: " + query + " (arrows, Enter, Esc)", max(0, width - 1))
        start = max(0, selected - max(1, height - 3) + 1)
        for number, row in enumerate(matching[start:start + max(0, height - 2)], start):
            text = f"{row['started']} {row['harness']} {row['cwd']} {row['initial_prompt']}".replace("\n", " ")
            screen.addnstr(number - start + 1, 0, text, max(0, width - 1), curses.A_REVERSE if number == selected else 0)
        key = screen.get_wch()
        if key in ("\n", "\r") and matching:
            return matching[selected]["path"]
        if key == "\x1b":
            raise ValueError("Selection canceled")
        if key == curses.KEY_UP:
            selected = max(0, selected - 1)
        elif key == curses.KEY_DOWN:
            selected = min(len(matching) - 1, selected + 1)
        elif key in (curses.KEY_BACKSPACE, "\x7f", "\b"):
            query = query[:-1]
        elif isinstance(key, str) and key.isprintable():
            query += key
