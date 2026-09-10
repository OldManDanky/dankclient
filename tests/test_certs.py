"""HTTPS on a machine whose certificate store has not heard of GitHub.

Windows fills its store on demand, and Python reading it is not a demand, so a
machine that had never opened GitHub in a browser failed every request with
"unable to get local issuer certificate".  A tester's client came up with no
map, no bots, and that on the Updates page.  Reproduced by giving Python no
roots at all, which fails the same way; with the bundle alone, both GitHub
hosts answered.  These tests stay off the network, like the rest.
"""

from __future__ import annotations

import ssl
import sys
from importlib import resources
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import update  # noqa: E402


def with_bare_machine(fn):
    """Run fn as if the machine's own store held nothing at all."""
    was = ssl.create_default_context

    def bare(*_a, **_k):
        return ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    ssl.create_default_context = bare
    update._trust.cache_clear()
    try:
        return fn()
    finally:
        ssl.create_default_context = was
        update._trust.cache_clear()


def test_the_bundle_ships_inside_the_package():
    """Read the way the client reads it, so a zip or an install finds it too."""
    text = (resources.files("mud") / "cacert.pem").read_text(encoding="ascii")
    assert text.count("-----BEGIN CERTIFICATE-----") >= 100


def test_a_machine_with_no_roots_still_gets_mozillas():
    context = with_bare_machine(update._trust)
    assert context.cert_store_stats()["x509_ca"] >= 100


def test_nothing_is_loosened():
    context = with_bare_machine(update._trust)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname


def test_the_machines_own_roots_are_kept_as_well():
    """A work proxy or an antivirus that re-signs HTTPS puts its root in the
    machine's store; trusting only the bundle would break exactly them."""
    update._trust.cache_clear()
    try:
        mine = ssl.create_default_context().cert_store_stats()["x509_ca"]
        both = update._trust().cert_store_stats()["x509_ca"]
    finally:
        update._trust.cache_clear()
    assert both >= mine


def test_every_request_goes_through_it():
    seen = {}

    class Reply:
        headers: dict = {}

        def read(self, _n):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    def fake(request, timeout, context=None):
        seen["context"] = context
        return Reply()

    was = update.urllib.request.urlopen
    update.urllib.request.urlopen = fake
    try:
        update._get("https://api.github.com/x", 5)
    finally:
        update.urllib.request.urlopen = was
    assert seen["context"] is update._trust()


def test_a_certificate_failure_says_what_to_check():
    exc = OSError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
                  "unable to get local issuer certificate")
    said = update._say(exc)
    assert "clock" in said and "proxy" in said
    assert "unable to get local issuer certificate" in said, "the detail is kept"
    assert update._say(OSError("timed out")) == "OSError: timed out"
