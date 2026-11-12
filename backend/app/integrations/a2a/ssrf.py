"""Agent URLs are the one place Covenant fetches a URL a user typed. Only an allowed host,
and never a link-local, metadata or (unless that host is allowed) private address."""

import ipaddress
import socket
from urllib.parse import urlparse

METADATA_IP = ipaddress.ip_address("169.254.169.254")


class AgentUrlRefused(ValueError):
    """The message is safe to show to the person who typed the URL."""


def check_agent_url(url: str, allowed_hosts: list[str]) -> str:
    """Return the hostname, or raise `AgentUrlRefused`."""
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in ("http", "https") or not host or parsed.username or parsed.password:
        raise AgentUrlRefused("Enter an http(s) agent URL without a username or password.")
    allowed = {item.lower().rstrip(".") for item in allowed_hosts}
    if host not in allowed:
        names = ", ".join(sorted(allowed))
        raise AgentUrlRefused(f"{host} isn't a host Covenant is allowed to call. Allowed: {names}.")
    try:
        records = socket.getaddrinfo(host, parsed.port, type=socket.SOCK_STREAM)
        addresses = {str(item[4][0]) for item in records}
    except socket.gaierror:
        raise AgentUrlRefused(f"Couldn't resolve {host}.") from None
    for raw in addresses:
        _check_ip(host, raw, allowed)
    return host


def _check_ip(host: str, raw: str, allowed: set[str]) -> None:
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        raise AgentUrlRefused(f"Couldn't resolve {host}.") from None
    if ip == METADATA_IP or ip.is_link_local:
        raise AgentUrlRefused(f"{host} resolves to a link-local or metadata address ({ip}).")
    private = (
        ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )
    if private and host not in allowed:
        raise AgentUrlRefused(f"{host} resolves to a private address ({ip}).")
