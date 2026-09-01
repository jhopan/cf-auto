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
def random_password(length: int = 14) -> str:
    """Password kuat yang memenuhi syarat Cloudflare."""
    if length < 8:
        length = 8
    upper = random.choices(string.ascii_uppercase, k=3)
    lower = random.choices(string.ascii_lowercase, k=max(3, length // 2))
    digit = random.choices(string.digits, k=3)
    special = random.choices("!@#$%^&*", k=2)
    pwd = upper + lower + digit + special
    # Tambah karakter acak sampai panjang yang diminta
    all_chars = string.ascii_letters + string.digits + "!@#$%^&*"
    extra = max(0, length - len(pwd))
    pwd += random.choices(all_chars, k=extra)
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

    # Keyword "human" multi-bahasa
    keywords = ['manusia', 'human', 'Verify you are human', 'Verifikasi',
                'sahkan', 'verify']

    while time.time() < deadline:
        # --- Cek auto-solve (token sudah ada) ---
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

        # --- Screenshot untuk debug ---
        try:
            debug_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..", "debug"
            )
            os.makedirs(debug_dir, exist_ok=True)
            page.screenshot(path=os.path.join(debug_dir, "turnstile_find.png"))
        except Exception:
            pass

        # --- Cari text "human/manusia" via Playwright get_by_text ---
        # Playwright bisa cari text di shadow DOM yang querySelector tidak bisa
        click_pos = None
        for kw in keywords:
            try:
                # Cari element yang mengandung text keyword
                # Tapi skip "Let us know" heading dan "Save email"
                loc = page.get_by_text(kw, exact=False)
                cnt = loc.count()
                for i in range(cnt):
                    try:
                        el = loc.nth(i)
                        txt = (el.text_content() or "").strip().lower()
                        # Skip heading dan save email
                        if 'let us know' in txt or 'beritahu kami' in txt:
                            continue
                        if 'save email' in txt or 'simpan email' in txt:
                            continue
                        # Cari element kecil (checkbox area, bukan heading)
                        box = el.bounding_box()
                        if box and box['width'] > 0 and box['height'] > 0 and box['height'] < 80:
                            click_pos = {
                                'x': box['x'] + 15,  # checkbox di kiri text
                                'y': box['y'] + box['height'] / 2,
                                'text': txt[:40],
                            }
                            break
                    except Exception:
                        continue
                if click_pos:
                    break
            except Exception:
                continue

        if click_pos:
            log.info("→ Klik Turnstile: '%s' di (%.0f, %.0f)",
                     click_pos['text'], click_pos['x'], click_pos['y'])
            try:
                page.mouse.click(click_pos['x'], click_pos['y'])
            except Exception:
                pass

            # Tunggu 10 detik, cek setiap 2 detik
            for _ in range(5):
                time.sleep(2)
                try:
                    val = page.evaluate("""() => {
                        const el = document.querySelector(
                            'input[name="cf_challenge_response"]'
                        );
                        return el ? el.value : null;
                    }""")
                    if val and len(val) > 20:
                        log.info("✓ Turnstile solved via text+click")
                        return True
                except Exception:
                    pass

            # Kalau belum solved, klik lagi sedikit beda posisi
            time.sleep(3)
            try:
                page.mouse.click(click_pos['x'] + 10, click_pos['y'])
                log.info("→ Klik ulang (+10px)")
            except Exception:
                pass

            for _ in range(5):
                time.sleep(2)
                try:
                    val = page.evaluate("""() => {
                        const el = document.querySelector(
                            'input[name="cf_challenge_response"]'
                        );
                        return el ? el.value : null;
                    }""")
                    if val and len(val) > 20:
                        log.info("✓ Turnstile solved via retry")
                        return True
                except Exception:
                    pass
        else:
            log.warning("⚠ Text 'human/manusia' tidak ditemukan di halaman, tunggu...")
            time.sleep(5)

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
