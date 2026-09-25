"""Lettura di una pagina web → testo/markdown ripulito, con protezione anti-SSRF."""

from __future__ import annotations

import html
import ipaddress
import os
import re
import socket
from urllib.parse import urlparse

import httpx

from ..config import WebConfig
from . import tool

_DROP_RE = re.compile(r"<(script|style|noscript|svg|nav|footer|header|form)[^>]*>.*?</\1>", re.DOTALL | re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_RE = re.compile(r"</?(p|div|br|li|h[1-6]|tr|pre|section|article)[^>]*>", re.I)


class UnsafeURLError(ValueError):
    pass


def check_url(url: str, allow_private: bool = False) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UnsafeURLError(f"only http(s) URLs are allowed: {url}")
    if allow_private:
        return
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"cannot resolve host {parsed.hostname}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise UnsafeURLError(f"private/local address blocked: {parsed.hostname} -> {ip}")


def html_to_text(raw: str) -> str:
    text = _DROP_RE.sub(" ", raw)
    text = _BLOCK_RE.sub("\n", text)
    text = html.unescape(_TAG_RE.sub(" ", text))
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def fetch(url: str, cfg: WebConfig) -> str:
    check_url(url, cfg.allow_private_urls)
    key = os.environ.get("FIRECRAWL_API_KEY")
    if key:
        try:
            resp = httpx.post(
                "https://api.firecrawl.dev/v1/scrape",
                headers={"Authorization": f"Bearer {key}"},
                json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
                timeout=cfg.timeout_s * 2,
            )
            resp.raise_for_status()
            markdown = resp.json().get("data", {}).get("markdown", "")
            if markdown:
                return markdown[: cfg.max_page_chars]
        except httpx.HTTPError:
            pass  # fallback al fetch diretto
    # redirect gestiti a mano: ogni hop viene ricontrollato contro l'SSRF
    current = url
    with httpx.Client(timeout=cfg.timeout_s, follow_redirects=False,
                      headers={"User-Agent": "MyDevAgent/1.0 (+local research agent)"}) as client:
        for _ in range(5):
            resp = client.get(current)
            if resp.is_redirect and resp.headers.get("location"):
                current = str(resp.url.join(resp.headers["location"]))
                check_url(current, cfg.allow_private_urls)
                continue
            break
        resp.raise_for_status()
    content_type = resp.headers.get("content-type", "")
    body = resp.text
    text = html_to_text(body) if "html" in content_type else body
    return text[: cfg.max_page_chars]


@tool(
    "web_fetch",
    "Fetch a web page (http/https) and return its main text content, truncated.",
    {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
)
def web_fetch_tool(ctx, url: str) -> str:
    if not ctx.connectivity.online():
        return "OFFLINE: cannot fetch pages."
    return fetch(url, ctx.settings.tools.web)
