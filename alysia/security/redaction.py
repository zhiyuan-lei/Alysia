from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from alysia.schemas.security import SecurityFinding, SecurityScanReport


REDACTED = "[REDACTED]"
_NAME_PATTERN = r"(?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|passwd|cookie|session(?:id)?|token|sessdata|bili_jct)"
_ASSIGNMENT = re.compile(
    rf"(?i)(?P<prefix>\b{_NAME_PATTERN}\b\s*[:=]\s*)(?P<quote>['\"]?)(?P<value>[^\s,;\"']+)(?P=quote)"
)
_BEARER = re.compile(r"(?i)(\b(?:authorization\s*[:=]\s*)?bearer\s+)[A-Za-z0-9._~+/=-]{6,}")
_LIKELY_SECRET_NAME = re.compile(
    r"(?i)(secret|token|password|passwd|cookie|session|api[_-]?key|authorization|sessdata|bili_jct)"
)


class Redactor:
    def __init__(self, secret_values: Iterable[str] | None = None) -> None:
        env_values = [
            value
            for key, value in os.environ.items()
            if value and len(value) >= 6 and _LIKELY_SECRET_NAME.search(key)
        ]
        explicit = [value for value in (secret_values or []) if value and len(value) >= 4]
        self.secret_values = sorted(set(env_values + explicit), key=len, reverse=True)

    def redact(self, value: str) -> str:
        output = value
        for secret in self.secret_values:
            output = output.replace(secret, REDACTED)
        output = _BEARER.sub(r"\1" + REDACTED, output)
        output = _ASSIGNMENT.sub(lambda match: match.group("prefix") + REDACTED, output)
        return output

    def redact_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, dict):
            return {
                str(key): REDACTED if _LIKELY_SECRET_NAME.search(str(key)) else self.redact_value(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self.redact_value(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.redact_value(item) for item in value)
        return value


class SecretScanner:
    TEXT_SUFFIXES = {".json", ".jsonl", ".log", ".txt", ".md", ".yaml", ".yml", ".env", ".toml", ".ini", ".cfg"}

    def __init__(self, redactor: Redactor | None = None) -> None:
        self.redactor = redactor or Redactor()

    def scan(self, target: Path) -> SecurityScanReport:
        root = target.resolve()
        files = [root] if root.is_file() else [path for path in root.rglob("*") if path.is_file()]
        findings: list[SecurityFinding] = []
        scanned = 0
        for path in files:
            if path.suffix.lower() not in self.TEXT_SUFFIXES and path.name != ".env":
                continue
            try:
                if path.stat().st_size > 2 * 1024 * 1024:
                    continue
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            scanned += 1
            local_values = self._env_secret_values(path, text)
            detector = Redactor([*self.redactor.secret_values, *local_values])
            for line_number, line in enumerate(text.splitlines(), start=1):
                categories = self._categories(line, local_values)
                if not categories:
                    continue
                excerpt = detector.redact(line.strip())[:240]
                for category in categories:
                    digest = hashlib.sha256(f"{path}|{line_number}|{category}".encode("utf-8")).hexdigest()[:16]
                    findings.append(
                        SecurityFinding(
                            finding_id=f"secret_{digest}", path=path, category=category,
                            line=line_number, redacted_excerpt=excerpt,
                        )
                    )
        return SecurityScanReport(
            root=root, scanned_files=scanned, findings=findings,
            generated_at=datetime.now().astimezone(),
        )

    @staticmethod
    def _env_secret_values(path: Path, text: str) -> list[str]:
        if path.name != ".env" and path.suffix.lower() != ".env":
            return []
        values: list[str] = []
        for line in text.splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip("'\"")
            if _LIKELY_SECRET_NAME.search(key) and value:
                values.append(value)
        return values

    @staticmethod
    def _categories(line: str, local_values: list[str]) -> list[str]:
        categories: list[str] = []
        if _BEARER.search(line):
            categories.append("authorization_bearer")
        if _ASSIGNMENT.search(line):
            categories.append("credential_assignment")
        if any(value and value in line for value in local_values):
            categories.append("env_secret_value")
        return list(dict.fromkeys(categories))
