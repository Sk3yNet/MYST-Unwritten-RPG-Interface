from __future__ import annotations

import os
from dataclasses import dataclass, field


def _list(name: str) -> set[str]:
    return {x.strip().lower() for x in os.getenv(name, "").split(",") if x.strip()}


@dataclass
class Settings:
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", "unwritten.sqlite"))
    # Header the auth proxy (oauth2-proxy via nginx) sets with the signed-in Google address.
    auth_header: str = "X-Auth-Request-Email"
    # Local development only: pretend this address is signed in when no header is present.
    dev_user: str = field(default_factory=lambda: os.getenv("DEV_USER", "").strip().lower())
    # Who may use the site at all. Empty (and no domains) = any Google account the proxy lets through.
    allowed_emails: set[str] = field(default_factory=lambda: _list("ALLOWED_EMAILS"))
    allowed_domains: set[str] = field(default_factory=lambda: _list("ALLOWED_DOMAINS"))
    # Who may create campaigns (be a GM). Empty = anyone signed in.
    gm_emails: set[str] = field(default_factory=lambda: _list("GM_EMAILS"))

    def may_sign_in(self, email: str) -> bool:
        if not self.allowed_emails and not self.allowed_domains:
            return True
        return email in self.allowed_emails or email.split("@")[-1] in self.allowed_domains

    def may_create(self, email: str) -> bool:
        return not self.gm_emails or email in self.gm_emails
