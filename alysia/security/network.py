from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from alysia.schemas.security import NetworkDecision


class NetworkPolicy:
    LOOPBACK_ACTORS = {"ComfyUI/H3 provider adapter", "LLMProviderAdapter"}

    def classify(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return "denied_private_network"
        hostname = parsed.hostname.casefold()
        if hostname == "localhost":
            return "local_loopback"
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            return "public_web_research"
        if address.is_loopback:
            return "local_loopback"
        if address.is_private or address.is_link_local or address.is_reserved:
            return "denied_private_network"
        return "public_web_research"

    def check(self, actor: str, url: str, *, approved_hosts: set[str] | None = None) -> NetworkDecision:
        category = self.classify(url)
        host = (urlparse(url).hostname or "").casefold()
        if category == "local_loopback":
            allowed = actor in self.LOOPBACK_ACTORS
            reason = "local_loopback_actor_allowed" if allowed else "local_loopback_actor_denied"
        elif category == "denied_private_network":
            allowed = False
            reason = "private_network_denied"
        elif approved_hosts and host in {item.casefold() for item in approved_hosts}:
            category = "approved_api"
            allowed = True
            reason = "approved_api_host"
        else:
            allowed = actor == "ResearcherAgent"
            reason = "public_research_allowed" if allowed else "public_network_role_denied"
        return NetworkDecision(actor=actor, url=url, category=category, allowed=allowed, reason=reason)
