from __future__ import annotations

import re
from typing import Any

FORBIDDEN_KEYS = {
    "account_no",
    "account_number",
    "api_key",
    "authorization",
    "credential",
    "env",
    "fill_id",
    "host",
    "hostname",
    "order_id",
    "pid",
    "process_id",
    "prompt",
    "raw_prompt",
    "report_path",
    "response_text",
    "run_id",
    "source_path",
}

WINDOWS_PATH = re.compile(
    r"(?i)(?:[a-z]:\\|\\\\)"
    r"(?:(?!\s+(?:account|bearer|token|api[_-]?key)\b)[^\r\n\t\"'])+"
)
CREDENTIAL = re.compile(r"(?i)\b(?:bearer\s+|sk-|or-)[a-z0-9._-]{8,}")
ACCOUNT_NUMBER = re.compile(
    r"(?i)(\baccount(?:\s+(?:no|number))?[\s:=#-]*)[0-9-]{4,}"
)


def sanitize_public_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: sanitize_public_payload(item)
            for key, item in value.items()
            if key.lower() not in FORBIDDEN_KEYS
        }
    if isinstance(value, list):
        return [sanitize_public_payload(item) for item in value]
    if isinstance(value, str):
        return _sanitize_text(value)
    return value


def _sanitize_text(value: str) -> str:
    redacted = WINDOWS_PATH.sub("[redacted-path]", value)
    redacted = CREDENTIAL.sub("[redacted-credential]", redacted)
    return ACCOUNT_NUMBER.sub(r"\1[redacted-account]", redacted)
