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

    # Wait untuk iframe Turnstile muncul
    try:
        page.wait_for_selector(
            'iframe[src*="challenges.cloudflare.com"]',
            timeout=10000, state="attached",
        )
        log.info("→ Turnstile iframe ditemukan")
    except Exception:
        log.warning("⚠ Turnstile iframe tidak ditemukan dalam 10s")

    # Keyword "human" multi-bahasa
    human_keywords = ['verify you are human', 'verifikasi bahwa',
                      'sahkan anda manusia', 'sahkan kamu manusia',
                      'verifikasi bahwa anda', 'verify you are',
                      'human', 'manusia']

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

        # --- Strategy: Screenshot → cari text "human/manusia" → klik koordinat ---
        try:
            import os as _os
            debug_dir = _os.path.join(
                _os.path.dirname(_os.path.abspath(__file__)), "..", "debug"
            )
            _os.makedirs(debug_dir, exist_ok=True)
            ss_path = _os.path.join(debug_dir, "turnstile_find.png")
            page.screenshot(path=ss_path)

            # Cari text "human" / "manusia" di screenshot via JS
            # Cloudflare render checkbox sebagai widget — cari posisi widget
            # dengan mencari element yang text-nya mengandung keyword
            click_pos = page.evaluate("""(keywords) => {
                // Cari SEMUA element yang text-nya mengandung keyword human
                // lalu cari yang BUKAN heading (height < 80px)
                // dan ada di bawah "Let us know" heading
                const all = document.querySelectorAll('*');
                let found = null;
                let headingY = -1;

                // Pertama: cari posisi Y heading "Let us know"
                for (const el of all) {
                    const txt = (el.textContent || '').toLowerCase().trim();
                    if ((txt.includes('let us know') || txt.includes('beritahu kami'))
                        && txt.length < 60) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0) {
                            headingY = r.y + r.height;
                            break;
                        }
                    }
                }

                // Kedua: cari checkbox/widget DI BAWAH heading
                for (const el of all) {
                    const txt = (el.textContent || '').toLowerCase().trim();
                    // Skip heading
                    if (txt.includes('let us know') || txt.includes('beritahu kami')) continue;
                    // Skip save email
                    if (txt.includes('save email') || txt.includes('simpan email')) continue;

                    // Cek keyword
                    let match = false;
                    for (const kw of keywords) {
                        if (txt.includes(kw)) {
                            match = true;
                            break;
                        }
                    }

                    if (match) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0 && r.height < 80) {
                            // Harus di BAWAH heading (kalau heading ada)
                            if (headingY < 0 || r.y > headingY) {
                                // Klik di kiri element (posisi checkbox biasanya di kiri)
                                return {
                                    x: r.x + 20,
                                    y: r.y + r.height / 2,
                                    text: txt.slice(0, 40),
                                    headingY: headingY,
                                    elY: r.y,
                                };
                            }
                        }
                    }
                }

                // Fallback: kalau tidak ada heading, cari element dengan keyword saja
                for (const el of all) {
                    const txt = (el.textContent || '').toLowerCase().trim();
                    if (txt.includes('let us know') || txt.includes('beritahu kami')) continue;
                    if (txt.includes('save email') || txt.includes('simpan email')) continue;

                    let match = false;
                    for (const kw of keywords) {
                        if (txt.includes(kw)) {
                            match = true;
                            break;
                        }
                    }

                    if (match) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0 && r.height < 80 && r.width < 500) {
                            return {
                                x: r.x + 20,
                                y: r.y + r.height / 2,
                                text: txt.slice(0, 40),
                                headingY: headingY,
                                elY: r.y,
                            };
                        }
                    }
                }

                return null;
            }""", human_keywords)

            if click_pos:
                log.info("→ Klik Turnstile: '%s' di (%.0f, %.0f)",
                         click_pos.get('text', '')[:40],
                         click_pos['x'], click_pos['y'])

                # Klik via page.mouse
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
                            log.info("✓ Turnstile solved via screenshot+click")
                            return True
                    except Exception:
                        pass

                # Kalau belum solved, klik lagi sedikit beda posisi
                time.sleep(5)
                try:
                    page.mouse.click(click_pos['x'] + 10, click_pos['y'])
                    log.info("→ Klik ulang Turnstile (+10px)")
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
                            log.info("✓ Turnstile solved via retry click")
                            return True
                    except Exception:
                        pass
            else:
                # Tidak ada checkbox/iframe → cek iframe fallback
                iframe_box = page.evaluate("""() => {
                    const iframe = document.querySelector(
                        'iframe[src*="challenges.cloudflare.com"]'
                    );
                    if (iframe) {
                        const rect = iframe.getBoundingClientRect();
                        return {x: rect.x, y: rect.y, width: rect.width, height: rect.height};
                    }
                    return null;
                }""")
                if iframe_box and iframe_box["width"] > 0:
                    click_x = iframe_box["x"] + 28
                    click_y = iframe_box["y"] + iframe_box["height"] / 2
                    try:
                        page.mouse.click(click_x, click_y)
                        log.info("→ Turnstile diklik iframe (%.0f, %.0f)", click_x, click_y)
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
                                log.info("✓ Turnstile solved via iframe click")
                                return True
                        except Exception:
                            pass
                else:
                    log.warning("⚠ Tidak ada checkbox/iframe Turnstile, tunggu...")
                    time.sleep(5)
        except Exception as e:
            log.warning("⚠ Error Turnstile: %s", str(e)[:80])
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
