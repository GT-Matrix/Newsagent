from __future__ import annotations

from typing import Any

from .contract import ExtractorFailure, WebSource


BLOCKED_MARKERS = (
    "cloudflare",
    "captcha",
    "cf-chl",
    "cf-ray",
    "attention required",
    "enable javascript",
    "access denied",
    "rate limit",
    "too many requests",
    "login required",
    "forbidden",
)

NETWORK_MARKERS = (
    "timeout",
    "timed out",
    "connection reset",
    "connection aborted",
    "temporary failure",
    "name resolution",
    "ssl",
    "tls",
    "proxy",
)


def classify_exception(exc: Exception) -> ExtractorFailure:
    message = str(exc)
    lowered = message.lower()
    if any(marker in lowered for marker in BLOCKED_MARKERS):
        return ExtractorFailure("blocked", message, retryable=False, unrepairable=True)
    if any(marker in lowered for marker in NETWORK_MARKERS):
        return ExtractorFailure("network_error", message, retryable=True, unrepairable=True)
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        return ExtractorFailure("contract_error", message, retryable=False, unrepairable=False)
    return ExtractorFailure("parse_error", message, retryable=False, unrepairable=False)


def classify_result(raw: dict[str, Any]) -> ExtractorFailure | None:
    diagnostics = raw.get("diagnostics") if isinstance(raw.get("diagnostics"), dict) else {}
    status = str(raw.get("status") or diagnostics.get("status") or "").lower()
    text = " ".join(str(value) for value in [status, diagnostics.get("error"), diagnostics.get("message")]).lower()
    if raw.get("ok") is True:
        return None
    if status in {"blocked", "network_error", "parse_error", "contract_error", "empty", "invalid_output"}:
        return ExtractorFailure(
            status,
            str(diagnostics.get("error") or diagnostics.get("message") or status),
            retryable=status in {"network_error"},
            unrepairable=status in {"blocked", "network_error"},
            diagnostics=diagnostics,
        )
    if any(marker in text for marker in BLOCKED_MARKERS):
        return ExtractorFailure("blocked", text, retryable=False, unrepairable=True, diagnostics=diagnostics)
    if any(marker in text for marker in NETWORK_MARKERS):
        return ExtractorFailure("network_error", text, retryable=True, unrepairable=True, diagnostics=diagnostics)
    return ExtractorFailure("parse_error", str(diagnostics.get("error") or "extractor returned ok=false"), diagnostics=diagnostics)


def should_auto_repair(source: WebSource, failure: ExtractorFailure, attempts: int) -> bool:
    policy = source.repair_policy or {}
    if not bool(policy.get("enabled", True)):
        return False
    if failure.unrepairable:
        return False
    threshold = int(policy.get("max_attempts_before_repair", 3))
    return attempts >= threshold
