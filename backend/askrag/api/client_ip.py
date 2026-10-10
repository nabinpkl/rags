"""The visitor's address behind our own proxies, for the per-IP budget (D11).

Deployed, the API's direct peer is always Caddy, so `request.client.host` alone
makes the per-IP cap a site-wide one. X-Forwarded-For carries the real address,
but only the entries our own proxies appended can be believed: anything left of
them is whatever the client sent. So the list is read from the right, skipping
trusted hops, and the first address that is not one of ours is the client.

The chain this is written against (deploy/Caddyfile): tailscale serve SETS the
header to the tailnet source address (it does not append, so a client cannot
pre-seed it), Caddy appends its peer, and the API trusts the compose subnet.
"""

import ipaddress
from collections.abc import Sequence

Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def parse_networks(cidrs: Sequence[str]) -> tuple[Network, ...]:
    """Raises on a malformed CIDR: a typo here would silently trust nothing,
    which is the site-wide-cap failure this module exists to remove."""
    return tuple(ipaddress.ip_network(c, strict=False) for c in cidrs)


def _trusted(address: str, networks: Sequence[Network]) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in net for net in networks)


def client_ip(peer: str | None, forwarded_for: str | None, trusted: Sequence[Network]) -> str:
    """The rightmost address not belonging to a trusted proxy.

    An untrusted peer IS the client, whatever it put in the header. A header
    made only of trusted hops (a request that started inside the network)
    resolves to its leftmost entry.
    """
    if peer is None:
        return "unknown"
    if not forwarded_for or not _trusted(peer, trusted):
        return peer
    hops = [h.strip() for h in forwarded_for.split(",") if h.strip()]
    for hop in reversed(hops):
        if not _trusted(hop, trusted):
            return hop
    return hops[0] if hops else peer
