from __future__ import annotations


def normalize_confidence(value: object) -> tuple[float, list[str]]:
    warnings: list[str] = []
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        warnings.append("confidence_missing_or_invalid")
        return 0.0, warnings

    if 0 <= confidence <= 1:
        return confidence, warnings
    if 1 < confidence <= 10:
        warnings.append("confidence_scaled_from_10")
        return confidence / 10.0, warnings
    if 10 < confidence <= 100:
        warnings.append("confidence_scaled_from_100")
        return confidence / 100.0, warnings

    warnings.append("confidence_out_of_range")
    return max(0.0, min(confidence, 1.0)), warnings


def as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def as_int_list(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    result: list[int] = []
    for item in value:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return result
