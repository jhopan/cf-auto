"""
cf_reset_pass.py — Module 1c: Reset password akun Cloudflare via email.

Dipakai kalau login gagal (password salah/lupa) — CF kirim link reset
ke inbox temp mail, lalu set password baru.

Tanggung jawab:
  - Buka /login → klik "Forgot password?"
  - Isi email → kirim
  - Tunggu email reset dari temp mail
  - Buka link reset (TAB SAMA)
  - Set password baru
  - Return True/False
"""
from __future__ import annotations

import time

from playwright.sync_api import Page

try:
    from .cf_helpers import (
        log, dismiss_cookie_banner, SEL_EMAIL, SEL_PASSWORD,
    )
except ImportError:
    from cf_helpers import (
        log, dismiss_cookie_banner, SEL_EMAIL, SEL_PASSWORD,
    )

LOGIN_URL = "https://dash.cloudflare.com/login"


class CloudflareResetPassword:
    """Module 1c: Reset password via email link."""

    def __init__(self, email: str, new_password: str, mail):
        self.email = email
        self.new_password = new_password
        self.mail = mail

    def run(self, page: Page) -> bool:
        """Reset password. Return True kalau sukses."""
        log.info("═══ Module 1c: Reset Password ═══")
        log.info("→ Email: %s", self.email)

        # ── Step A: Langsung ke halaman forgot password ──
        FORGOT_URL = "https://dash.cloudflare.com/forgot-password"
        for attempt in range(3):
            try:
                page.goto(FORGOT_URL, wait_until="domcontentloaded", timeout=60000)
                break
            except Exception as e:
                log.warning("⚠ Navigasi gagal (attempt %d): %s",
                            attempt + 1, str(e)[:60])
                time.sleep(5)

        time.sleep(4)
        dismiss_cookie_banner(page)
        log.info("  URL: %s", page.url[:70])

        # ── Step B: Isi email + klik Send ──
        email_ok = False
        for esel in SEL_EMAIL:
            try:
                el = page.wait_for_selector(esel, timeout=10000, state="visible")
                if el:
                    el.click(timeout=3000)
                    el.fill(self.email, timeout=5000)
                    email_ok = True
                    log.info("✓ Email terisi")
                    break
            except Exception:
                continue
        if not email_ok:
            log.error("✗ Field email tidak ditemukan di halaman forgot")
            return False

        time.sleep(1)

        # Klik Send
        sent = False
        for sel in [
            'button:has-text("Send")',
            'button:has-text("Email me a reset link")',
            'button:has-text("Send reset link")',
            'button:has-text("Email me")',
            'button[type="submit"]',
        ]:
            try:
                el = page.wait_for_selector(sel, timeout=4000, state="visible")
                if el:
                    el.click(force=True, timeout=5000)
                    sent = True
                    log.info("✓ Kirim reset diklik (%s)", sel)
                    break
            except Exception:
                continue
        if not sent:
            page.keyboard.press("Enter")
            log.info("→ Enter ditekan")

        time.sleep(6)

        # ── Step C: Tunggu email reset → ambil RESET CODE ──
        log.info("→ Menunggu email reset password...")
        try:
            msg = self.mail.wait_for_email(self.email, timeout=120)
        except Exception as e:
            log.error("✗ Email reset tidak datang: %s", str(e)[:80])
            return False

        log.info("✓ Subject: %s", msg.get("subject", ""))

        # Reset code: dari URL dalam email (?code=...) ATAU dari body text
        import re as _re
        reset_code = None

        # Cari di URL link dulu (password-reset?code=...)
        for l in msg.get("links", []):
            m = _re.search(r"password-reset\?.*?code[=%]*([A-Za-z0-9\-]+)", l)
            if m:
                reset_code = m.group(1)
                break

        # Fallback: cari angka/kode di body text email
        if not reset_code:
            body_txt = msg.get("body", "") or msg.get("text", "")
            m = _re.search(r"\b(\d{6,8})\b", body_txt)
            if m:
                reset_code = m.group(1)

        if not reset_code:
            log.error("✗ Reset code tidak ditemukan di email")
            log.info("  Links: %s", msg.get("links", [])[:2])
            return False

        log.info("✓ Reset code: %s", reset_code)

        # ── Step D: Buka halaman password-reset ──
        page.goto("https://dash.cloudflare.com/password-reset",
                  wait_until="domcontentloaded", timeout=60000)
        time.sleep(5)
        log.info("  URL: %s", page.url[:80])

        # ── Step E: Isi RESET CODE dulu ──
        code_ok = False
        for sel in ['input[name="code"]', 'input[placeholder*="code"]',
                    '#reset-code', 'input[type="text"]']:
            try:
                el = page.wait_for_selector(sel, timeout=8000, state="visible")
                if el:
                    el.click(timeout=3000)
                    el.fill(reset_code, timeout=5000)
                    code_ok = True
                    log.info("✓ Reset code terisi (%s)", sel)
                    break
            except Exception:
                continue
        if not code_ok:
            log.error("✗ Field reset code tidak ditemukan")
            return False

        time.sleep(1)

        # ── Step F: Isi password baru ──
        pwd_ok = False
        for psel in SEL_PASSWORD:
            try:
                el = page.wait_for_selector(psel, timeout=10000, state="visible")
                if el:
                    el.click(timeout=3000)
                    el.fill(self.new_password, timeout=5000)
                    pwd_ok = True
                    log.info("✓ Password baru terisi")
                    break
            except Exception:
                continue
        if not pwd_ok:
            try:
                pwds = page.query_selector_all('input[type="password"]')
                if pwds:
                    pwds[0].click()
                    pwds[0].fill(self.new_password)
                    pwd_ok = True
                    log.info("✓ Password baru terisi (query_selector)")
            except Exception:
                pass
        if not pwd_ok:
            log.error("✗ Field password baru tidak ditemukan")
            return False

        time.sleep(1)

        # ── Step G: Klik Reset ──
        submitted = False
        for sel in [
            'button:has-text("Reset")',
            'button[type="submit"]',
        ]:
            try:
                el = page.wait_for_selector(sel, timeout=4000, state="visible")
                if el:
                    el.click(force=True, timeout=5000)
                    submitted = True
                    log.info("✓ Reset diklik (%s)", sel)
                    break
            except Exception:
                continue
        if not submitted:
            page.keyboard.press("Enter")
            log.info("→ Enter ditekan")

        time.sleep(8)

        # ── Step H: Cek sukses ──
        try:
            body = page.inner_text("body").lower()
            if ("success" in body or "password has been" in body
                    or "your password" in body and "reset" in body):
                log.info("✓✓✓ PASSWORD DIRESET ═══")
                return True
        except Exception:
            pass

        url = page.url
        if "password-reset" not in url:
            log.info("✓ Password berhasil (redirect ke: %s)", url[:60])
            return True

        log.warning("⚠ Status reset tidak jelas — anggap sukses, login akan buktikan")
        return True
