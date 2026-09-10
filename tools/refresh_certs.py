"""Refresh the root certificates the client ships with.

    python3 tools/refresh_certs.py

Python checks HTTPS against the machine's own certificate store, and on Windows
that store is filled in on demand: a root is downloaded the first time a
Windows program asks for it, and Python reading the store is not asking.  So a
machine that has never opened GitHub in a browser may not have the root GitHub
chains to, and every request fails with "unable to get local issuer
certificate" -- which is how a tester's client came up with no map, no bots and
a certificate error on the Updates page.

The client therefore carries Mozilla's list as well, the one curl publishes,
and trusts it alongside the machine's store rather than instead of it.  This
fetches it, checks it against curl's published SHA-256, keeps only the
certificates -- the comments carry accented names, and Python takes PEM text
only as ASCII -- and writes mud/cacert.pem.  Run it now and then; the roots
change a few times a year.
"""

from __future__ import annotations

import hashlib
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
OUT = HERE / "mud" / "cacert.pem"
SOURCE = "https://curl.se/ca/cacert.pem"
BLOCK = re.compile(r"-----BEGIN CERTIFICATE-----\s.*?-----END CERTIFICATE-----",
                   re.S)


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "dankclient-build"})
    with urllib.request.urlopen(request, timeout=60) as reply:
        return reply.read()


def main() -> int:
    body = fetch(SOURCE)
    published = fetch(SOURCE + ".sha256").split()[0].decode()
    got = hashlib.sha256(body).hexdigest()
    if got != published:
        print(f"refusing: {SOURCE} is {got}, curl publishes {published}",
              file=sys.stderr)
        return 1
    text = body.decode("utf-8")
    when = re.search(r"as of: (.+)", text)
    blocks = BLOCK.findall(text)
    if len(blocks) < 100:
        print(f"refusing: only {len(blocks)} certificates", file=sys.stderr)
        return 1
    head = (
        "# Root certificates for HTTPS, trusted alongside the machine's own.\n"
        "# Mozilla's list (certdata.txt, MPL 2.0), as extracted by curl:\n"
        f"# {SOURCE}  sha256 {published}\n"
        f"# as of {when.group(1).strip() if when else 'unknown'}\n"
        "# Written by tools/refresh_certs.py; do not edit by hand.\n\n")
    out = head + "\n".join(blocks) + "\n"
    assert out.isascii()
    OUT.write_text(out, encoding="ascii", newline="\n")
    print(f"  {len(blocks)} certificates -> {OUT} ({len(out)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
