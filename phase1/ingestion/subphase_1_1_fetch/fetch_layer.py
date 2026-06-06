"""Phase 1.1 — HTTP fetch with allowlist enforcement, retries, backoff, User-Agent, stagger."""

from __future__ import annotations

import ssl
import time
from dataclasses import dataclass, field
from email.message import Message
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from phase1.ingestion.common.allowlist import (
    AllowlistError,
    assert_url_allowlisted,
    load_allowlist,
    load_corpus_manifest,
    manifest_path_default,
)

USER_AGENT = (
    "RAGCHATBOT_NL/1.0 (Phase-1.1; mutual-fund FAQ corpus; polite bot; contact project owner)"
)

DEFAULT_TIMEOUT_SEC = 30.0
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_BASE_SEC = 1.0
DEFAULT_STAGGER_SEC = 1.0


def build_ssl_context(*, insecure: bool = False) -> ssl.SSLContext:
    """TLS context; uses certifi CA bundle when available for portable verification."""
    if insecure:
        return ssl._create_unverified_context()
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


@dataclass
class FetchAttempt:
    attempt_index: int
    status_code: int | None
    error: str | None


@dataclass
class FetchReport:
    source_id: str
    amc_name: str
    url: str
    ok: bool
    status_code: int | None
    final_url: str | None
    content_type: str | None
    """Simplified MIME type (no parameters)."""

    body_bytes: int
    error: str | None
    attempts: list[FetchAttempt] = field(default_factory=list)
    raw_body: bytes | None = None
    """Response body when ``capture_body=True`` on a successful 2xx response."""

    content_type_header: str | None = None
    """Full ``Content-Type`` header value including charset, if sent."""


def _join_headers(resp_headers: Message | None) -> str:
    if resp_headers is None:
        return ""
    if hasattr(resp_headers, "get_content_type"):
        ct = resp_headers.get_content_type()
        if ct:
            return ct
    raw = resp_headers.get("Content-Type")
    return (raw or "").split(";")[0].strip()


def _should_retry_http(status: int) -> bool:
    return status == 429 or (status >= 500 and status < 600)


def fetch_url_allowlisted(
    url: str,
    *,
    allowlist: frozenset[str],
    manifest_path: Path | None = None,
    ssl_context: ssl.SSLContext | None = None,
    capture_body: bool = False,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_base_sec: float = DEFAULT_BACKOFF_BASE_SEC,
) -> FetchReport:
    """
    GET url only if present in allowlist. Returns FetchReport (body read for sizing only).
    Retries on timeouts, connection errors, HTTP 429, and HTTP 5xx.
    """
    assert_url_allowlisted(url, allowlist)
    ctx = ssl_context if ssl_context is not None else build_ssl_context(insecure=False)

    source_id = ""
    amc_name = ""
    data = load_corpus_manifest(manifest_path)
    for src in data.get("sources", []):
        if isinstance(src, dict) and src.get("url") == url:
            source_id = str(src.get("id", ""))
            amc_name = str(src.get("amc_name", ""))
            break

    attempts: list[FetchAttempt] = []
    last_error: str | None = None
    status_code: int | None = None
    final_url: str | None = None
    content_type: str | None = None
    body_len = 0

    for attempt in range(max_attempts):
        try:
            req = Request(
                url,
                headers={"User-Agent": USER_AGENT},
                method="GET",
            )
            with urlopen(req, timeout=timeout_sec, context=ctx) as resp:  # noqa: S310 — URLs gated by allowlist
                status_code = resp.status
                final_url = resp.geturl()
                ct_header = resp.headers.get("Content-Type")
                content_type = _join_headers(resp.headers)
                body = resp.read()
                body_len = len(body)
                if 200 <= status_code < 300:
                    attempts.append(
                        FetchAttempt(attempt_index=attempt + 1, status_code=status_code, error=None)
                    )
                    return FetchReport(
                        source_id=source_id,
                        amc_name=amc_name,
                        url=url,
                        ok=True,
                        status_code=status_code,
                        final_url=final_url,
                        content_type=content_type,
                        body_bytes=body_len,
                        error=None,
                        attempts=attempts,
                        raw_body=body if capture_body else None,
                        content_type_header=ct_header,
                    )
                err_msg = f"HTTP {status_code}"
                last_error = err_msg
                attempts.append(
                    FetchAttempt(attempt_index=attempt + 1, status_code=status_code, error=err_msg)
                )
                if _should_retry_http(status_code) and attempt < max_attempts - 1:
                    time.sleep(backoff_base_sec * (2**attempt))
                    continue
                return FetchReport(
                    source_id=source_id,
                    amc_name=amc_name,
                    url=url,
                    ok=False,
                    status_code=status_code,
                    final_url=final_url,
                    content_type=content_type,
                    body_bytes=body_len,
                    error=last_error,
                    attempts=attempts,
                    raw_body=None,
                    content_type_header=ct_header,
                )
        except HTTPError as e:
            code = e.code
            status_code = code
            try:
                body = e.read()
                body_len = len(body) if body else 0
            except Exception:
                body_len = 0
            err_msg = f"HTTPError {code}: {e.reason}"
            last_error = err_msg
            attempts.append(FetchAttempt(attempt_index=attempt + 1, status_code=code, error=err_msg))
            final_url = getattr(e, "url", url)
            if _should_retry_http(code) and attempt < max_attempts - 1:
                time.sleep(backoff_base_sec * (2**attempt))
                continue
            return FetchReport(
                source_id=source_id,
                amc_name=amc_name,
                url=url,
                ok=False,
                status_code=code,
                final_url=final_url,
                content_type=None,
                body_bytes=body_len,
                error=last_error,
                attempts=attempts,
                raw_body=None,
                content_type_header=None,
            )
        except URLError as e:
            err_msg = f"URLError: {e.reason!r}"
            last_error = err_msg
            attempts.append(FetchAttempt(attempt_index=attempt + 1, status_code=None, error=err_msg))
            if attempt < max_attempts - 1:
                time.sleep(backoff_base_sec * (2**attempt))
                continue
            return FetchReport(
                source_id=source_id,
                amc_name=amc_name,
                url=url,
                ok=False,
                status_code=None,
                final_url=None,
                content_type=None,
                body_bytes=0,
                error=last_error,
                attempts=attempts,
                raw_body=None,
                content_type_header=None,
            )
        except AllowlistError:
            raise
        except Exception as e:  # noqa: BLE001 — surface last-resort error per URL
            err_msg = f"{type(e).__name__}: {e}"
            last_error = err_msg
            attempts.append(FetchAttempt(attempt_index=attempt + 1, status_code=None, error=err_msg))
            if attempt < max_attempts - 1:
                time.sleep(backoff_base_sec * (2**attempt))
                continue
            return FetchReport(
                source_id=source_id,
                amc_name=amc_name,
                url=url,
                ok=False,
                status_code=status_code,
                final_url=final_url,
                content_type=content_type,
                body_bytes=body_len,
                error=last_error,
                attempts=attempts,
                raw_body=None,
                content_type_header=None,
            )

    return FetchReport(
        source_id=source_id,
        amc_name=amc_name,
        url=url,
        ok=False,
        status_code=status_code,
        final_url=final_url,
        content_type=content_type,
        body_bytes=body_len,
        error=last_error or "unknown failure",
        attempts=attempts,
        raw_body=None,
        content_type_header=None,
    )


def fetch_all_allowlisted(
    *,
    manifest_path: Path | None = None,
    ssl_context: ssl.SSLContext | None = None,
    insecure: bool = False,
    capture_body: bool = False,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    stagger_sec: float = DEFAULT_STAGGER_SEC,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_base_sec: float = DEFAULT_BACKOFF_BASE_SEC,
) -> tuple[list[FetchReport], frozenset[str]]:
    """Fetch every URL in corpus_manifest.json in manifest order, with stagger between URLs."""
    mp = manifest_path or manifest_path_default()
    ctx = ssl_context if ssl_context is not None else build_ssl_context(insecure=insecure)
    allowlist = load_allowlist(mp)
    data = load_corpus_manifest(mp)
    sources: list[dict[str, Any]] = [
        s for s in data.get("sources", []) if isinstance(s, dict)
    ]
    reports: list[FetchReport] = []
    for i, src in enumerate(sources):
        url = src.get("url")
        if not isinstance(url, str):
            continue
        if i > 0 and stagger_sec > 0:
            time.sleep(stagger_sec)
        reports.append(
            fetch_url_allowlisted(
                url.strip(),
                allowlist=allowlist,
                manifest_path=mp,
                ssl_context=ctx,
                capture_body=capture_body,
                timeout_sec=timeout_sec,
                max_attempts=max_attempts,
                backoff_base_sec=backoff_base_sec,
            )
        )
    return reports, allowlist
