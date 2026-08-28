"""
cf_helpers.py — Helper functions bersama untuk semua module.
Berisi: random_password, fill_input, wait_and_click, wait_for_turnstile,
dismiss_cookie_banner, extract_account_id_from_url.
Dipakai oleh cf_signup, cf_confirm_email, cf_get_apikey.
"""
from __future__ import annotations
import re
import time
import random
import string
import logging
from typing import Optional

from playwright.sync_api import Page, TimeoutError as PWTimeout

log = logging.getLogger("cf")

# Selectors Cloudflare (bisa berubah, pusatkan di sini)
SEL_EMAIL = [
    'input[name="email"]',
    'input[type="email"]',
    'input[placeholder*="mail" i]',
    'input[autocomplete*="email"]',
]
SEL_PASSWORD = [
    'input[name="password"]',
    'input[type="password"]',
]
SEL_SIGNUP_BTN = [
    'button[type="submit"]:has-text("Sign up")',
    'button:has-text("Sign up")',
]

SIGNUP_URL = "https://dash.cloudflare.com/sign-up"
API_TOKENS_URL = "https://dash.cloudflare.com/profile/api-tokens"


# ---------------------------------------------------------------------------
# Password
# ---------------------------------------------------------------------------
def random_password() -> str:
    """Password kuat yang memenuhi syarat Cloudflare."""
    upper = random.choices(string.ascii_uppercase, k=3)
    lower = random.choices(string.ascii_lowercase, k=6)
    digit = random.choices(string.digits, k=3)
    special = random.choices("!@#$%^&*", k=2)
    pwd = upper + lower + digit + special
    random.shuffle(pwd)
    return "".join(pwd)


# ---------------------------------------------------------------------------
# Cookie banner
# ---------------------------------------------------------------------------
def dismiss_cookie_banner(page: Page) -> None:
    """Tutup OneTrust cookie consent banner."""
    try:
        page.evaluate("""() => {
            const btn = document.querySelector(
                '#onetrust-reject-all-handler, .ot-pc-refuse-all-handler'
            );
            if (btn) { btn.click(); return; }
            const ot = document.querySelector(
                '#onetrust-banner-sdk, #onetrust-consent-sdk'
            );
            if (ot) ot.style.display = 'none';
            const ov = document.querySelector(
                '#onetrust-pc-sdk, .onetrust-pc-dark-filter'
            );
            if (ov) ov.style.display = 'none';
        }""")
        page.wait_for_timeout(500)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Fill input (Playwright fill = simulasi keyboard, bukan JS el.value)
# ---------------------------------------------------------------------------
def fill_input(page: Page, selectors: list[str], value: str,
               timeout: int = 15000) -> bool:
    """Isi input field pakai Playwright fill (simulasi keyboard sungguhan).

    Penting untuk React controlled components: el.value=... via JS TIDAK
    terdeteksi React, tapi page.fill()模拟 keyboard event dan TERDETEKSI.
    """
    for sel in selectors:
        try:
            el = page.wait_for_selector(sel, timeout=timeout, state="visible")
            if el:
                try:
                    el.click(timeout=5000)
                except Exception:
                    try:
                        el.evaluate("e => e.focus()")
                    except Exception:
                        pass
                el.fill(value)
                return True
        except PWTimeout:
            continue
    # Fallback: type via keyboard
    for sel in selectors:
        try:
            page.evaluate(f"""() => {{
                const el = document.querySelector('{sel}');
                if (el) el.focus();
            }}""")
            page.keyboard.type(value, delay=50)
            return True
        except Exception:
            continue
    return False


# ---------------------------------------------------------------------------
# Wait and click
# ---------------------------------------------------------------------------
def wait_and_click(page: Page, selectors: list[str],
                   timeout: int = 15000, force: bool = False) -> bool:
    """Klik elemen pertama yang ditemukan."""
    for sel in selectors:
        try:
            el = page.wait_for_selector(sel, timeout=timeout, state="visible")
            if el:
                try:
                    el.click(force=force, timeout=10000)
                    return True
                except Exception:
                    try:
                        el.evaluate("e => e.click()")
                        return True
                    except Exception:
                        continue
        except PWTimeout:
            continue
    return False


# ---------------------------------------------------------------------------
# Turnstile solver
# ---------------------------------------------------------------------------
def wait_for_turnstile(page: Page, timeout: int = 90) -> bool:
    """Tunggu & selesaikan Turnstile challenge.

    Strategi:
    1. Cek auto-solve (cf_challenge_response terisi)
    2. Klik checkbox via frame_locator
    3. Klik checkbox via frame object
    4. Klik via coordinate di dalam iframe
    5. Klik via mouse di posisi iframe di halaman utama
    """
    log.info("⏳ Menunggu Turnstile solve...")
    deadline = time.time() + timeout

    # Wait untuk iframe Turnstile muncul
    try:
        page.wait_for_selector(
            'iframe[src*="challenges.cloudflare.com"]',
            timeout=10000, state="attached",
        )
    except Exception:
        pass

    while time.time() < deadline:
        # --- Strategy 1: cek auto-solve ---
        try:
            val = page.evaluate("""() => {
                const el = document.querySelector(
                    'input[name="cf_challenge_response"]'
                );
                return el ? el.value : null;
            }""")
            if val and len(val) > 20:
                log.info("✓ Turnstile solved (token: %s...)", val[:20])
                return True
        except Exception:
            pass

        # --- Strategy 2: frame_locator ---
        try:
            ts_frame = page.frame_locator(
                'iframe[src*="challenges.cloudflare.com"]'
            )
            for sel in [
                'input[type="checkbox"]',
                '[role="checkbox"]',
                '#challenge-stage input',
                'label',
                '.cb-lb',
                '.ctp-checkbox-label',
                '#verify',
                'div[role="checkbox"]',
                '.mark',
            ]:
                try:
                    loc = ts_frame.locator(sel).first
                    if loc.count() > 0 and loc.is_visible(timeout=2000):
                        loc.click(timeout=5000)
                        log.info("→ Turnstile diklik frame_locator (%s)", sel)
                        page.wait_for_timeout(5000)
                        val = page.evaluate("""() => {
                            const el = document.querySelector(
                                'input[name="cf_challenge_response"]'
                            );
                            return el ? el.value : null;
                        }""")
                        if val and len(val) > 20:
                            log.info("✓ Turnstile solved setelah klik")
                            return True
                        break
                except Exception:
                    continue
        except Exception:
            pass

        # --- Strategy 3: frame object ---
        try:
            for frame in page.frames:
                frame_url = frame.url or ""
                if "challenges.cloudflare.com" in frame_url:
                    for sel in [
                        'input[type="checkbox"]',
                        '[role="checkbox"]',
                        'label',
                        '.cb-lb',
                        '.mark',
                    ]:
                        try:
                            el = frame.wait_for_selector(
                                sel, timeout=2000, state="visible"
                            )
                            if el:
                                el.click(timeout=3000)
                                log.info("→ Turnstile diklik frame (%s)", sel)
                                page.wait_for_timeout(5000)
                                break
                        except Exception:
                            continue
                    break
        except Exception:
            pass

        # --- Strategy 4: coordinate click ---
        try:
            for frame in page.frames:
                if "challenges.cloudflare.com" in (frame.url or ""):
                    for coord in [
                        {"x": 28, "y": 28},
                        {"x": 20, "y": 20},
                        {"x": 35, "y": 35},
                        {"x": 15, "y": 15},
                        {"x": 25, "y": 30},
                        {"x": 30, "y": 25},
                        {"x": 40, "y": 40},
                        {"x": 50, "y": 50},
                        {"x": 12, "y": 12},
                        {"x": 24, "y": 24},
                    ]:
                        try:
                            frame.click(
                                "body", timeout=2000, position=coord
                            )
                            log.info(
                                "→ Turnstile diklik coordinate (%d,%d)",
                                coord["x"], coord["y"],
                            )
                            page.wait_for_timeout(5000)
                            val = page.evaluate("""() => {
                                const el = document.querySelector(
                                    'input[name="cf_challenge_response"]'
                                );
                                return el ? el.value : null;
                            }""")
                            if val and len(val) > 20:
                                log.info(
                                    "✓ Turnstile solved via coordinate"
                                )
                                return True
                            break
                        except Exception:
                            continue
                    break
        except Exception:
            pass

        # --- Strategy 5: page.mouse.click() di posisi iframe ---
        try:
            iframe_box = page.evaluate("""() => {
                const iframe = document.querySelector(
                    'iframe[src*="challenges.cloudflare.com"]'
                );
                if (iframe) {
                    const rect = iframe.getBoundingClientRect();
                    return {
                        x: rect.x, y: rect.y,
                        width: rect.width, height: rect.height
                    };
                }
                return null;
            }""")
            if iframe_box and iframe_box["width"] > 0:
                click_x = iframe_box["x"] + 28
                click_y = iframe_box["y"] + 28
                page.mouse.click(click_x, click_y)
                log.info(
                    "→ Turnstile diklik via mouse (%.0f, %.0f)",
                    click_x, click_y,
                )
                page.wait_for_timeout(5000)
                val = page.evaluate("""() => {
                    const el = document.querySelector(
                        'input[name="cf_challenge_response"]'
                    );
                    return el ? el.value : null;
                }""")
                if val and len(val) > 20:
                    log.info("✓ Turnstile solved via mouse click")
                    return True
        except Exception:
            pass

        time.sleep(3)

    # --- Last check ---
    try:
        val = page.evaluate("""() => {
            const el = document.querySelector(
                'input[name="cf_challenge_response"]'
            );
            return el ? el.value : null;
        }""")
        if val and len(val) > 20:
            log.info("✓ Turnstile solved")
            return True
    except Exception:
        pass

    log.warning("⚠ Turnstile belum ter-solve dalam %ds.", timeout)
    return False


# ---------------------------------------------------------------------------
# Account ID extraction
# ---------------------------------------------------------------------------
def extract_account_id_from_url(url: str) -> Optional[str]:
    """Ambil account_id dari URL dashboard."""
    m = re.search(r"dash\.cloudflare\.com/([a-f0-9]{20,})", url)
    return m.group(1) if m else None
