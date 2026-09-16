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

    while time.time() < deadline:
        # --- PENTING: pastikan window visible (jangan minimize!) ---
        # Page Visibility API: kalau hidden, Turnstile suspend challenge
        # (requestAnimationFrame berhenti), klik tidak di-process.
        try:
            state = page.evaluate(
                "() => document.visibilityState + '/' + document.hasFocus()"
            )
            if "hidden" in state:
                page.bring_to_front()
                log.info("→ Window hidden, di-restore otomatis (jangan minimize!)")
                time.sleep(2)
        except Exception:
            pass

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

        # --- Strategy 1: Cari iframe Turnstile, klik coordinate (28,28) ---
        # Ini metode awal yang terbukti work
        turnstile_frame = None
        for frame in page.frames:
            if "challenges.cloudflare.com" in (frame.url or ""):
                turnstile_frame = frame
                break

        if turnstile_frame:
            log.info("→ Turnstile iframe ditemukan: %s", turnstile_frame.url[:60])
            # Klik coordinate (28,28) di dalam iframe
            for coord in [
                {"x": 28, "y": 28},
                {"x": 20, "y": 20},
                {"x": 35, "y": 35},
            ]:
                try:
                    turnstile_frame.click("body", timeout=2000, position=coord)
                    log.info("→ Turnstile diklik coordinate (%d,%d)", coord["x"], coord["y"])
                    break
                except Exception:
                    continue

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
                        log.info("✓ Turnstile solved via coordinate click")
                        return True
                except Exception:
                    pass

        # --- Strategy 2: Cari iframe via JS, klik page.mouse ---
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
            log.info("→ Turnstile iframe di (%.0f, %.0f) %dx%d",
                     iframe_box["x"], iframe_box["y"],
                     iframe_box["width"], iframe_box["height"])
            # Klik page.mouse di posisi iframe (kiri-atas + 28)
            click_x = iframe_box["x"] + 28
            click_y = iframe_box["y"] + iframe_box["height"] / 2
            try:
                page.mouse.click(click_x, click_y)
                log.info("→ Klik mouse iframe (%.0f, %.0f)", click_x, click_y)
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
                        log.info("✓ Turnstile solved via mouse iframe click")
                        return True
                except Exception:
                    pass

        # --- Strategy 3: Cari element dengan text "human/manusia" ---
        # Pakai page.evaluate (querySelectorAll) — metode awal
        click_pos = page.evaluate("""() => {
            const keywords = ['manusia', 'human', 'verify you are', 'sahkan'];
            const all = document.querySelectorAll('*');
            // Cari heading Y dulu
            let headingY = -1;
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
            // Cari element dengan keyword DI BAWAH heading
            for (const el of all) {
                const txt = (el.textContent || '').toLowerCase().trim();
                if (txt.includes('let us know') || txt.includes('beritahu kami')) continue;
                if (txt.includes('save email') || txt.includes('simpan email')) continue;
                for (const kw of keywords) {
                    if (txt.includes(kw)) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0 && r.height < 80) {
                            if (headingY < 0 || r.y > headingY) {
                                return {
                                    x: r.x + 15,
                                    y: r.y + r.height / 2,
                                    text: txt.slice(0, 40),
                                };
                            }
                        }
                    }
                }
            }
            return null;
        }""")

        if click_pos:
            log.info("→ Klik Turnstile text: '%s' di (%.0f, %.0f)",
                     click_pos['text'], click_pos['x'], click_pos['y'])
            try:
                page.mouse.click(click_pos['x'], click_pos['y'])
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
                        log.info("✓ Turnstile solved via text click")
                        return True
                except Exception:
                    pass

            # Retry klik
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

        # Kalau semua strategy gagal, tunggu 5 detik
        if not turnstile_frame and not iframe_box and not click_pos:
            log.warning("⚠ Turnstile tidak ditemukan, tunggu...")
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

    # ── STRATEGI BARU: inject widget dummy & solve via Turnstile API resmi ──
    # (teknik dari Turnstile-Solver/Boterdrop: render widget sendiri,
    #  biarkan auto-solve, ambil token dari input cf-turnstile-response,
    #  lalu tempel ke field response form asli)
    try:
        if _solve_via_injected_widget(page):
            return True
    except Exception as e:
        log.warning("⚠ Strategi injected-widget gagal: %s", str(e)[:80])

    # ── Fallback manual: notif Telegram + tunggu klik manusia ──
    return _wait_manual_help(page)


def _solve_via_injected_widget(page: Page) -> bool:
    """Solve Turnstile dengan inject widget dummy ke halaman sekarang.

    - Ambil sitekey dari widget asli (data-sitekey / input config)
    - Inject <div class="cf-turnstile"> + script api.js resmi
    - Widget baru biasanya non-interactive → auto-solve (tanpa klik)
    - Ambil token dari [name=cf-turnstile-response] → paste ke form asli
    """
    log.info("→ Strategi injected-widget: render widget solver sendiri...")

    # 1. Ambil sitekey dari widget asli
    sitekey = page.evaluate("""() => {
        // Widget asli CF di halaman signup
        const el = document.querySelector('[data-sitekey]')
            || document.querySelector('div[class*="turnstile"]');
        if (el && el.dataset && el.dataset.sitekey) return el.dataset.sitekey;
        // Cari di semua iframe src (kadang sitekey di query string)
        for (const f of document.querySelectorAll('iframe')) {
            const m = (f.src || '').match(/sitekey=([0-9a-zA-Z_-]+)/);
            if (m) return m[1];
        }
        return null;
    }""")
    if not sitekey:
        log.info("  sitekey tidak ditemukan di halaman")
        return False
    log.info("  sitekey: %s", sitekey[:20])

    # 2. Cek apakah halaman sudah punya turnstile API script — kalau belum, inject
    has_api = page.evaluate(
        "() => !!document.querySelector("
        "'script[src*=\"challenges.cloudflare.com/turnstile\"]')")
    if not has_api:
        page.evaluate("""() => {
            const s = document.createElement('script');
            s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js';
            s.async = true;
            document.head.appendChild(s);
        }""")
        time.sleep(2)

    # 3. Inject widget dummy (di luar viewport, tidak mengganggu layout)
    page.evaluate("""(sitekey) => {
        if (document.getElementById('__cfauto_solver')) return;
        const wrap = document.createElement('div');
        wrap.id = '__cfauto_solver';
        wrap.style.cssText = 'position:fixed;bottom:0;right:0;'
            + 'width:320px;height:80px;z-index:99999;opacity:0.01;';
        wrap.innerHTML = '<div class="cf-turnstile" data-sitekey="'
            + sitekey + '"></div>';
        document.body.appendChild(wrap);
    }""", sitekey)
    time.sleep(2)

    # 4. Poll token dari widget dummy sampai terisi (max 60s)
    token = None
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            token = page.evaluate("""() => {
                const el = document.querySelector(
                    '#__cfauto_solver [name=cf-turnstile-response]');
                return el ? el.value : null;
            }""")
            if token and len(token) > 20:
                break
            # widget kadang perlu satu klik
            page.locator('#__cfauto_solver .cf-turnstile').click(
                timeout=1000, force=True)
        except Exception:
            pass
        time.sleep(1.5)

    if not token:
        log.info("  widget dummy tidak menghasilkan token dalam 60s")
        return False
    log.info("✓ Token didapat dari widget dummy: %s...", token[:25])

    # 5. Tempel token ke field response form asli
    pasted = page.evaluate("""(token) => {
        // Cari input response asli (bukan punya widget dummy)
        const candidates = document.querySelectorAll(
            '[name=cf-turnstile-response], [name="cf_challenge_response"]');
        for (const el of candidates) {
            if (el.closest('#__cfauto_solver')) continue;
            el.value = token;
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            return true;
        }
        // Kalau field response ada di dalam iframe widget asli
        for (const f of document.querySelectorAll('iframe')) {
            try {
                const w = f.contentWindow.document.querySelector(
                    '[name=cf-turnstile-response]');
                if (w) { w.value = token; return true; }
            } catch (e) {}
        }
        return false;
    }""", token)
    if pasted:
        log.info("✓ Token ditempel ke form asli — submit bisa lanjut")
        return True

    log.info("  field response asli tidak ditemukan")
    return False


def _wait_manual_help(page: Page) -> bool:
    """Kirim notif Telegram (screenshot), lalu tunggu solved secara manual.

    Timeout dari config telegram.manual_timeout_minutes (default 10).
    Return True kalau solved (klik manual via VNC / challenge selesai).
    """
    try:
        import cf_telegram
    except Exception:
        return False

    tcfg = cf_telegram._cfg()
    if not cf_telegram.enabled() or not tcfg.get("notify_manual", True):
        return False

    manual_deadline = time.time() + int(
        tcfg.get("manual_timeout_minutes", 10)) * 60
    notified = False

    log.info("→ Mode bantuan manual: notif Telegram + tunggu hingga %d menit...",
             int(tcfg.get("manual_timeout_minutes", 10)))

    while time.time() < manual_deadline:
        # solved?
        try:
            val = page.evaluate("""() => {
                const el = document.querySelector(
                    'input[name="cf_challenge_response"]'
                );
                return el ? el.value : null;
            }""")
            if val and len(val) > 20:
                log.info("✓✓✓ Turnstile solved (manual help)!")
                cf_telegram.send_message(
                    "✅ <b>Solved!</b> Batch lanjut otomatis.")
                return True
        except Exception:
            # Page bisa saja sudah ditutup/navigasi — keluar
            return False

        # Kirim notif sekali (setelah 5 detik pertama, biar screenshot fresh)
        if not notified:
            try:
                debug_dir = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "..", "debug")
                os.makedirs(debug_dir, exist_ok=True)
                shot = os.path.join(debug_dir, "turnstile_manual.png")
                page.screenshot(path=shot)
                cf_telegram.notify_manual_need(
                    idx=0, email=page.url[:60],
                    reason="Turnstile butuh klik manual",
                    screenshot_path=shot)
                notified = True
            except Exception:
                pass

        # Setelah notif, bantu re-klik sekali tiap 30 detik (kadang
        # challenge baru muncul setelah klik manual pertama)
        time.sleep(5)
        try:
            for frame in page.frames:
                if "challenges.cloudflare.com" in (frame.url or ""):
                    try:
                        frame.click("body", timeout=2000,
                                    position={"x": 28, "y": 28})
                    except Exception:
                        pass
                    break
        except Exception:
            pass
        time.sleep(25)

    log.warning("⚠ Bantuan manual timeout — Turnstile tetap belum solved.")
    cf_telegram.send_message("⏰ Timeout bantuan manual — akun ini di-skip.")
    return False


# ---------------------------------------------------------------------------
# Account ID extraction
# ---------------------------------------------------------------------------
def extract_account_id_from_url(url: str) -> Optional[str]:
    """Ambil account_id dari URL dashboard."""
    m = re.search(r"dash\.cloudflare\.com/([a-f0-9]{20,})", url)
    return m.group(1) if m else None
