"""The guide: how to use the client, one topic at a time.

Written once, as Markdown in `ui/guide/`, and read two ways: Options -> Help
draws it, and `/help <topic>` prints it in the output.  One source, so the two
cannot come to say different things.  The list of client commands is not
written out at all -- it is `commands.HELP`, the same list /help has always
printed, so it cannot fall behind the commands themselves.

Only a small part of Markdown is used, and only that part is understood:
headings, paragraphs, `-` and `1.` lists, tables, fenced code, `code`,
**bold**, *italic*, and links -- `[text](#topic)` to another topic,
`[text](options:page)` to a page of Options.
"""

from __future__ import annotations

import re
from importlib import resources

from .web import UI_PACKAGE

#: The generated topic's id; see commands().
COMMANDS = "commands"


def _folder():
    return resources.files(UI_PACKAGE[0]) / UI_PACKAGE[1] / "guide"


def topics() -> list[dict]:
    """Every topic, in order: id, title, a one-line summary, and its Markdown."""
    out = []
    for entry in sorted(_folder().iterdir(), key=lambda e: e.name):
        name = entry.name
        if not name.endswith(".md"):
            continue
        body = entry.read_text(encoding="utf-8")
        title, _, rest = body.partition("\n")
        rest = rest.strip()
        summary = rest.split("\n\n", 1)[0].replace("\n", " ")
        out.append({"id": re.sub(r"^\d+-", "", name[:-3]),
                    "title": title.lstrip("# ").strip(),
                    "summary": _plain_inline(summary),
                    "body": rest})
    out.append(commands())
    return out


def commands() -> dict:
    """The client's own commands, as a topic, from the list /help prints."""
    from .commands import HELP

    parts = []
    for title, blurb, rows in HELP:
        parts.append(f"## {title}")
        if blurb:
            parts.append(blurb)
        parts.append("| Type | To |\n|---|---|\n" + "\n".join(
            f"| `{verb.replace('|', chr(92) + '|')}` | {what.replace('|', chr(92) + '|')} |"
            for verb, what in rows))
    return {"id": COMMANDS, "title": "All client commands",
            "summary": "Every command that starts with /, grouped by what it is for.",
            "body": "Typed in the command box. They never reach 3K.\n\n"
                    + "\n\n".join(parts)}


def find(word: str) -> list[dict]:
    """Topics for a word: its own topic first, then any that mention it."""
    want = word.strip().lower().lstrip("/")
    if not want:
        return []
    every = topics()
    exact = [t for t in every if want in (t["id"], t["title"].lower())
             or t["id"].rstrip("s") == want.rstrip("s")]
    if exact:
        return exact[:1]
    named = [t for t in every if want in t["title"].lower()]
    if len(named) == 1:
        return named                      # "regex" is Patterns and regex
    rest = [t for t in every if t not in named
            and want in (t["title"] + " " + t["body"]).lower()]
    return named + rest


# --- as plain text, for the output -------------------------------------------

def _plain_inline(text: str) -> str:
    """Markup taken off.  What is inside `code` is left exactly as written --
    `.*` and `\\w+` are the point of it -- so it is set aside first."""
    parts = re.split(r"(`[^`]+`)", text)
    for n, part in enumerate(parts):
        if n % 2:
            parts[n] = part[1:-1]
            continue
        part = re.sub(r"\[([^\]]+)\]\((?:#|options:)[^)]*\)", r"\1", part)
        part = re.sub(r"<(https?://[^>]+)>", r"\1", part)
        part = re.sub(r"\*\*([^*]+)\*\*", r"\1", part)
        parts[n] = re.sub(r"(?<![\w*])\*([^*\s][^*]*)\*(?![\w*])", r"\1", part)
    return "".join(parts).replace("\\|", "|")


def _cells(row: str) -> list[str]:
    row = row.strip().strip("|")
    return [c.strip() for c in re.split(r"(?<!\\)\|", row)]


def plain(topic: dict) -> str:
    """A topic as the output shows it: no markup, tables lined up."""
    lines = [topic["title"].upper(), ""]
    block = topic["body"].split("\n")
    i = 0
    while i < len(block):
        line = block[i]
        if line.startswith("```"):
            i += 1
            while i < len(block) and not block[i].startswith("```"):
                lines.append("    " + block[i])
                i += 1
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(block) and block[i].startswith("|"):
                if not re.fullmatch(r"\|[\s|:-]+\|?", block[i].strip()):
                    rows.append([_plain_inline(c) for c in _cells(block[i])])
                i += 1
            wide = [max(len(r[c]) for r in rows if c < len(r))
                    for c in range(max(len(r) for r in rows))]
            for r in rows:
                lines.append("  " + "  ".join(c.ljust(wide[n]) for n, c in enumerate(r)).rstrip())
            continue
        if line.startswith("## "):
            lines += ["", line[3:].strip()]
        elif line.startswith("### "):
            lines.append(line[4:].strip())
        else:
            lines.append(_plain_inline(line))
        i += 1
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def index() -> str:
    """What /help ends with: the topics, and how to read one."""
    names = "  ".join(t["id"] for t in topics())
    return ("The guide -- /help <topic>, or Options -> Help:\n  " + names)
