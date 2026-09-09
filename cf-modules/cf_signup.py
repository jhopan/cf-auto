"""
cf_signup.py — Module 1a: Signup Cloudflare + Solve Turnstile

Tanggung jawab:
  - Buka dash.cloudflare.com/sign-up
  - Isi email (via fill, bukan otomatisasi berlebihan)
  - Isi password
  - Selesaikan Turnstile sampai dapat token
  - Klik Sign up
  - DETEKSI "email already exists" → fallback ke cf_login / cf_reset_pass

TIDAK tanggung jawab:
  - Verifikasi email (module 2)
  - Ambil API key (module 3+)
"""
from __future__ import annotations
import logging
import time

from playwright.sync_api import Page

from cf_helpers import (
    log,
    SIGNUP_URL,
    SEL_EMAIL,
    SEL_PASSWORD,
    SEL_SIGNUP_BTN,
    random_password,
    fill_input,
    wait_and_click,
    wait_for_turnstile,
    dismiss_cookie_banner,
    extract_account_id_from_url,
)

__all__ = ["CloudflareSignup"]


class CloudflareSignup:
    """Module 1: Signup Cloudflare + Turnstile."""

    def __init__(self, email: str, password: str, mail=None):
        self.email = email
        self.password = password
        self.mail = mail  # untuk reset password fallback (optional)

    def run(self, page: Page) -> str | None:
        """Jalankan signup flow.

        Returns:
            account_id jika berhasil masuk dashboard, None jika gagal.
        """
        log.info("═══ Module 1: Signup Cloudflare ═══")

        # Buka halaman signup
        page.goto(SIGNUP_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3.0)
        dismiss_cookie_banner(page)

        # Isi email — pakai fill (simulasi keyboard)
        if not fill_input(page, SEL_EMAIL, self.email, timeout=15000):
            log.error("✗ Field email tidak ditemukan")
            return None
        log.info("✓ Email terisi: %s", self.email)

        # Isi password
        if not fill_input(page, SEL_PASSWORD, self.password, timeout=10000):
            log.error("✗ Field password tidak ditemukan")
            return None
        log.info("✓ Password terisi")

        # Uncheck "Save email" checkbox
        try:
            page.uncheck('input[type="checkbox"]', timeout=3000)
        except Exception:
            pass

        # --- Selesaikan Turnstile (KRITIS) ---
        solved = wait_for_turnstile(page, timeout=90)
        if not solved:
            log.warning("⚠ Turnstile belum solved otomatis, tunggu manual...")
            try:
                page.wait_for_function(
                    """() => {
                        const el = document.querySelector(
                            'input[name="cf_challenge_response"]'
                        );
                        return el && el.value && el.value.length > 20;
                    }""",
                    timeout=120000,
                )
                log.info("✓ Turnstile solved (manual)")
            except Exception:
                log.error("✗ Turnstile tidak solved dalam 2 menit")
                return None

        # Klik Sign up
        time.sleep(1.0)
        if not wait_and_click(page, SEL_SIGNUP_BTN, timeout=10000, force=True):
            page.keyboard.press("Enter")
        log.info("✓ Tombol Sign up diklik")

        # Tunggu navigasi ke dashboard — Cloudflare butuh waktu redirect
        time.sleep(8.0)

        # ── DETEKSI "email already exists" SEBELUM tunggu dashboard ──
        try:
            body_early = page.inner_text("body").lower()
        except Exception:
            body_early = ""
        if "already exists" in body_early or "already have an account" in body_early:
            log.warning("⚠ Email SUDAH TERDAFTAR di Cloudflare!")
            log.info("→ Fallback: LOGIN dengan password yang diberikan...")

            # Impor di sini agar tidak circular import saat load module
            from cf_login import CloudflareLogin
            login = CloudflareLogin(self.email, self.password)
            aid = login.run(page)

            if aid:
                log.info("✓ Fallback login sukses — lanjut sebagai akun existing")
                return aid

            # Login gagal → password beda dari run sebelumnya → RESET
            log.warning("⚠ Login gagal (password salah/lupa) → RESET password...")
            from cf_reset_pass import CloudflareResetPassword
            new_password = random_password(16)
            resetter = CloudflareResetPassword(self.email, new_password, self.mail)
            if resetter.run(page):
                log.info("→ Password direset. Login dengan password baru...")
                login2 = CloudflareLogin(self.email, new_password)
                aid = login2.run(page)
                if aid:
                    # Update password di memory agar module lain pakai yang baru
                    self.password = new_password
                    log.info("✓ Password diperbarui untuk akun existing")
                    return aid

            log.error("✗ Semua fallback gagal (login + reset)")
            return None

        url = page.url
        log.info("  URL setelah signup: %s", url)

        # Cek berhasil masuk dashboard
        aid = extract_account_id_from_url(url)
        if aid:
            log.info("✓✓✓ SIGNUP BERHASIL ═══")
            log.info("  Account ID: %s", aid)
            return aid

        # Mungkin masih loading atau ada onboarding screen
        # Tunggu lebih lama sampai 60 detik
        for _ in range(30):
            time.sleep(2.0)
            url = page.url
            aid = extract_account_id_from_url(url)
            if aid:
                log.info("✓✓✓ SIGNUP BERHASIL ═══")
                log.info("  Account ID: %s", aid)
                return aid
            # Deteksi error email taken juga di loop ini
            try:
                body = page.inner_text("body").lower()
                if "already exists" in body:
                    log.warning("⚠ Email SUDAH TERDAFTAR (terlambat terdeteksi)")
                    log.info("→ Fallback: LOGIN...")
                    from cf_login import CloudflareLogin
                    login = CloudflareLogin(self.email, self.password)
                    aid = login.run(page)
                    if aid:
                        return aid
                    # login gagal → reset
                    from cf_reset_pass import CloudflareResetPassword
                    new_password = random_password(16)
                    if CloudflareResetPassword(self.email, new_password, self.mail).run(page):
                        login2 = CloudflareLogin(self.email, new_password)
                        aid = login2.run(page)
                        if aid:
                            self.password = new_password
                            return aid
                    log.error("✗ Semua fallback gagal")
                    return None
                if "workers-and-pages" in url or "onboard" in url:
                    log.info("→ Onboarding page terdeteksi, skip...")
                    break
            except Exception:
                pass

        # Jika tidak dapat account ID dari URL, coba dari page content
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
                log.info("✓✓✓ SIGNUP BERHASIL (from page) ═══")
                log.info("  Account ID: %s", aid)
                return aid
        except Exception:
            pass

        log.error("✗ Signup gagal — tidak masuk dashboard")
        log.info("  URL: %s", page.url)
        return None
