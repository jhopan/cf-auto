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

        # Reset code: URL email berisi full code di query string.
        # PENTING: code valid = FULL value param 'code' (bisa 100+ char hex-dash)
        import re as _re
        from urllib.parse import urlparse, parse_qs

        reset_code = None
        reset_url = None

        for l in msg.get("links", []):
            if "password-reset" not in l:
                continue
            try:
                qs = parse_qs(urlparse(l).query)
                if "code" in qs and qs["code"]:
                    reset_code = qs["code"][0]
                    reset_url = l
                    break
            except Exception:
                continue

        # Fallback: regex longgar ambil SEMUA char setelah code= sampai
        # karakter non-url (spasi, ", <, >)
        if not reset_code:
            for l in msg.get("links", []):
                if "password-reset" in l:
                    m = _re.search(r"password-reset\?code=([A-Za-z0-9\-_%]+)", l)
                    if m:
                        reset_code = m.group(1)
                        reset_url = l
                        break

        if not reset_code:
            log.error("✗ Reset code tidak ditemukan di email")
            log.info("  Links: %s", msg.get("links", [])[:2])
            return False

        log.info("✓ Reset code ditemukan (%d char): %s...", len(reset_code),
                 reset_code[:20])
        if reset_url:
            log.info("✓ URL reset dari email: %s", reset_url[:90])

        # ── Step D: Buka URL DARI EMAIL (code biasanya auto-terisi) ──
        page.goto(reset_url or "https://dash.cloudflare.com/password-reset",
                  wait_until="domcontentloaded", timeout=60000)
        time.sleep(5)
        log.info("  URL: %s", page.url[:90])

        # ── Step E: Cek apakah reset code auto-terisi ──
        # Kalau field kosong → isi manual dengan code dari URL email
        # (code = SEMUA char setelah 'code=' sampai habis)
        code_el = None
        for sel in ['input[name="code"]', 'input[placeholder*="code" i]',
                    '#reset-code', 'input[type="text"]']:
            try:
                el = page.wait_for_selector(sel, timeout=8000, state="visible")
                if el:
                    code_el = el
                    break
            except Exception:
                continue
        if not code_el:
            log.error("✗ Field reset code tidak ditemukan")
            return False

        current = (code_el.input_value() or "").strip()
        if current:
            log.info("✓ Reset code AUTO-terisi (%d char)", len(current))
        else:
            log.info("→ Code tidak auto-isi, isi manual dari URL email...")
            code_el.click(timeout=3000)
            code_el.fill(reset_code, timeout=5000)
            log.info("✓ Reset code diisi manual (%d char): %s...",
                     len(reset_code), reset_code[:20])
        code_ok = True

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
