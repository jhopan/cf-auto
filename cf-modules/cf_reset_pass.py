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

        # ── Step A: Buka login → Forgot password ──
        for attempt in range(3):
            try:
                page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
                break
            except Exception as e:
                log.warning("⚠ Navigasi gagal (attempt %d): %s",
                            attempt + 1, str(e)[:60])
                time.sleep(5)

        time.sleep(4)
        dismiss_cookie_banner(page)

        # Isi email dulu
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
            log.error("✗ Field email tidak ditemukan")
            return False

        # Klik "Forgot password?"
        forgot_clicked = False
        for sel in [
            'a:has-text("Forgot password")',
            'a:has-text("Forgot your password")',
            'button:has-text("Forgot password")',
            'a[href*="forgot"]',
        ]:
            try:
                el = page.wait_for_selector(sel, timeout=5000, state="visible")
                if el:
                    el.click(force=True, timeout=5000)
                    forgot_clicked = True
                    log.info("✓ Forgot password diklik (%s)", sel)
                    break
            except Exception:
                continue
        if not forgot_clicked:
            log.error("✗ Link Forgot password tidak ditemukan")
            return False

        time.sleep(4)

        # ── Step B: Halaman forgot — isi email + kirim ──
        # Email mungkin sudah terisi (dibawa dari halaman login)
        try:
            el = page.wait_for_selector(
                'input[name="email"], input[type="email"]',
                timeout=8000, state="visible",
            )
            if el:
                current = el.input_value() or ""
                if self.email.lower() not in current.lower():
                    el.click(timeout=3000)
                    el.fill(self.email, timeout=5000)
                log.info("✓ Email di halaman forgot: %s", el.input_value())
        except Exception:
            log.info("→ Field email tidak ada di halaman forgot (mungkin auto)")

        time.sleep(1)

        # Klik Email/Kirim/Continue
        sent = False
        for sel in [
            'button:has-text("Email me a reset link")',
            'button:has-text("Send reset link")',
            'button:has-text("Email me")',
            'button:has-text("Send")',
            'button:has-text("Continue")',
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

        # ── Step C: Tunggu email reset ──
        log.info("→ Menunggu email reset password...")
        try:
            msg = self.mail.wait_for_email(self.email, timeout=120)
        except Exception as e:
            log.error("✗ Email reset tidak datang: %s", str(e)[:80])
            return False

        log.info("✓ Subject: %s", msg.get("subject", ""))

        # Cari link reset
        reset_link = None
        links = msg.get("links", [])
        for l in links:
            low = l.lower()
            if ("password" in low or "reset" in low) and "cloudflare.com" in low:
                reset_link = l
                break
        if not reset_link and links:
            # fallback: link cloudflare pertama yang bukan dokumentasi
            for l in links:
                if "developers.cloudflare.com" not in l.lower():
                    reset_link = l
                    break
        if not reset_link:
            log.error("✗ Link reset tidak ditemukan di email")
            log.info("  Links: %s", links[:3])
            return False

        log.info("✓ Link reset: %s", reset_link[:80])

        # ── Step D: Buka link di TAB SAMA ──
        page.goto(reset_link, wait_until="domcontentloaded", timeout=60000)
        time.sleep(5)
        log.info("  URL: %s", page.url[:80])

        # ── Step E: Set password baru ──
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
            # Mungkin dua field (password + confirm)
            try:
                pwds = page.query_selector_all('input[type="password"]')
                if len(pwds) >= 2:
                    pwds[0].click()
                    pwds[0].fill(self.new_password)
                    pwds[1].click()
                    pwds[1].fill(self.new_password)
                    pwd_ok = True
                    log.info("✓ Password baru + confirm terisi")
            except Exception:
                pass
        if not pwd_ok:
            log.error("✗ Field password baru tidak ditemukan")
            return False

        time.sleep(1)

        # ── Step F: Submit ──
        submitted = False
        for sel in [
            'button:has-text("Save")',
            'button:has-text("Reset password")',
            'button:has-text("Set password")',
            'button:has-text("Change password")',
            'button[type="submit"]',
        ]:
            try:
                el = page.wait_for_selector(sel, timeout=4000, state="visible")
                if el:
                    el.click(force=True, timeout=5000)
                    submitted = True
                    log.info("✓ Submit password baru (%s)", sel)
                    break
            except Exception:
                continue
        if not submitted:
            page.keyboard.press("Enter")
            log.info("→ Enter ditekan")

        time.sleep(6)

        # Cek sukses
        try:
            body = page.inner_text("body").lower()
            if "success" in body or "password has been" in body or "updated" in body:
                log.info("✓✓✓ PASSWORD DIRESET ═══")
                return True
        except Exception:
            pass

        # Kalau redirect ke login/dashboard, anggap sukses
        url = page.url
        if "login" not in url or "password" not in body:
            log.info("✓ Password kemungkinan berhasil (URL: %s)", url[:60])
            return True

        log.warning("⚠ Status reset tidak jelas")
        return True  # optimis — coba login nanti akan buktikan
