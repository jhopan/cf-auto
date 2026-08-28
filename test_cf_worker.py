"""
test_cf_worker.py — End-to-end test: signup CF + verify email + deploy Hello World worker

Flow:
  1. Buat inbox di temp mail self-hosted (renunganbot.qzz.io)
  2. Signup Cloudflare dengan Camoufox (headed, Turnstile manual/auto)
  3. Buka workers-and-pages untuk trigger email verifikasi
  4. Tunggu email verifikasi via /wait endpoint (blocking)
  5. Buka link verifikasi di tab baru (login otomatis karena session shared)
  6. Navigasi ke profile/api-tokens
  7. Klik "View" di Global API Key
  8. Modal "Verify Your Identity" → Send Verification Code
  9. Tunggu email kode 7-digit via /wait endpoint
 10. Masukkan kode, solve Turnstile, klik View
 11. Copy API key
 12. Deploy Hello World worker via Cloudflare API
"""
from __future__ import annotations
import json
import os
import re
import time
import random
import string
import logging
import argparse
from typing import Optional

import requests
from camoufox.sync_api import Camoufox
from camoufox import DefaultAddons

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("cf_test")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MAIL_BASE = "https://tempmail.renunganbot.qzz.io"
MAIL_API_KEY = "e763e811971502063b94be13707b3d9990c921493a7234469293c73bc289176f"
MAIL_DOMAIN = "renunganbot.qzz.io"

SIGNUP_URL = "https://dash.cloudflare.com/sign-up"
API_TOKENS_URL = "https://dash.cloudflare.com/profile/api-tokens"
CF_API_BASE = "https://api.cloudflare.com/client/v4"

SEL_EMAIL = ['input[name="email"]', 'input[type="email"]']
SEL_PASSWORD = ['input[name="password"]', 'input[type="password"]']
SEL_SIGNUP_BTN = ['button[type="submit"]:has-text("Sign up")', 'button:has-text("Sign up")']


# ---------------------------------------------------------------------------
# TempMail API client
# ---------------------------------------------------------------------------
class TempMailAPI:
    """Client untuk TempMailByJhopanstore API."""

    def __init__(self, base_url: str = MAIL_BASE, api_key: str = MAIL_API_KEY,
                 domain: str = MAIL_DOMAIN):
        self.base = base_url
        self.headers = {"X-Email-API-Key": api_key, "Content-Type": "application/json"}
        self.domain = domain

    def create_inbox(self, username: Optional[str] = None) -> dict:
        """Buat inbox. Return dict dengan email, inbox_id, dll."""
        payload = {"domain": self.domain}
        if username:
            payload["username"] = username
        r = requests.post(f"{self.base}/api/inbox", headers=self.headers,
                          json=payload, timeout=15)
        r.raise_for_status()
        return r.json()

    def wait_for_email(self, email: str, timeout: int = 120) -> dict:
        """Block sampai email masuk. Return message dict dengan codes & links."""
        log.info("⏳ Menunggu email masuk di %s (timeout %ds)...", email, timeout)
        r = requests.get(
            f"{self.base}/api/inbox/{email}/wait",
            headers=self.headers,
            timeout=timeout + 10,
            params={"timeout": timeout},
        )
        if r.status_code == 404:
            raise TimeoutError("Tidak ada email masuk")
        r.raise_for_status()
        data = r.json()
        log.info("✓ Email diterima: %s", data.get("subject", ""))
        return data

    def list_messages(self, email: str) -> list:
        """List semua pesan di inbox."""
        r = requests.get(f"{self.base}/api/inbox/{email}",
                         headers=self.headers, timeout=15)
        r.raise_for_status()
        return r.json().get("data", [])

    def delete_inbox(self, email: str) -> None:
        """Hapus semua pesan di inbox."""
        requests.delete(f"{self.base}/api/inbox/{email}",
                        headers=self.headers, timeout=15)

    def get_message(self, msg_id: int) -> dict:
        """Ambil detail pesan."""
        r = requests.get(f"{self.base}/api/message/{msg_id}",
                         headers=self.headers, timeout=15)
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def random_password() -> str:
    upper = random.choices(string.ascii_uppercase, k=3)
    lower = random.choices(string.ascii_lowercase, k=6)
    digit = random.choices(string.digits, k=3)
    special = random.choices("!@#$%^&*", k=2)
    pwd = upper + lower + digit + special
    random.shuffle(pwd)
    return "".join(pwd)


def fill_input(page, selectors, value, timeout=15000):
    for sel in selectors:
        try:
            el = page.wait_for_selector(sel, timeout=timeout, state="visible")
            if el:
                el.click(timeout=5000)
                el.fill(value)
                return True
        except Exception:
            continue
    return False


def wait_and_click(page, selectors, timeout=15000, force=False):
    for sel in selectors:
        try:
            el = page.wait_for_selector(sel, timeout=timeout, state="visible")
            if el:
                el.click(force=force, timeout=10000)
                return True
        except Exception:
            continue
    return False


def dismiss_cookie_banner(page):
    try:
        page.evaluate("""() => {
            const btn = document.querySelector('#onetrust-reject-all-handler, .ot-pc-refuse-all-handler');
            if (btn) btn.click();
            const ot = document.querySelector('#onetrust-banner-sdk');
            if (ot) ot.style.display = 'none';
        }""")
    except Exception:
        pass


def wait_for_turnstile(page, timeout=90):
    """Tunggu & solve Turnstile."""
    log.info("⏳ Menunggu Turnstile solve...")
    deadline = time.time() + timeout
    try:
        page.wait_for_selector('iframe[src*="challenges.cloudflare.com"]',
                              timeout=10000, state="attached")
    except Exception:
        pass

    while time.time() < deadline:
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

        # Strategy: frame_locator
        try:
            ts_frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
            for sel in ['input[type="checkbox"]', '[role="checkbox"]', 'label', '.cb-lb']:
                try:
                    loc = ts_frame.locator(sel).first
                    if loc.count() > 0 and loc.is_visible(timeout=2000):
                        loc.click(timeout=5000)
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

        # Strategy: coordinate click
        try:
            for frame in page.frames:
                if "challenges.cloudflare.com" in (frame.url or ""):
                    for coord in [{"x": 28, "y": 28}, {"x": 20, "y": 20},
                                  {"x": 35, "y": 35}, {"x": 15, "y": 15}]:
                        try:
                            frame.click("body", timeout=2000, position=coord)
                            page.wait_for_timeout(5000)
                            val = page.evaluate("""() => {
                                const el = document.querySelector('input[name="cf_challenge_response"]');
                                return el ? el.value : null;
                            }""")
                            if val and len(val) > 20:
                                log.info("✓ Turnstile solved via coordinate")
                                return True
                            break
                        except Exception:
                            continue
                    break
        except Exception:
            pass

        time.sleep(3)
    return False


def extract_account_id_from_url(url: str) -> Optional[str]:
    m = re.search(r"dash\.cloudflare\.com/([a-f0-9]{32})", url)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Cloudflare API client
# ---------------------------------------------------------------------------
def cf_verify_token(api_key: str) -> bool:
    """Verify Cloudflare API token."""
    r = requests.get(f"{CF_API_BASE}/user/tokens/verify",
                     headers={"Authorization": f"Bearer {api_key}"}, timeout=15)
    if r.status_code == 200:
        data = r.json()
        return data.get("success") and data.get("result", {}).get("status") == "active"
    return False


def cf_list_accounts(api_key: str) -> list:
    """List accounts yang bisa diakses token."""
    r = requests.get(f"{CF_API_BASE}/accounts",
                     headers={"Authorization": f"Bearer {api_key}"}, timeout=15)
    if r.status_code == 200:
        return r.json().get("result", [])
    return []


def cf_deploy_hello_world_worker(api_key: str, account_id: str,
                                 worker_name: str = "hello-world-test") -> dict:
    """Deploy Hello World worker via Cloudflare API."""
    worker_script = """
export default {
  async fetch(request, env, ctx) {
    return new Response("Hello World from Cloudflare Workers! 🎉", {
      headers: { "content-type": "text/plain" },
    });
  },
};
""".strip()

    url = f"{CF_API_BASE}/accounts/{account_id}/workers/scripts/{worker_name}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/javascript",
    }
    r = requests.put(url, headers=headers, data=worker_script, timeout=30)
    if r.status_code in (200, 200):
        log.info("✓ Worker '%s' berhasil di-deploy!", worker_name)
        return r.json()
    else:
        log.error("✗ Deploy worker gagal: %s %s", r.status_code, r.text[:300])
        return {}


def cf_get_worker_subdomain(api_key: str, account_id: str) -> Optional[str]:
    """Get workers.dev subdomain."""
    r = requests.get(f"{CF_API_BASE}/accounts/{account_id}/workers/subdomain",
                     headers={"Authorization": f"Bearer {api_key}"}, timeout=15)
    if r.status_code == 200:
        return r.json().get("result", {}).get("subdomain")
    return None


def cf_enable_worker_route(api_key: str, account_id: str, worker_name: str) -> bool:
    """Enable workers.dev route for worker."""
    subdomain = cf_get_worker_subdomain(api_key, account_id)
    if not subdomain:
        log.warning("⚠ Tidak ada workers.dev subdomain")
        return False
    url = f"https://{worker_name}.{subdomain}.workers.dev"
    log.info("✓ Worker URL: %s", url)
    return True


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Test CF signup + worker deploy")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    mail = TempMailAPI()

    # === Step 1: Buat inbox ===
    log.info("═══ Step 1: Buat temp mail inbox ═══")
    username = "cf" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    inbox = mail.create_inbox(username=username)
    cf_email = inbox["email"]
    cf_password = random_password()
    log.info("✓ Email    : %s", cf_email)
    log.info("✓ Password : %s", cf_password)

    # === Step 2: Signup Cloudflare ===
    log.info("═══ Step 2: Signup Cloudflare ═══")
    with Camoufox(
        headless=args.headless,
        humanize=True,
        disable_coop=True,
        geoip=True,
        exclude_addons=[DefaultAddons.UBO],
        i_know_what_im_doing=True,
    ) as browser:
        page = browser.new_page()
        page.set_default_timeout(30000)

        page.goto(SIGNUP_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        dismiss_cookie_banner(page)

        fill_input(page, SEL_EMAIL, cf_email, timeout=15000)
        log.info("✓ Email terisi")
        fill_input(page, SEL_PASSWORD, cf_password, timeout=10000)
        log.info("✓ Password terisi")

        try:
            page.uncheck('input[type="checkbox"]', timeout=3000)
        except Exception:
            pass

        solved = wait_for_turnstile(page, timeout=90)
        if not solved:
            log.warning("⚠ Turnstile belum solved otomatis! Klik manual di browser...")
            try:
                page.wait_for_function(
                    """() => {
                        const el = document.querySelector('input[name="cf_challenge_response"]');
                        return el && el.value && el.value.length > 20;
                    }""",
                    timeout=120000,
                )
                log.info("✓ Turnstile solved (manual)")
            except Exception:
                log.error("✗ Turnstile tidak solved dalam 2 menit")
                return

        page.wait_for_timeout(1000)
        wait_and_click(page, SEL_SIGNUP_BTN, timeout=10000, force=True)
        log.info("✓ Tombol Sign up diklik")
        page.wait_for_timeout(8000)
        log.info("  URL: %s", page.url)

        # === Step 3: Trigger verifikasi via workers-and-pages ===
        log.info("═══ Step 3: Trigger verifikasi ═══")
        aid = extract_account_id_from_url(page.url)
        if not aid:
            for _ in range(5):
                page.wait_for_timeout(2000)
                aid = extract_account_id_from_url(page.url)
                if aid:
                    break

        if aid:
            log.info("✓ Account ID: %s", aid)
            workers_url = f"https://dash.cloudflare.com/{aid}/workers-and-pages"
            # Retry navigasi karena NS_BINDING_ABORTED bisa terjadi
            for attempt in range(3):
                try:
                    page.goto(workers_url, wait_until="domcontentloaded", timeout=60000)
                    break
                except Exception as e:
                    log.warning("⚠ Navigasi gagal (attempt %d): %s", attempt + 1, str(e)[:80])
                    page.wait_for_timeout(3000)
            page.wait_for_timeout(5000)
            log.info("  URL: %s", page.url)
        else:
            log.error("✗ Account ID tidak ditemukan di URL")
            return

        # Klik Resend email jika ada
        wait_and_click(page, ['button:has-text("Resend email")',
                              'button:has-text("Resend")'], timeout=5000, force=True)
        page.wait_for_timeout(2000)

        # === Step 4: Tunggu email verifikasi ===
        log.info("═══ Step 4: Tunggu email verifikasi ═══")
        msg = mail.wait_for_email(cf_email, timeout=120)
        log.info("✓ From   : %s", msg.get("from", ""))
        log.info("✓ Subject: %s", msg.get("subject", ""))

        # Ambil link verifikasi
        links = msg.get("links", [])
        verify_link = None
        for l in links:
            if "developers.cloudflare.com" not in l.lower() and "cloudflare.com" in l.lower():
                verify_link = l
                break
        if not verify_link and links:
            verify_link = links[0]

        if not verify_link:
            log.error("✗ Link verifikasi tidak ditemukan")
            log.info("  Links: %s", links)
            return

        log.info("✓ Link verifikasi: %s", verify_link[:100])

        # === Step 5: Verifikasi email di TAB YANG SAMA (page utama) ===
        # JANGAN buka tab baru! Pakai page yang sama dengan signup,
        # karena session cookie sudah ada → Cloudflare langsung verifikasi.
        log.info("═══ Step 5: Verifikasi email di tab yang sama ═══")

        # Simpan URL dashboard untuk kembali nanti
        dashboard_url = page.url
        log.info("  Dashboard URL: %s", dashboard_url)

        # Buka link verifikasi di tab yang SAMA
        page.goto(verify_link, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        log.info("  URL setelah buka verify link: %s", page.url)

        # Jika redirect ke login, isi email+password
        if "/login" in page.url:
            log.info("→ Redirect ke login, isi credentials...")
            dismiss_cookie_banner(page)

            # Isi email - coba berbagai selector
            email_filled = False
            for esel in ['input[name="email"]', 'input[type="email"]',
                         'input[placeholder*="mail" i]', 'input[autocomplete*="email"]']:
                try:
                    el = page.wait_for_selector(esel, timeout=5000, state="visible")
                    if el:
                        el.click(timeout=3000)
                        el.fill(cf_email, timeout=5000)
                        email_filled = True
                        log.info("✓ Email terisi (%s)", esel)
                        break
                except Exception:
                    continue

            if not email_filled:
                page.evaluate(f"""() => {{
                    const el = document.querySelector('input[type="email"], input[name="email"]');
                    if (el) {{ el.focus(); }}
                }}""")
                page.keyboard.type(cf_email, delay=50)
                log.info("→ Email diketik via keyboard")

            # Isi password
            for psel in ['input[name="password"]', 'input[type="password"]']:
                try:
                    el = page.wait_for_selector(psel, timeout=5000, state="visible")
                    if el:
                        el.click(timeout=3000)
                        el.fill(cf_password, timeout=5000)
                        log.info("✓ Password terisi")
                        break
                except Exception:
                    continue

            page.wait_for_timeout(1000)

            # Klik tombol submit - "Continue with password" atau "Sign in"
            # JANGAN klik "Continue with SSO"
            login_clicked = False
            for bsel in ['button:has-text("Continue with password")',
                         'button:has-text("Sign in")',
                         'button:has-text("Continue")',
                         'button[type="submit"]']:
                try:
                    el = page.wait_for_selector(bsel, timeout=5000, state="visible")
                    if el:
                        txt = el.text_content() or ""
                        if "sso" in txt.lower():
                            log.info("→ Skip SSO button: %s", txt)
                            continue
                        el.click(force=True, timeout=5000)
                        login_clicked = True
                        log.info("✓ Login diklik (%s)", bsel)
                        break
                except Exception:
                    continue

            if not login_clicked:
                page.keyboard.press("Enter")
                log.info("→ Enter ditekan")

            page.wait_for_timeout(5000)
            log.info("  URL setelah login: %s", page.url)

        # Klik Verify/Continue jika ada
        for sel in ['a:has-text("Verify your email")',
                     'button:has-text("Verify your email")',
                     'button:has-text("Verify")',
                     'a:has-text("Verify")',
                     'button:has-text("Continue")',
                     'a:has-text("Continue")']:
            try:
                el = page.wait_for_selector(sel, timeout=5000, state="visible")
                if el:
                    el.click(force=True, timeout=5000)
                    log.info("✓ Verify diklik (%s)", sel)
                    break
            except Exception:
                continue

        page.wait_for_timeout(5000)
        log.info("  URL setelah verify: %s", page.url)

        # Cek apakah verifikasi berhasil
        try:
            body_text = page.inner_text("body")
            if "verified" in body_text.lower() or "success" in body_text.lower():
                log.info("✓✓✓ VERIFIKASI BERHASIL! ✓✓✓")
            else:
                log.warning("⚠ Status verifikasi tidak diketahui")
        except Exception:
            pass

        # === Step 6: Navigasi ke API Tokens ===
        log.info("═══ Step 6: Navigasi ke API Tokens ═══")
        page.goto(API_TOKENS_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        dismiss_cookie_banner(page)
        log.info("  URL: %s", page.url)

        # === Step 7: Klik View di Global API Key ===
        log.info("═══ Step 7: Ambil Global API Key ═══")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(2000)

        wait_and_click(page, ['button:has-text("View")',
                              'a:has-text("View")'], timeout=15000, force=True)
        page.wait_for_timeout(3000)

        # Modal "Verify Your Identity" → Send Verification Code
        log.info("→ Menunggu modal 'Verify Your Identity'...")
        wait_and_click(page, ['button:has-text("Send Verification Code")',
                              'button:has-text("Send")'], timeout=15000, force=True)
        page.wait_for_timeout(3000)
        log.info("✓ Verification code dikirim ke email")

        # === Step 8: Tunggu email kode 7-digit ===
        log.info("═══ Step 8: Tunggu email kode verifikasi ═══")
        # Hapus inbox lama dulu agar dapat email baru (kode 7-digit)
        mail.delete_inbox(cf_email)
        log.info("✓ Inbox lama dibersihkan")
        page.wait_for_timeout(2000)

        # Tunggu email baru (kode verifikasi)
        code_msg = mail.wait_for_email(cf_email, timeout=120)
        codes = code_msg.get("codes", [])
        code = codes[0] if codes else None
        if not code:
            text = code_msg.get("text_body", "")
            m = re.search(r"\b(\d{7})\b", text)
            code = m.group(1) if m else None
        if not code:
            log.error("✗ Kode 7-digit tidak ditemukan")
            log.info("  Codes: %s", codes)
            log.info("  Text: %s", code_msg.get("text_body", "")[:200])
            return

        log.info("✓ Kode verifikasi: %s", code)

        # === Step 9: Masukkan kode + solve Turnstile + klik View ===
        log.info("═══ Step 9: Input kode + Turnstile + View ═══")

        # Tunggu modal "Your API Key" muncul
        for modal_sel in ['[data-testid*="modal"]', '[role="dialog"]',
                          '[aria-modal="true"]', '.modal']:
            try:
                page.wait_for_selector(modal_sel, timeout=10000, state="visible")
                log.info("✓ Modal terdeteksi: %s", modal_sel)
                break
            except Exception:
                continue

        # Isi kode via Playwright fill (bukan JS, agar React detect)
        code_filled = False
        for sel in ['[data-testid*="modal"] input[name="code"]',
                     '[role="dialog"] input[name="code"]',
                     'input[name="code"]',
                     '[data-testid*="modal"] input[placeholder*="code" i]',
                     '[role="dialog"] input[placeholder*="Verify" i]']:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible(timeout=3000):
                    loc.click(timeout=3000)
                    loc.fill(code, timeout=5000)
                    code_filled = True
                    log.info("✓ Kode dimasukkan (%s)", sel)
                    break
            except Exception:
                continue

        if not code_filled:
            # Fallback: keyboard type
            page.evaluate("""() => {
                const modal = document.querySelector('[data-testid*="modal"], [role="dialog"]');
                if (modal) {
                    const inp = modal.querySelector('input[type="text"], input:not([type])');
                    if (inp && !inp.name?.includes('search')) inp.focus();
                }
            }""")
            page.wait_for_timeout(500)
            page.keyboard.type(code, delay=50)
            log.info("✓ Kode diketik via keyboard")

        page.wait_for_timeout(1000)

        # Solve Turnstile di modal
        solved = wait_for_turnstile(page, timeout=90)
        if not solved:
            log.warning("⚠ Turnstile modal belum solved, klik manual...")
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
                log.error("✗ Turnstile modal tidak solved")
                return

        # Klik "View" di DALAM modal
        # query_selector tidak support :has-text, pakai locator
        page.wait_for_timeout(1000)
        view_clicked = False
        for modal_sel in ['[data-testid*="modal"]', '[role="dialog"]',
                          '[aria-modal="true"]', '.modal']:
            try:
                loc = page.locator(f'{modal_sel} >> button:has-text("View")').first
                if loc.count() > 0:
                    loc.click(force=True, timeout=5000)
                    view_clicked = True
                    log.info("✓ Klik View di modal (%s)", modal_sel)
                    break
            except Exception:
                continue
        if not view_clicked:
            # Fallback: cari semua tombol, klik yang di modal
            try:
                btns = page.locator('button:has-text("View")')
                cnt = btns.count()
                if cnt > 1:
                    btns.nth(cnt - 1).click(force=True, timeout=5000)
                    view_clicked = True
                    log.info("✓ Klik View terakhir (modal, %d total)", cnt)
                elif cnt == 1:
                    btns.first.click(force=True, timeout=5000)
                    view_clicked = True
                    log.info("→ Klik View (1 ditemukan)")
            except Exception:
                pass
        if not view_clicked:
            page.evaluate("""() => {
                const m = document.querySelector('[data-testid*="modal"], [role="dialog"]');
                if (m) { const b = Array.from(m.querySelectorAll('button')).find(b => b.textContent.includes('View')); if (b) b.click(); }
            }""")
            log.info("→ Klik View via JS")

        # Tunggu API key muncul
        log.info("→ Menunggu API key muncul...")
        api_key = None
        deadline = time.time() + 30
        while time.time() < deadline:
            page.wait_for_timeout(500)
            try:
                results = page.evaluate("""() => {
                    const results = [];
                    document.querySelectorAll('input, code, pre, .font-mono, span, div, p, textarea').forEach(el => {
                        const v = (el.value || el.textContent || '').trim();
                        if (v.match(/^[a-f0-9]{37}$/)) results.push(v);
                        if (v.match(/^cfx_tk_[A-Za-z0-9]+$/)) results.push(v);
                        if (v.match(/^[A-Za-z0-9_-]{40,60}$/) && v.length < 100) results.push(v);
                    });
                    return results;
                }""")
                if results:
                    api_key = results[0]
                    break
            except Exception:
                pass

        if not api_key:
            log.error("✗ Global API Key tidak ditemukan")
            # Debug
            try:
                debug_dir = os.path.join(os.path.dirname(__file__), "debug")
                os.makedirs(debug_dir, exist_ok=True)
                page.screenshot(path=os.path.join(debug_dir, "step9_after_view.png"))
                body = page.inner_text("body")
                log.info("→ Body: %s", body[:300])
            except Exception:
                pass
            return

        log.info("✓✓✓ Global API Key: %s ✓✓✓", api_key[:8] + "..." + api_key[-4:])

        # === Step 10: Deploy Hello World Worker ===
        log.info("═══ Step 10: Deploy Hello World Worker ═══")

        # Verify token
        if cf_verify_token(api_key):
            log.info("✓ Token valid")
        else:
            log.warning("⚠ Token tidak valid via verify endpoint")

        # List accounts
        accounts = cf_list_accounts(api_key)
        if accounts:
            account_id = accounts[0]["id"]
            log.info("✓ Account ID (API): %s", account_id)
        elif aid:
            account_id = aid
            log.info("→ Pakai Account ID dari URL: %s", account_id)
        else:
            log.error("✗ Tidak dapat account ID")
            return

        # Deploy worker
        worker_name = "hello-world-" + "".join(random.choices(string.digits, k=4))
        result = cf_deploy_hello_world_worker(api_key, account_id, worker_name)
        if result:
            log.info("✓✓✓ WORKER DEPLOYED! ✓✓✓")
            log.info("  Name: %s", worker_name)

            # Get workers.dev subdomain
            subdomain = cf_get_worker_subdomain(api_key, account_id)
            if subdomain:
                worker_url = f"https://{worker_name}.{subdomain}.workers.dev"
                log.info("  URL : %s", worker_url)

                # Test worker
                import time as _time
                _time.sleep(3)
                try:
                    r = requests.get(worker_url, timeout=15)
                    log.info("  Test: %s → %s", r.status_code, r.text[:100])
                except Exception as e:
                    log.warning("⚠ Worker belum siap atau URL tidak aktif: %s", e)
            else:
                log.info("  (subdomain workers.dev belum diset)")
        else:
            log.error("✗ Deploy worker gagal")

        # Simpan hasil
        result_data = {
            "email": cf_email,
            "password": cf_password,
            "global_api_key": api_key,
            "account_id": account_id,
            "worker_name": worker_name,
        }
        with open("test_result.json", "w") as f:
            json.dump(result_data, f, indent=2)
        log.info("✓ Hasil disimpan: test_result.json")

        # Cleanup inbox
        mail.delete_inbox(cf_email)
        log.info("✓ Inbox dibersihkan")

        log.info("═══ SELESAI ═══")
        log.info("Email      : %s", cf_email)
        log.info("Password   : %s", cf_password)
        log.info("API Key    : %s", api_key[:8] + "..." + api_key[-4:])
        log.info("Account ID : %s", account_id)
        log.info("Worker     : %s", worker_name)


if __name__ == "__main__":
    main()
