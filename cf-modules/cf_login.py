"""
cf_login.py — Module 1b: Login ke akun Cloudflare yang sudah ada.

Dipakai sebagai fallback oleh cf_signup (email already exists),
atau standalone untuk akun lama.

Tanggung jawab:
  - Buka /login
  - Isi email + password
  - Klik Sign in (skip SSO)
  - Handle redirect / email verification
  - Return account_id
"""
from __future__ import annotations

import time

from playwright.sync_api import Page

try:
    from .cf_helpers import (
        log, dismiss_cookie_banner, fill_input, wait_and_click,
        extract_account_id_from_url, SEL_EMAIL, SEL_PASSWORD,
        wait_for_turnstile,
    )
except ImportError:
    from cf_helpers import (
        log, dismiss_cookie_banner, fill_input, wait_and_click,
        extract_account_id_from_url, SEL_EMAIL, SEL_PASSWORD,
        wait_for_turnstile,
    )

LOGIN_URL = "https://dash.cloudflare.com/login"

# Sinyal error login
WRONG_PASSWORD_SIGNS = [
    "incorrect email or password",
    "wrong email or password",
    "password is incorrect",
    "sandi salah",
    "kata sandi salah",
]


class CloudflareLogin:
    """Module 1b: Login Cloudflare (email + password)."""

    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password

    def run(self, page: Page) -> str | None:
        """Login. Return account_id kalau sukses, None kalau gagal."""
        log.info("═══ Module 1b: Login Cloudflare ═══")
        log.info("→ Email: %s", self.email)

        for attempt in range(3):
            try:
                page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
                break
            except Exception as e:
                log.warning("⚠ Navigasi login gagal (attempt %d): %s",
                            attempt + 1, str(e)[:60])
                time.sleep(5)

        time.sleep(4)
        dismiss_cookie_banner(page)

        # ── Isi email ──
        email_ok = False
        for esel in SEL_EMAIL:
            try:
                el = page.wait_for_selector(esel, timeout=10000, state="visible")
                if el:
                    el.click(timeout=3000)
                    el.fill(self.email, timeout=5000)
                    email_ok = True
                    log.info("✓ Email terisi (%s)", esel)
                    break
            except Exception:
                continue
        if not email_ok:
            log.error("✗ Field email tidak ditemukan")
            return None

        # ── Isi password ──
        time.sleep(1)
        pwd_ok = False
        for psel in SEL_PASSWORD:
            try:
                el = page.wait_for_selector(psel, timeout=10000, state="visible")
                if el:
                    el.click(timeout=3000)
                    el.fill(self.password, timeout=5000)
                    pwd_ok = True
                    log.info("✓ Password terisi")
                    break
            except Exception:
                continue
        if not pwd_ok:
            log.error("✗ Field password tidak ditemukan")
            return None

        # ── Klik Sign in (JANGAN SSO) ──
        time.sleep(1)
        clicked = False
        for bsel in [
            'button:has-text("Continue with password")',
            'button:has-text("Sign in")',
            'button:has-text("Log in")',
            'button[type="submit"]',
        ]:
            try:
                el = page.wait_for_selector(bsel, timeout=5000, state="visible")
                if el:
                    txt = (el.text_content() or "").lower()
                    if "sso" in txt or "google" in txt or "apple" in txt or "github" in txt:
                        continue
                    el.click(force=True, timeout=5000)
                    clicked = True
                    log.info("✓ Sign in diklik (%s)", bsel)
                    break
            except Exception:
                continue
        if not clicked:
            page.keyboard.press("Enter")
            log.info("→ Enter ditekan sebagai fallback")

        time.sleep(8)

        # ── Deteksi hasil ──
        body = ""
        try:
            body = page.inner_text("body").lower()
        except Exception:
            pass

        # Salah password?
        for sig in WRONG_PASSWORD_SIGNS:
            if sig in body:
                log.warning("⚠ Password salah untuk %s", self.email)
                return None

        # Email tidak ditemukan?
        if "couldn't find" in body or "no account" in body:
            log.warning("⚠ Akun tidak ditemukan: %s", self.email)
            return None

        # Tunggu redirect ke dashboard (mungkin perlu waktu)
        log.info("→ Menunggu redirect dashboard...")
        for _ in range(15):
            time.sleep(2)
            url = page.url
            aid = extract_account_id_from_url(url)
            if aid:
                log.info("✓✓✓ LOGIN BERHASIL ═══")
                log.info("  Account ID: %s", aid)
                return aid

        # Fallback: cari account_id dari page content
        try:
            aid = page.evaluate("""() => {
                const links = document.querySelectorAll('a[href*="/"]');
                for (const a of links) {
                    const m = a.href.match(/dash\\.cloudflare\\.com\\/([a-f0-9]{20,})/);
                    if (m) return m[1];
                }
                return null;
            }""")
            if aid:
                log.info("✓✓✓ LOGIN BERHASIL (from page) ═══")
                log.info("  Account ID: %s", aid)
                return aid
        except Exception:
            pass

        log.error("✗ Login gagal — tidak masuk dashboard")
        log.info("  URL: %s", page.url)
        return None
