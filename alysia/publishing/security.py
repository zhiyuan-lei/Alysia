from __future__ import annotations

import os
import re


_SENSITIVE_NAMES = (
    "BILIBILI_ACCESS_TOKEN",
    "BILIBILI_CLIENT_SECRET",
    "BILIBILI_CLIENT_ID",
)


def redact_credentials(value: str) -> str:
    redacted = value
    for name in _SENSITIVE_NAMES:
        secret = os.environ.get(name)
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    redacted = re.sub(
        r"(?i)(access[_-]?token|client[_-]?secret|password|cookie)\s*[:=]\s*[^\s,;]+",
        r"\1=[REDACTED]",
        redacted,
    )
    return redacted

