"""
cf_solver_client.py — klien HTTP ke solver-server (lapisan solver terpisah).

solver-server jalan di MESIN YANG SAMA (IP sama dengan browser cf-auto), jadi
token Turnstile yang dihasilkan sah untuk form yang disubmit runner.

Contoh pakai (dari cf_helpers, strategi setelah injected-widget):

    import cf_solver_client as solver
    token = solver.solve_turnstile(cfg, page.url, sitekey)
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

log = logging.getLogger("cf")

DEFAULT_BASE_URL = "http://127.0.0.1:8001"


def _section(cfg: dict) -> dict:
    return (cfg or {}).get("solver") or {}


def base_url(cfg: dict) -> str:
    return str(_section(cfg).get("base_url") or DEFAULT_BASE_URL).rstrip("/")


def is_enabled(cfg: dict) -> bool:
    return bool(_section(cfg).get("enabled", False))


def request_timeout(cfg: dict) -> float:
    return float(_section(cfg).get("timeout", 90))


def _get_json(url: str, timeout: float) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def health(cfg: dict) -> Optional[dict]:
    """Info pool solver. None kalau server tidak bisa dihubungi."""
    try:
        return _get_json(f"{base_url(cfg)}/health", float(_section(cfg).get("probe_timeout", 3)))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        log.info("  solver-server tidak terjangkau: %s", str(exc)[:100])
        return None


def solve_turnstile(cfg: dict, url: str, sitekey: str) -> Optional[str]:
    """Minta token Turnstile ke solver-server. None kalau gagal/timeout."""
    # Probe cepat dulu: kalau server mati/diblokir, jangan tunggu `timeout` penuh
    # (connect yang di-blackhole baru gagal setelah timeout, bukan seketika).
    if health(cfg) is None:
        return None

    endpoint = f"{base_url(cfg)}/solve/turnstile?" + urllib.parse.urlencode(
        {"url": url, "sitekey": sitekey}
    )
    try:
        payload = _get_json(endpoint, request_timeout(cfg))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        log.warning("⚠ solver-server (%s) gagal dipanggil: %s", base_url(cfg), str(exc)[:120])
        return None

    if payload.get("ok") and payload.get("token"):
        log.info("✓ Token dari solver-server (%ss, putaran %s)", payload.get("elapsed"), payload.get("round"))
        return str(payload["token"])

    log.info("  solver-server tidak dapat token: %s %s",
             payload.get("error"), str(payload.get("message") or "")[:100])
    return None


if __name__ == "__main__":
    # self-check: solver-server hidup atau tidak (tanpa browser)
    import sys

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    base = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL
    info = health({"solver": {"base_url": base, "probe_timeout": 5}})
    print(f"{base}/health -> {json.dumps(info) if info else 'tidak menjawab'}")
    sys.exit(0 if info else 1)
