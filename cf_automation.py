"""
cf_automation.py — Automation pendaftaran Cloudflare dengan Camoufox
Menggunakan temp mail (mail.tm) untuk email verifikasi,
lalu mengambil Global API Key, email, dan Account ID.

Flow (Berdasarkan observasi UI Cloudflare dashboard):
  1. Buat email sementara via mail.tm
  2. Buka dash.cloudflare.com/sign-up dengan Camoufox
  3. Isi email + password, solve Turnstile, submit
  4. Setelah masuk dashboard, klik "Workers & Pages" di sidebar
     → Cloudflare menampilkan "Verify your account" dan mengirim email verifikasi
  5. Tunggu email verifikasi dari Cloudflare di mail.tm
  6. Buka link verifikasi di TAB BARU (tab CF tetap terbuka)
  7. Klik "Verify your email" di tab verifikasi
  8. Kembali ke tab CF, navigasi ke profile/api-tokens
  9. Scroll ke "Global API Key" → klik "View"
 10. Modal "Verify Your Identity" → klik "Send Verification Code"
 11. Cloudflare kirim email berisi kode 7-digit
 12. Tunggu email kode, masukkan ke modal "Your API Key"
 13. Solve Turnstile di modal, klik "View"
 14. Copy Global API Key yang muncul
 15. Ambil Account ID dari halaman
"""
from __future__ import annotations
import json
import re
import os
import time
import random
import string
import logging
import argparse
from typing import Optional

from camoufox.sync_api import Camoufox
from camoufox import DefaultAddons
from playwright.sync_api import Page, TimeoutError as PWTimeout

from temp_mail import TempMail, TempMailAccount

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("cf_auto")

SIGNUP_URL = "https://dash.cloudflare.com/sign-up"
API_TOKENS_URL = "https://dash.cloudflare.com/profile/api-tokens"
WORKERS_URL = "https://dash.cloudflare.com/?to=/:account/workers"
CF_API_BASE = "https://api.cloudflare.com/client/v4"

# Selectors
SEL_EMAIL = ['input[name="email"]', 'input[type="email"]', 'input[placeholder*="mail" i]']
SEL_PASSWORD = ['input[name="password"]', 'input[type="password"]']
SEL_SIGNUP_BTN = ['button[type="submit"]:has-text("Sign up")',
                  'button:has-text("Sign up")']


# ---------------------------------------------------------------------------
# Helpers
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


def find_first(page: Page, selectors: list[str], timeout: int = 15000):
    """Cari elemen pertama yang ada dari daftar selector."""
    for sel in selectors:
        try:
            el = page.wait_for_selector(sel, timeout=timeout, state="visible")
            if el:
                return el
        except PWTimeout:
            continue
    return None


def wait_and_click(page: Page, selectors: list[str], timeout: int = 15000,
                   force: bool = False) -> bool:
    """Klik elemen pertama yang ditemukan dari daftar selector."""
    el = find_first(page, selectors, timeout=timeout)
    if el:
        try:
            el.click(force=force, timeout=10000)
            return True
        except Exception:
            try:
                el.evaluate("e => e.click()")
                return True
            except Exception:
                return False
    return False


def fill_input(page: Page, selectors: list[str], value: str, timeout: int = 15000) -> bool:
    """Isi input field."""
    el = find_first(page, selectors, timeout=timeout)
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
    # Last resort: fill via JS
    for sel in selectors:
        try:
            page.evaluate(f"""(v) => {{
                const el = document.querySelector('{sel}');
                if (el) {{ el.focus(); el.value = v; el.dispatchEvent(new Event('input', {{bubbles: true}})); }}
            }}""", value)
            return True
        except Exception:
            continue
    return False


def dismiss_cookie_banner(page: Page) -> None:
    """Tutup OneTrust cookie consent banner yang bisa blocking form."""
    try:
        page.evaluate("""() => {
            const btn = document.querySelector('#onetrust-reject-all-handler, .ot-pc-refuse-all-handler');
            if (btn) { btn.click(); return; }
            const ot = document.querySelector('#onetrust-banner-sdk, #onetrust-consent-sdk');
            if (ot) ot.style.display = 'none';
            const ov = document.querySelector('#onetrust-pc-sdk, .onetrust-pc-dark-filter');
            if (ov) ov.style.display = 'none';
        }""")
        page.wait_for_timeout(500)
    except Exception:
        pass


def wait_for_turnstile(page: Page, timeout: int = 90, in_modal: bool = False) -> bool:
    """Tunggu & selesaikan Turnstile challenge.

    Strategi:
    1. Cek auto-solve (cf_challenge_response terisi)
    2. Klik checkbox via frame_locator
    3. Klik checkbox via frame object
    4. Klik via coordinate di dalam iframe
    5. Klik via mouse di posisi iframe di halaman utama (bypass iframe)
    """
    log.info("⏳ Menunggu Turnstile solve...")
    deadline = time.time() + timeout
    attempt = 0

    # Wait untuk iframe Turnstile muncul
    try:
        page.wait_for_selector('iframe[src*="challenges.cloudflare.com"]',
                              timeout=10000, state="attached")
    except Exception:
        pass

    while time.time() < deadline:
        # --- Strategy 1: cek auto-solve ---
        try:
            val = page.evaluate("""() => {
                const el = document.querySelector('input[name="cf_challenge_response"]');
                return el ? el.value : null;
            }""")
            if val and len(val) > 20:
                log.info("✓ Turnstile solved (token: %s...)", val[:20])
                return True
        except Exception:
            pass

        attempt += 1

        # --- Strategy 2: frame_locator ---
        try:
            ts_frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
            for sel in ['input[type="checkbox"]',
                        '[role="checkbox"]',
                        '#challenge-stage input',
                        'label',
                        '.cb-lb',
                        '.ctp-checkbox-label',
                        '#verify',
                        'div[role="checkbox"]',
                        '.mark']:
                try:
                    loc = ts_frame.locator(sel).first
                    if loc.count() > 0 and loc.is_visible(timeout=2000):
                        loc.click(timeout=5000)
                        log.info("→ Turnstile diklik frame_locator (%s, attempt %d)", sel, attempt)
                        page.wait_for_timeout(5000)
                        val = page.evaluate("""() => {
                            const el = document.querySelector('input[name="cf_challenge_response"]');
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
                    for sel in ['input[type="checkbox"]',
                                '[role="checkbox"]',
                                'label',
                                '.cb-lb',
                                '.mark']:
                        try:
                            el = frame.wait_for_selector(sel, timeout=2000, state="visible")
                            if el:
                                el.click(timeout=3000)
                                log.info("→ Turnstile diklik via frame (%s)", sel)
                                page.wait_for_timeout(5000)
                                break
                        except Exception:
                            continue
                    break
        except Exception:
            pass

        # --- Strategy 4: coordinate click di dalam iframe ---
        try:
            for frame in page.frames:
                if "challenges.cloudflare.com" in (frame.url or ""):
                    for coord in [{"x": 28, "y": 28}, {"x": 20, "y": 20},
                                  {"x": 35, "y": 35}, {"x": 15, "y": 15},
                                  {"x": 25, "y": 30}, {"x": 30, "y": 25},
                                  {"x": 40, "y": 40}, {"x": 50, "y": 50},
                                  {"x": 12, "y": 12}, {"x": 24, "y": 24}]:
                        try:
                            frame.click("body", timeout=2000, position=coord)
                            log.info("→ Turnstile diklik coordinate (%d,%d)", coord["x"], coord["y"])
                            page.wait_for_timeout(5000)
                            val = page.evaluate("""() => {
                                const el = document.querySelector('input[name="cf_challenge_response"]');
                                return el ? el.value : null;
                            }""")
                            if val and len(val) > 20:
                                log.info("✓ Turnstile solved setelah coordinate click")
                                return True
                            break
                        except Exception:
                            continue
                    break
        except Exception:
            pass

        # --- Strategy 5: page.mouse.click() di posisi iframe (bypass iframe) ---
        # Cari posisi iframe di halaman, lalu klik di pojok kiri atas
        try:
            iframe_box = page.evaluate("""() => {
                const iframe = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
                if (iframe) {
                    const rect = iframe.getBoundingClientRect();
                    return {x: rect.x, y: rect.y, width: rect.width, height: rect.height};
                }
                return null;
            }""")
            if iframe_box and iframe_box["width"] > 0:
                # Checkbox biasanya di pojok kiri atas iframe
                click_x = iframe_box["x"] + 28
                click_y = iframe_box["y"] + 28
                page.mouse.click(click_x, click_y)
                log.info("→ Turnstile diklik via mouse (%.0f, %.0f)", click_x, click_y)
                page.wait_for_timeout(5000)
                val = page.evaluate("""() => {
                    const el = document.querySelector('input[name="cf_challenge_response"]');
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
            const el = document.querySelector('input[name="cf_challenge_response"]');
            return el ? el.value : null;
        }""")
        if val and len(val) > 20:
            log.info("✓ Turnstile solved")
            return True
    except Exception:
        pass

    log.warning("⚠ Turnstile belum ter-solve dalam %ds.", timeout)
    return False


def extract_account_id_from_url(url: str) -> Optional[str]:
    """Ambil account_id dari URL dashboard."""
    m = re.search(r"dash\.cloudflare\.com/([a-f0-9]{20,})", url)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Main automation
# ---------------------------------------------------------------------------
class CloudflareAutomation:
    def __init__(self, headless: bool = False, proxy: Optional[str] = None,
                 mail_proxy: Optional[str] = None):
        self.headless = headless
        self.proxy = proxy
        self.mail = TempMail(proxy=mail_proxy)
        self.mail_account: Optional[TempMailAccount] = None
        self.cf_email: Optional[str] = None
        self.cf_password: Optional[str] = None
        self.global_api_key: Optional[str] = None
        self.account_id: Optional[str] = None

    # ------------------------------------------------------------------
    def step1_create_temp_email(self) -> str:
        """Buat email sementara via mail.tm."""
        log.info("═══ Step 1: Buat temp mail ═══")
        self.mail_account = self.mail.create_account()
        self.cf_email = self.mail_account.address
        self.cf_password = random_password()
        log.info("  Email    : %s", self.cf_email)
        log.info("  Password : %s", self.cf_password)
        return self.cf_email

    # ------------------------------------------------------------------
    def step2_signup_cloudflare(self, page: Page) -> None:
        """Isi form signup, solve Turnstile, dan submit."""
        log.info("═══ Step 2: Signup Cloudflare ═══")
        page.goto(SIGNUP_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        dismiss_cookie_banner(page)

        # Isi email
        if not fill_input(page, SEL_EMAIL, self.cf_email, timeout=15000):
            raise RuntimeError("Field email tidak ditemukan")
        log.info("✓ Email terisi")

        # Isi password
        if not fill_input(page, SEL_PASSWORD, self.cf_password, timeout=10000):
            raise RuntimeError("Field password tidak ditemukan")
        log.info("✓ Password terisi")

        # Uncheck "Save email" checkbox
        try:
            page.uncheck('input[type="checkbox"]', timeout=3000)
        except Exception:
            pass

        # Solve Turnstile (WAJIB sebelum submit)
        solved = wait_for_turnstile(page, timeout=90)
        if not solved:
            log.warning("⚠ Turnstile belum solved! Menunggu klik manual...")
            try:
                page.wait_for_function(
                    """() => {
                        const el = document.querySelector('input[name="cf_challenge_response"]');
                        return el && el.value && el.value.length > 20;
                    }""",
                    timeout=60000,
                )
                log.info("✓ Turnstile solved (manual)")
            except Exception:
                log.error("✗ Turnstile tidak solved. Aborting signup.")
                return

        # Klik Sign up
        page.wait_for_timeout(1000)
        if not wait_and_click(page, SEL_SIGNUP_BTN, timeout=10000, force=True):
            page.keyboard.press("Enter")
        log.info("✓ Tombol Sign up diklik")

        # Tunggu navigasi
        page.wait_for_timeout(5000)
        log.info("  URL setelah signup: %s", page.url)

    # ------------------------------------------------------------------
    def step3_trigger_verification(self, page: Page) -> None:
        """Buka Workers & Pages untuk trigger email verifikasi.

        URL yang benar: /{account_id}/workers-and-pages
        Ini memicu Cloudflare menampilkan "Verify your account" dan
        mengirim email verifikasi ke temp mail.
        """
        log.info("═══ Step 3: Trigger verifikasi via Workers & Pages ═══")

        # Tunggu dashboard load
        page.wait_for_timeout(5000)
        dismiss_cookie_banner(page)

        # Ambil account ID dari URL dashboard
        url = page.url
        aid = extract_account_id_from_url(url)
        if not aid:
            # Tunggu URL stabil
            for _ in range(5):
                page.wait_for_timeout(2000)
                aid = extract_account_id_from_url(page.url)
                if aid:
                    break

        if aid:
            self.account_id = aid
            log.info("✓ Account ID: %s", aid)
            # Navigasi langsung ke workers-and-pages (URL yang benar!)
            workers_url = f"https://dash.cloudflare.com/{aid}/workers-and-pages"
            log.info("→ Navigasi ke: %s", workers_url)
            page.goto(workers_url, wait_until="domcontentloaded", timeout=60000)
        else:
            log.warning("⚠ Account ID tidak ditemukan di URL, coba sidebar")
            # Fallback: klik sidebar
            clicked = wait_and_click(page, [
                'a:has-text("Workers & Pages")',
                'a:has-text("Workers")',
                'a[href*="workers"]',
            ], timeout=10000, force=True)
            if not clicked:
                page.goto(WORKERS_URL, wait_until="domcontentloaded", timeout=60000)

        page.wait_for_timeout(5000)
        log.info("  URL: %s", page.url)

        # Cek apakah halaman "Verify your account" muncul
        body_text = page.inner_text("body")
        if "verify" in body_text.lower() or "Verify your account" in body_text:
            log.info("✓ Halaman verifikasi muncul - Cloudflare akan kirim email")
        else:
            log.info("→ Halaman workers-and-pages loaded")

        # Klik "Resend email" jika ada (untuk pastikan email terkirim)
        wait_and_click(page, ['button:has-text("Resend email")',
                              'button:has-text("Resend")'], timeout=5000, force=True)
        page.wait_for_timeout(2000)

    # ------------------------------------------------------------------
    def step3b_open_mail_tab(self, browser) -> object:
        """Buka tab mail.tm web untuk monitoring email.

        Tab ini dibuka di context yang SAMA dengan tab Cloudflare,
        sehingga semua session cookie shared. Mail.tm tidak butuh
        login CF, tapi tab ini berguna untuk monitoring manual.
        """
        log.info("═══ Step 3b: Buka tab mail.tm ═══")
        mail_page = browser.new_page()
        mail_url = f"https://mail.tm/id/login"  # Login page mail.tm
        mail_page.goto(mail_url, wait_until="domcontentloaded", timeout=60000)
        mail_page.wait_for_timeout(2000)

        # Login ke mail.tm dengan akun yang sudah dibuat
        try:
            # Isi email
            mail_page.fill('input[name="address"]', self.mail_account.address, timeout=5000)
            mail_page.fill('input[name="password"]', self.mail_account.password, timeout=5000)
            mail_page.click('button[type="submit"]', timeout=5000)
            mail_page.wait_for_timeout(3000)
            log.info("✓ Tab mail.tm login: %s", self.mail_account.address)
        except Exception:
            # Mungkin sudah login atau form berbeda
            log.info("→ Tab mail.tm dibuka (login mungkin tidak diperlukan)")

        log.info("✓ Tab mail.tm siap untuk monitoring")
        return mail_page

    # ------------------------------------------------------------------
    def step4_verify_email_new_tab(self, page: Page, browser=None) -> None:
        """Tunggu email verifikasi, buka di tab baru (tab ke-3), klik Verify.

        Penting: Tab verifikasi dibuka di context yang SAMA dengan tab CF.
        Karena satu context = satu session = cookie shared,
        CF akan auto-recognize login di tab verifikasi.

        Tab layout:
        - Tab 1: Cloudflare dashboard (workers-and-pages)
        - Tab 2: mail.tm (monitoring)
        - Tab 3: Link verifikasi (kosong, lalu buka verify link)
        """
        log.info("═══ Step 4: Verifikasi email di tab baru ═══")
        msg = self.mail.wait_for_email(
            token=self.mail_account.token,
            from_contains="cloudflare",
            timeout=180,
        )
        log.info("✓ Email dari: %s", msg.get("from", {}).get("address", "?"))
        log.info("✓ Subject: %s", msg.get("subject", "?"))

        # Parse email content
        html_raw = msg.get("html") or ""
        if isinstance(html_raw, list):
            html = "\n".join(str(h) for h in html_raw)
        else:
            html = str(html_raw) if html_raw else ""
        text_raw = msg.get("text") or ""
        if isinstance(text_raw, list):
            text = "\n".join(str(t) for t in text_raw)
        else:
            text = str(text_raw) if text_raw else ""

        # Cari verification link (skip link dokumentasi)
        link = TempMail.extract_link(html)
        if not link:
            # Cari link dash.cloudflare.com di text email
            links = re.findall(r"https?://\S+", html + "\n" + text)
            # Filter: skip developers.cloudflare.com (dokumentasi)
            real_links = [l.rstrip(".,)") for l in links
                         if "developers.cloudflare.com" not in l.lower()
                         and "cloudflare.com" in l.lower()]
            link = real_links[0] if real_links else None
        if not link:
            raise RuntimeError("Link verifikasi tidak ditemukan di email")

        log.info("✓ Link verifikasi: %s", link[:100])

        # Buka link di TAB BARU (tab ke-3) di context yang sama
        # Karena satu context, session cookie CF terbawa → auto-login
        verify_page = None
        try:
            if browser:
                verify_page = browser.new_page()
                log.info("✓ Tab baru (tab 3) dibuka untuk verifikasi")
            else:
                verify_page = page.context.new_page()
                log.info("✓ Tab baru (tab 3) dibuka untuk verifikasi")
        except Exception:
            log.warning("⚠ Tidak bisa buka tab baru, gunakan page yang sama")
            verify_page = page

        verify_page.goto(link, wait_until="domcontentloaded", timeout=60000)
        verify_page.wait_for_timeout(5000)
        log.info("✓ Link verifikasi dibuka di tab baru")
        log.info("  URL: %s", verify_page.url)

        # Cek apakah redirect ke login page
        if "/login" in verify_page.url:
            log.info("→ Redirect ke login. Isi email+password untuk verifikasi...")
            dismiss_cookie_banner(verify_page)

            # Isi email
            if fill_input(verify_page, SEL_EMAIL, self.cf_email, timeout=10000):
                log.info("✓ Email terisi di login page")
            # Isi password
            if fill_input(verify_page, SEL_PASSWORD, self.cf_password, timeout=10000):
                log.info("✓ Password terisi di login page")

            # Klik Sign in
            verify_page.wait_for_timeout(1000)
            wait_and_click(verify_page, [
                'button:has-text("Sign in")',
                'button[type="submit"]',
            ], timeout=10000, force=True)
            log.info("✓ Tombol Sign in diklik di tab verifikasi")
            verify_page.wait_for_timeout(5000)
            log.info("  URL setelah login: %s", verify_page.url)

        # --- DEBUG: screenshot setelah login/redirect ---
        try:
            debug_dir = os.path.join(os.path.dirname(__file__), "debug")
            os.makedirs(debug_dir, exist_ok=True)
            verify_page.screenshot(path=os.path.join(debug_dir, "step4_verify_page.png"))
            log.info("→ Screenshot verifikasi: debug/step4_verify_page.png")
        except Exception:
            pass

        # Cek apakah verifikasi sudah selesai (auto-verify setelah login)
        try:
            body_text = verify_page.inner_text("body")
            if "verified" in body_text.lower() and "success" in body_text.lower():
                log.info("✓ Email sudah terverifikasi (auto)")
            elif "verify your email" in body_text.lower():
                log.info("→ Halaman verifikasi muncul, cari tombol Verify")
        except Exception:
            pass

        # Klik "Verify your email" button (coba berbagai selector)
        # Pentung: setelah login, page mungkin berbeda dari sebelumnya
        verify_clicked = False
        for sel in ['a:has-text("Verify your email")',
                     'button:has-text("Verify your email")',
                     'button:has-text("Verify")',
                     'a:has-text("Verify")',
                     'button:has-text("Confirm")',
                     'a:has-text("Confirm")',
                     'button:has-text("Continue")',
                     'a:has-text("Continue")']:
            try:
                el = verify_page.wait_for_selector(sel, timeout=5000, state="visible")
                if el:
                    el.click(force=True, timeout=5000)
                    verify_clicked = True
                    log.info("✓ Tombol Verify diklik (%s)", sel)
                    break
            except Exception:
                continue

        if not verify_clicked:
            # Mungkin tidak perlu klik - verifikasi otomatis
            log.info("→ Tidak ada tombol Verify - mungkin verifikasi otomatis")

        verify_page.wait_for_timeout(5000)

        # --- Cek apakah verifikasi berhasil ---
        try:
            body_text = verify_page.inner_text("body")
            if "verified" in body_text.lower() or "success" in body_text.lower():
                log.info("✓✓✓ VERIFIKASI EMAIL BERHASIL! ✓✓✓")
            else:
                log.warning("⚠ Status verifikasi tidak diketahui")
                log.info("  Body text: %s", body_text[:200])
        except Exception:
            pass

        log.info("✓ Tombol Verify diklik")

        # Klik "Confirm" / "Get Started" jika ada
        wait_and_click(verify_page, [
            'button:has-text("Confirm")',
            'a:has-text("Confirm")',
            'button:has-text("Continue")',
            'button:has-text("Get Started")',
        ], timeout=8000, force=True)
        verify_page.wait_for_timeout(3000)

        # Tutup tab verifikasi setelah selesai
        if verify_page != page:
            try:
                verify_page.close()
                log.info("✓ Tab verifikasi ditutup")
            except Exception:
                pass

    # ------------------------------------------------------------------
    def step5_navigate_to_api_tokens(self, page: Page) -> None:
        """Navigasi ke profile/api-tokens di tab CF asli."""
        log.info("═══ Step 5: Navigasi ke API Tokens ═══")
        page.goto(API_TOKENS_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        dismiss_cookie_banner(page)
        log.info("  URL: %s", page.url)

    # ------------------------------------------------------------------
    def step6_get_global_api_key(self, page: Page) -> str:
        """Klik View di Global API Key, solve modal verification, ambil key.

        Flow modal:
        1. Klik "View" di sebelah "Global API Key"
        2. Modal "Verify Your Identity" → klik "Send Verification Code"
        3. Cloudflare kirim email berisi kode 7-digit
        4. Tunggu email, masukkan kode ke modal "Your API Key"
        5. Solve Turnstile di modal
        6. Klik "View" → API key muncul
        """
        log.info("═══ Step 6: Ambil Global API Key ═══")

        # Scroll ke bawah sampai ketemu "Global API Key"
        page.evaluate("""() => {
            window.scrollTo(0, document.body.scrollHeight);
        }""")
        page.wait_for_timeout(2000)

        # Klik "View" di sebelah "Global API Key"
        view_clicked = wait_and_click(page, [
            'button:has-text("View")',
            'a:has-text("View")',
        ], timeout=15000, force=True)

        if not view_clicked:
            page.evaluate("""() => {
                const els = Array.from(document.querySelectorAll('button, a'));
                const view = els.find(e => e.textContent.trim().toLowerCase() === 'view');
                if (view) { view.scrollIntoView(); view.click(); }
            }""")
            log.info("→ Klik View via JS")
            page.wait_for_timeout(3000)

        # --- Modal 1: "Verify Your Identity" → Send Verification Code ---
        log.info("→ Menunggu modal 'Verify Your Identity'...")
        page.wait_for_timeout(3000)

        send_clicked = wait_and_click(page, [
            'button:has-text("Send Verification Code")',
            'button:has-text("Send")',
        ], timeout=15000, force=True)

        if not send_clicked:
            page.evaluate("""() => {
                const els = Array.from(document.querySelectorAll('button'));
                const btn = els.find(e => e.textContent.toLowerCase().includes('send'));
                if (btn) btn.click();
            }""")
            log.info("→ Klik Send Verification Code via JS")

        page.wait_for_timeout(3000)
        log.info("✓ Verification code dikirim ke email")

        # --- Tunggu email berisi kode 7-digit ---
        log.info("→ Menunggu email kode verifikasi...")
        code_msg = self.mail.wait_for_email(
            token=self.mail_account.token,
            from_contains="cloudflare",
            subject_contains="code",
            timeout=120,
        )

        # Parse kode dari email
        code_html_raw = code_msg.get("html") or ""
        if isinstance(code_html_raw, list):
            code_html = "\n".join(str(h) for h in code_html_raw)
        else:
            code_html = str(code_html_raw) if code_html_raw else ""
        code_text_raw = code_msg.get("text") or ""
        if isinstance(code_text_raw, list):
            code_text = "\n".join(str(t) for t in code_text_raw)
        else:
            code_text = str(code_text_raw) if code_text_raw else ""

        # Ekstrak kode 7-digit
        code = TempMail.extract_otp(code_html + "\n" + code_text, length=7)
        if not code:
            # Cari pola "code" atau angka 7 digit
            m = re.search(r"\b(\d{7})\b", code_html + code_text)
            if m:
                code = m.group(1)
        if not code:
            raise RuntimeError("Kode verifikasi 7-digit tidak ditemukan di email")

        log.info("✓ Kode verifikasi: %s", code)

        # --- Modal 2: "Your API Key" → input kode + Turnstile ---
        # Target SPESIFIK modal, bukan seluruh halaman!
        log.info("→ Cari modal 'Your API Key'...")

        # Tunggu modal muncul - coba berbagai selector
        modal_found = False
        for modal_sel in ['[role="dialog"]', '[data-testid*="modal"]', '.modal',
                          '[class*="modal"]', '[class*="Modal"]',
                          '[class*="dialog"]', '[class*="Dialog"]',
                          '[aria-modal="true"]']:
            try:
                page.wait_for_selector(modal_sel, timeout=5000, state="visible")
                log.info("✓ Modal terdeteksi: %s", modal_sel)
                modal_found = True
                break
            except Exception:
                continue

        if not modal_found:
            log.warning("⚠ Modal tidak terdeteksi via selector")
            # Debug: inspect DOM untuk lihat struktur modal
            try:
                modal_debug = page.evaluate("""() => {
                    // Cari semua element yang mungkin modal
                    const candidates = [];
                    document.querySelectorAll('div, section, aside').forEach(el => {
                        const cls = el.className?.toString() || '';
                        const role = el.getAttribute('role');
                        const aria = el.getAttribute('aria-modal');
                        const text = el.textContent?.slice(0, 50) || '';
                        // Cari yang punya teks "Your API Key" atau "Verify code"
                        if (text.includes('API Key') || text.includes('Verify code') ||
                            text.includes('digit code') || role === 'dialog' || aria === 'true' ||
                            cls.toLowerCase().includes('modal') || cls.toLowerCase().includes('dialog')) {
                            if (el.offsetHeight > 0 && el.offsetWidth > 0) {
                                candidates.push({
                                    tag: el.tagName,
                                    class: cls.slice(0, 80),
                                    role: role,
                                    ariaModal: aria,
                                    text: text,
                                    children: el.children.length,
                                });
                            }
                        }
                    });
                    return candidates.slice(0, 5);
                }""")
                log.info("→ Modal candidates: %s", json.dumps(modal_debug, indent=2)[:800])
            except Exception as e:
                log.debug("Debug error: %s", e)

        # Isi kode - PENTING: pakai Playwright fill(), BUKAN JS el.value
        # React controlled components tidak react ke el.value, harus simulate keyboard
        code_filled = False

        # Cara 1: pakai Playwright locator (simulasi keyboard sungguhan)
        # Cari input dengan name="code" di dalam modal
        for sel in ['[data-testid*="modal"] input[name="code"]',
                     '[role="dialog"] input[name="code"]',
                     '[aria-modal="true"] input[name="code"]',
                     '.modal input[name="code"]',
                     '[class*="modal"] input[name="code"]',
                     'input[name="code"]',
                     '[data-testid*="modal"] input[placeholder*="code" i]',
                     '[role="dialog"] input[placeholder*="Verify" i]',
                     '[data-testid*="modal"] input[type="text"]:not([name="search"])',
                     '[role="dialog"] input[type="text"]:not([name="search"])']:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible(timeout=3000):
                    loc.click(timeout=3000)
                    loc.fill(code, timeout=5000)
                    code_filled = True
                    log.info("✓ Kode dimasukkan via Playwright fill (%s)", sel)
                    break
            except Exception:
                continue

        # Cara 2: pakai page.fill (juga simulasi keyboard)
        if not code_filled:
            try:
                # Cari SEMUA input name="code" yang visible
                loc = page.locator('input[name="code"]')
                count = loc.count()
                for i in range(count):
                    if loc.nth(i).is_visible(timeout=2000):
                        loc.nth(i).click(timeout=3000)
                        loc.nth(i).fill(code, timeout=5000)
                        code_filled = True
                        log.info("✓ Kode dimasukkan via page.fill (input[name=code] #%d)", i)
                        break
            except Exception:
                pass

        # Cara 3: type manual via keyboard
        if not code_filled:
            try:
                # Klik input pertama yang bukan search, lalu ketik
                page.evaluate("""() => {
                    const modal = document.querySelector('[data-testid*="modal"], [role="dialog"], [aria-modal="true"]');
                    if (modal) {
                        const inputs = modal.querySelectorAll('input[type="text"], input:not([type])');
                        for (const inp of inputs) {
                            if (!inp.name?.includes('search') && !inp.id?.includes('search')) {
                                inp.focus();
                                return;
                            }
                        }
                    }
                }""")
                page.wait_for_timeout(500)
                page.keyboard.type(code, delay=50)
                code_filled = True
                log.info("✓ Kode diketik via keyboard")
            except Exception:
                pass

        if not code_filled:
            log.warning("⚠ Tidak ada input field ditemukan untuk kode!")

        page.wait_for_timeout(1000)

        # Solve Turnstile di DALAM modal
        # Turnstile iframe di dalam modal, jadi kita target iframe di dalam modal container
        solved = False
        # Coba cari Turnstile iframe di dalam modal
        try:
            modal_iframes = page.evaluate("""() => {
                const modal = document.querySelector('[role="dialog"], [data-testid*="modal"], .modal, [class*="modal"]');
                if (!modal) return [];
                const iframes = modal.querySelectorAll('iframe[src*="challenges.cloudflare.com"]');
                return Array.from(iframes).map(f => ({src: f.src, id: f.id}));
            }""")
            if modal_iframes:
                log.info("→ Turnstile iframe ditemukan di modal: %d iframes", len(modal_iframes))
        except Exception:
            pass

        # Solve Turnstile (sekarang harusnya di modal karena satu-satunya Turnstile di halaman)
        solved = wait_for_turnstile(page, timeout=90, in_modal=True)
        if not solved:
            log.warning("⚠ Turnstile modal belum solved, menunggu manual...")
            try:
                page.wait_for_function(
                    """() => {
                        const el = document.querySelector('input[name="cf_challenge_response"]');
                        return el && el.value && el.value.length > 20;
                    }""",
                    timeout=60000,
                )
                log.info("✓ Turnstile solved (manual)")
                solved = True
            except Exception:
                log.error("✗ Turnstile modal tidak solved")
                return ""

        # Klik "View" di DALAM modal (bukan View di baris Global API Key!)
        # Penting: target spesifik tombol View di dalam modal container
        page.wait_for_timeout(1000)

        # Ambil screenshot SEBELUM klik View untuk debug
        try:
            debug_dir = os.path.join(os.path.dirname(__file__), "debug")
            os.makedirs(debug_dir, exist_ok=True)
            page.screenshot(path=os.path.join(debug_dir, "step6_before_view.png"))
        except Exception:
            pass

        # Cari tombol "View" di DALAM modal
        view_in_modal_clicked = False
        for modal_sel in ['[role="dialog"]', '[aria-modal="true"]',
                          '[data-testid*="modal"]', '.modal',
                          '[class*="modal"]', '[class*="Modal"]']:
            try:
                modal_el = page.query_selector(modal_sel)
                if modal_el:
                    # Cari tombol View di dalam modal
                    btn = modal_el.query_selector('button:has-text("View"), button[type="submit"]')
                    if btn:
                        btn.click(force=True, timeout=5000)
                        view_in_modal_clicked = True
                        log.info("✓ Klik View di dalam modal (%s)", modal_sel)
                        break
            except Exception:
                continue

        if not view_in_modal_clicked:
            # Fallback: cari SEMUA tombol View, klik yang terakhir (biasanya yang di modal)
            try:
                view_buttons = page.query_selector_all('button:has-text("View")')
                if view_buttons and len(view_buttons) > 1:
                    # Klik View terakhir (yang di modal, bukan yang di baris Global API Key)
                    view_buttons[-1].click(force=True, timeout=5000)
                    view_in_modal_clicked = True
                    log.info("✓ Klik View terakhir (modal)")
                elif view_buttons:
                    view_buttons[0].click(force=True, timeout=5000)
                    view_in_modal_clicked = True
                    log.info("→ Klik View (hanya 1 ditemukan)")
            except Exception:
                pass

        if not view_in_modal_clicked:
            # Last resort: klik via JS di dalam modal
            page.evaluate("""() => {
                const modal = document.querySelector('[role="dialog"], [aria-modal="true"], [data-testid*="modal"], .modal, [class*="modal"], [class*="Modal"]');
                if (modal) {
                    const btns = modal.querySelectorAll('button');
                    const view = Array.from(btns).find(b => b.textContent.trim().toLowerCase().includes('view'));
                    if (view) view.click();
                }
            }""")
            log.info("→ Klik View via JS di modal")

        # Tunggu modal "Your API Key" muncul dengan token
        # Cek setiap 500ms untuk tangkap key sebelum modal tertutup
        log.info("→ Menunggu modal API Key muncul...")
        key = None
        deadline_key = time.time() + 30
        while time.time() < deadline_key:
            page.wait_for_timeout(500)

            # Cek apakah modal "Your API Key" dengan token muncul
            try:
                body = page.inner_text("body")
                if "Protect this key" in body or "protect this key" in body.lower():
                    log.info("→ Modal 'Your API Key' terdeteksi (Protect this key)")
            except Exception:
                pass

            key = self._extract_api_key_from_page(page)
            if key:
                log.info("✓ API Key ditemukan!")
                break

        if key:
            self.global_api_key = key
            log.info("✓ Global API Key: %s", key[:8] + "..." + key[-4:])
            return key

        # --- DEBUG ---
        try:
            page.screenshot(path=os.path.join(debug_dir, "step6_after_view.png"))
            log.info("→ Screenshot disimpan: debug/step6_after_view.png")
        except Exception:
            pass

        try:
            body = page.inner_text("body")
            log.info("→ Body text (500 char): %s", body[:500])
        except Exception:
            pass

        raise RuntimeError("Global API Key tidak ditemukan setelah verifikasi")

    def _extract_api_key_from_page(self, page: Page) -> Optional[str]:
        """Coba berbagai cara untuk ekstrak API key dari halaman/modal.

        Cloudflare Global API Key formatnya bisa:
        - Hex 37 char (format lama)
        - cfx_tk_... (format baru)
        - String alfanumerik lainnya
        """
        # 1. Cari input readonly, code, pre, span yang berisi key
        try:
            results = page.evaluate("""() => {
                const results = [];
                // Cari di input, code, pre, font-mono, span, div, p
                const selectors = 'input, [readonly], code, pre, .font-mono, span, div, p, textarea';
                document.querySelectorAll(selectors).forEach(el => {
                    const v = el.value || el.textContent || '';
                    const trimmed = v.trim();
                    // Hex 37 char (format lama)
                    if (trimmed.match(/^[a-f0-9]{37}$/)) results.push(trimmed);
                    // cfx_tk_ prefix (format baru)
                    if (trimmed.match(/^cfx_tk_[A-Za-z0-9]+$/)) results.push(trimmed);
                    // String alfanumerik 40+ char (API key generic)
                    if (trimmed.match(/^[A-Za-z0-9_-]{40,}$/) && trimmed.length < 100) {
                        results.push(trimmed);
                    }
                });
                return results;
            }""")
            if results:
                return results[0]
        except Exception:
            pass

        # 2. Cari di seluruh body text dengan regex
        try:
            body_text = page.inner_text("body")
            # Cari hex 37 char
            m = re.search(r"\b([a-f0-9]{37})\b", body_text)
            if m:
                return m.group(1)
            # Cari cfx_tk_ pattern
            m = re.search(r"(cfx_tk_[A-Za-z0-9]+)", body_text)
            if m:
                return m.group(1)
            # Cari string 40-60 char alfanumerik
            m = re.search(r"\b([A-Za-z0-9_-]{40,60})\b", body_text)
            if m:
                return m.group(1)
        except Exception:
            pass

        return None

    # ------------------------------------------------------------------
    def step7_get_account_id(self, page: Page) -> str:
        """Ambil Account ID dari URL dashboard atau halaman."""
        log.info("═══ Step 7: Ambil Account ID ═══")

        # Coba dari URL
        for _ in range(3):
            url = page.url
            aid = extract_account_id_from_url(url)
            if aid:
                self.account_id = aid
                log.info("✓ Account ID (URL): %s", aid)
                return aid
            page.wait_for_timeout(2000)

        # Coba dari halaman (sidebar "Account details")
        try:
            body_text = page.inner_text("body")
            # Account ID pattern: 32 hex chars
            m = re.search(r"Account ID[:\s]*([a-f0-9]{20,})", body_text, re.IGNORECASE)
            if m:
                self.account_id = m.group(1)
                log.info("✓ Account ID (page): %s", m.group(1))
                return m.group(1)
        except Exception:
            pass

        # Fallback: via API
        if self.global_api_key:
            acct = cf_api_get_accounts(self.cf_email, self.global_api_key)
            if acct:
                self.account_id = acct["id"]
                log.info("✓ Account ID (API): %s", acct["id"])
                return acct["id"]

        raise RuntimeError("Account ID tidak ditemukan")

    # ------------------------------------------------------------------
    def run(self) -> dict:
        """Jalankan seluruh automation flow."""
        # Step 1: Temp mail
        self.step1_create_temp_email()

        # Launch Camoufox
        log.info("═══ Launch Camoufox ═══")
        launch_kwargs = {
            "headless": self.headless,
            "humanize": True,
            "disable_coop": True,
            "geoip": True,
            "exclude_addons": [DefaultAddons.UBO],
            "i_know_what_im_doing": True,
        }
        if self.proxy:
            launch_kwargs["proxy"] = {"server": self.proxy}

        with Camoufox(**launch_kwargs) as browser:
            page = browser.new_page()
            page.set_default_timeout(30000)

            # Step 2: Signup
            self.step2_signup_cloudflare(page)

            # Step 3: Trigger verifikasi via Workers & Pages
            self.step3_trigger_verification(page)

            # Step 3b: Buka tab mail.tm untuk monitoring
            mail_page = self.step3b_open_mail_tab(browser)

            # Step 4: Verifikasi email di tab baru (tab 3)
            self.step4_verify_email_new_tab(page, browser)

            # Step 5: Navigasi ke API tokens
            self.step5_navigate_to_api_tokens(page)

            # Step 6: Global API Key
            self.step6_get_global_api_key(page)

            # Step 7: Account ID
            self.step7_get_account_id(page)

        # Simpan hasil
        result = {
            "email": self.cf_email,
            "password": self.cf_password,
            "global_api_key": self.global_api_key,
            "account_id": self.account_id,
            "mail_password": self.mail_account.password if self.mail_account else None,
        }

        # Simpan ke file
        out_file = "cf_accounts.json"
        accounts = []
        if os.path.exists(out_file):
            try:
                with open(out_file) as f:
                    accounts = json.load(f)
            except (json.JSONDecodeError, IOError):
                accounts = []
        accounts.append(result)
        with open(out_file, "w") as f:
            json.dump(accounts, f, indent=2)

        log.info("═══ SELESAI ═══")
        log.info("Email      : %s", self.cf_email)
        log.info("Password   : %s", self.cf_password)
        log.info("API Key    : %s", self.global_api_key)
        log.info("Account ID : %s", self.account_id)
        log.info("Disimpan ke: %s", os.path.abspath(out_file))
        return result


# ---------------------------------------------------------------------------
# Cloudflare API helper
# ---------------------------------------------------------------------------
def cf_api_get_accounts(email: str, global_api_key: str) -> Optional[dict]:
    """Ambil daftar account via Cloudflare API menggunakan Global API Key."""
    import requests
    headers = {
        "X-Auth-Email": email,
        "X-Auth-Key": global_api_key,
        "Content-Type": "application/json",
    }
    r = requests.get(f"{CF_API_BASE}/accounts", headers=headers, timeout=20)
    if r.status_code == 200:
        data = r.json()
        if data.get("success"):
            accounts = data.get("result", [])
            if accounts:
                return accounts[0]
    log.error("CF API error: %s %s", r.status_code, r.text[:300])
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Automation signup Cloudflare + temp mail (mail.tm) dengan Camoufox")
    parser.add_argument("--headless", action="store_true",
                        help="Jalankan browser headless (WARNING: di Windows bisa crash "
                             "GPU, lebih disarankan headed mode)")
    parser.add_argument("--proxy", type=str, default=None,
                        help="Proxy untuk browser (socks5://host:port atau http://...)")
    parser.add_argument("--mail-proxy", type=str, default=None,
                        help="Proxy untuk mail.tm API")
    args = parser.parse_args()

    auto = CloudflareAutomation(headless=args.headless, proxy=args.proxy,
                                mail_proxy=args.mail_proxy)
    try:
        result = auto.run()
        print("\n" + "=" * 60)
        print("✓ AUTOMATION BERHASIL")
        print("=" * 60)
        print(f"  Email          : {result['email']}")
        print(f"  Password       : {result['password']}")
        print(f"  Global API Key : {result['global_api_key']}")
        print(f"  Account ID     : {result['account_id']}")
        print("=" * 60)
    except Exception as e:
        log.error("✗ Automation gagal: %s", e, exc_info=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
