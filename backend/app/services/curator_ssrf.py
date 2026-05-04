"""SSRF guard for the optional LLM Wiki Curator endpoint.

The curator URL is user-supplied and reaches outbound HTTP. We default-deny
private/loopback targets so a misconfigured (or malicious) admin can't turn
the backend into a port scanner of the internal network. Local-model setups
are the intended use case, so an explicit ``ALLOW_LOCAL_CURATOR=1``
environment opt-in re-enables RFC1918 / loopback / link-local destinations.

Used by the curator-test route (PR B) and the curator client (PR C).
"""

from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse


class CuratorURLBlocked(Exception):
    """Raised when a curator URL fails the SSRF guard.

    The message is safe to surface in API responses — it never echoes
    the resolved IP back to the client (only the offending hostname),
    so we don't expose internal DNS data.
    """


_LOCAL_OPT_IN_ENV = "ALLOW_LOCAL_CURATOR"
_LOCAL_OPT_IN_HINT = (
    "Local curator endpoints require ALLOW_LOCAL_CURATOR=1."
)


def _local_opt_in_enabled() -> bool:
    """Read ALLOW_LOCAL_CURATOR=1 at call time so tests can flip it."""
    return os.environ.get(_LOCAL_OPT_IN_ENV, "").strip() in ("1", "true", "True")


def _is_blocked_address(ip: str) -> bool:
    """Return True for private / loopback / link-local / multicast IPs."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        # Unresolvable bytes — treat as blocked rather than fail-open.
        return True
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def assert_curator_url_safe(url: str) -> None:
    """Validate a curator URL and raise ``CuratorURLBlocked`` on rejection.

    Rules:
      - URL must be http:// or https://. Other schemes (file://, gopher://,
        data://, javascript:) are denied unconditionally.
      - URL may not include credentials (``user:pass@``).
      - The hostname must resolve. If any resolved address is private /
        loopback / link-local / multicast / reserved / unspecified, the
        URL is denied unless ``ALLOW_LOCAL_CURATOR=1`` is set.
      - Empty URL is treated as "curator disabled" — the caller is
        responsible for not invoking this with an empty URL when curator
        is enabled.

    The caller is expected to also pass ``follow_redirects=False`` to its
    HTTP client so a 30x to a private host can't bypass the guard.
    """
    if not url or not url.strip():
        raise CuratorURLBlocked("Curator URL is empty.")

    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise CuratorURLBlocked(
            f"Curator URL scheme must be http or https (got {parsed.scheme!r})."
        )
    if parsed.username or parsed.password:
        raise CuratorURLBlocked(
            "Curator URL must not embed credentials (user:pass@host)."
        )
    host = parsed.hostname
    if not host:
        raise CuratorURLBlocked("Curator URL has no hostname.")

    # Hostname literal IPs short-circuit DNS.
    try:
        ipaddress.ip_address(host)
        candidates = [host]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, parsed.port or 80, type=socket.SOCK_STREAM)
        except OSError as e:
            raise CuratorURLBlocked(
                f"Curator URL host {host!r} did not resolve: {e}"
            ) from e
        candidates = sorted({info[4][0] for info in infos})
        if not candidates:
            raise CuratorURLBlocked(f"Curator URL host {host!r} resolved to nothing.")

    blocked = [ip for ip in candidates if _is_blocked_address(ip)]
    if blocked and not _local_opt_in_enabled():
        # Don't echo the resolved IPs back — saying "private/loopback"
        # is enough for the operator and avoids leaking internal DNS.
        raise CuratorURLBlocked(
            f"Curator URL host {host!r} resolves to a private / loopback / "
            f"link-local address. {_LOCAL_OPT_IN_HINT}"
        )
