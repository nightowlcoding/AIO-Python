from __future__ import annotations

from collections.abc import Mapping, Sequence

_WARNED_MISSING_SCOPE: set[tuple[str, str, str]] = set()


def normalize_scope_text(value, max_length: int = 120) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if max_length > 0:
        return text[:max_length]
    return text


def warn_missing_tenant_scope(logger, *, app_name: str, request_path: str = "", method: str = "") -> None:
    key = (str(app_name or ""), str(request_path or ""), str(method or ""))
    if key in _WARNED_MISSING_SCOPE:
        return
    _WARNED_MISSING_SCOPE.add(key)

    if logger is None:
        return

    logger.warning(
        "[%s] request missing tenant company scope; default protections remain active path=%s method=%s",
        app_name or "app",
        request_path or "",
        method or "",
    )


def resolve_tenant_scope(
    headers: Mapping | None,
    *,
    session_data: Mapping | None = None,
    company_session_keys: Sequence[str] = (),
    app_name: str = "",
    logger=None,
    request_path: str = "",
    method: str = "",
) -> dict:
    header_map = headers or {}
    session_map = session_data or {}

    is_dexter_proxy = normalize_scope_text(header_map.get("X-Dexter-Auth"), 8) == "1"

    company_name = normalize_scope_text(header_map.get("X-Dexter-Company-Name"), 120)
    if not company_name:
        for key in company_session_keys:
            candidate = normalize_scope_text(session_map.get(key), 120)
            if candidate:
                company_name = candidate
                break

    restaurant_name = normalize_scope_text(header_map.get("X-Dexter-Restaurant-Name"), 120)
    restaurant_location = normalize_scope_text(header_map.get("X-Dexter-Restaurant-Location"), 120)

    if is_dexter_proxy and not company_name:
        warn_missing_tenant_scope(
            logger,
            app_name=app_name,
            request_path=request_path,
            method=method,
        )

    return {
        "is_dexter_proxy": is_dexter_proxy,
        "company_name": company_name,
        "restaurant_name": restaurant_name,
        "restaurant_location": restaurant_location,
    }


def tenant_blank_state_required(company_name: str, available_locations_count: int) -> bool:
    if not normalize_scope_text(company_name, 120):
        return False
    return int(available_locations_count or 0) <= 0
