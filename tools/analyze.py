#!/usr/bin/env python3
"""Turn a capture into an inventory of what 3k.org actually speaks.

    python3 tools/analyze.py captures/first

Answers the questions the code currently guesses at: which codes are live,
what shapes their payloads take, whether the composite arrives on a cadence,
and what leads a room block.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import codes  # noqa: E402
from mud.capture import read_capture  # noqa: E402
from mud.scanner import Message, Scanner  # noqa: E402
from mud.telnet import TelnetFilter  # noqa: E402

# What the v9.0 white sheet documents.
SPEC_V9 = {
    "AAA", "AAB", "AAC", "AAD", "AAF", "AAG", "AAH",
    "BAA", "BAB", "BAD", "BAE", "BAF", "BBC", "BBD",
    "CAP", "CAA", "CDF", "CCF", "CEF", "DDD", "FFF",
}
# Present in Portal's source but not the white sheet.
PORTAL_ONLY = {"AAE", "BAC", "BBA", "BBB"}
KNOWN = SPEC_V9 | PORTAL_ONLY

BOLD, DIM, CYAN, YELLOW, GREEN, RESET = (
    "\x1b[1m", "\x1b[2m", "\x1b[36m", "\x1b[33m", "\x1b[32m", "\x1b[0m",
)


def replay(stem: Path) -> list[tuple[float | None, Message]]:
    tel, scan = TelnetFilter(), Scanner()
    found: list[tuple[float | None, Message]] = []
    for ts, chunk in read_capture(stem):
        clean, _, _ = tel.feed(chunk)
        for ev in scan.feed(clean):
            if isinstance(ev, Message):
                found.append((ts, ev))
    return found


def histogram(values: list[float], width: int = 34) -> list[str]:
    if not values:
        return []
    buckets = Counter(round(v, 1) for v in values)
    peak = max(buckets.values())
    lines = []
    for key in sorted(buckets):
        n = buckets[key]
        bar = "#" * max(1, int(width * n / peak))
        lines.append(f"    {key:>5.1f}s  {n:>5}  {bar}")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("capture", help="capture stem, e.g. captures/first")
    ap.add_argument("--examples", type=int, default=2)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    stem = Path(args.capture).with_suffix("")
    if not stem.with_suffix(".bin").exists():
        print(f"no such capture: {stem}.bin", file=sys.stderr)
        return 1

    records = replay(stem)
    if not records:
        print("no MIP messages -- did the handshake fire?", file=sys.stderr)
        return 1

    counts: Counter[str] = Counter()
    arity: defaultdict[str, Counter[int]] = defaultdict(Counter)
    samples: defaultdict[str, list[str]] = defaultdict(list)
    times: defaultdict[str, list[float]] = defaultdict(list)
    successor: defaultdict[str, Counter[str]] = defaultdict(Counter)

    composite_tags: Counter[str] = Counter()
    gline_labels: dict[str, str] = {}
    haa_kinds: Counter[str] = Counter()
    haa_verbs: Counter[str] = Counter()

    prev_code = None
    for ts, msg in records:
        counts[msg.code] += 1
        arity[msg.code][len(msg.data.split("~"))] += 1
        if ts is not None:
            times[msg.code].append(ts)
        if len(samples[msg.code]) < args.examples and msg.data:
            samples[msg.code].append(msg.data)
        if prev_code:
            successor[prev_code][msg.code] += 1
        prev_code = msg.code

        if msg.code == "FFF":
            values, unknown = codes.parse_composite(msg.data)
            for tag, name in codes.COMPOSITE_TAGS.items():
                if name in values:
                    composite_tags[tag] += 1
            for tag in unknown:
                composite_tags[f"?{tag}"] += 1
            for line in (values.get("gline1"), values.get("gline2")):
                if isinstance(line, str):
                    for label, f in codes.parse_gline(line).items():
                        gline_labels[label] = f.value
        elif msg.code in codes.ROOM_RECORD_CODES:
            obj = codes.parse_haa(msg.data)
            haa_kinds[obj.kind] += 1
            for action in obj.actions:
                haa_verbs[action.split()[0].lower()] += 1

    undocumented = sorted(set(counts) - KNOWN)

    if args.json:
        print(json.dumps({
            "messages": len(records),
            "codes": dict(counts),
            "undocumented": undocumented,
            "composite_tags": dict(composite_tags),
            "gline_labels": gline_labels,
            "haa_kinds": dict(haa_kinds),
            "haa_verbs": dict(haa_verbs),
        }, indent=2))
        return 0

    span = ""
    all_ts = [t for t, _ in records if t is not None]
    if all_ts:
        span = f" over {max(all_ts) - min(all_ts):.0f}s"
    print(f"\n{BOLD}{len(records)} MIP messages{span}, "
          f"{len(counts)} distinct codes{RESET}\n")

    print(f"{BOLD}code   count  fields  provenance{RESET}")
    for code, n in counts.most_common():
        shapes = ",".join(str(k) for k in sorted(arity[code]))
        if code in SPEC_V9:
            tag = f"{DIM}spec v9.0{RESET}"
        elif code in PORTAL_ONLY:
            tag = f"{CYAN}Portal source only{RESET}"
        else:
            tag = f"{YELLOW}UNDOCUMENTED{RESET}"
        print(f"{code:<5} {n:>7}  {shapes:>6}  {tag}")
        for s in samples[code]:
            print(f"{DIM}         {s[:96]}{RESET}")

    if undocumented:
        print(f"\n{YELLOW}{BOLD}Undocumented codes: "
              f"{', '.join(undocumented)}{RESET}")
        print(f"{DIM}  In no white sheet and no released client. "
              f"The wire is the specification.{RESET}")

    if composite_tags:
        print(f"\n{BOLD}composite tags{RESET}")
        for tag, n in composite_tags.most_common():
            name = codes.COMPOSITE_TAGS.get(tag, YELLOW + "unknown" + RESET)
            print(f"  {tag:<3} {n:>6}  {name}")

    if gline_labels:
        print(f"\n{BOLD}guild-line fields discovered{RESET}")
        for label, value in sorted(gline_labels.items()):
            print(f"  {label:<22} = {value}")

    if haa_kinds:
        print(f"\n{BOLD}room contents{RESET}")
        print(f"  kinds:  {dict(haa_kinds)}")
        print(f"  verbs:  {', '.join(sorted(haa_verbs))}")

    # cadence: is the composite round-driven, or change-driven?
    fff = times.get("FFF", [])
    if len(fff) > 4:
        deltas = [b - a for a, b in zip(fff, fff[1:]) if b > a]
        if deltas:
            print(f"\n{BOLD}FFF inter-arrival{RESET}  "
                  f"median {statistics.median(deltas):.2f}s  "
                  f"min {min(deltas):.2f}s  max {max(deltas):.2f}s")
            for line in histogram([d for d in deltas if d < 10]):
                print(line)
            print(f"{DIM}  A spike at ~2.0s means the composite tracks the "
                  f"combat round and can drive timing.{RESET}")

    for lead in ("DDD", "BAD"):
        if successor.get(lead):
            top = ", ".join(f"{c}({n})" for c, n in successor[lead].most_common(4))
            print(f"\n{BOLD}what follows {lead}{RESET}: {top}")
            first = successor[lead].most_common(1)[0][0]
            if first in codes.ROOM_RECORD_CODES:
                print(f"{DIM}  {first} leading confirms {lead} opens the room block, "
                      f"so clearing contents on {lead} is correct.{RESET}")
            else:
                print(f"{YELLOW}  {lead} is not followed by an H** record -- contents "
                      f"may need a different reset trigger.{RESET}")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
