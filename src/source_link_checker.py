"""Source link verification for selected Frontier Pulse stories.

Discovery source URLs are written by the model and can point to pages that do not exist.
This module performs lightweight HTTP checks and classifies each URL:

- ``reachable``: 2xx/3xx response.
- ``blocked``: 401/403/429 (publisher blocks automated clients; the page may exist).
- ``broken``: 404/410 response, or the domain does not resolve.
- ``unverified``: timeouts, other network errors, or other status codes.

Only ``broken`` links are removed. If every checked URL fails at the network level, the
environment is treated as offline and nothing is removed, so a connectivity problem can
never empty an edition.
"""

from __future__ import annotations

import socket
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Iterable

import requests

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FrontierPulseLinkCheck/1.0)",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}
DNS_ERROR_MARKERS = (
    "nameresolutionerror",
    "name or service not known",
    "nodename nor servname",
    "getaddrinfo failed",
    "no address associated",
    "temporary failure in name resolution",
    "failed to resolve",
)
NETWORK_ERROR_KINDS = {"dns", "connection", "timeout"}


def classify_status_code(status_code: int) -> str:
    if 200 <= status_code < 400:
        return "reachable"
    if status_code in (404, 410):
        return "broken"
    if status_code in (401, 403, 429):
        return "blocked"
    return "unverified"


def _is_dns_error(exc: BaseException) -> bool:
    """Walk an exception chain looking for a DNS resolution failure."""
    seen: set[int] = set()
    stack: list[Any] = [exc]
    while stack:
        current = stack.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, socket.gaierror):
            return True
        if isinstance(current, BaseException):
            if "NameResolution" in type(current).__name__:
                return True
            if any(marker in str(current).lower() for marker in DNS_ERROR_MARKERS):
                return True
            stack.extend([current.__cause__, current.__context__, getattr(current, "reason", None)])
            stack.extend(arg for arg in current.args if isinstance(arg, BaseException))
    return False


def check_url(url: str, timeout: float = 5.0, session: Any = None) -> dict:
    """Check one URL and return ``{url, status, http_status, error, error_kind}``.

    HEAD is tried first; any non-2xx/3xx HEAD answer is confirmed with a streamed GET, because
    some servers reject HEAD requests for pages that exist.
    """
    http = session or requests
    result = {"url": url, "status": "unverified", "http_status": None, "error": None, "error_kind": None}
    try:
        response = http.head(url, allow_redirects=True, timeout=timeout, headers=REQUEST_HEADERS)
        status_code = response.status_code
        if classify_status_code(status_code) != "reachable":
            response = http.get(url, allow_redirects=True, timeout=timeout, headers=REQUEST_HEADERS, stream=True)
            status_code = response.status_code
            close = getattr(response, "close", None)
            if callable(close):
                close()
        result["http_status"] = status_code
        result["status"] = classify_status_code(status_code)
    except requests.exceptions.Timeout as exc:
        result.update(status="unverified", error=f"Timeout: {exc}"[:300], error_kind="timeout")
    except requests.exceptions.ConnectionError as exc:
        if _is_dns_error(exc):
            result.update(status="broken", error=f"DNS resolution failed: {exc}"[:300], error_kind="dns")
        else:
            result.update(status="unverified", error=f"Connection error: {exc}"[:300], error_kind="connection")
    except requests.exceptions.InvalidURL as exc:
        result.update(status="broken", error=f"Invalid URL: {exc}"[:300], error_kind="invalid_url")
    except requests.exceptions.RequestException as exc:
        result.update(status="unverified", error=f"{type(exc).__name__}: {exc}"[:300], error_kind="request")
    return result


def check_urls(
    urls: Iterable[str],
    timeout: float = 5.0,
    max_workers: int = 6,
    checker: Callable[..., dict] = check_url,
) -> dict[str, dict]:
    """Check unique URLs concurrently and return results keyed by URL."""
    unique_urls = list(dict.fromkeys(str(u) for u in urls if u))
    if not unique_urls:
        return {}
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(unique_urls)))) as pool:
        results = list(pool.map(lambda u: checker(u, timeout=timeout), unique_urls))
    return {r["url"]: r for r in results}


def network_unavailable(results: dict[str, dict]) -> bool:
    """True when every checked URL failed at the network level (likely no outbound access)."""
    return bool(results) and all(r.get("error_kind") in NETWORK_ERROR_KINDS for r in results.values())


def _without_broken_sources(item: dict, results: dict[str, dict]) -> tuple[dict, list[str]]:
    kept, removed = [], []
    for source in item.get("sources", []) or []:
        url = str(source.get("url", ""))
        if results.get(url, {}).get("status") == "broken":
            removed.append(url)
        else:
            kept.append(source)
    new_item = dict(item)
    new_item["sources"] = kept
    return new_item, removed


def remove_broken_sources(items: list[dict], results: dict[str, dict]) -> tuple[list[dict], dict[str, list[str]], list[str]]:
    """Remove broken source URLs from items and drop items left without sources.

    Returns ``(kept_items, removed_urls_by_id, dropped_ids)``. Inputs are not mutated.
    """
    kept_items: list[dict] = []
    removed_by_id: dict[str, list[str]] = {}
    dropped_ids: list[str] = []
    for item in items:
        new_item, removed = _without_broken_sources(item, results)
        if removed:
            removed_by_id[str(item.get("id"))] = removed
        if new_item["sources"]:
            kept_items.append(new_item)
        else:
            dropped_ids.append(str(item.get("id")))
    return kept_items, removed_by_id, dropped_ids
