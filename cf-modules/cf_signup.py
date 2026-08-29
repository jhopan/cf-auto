"""
cf_signup.py — Module 1: Signup Cloudflare + Solve Turnstile

Tanggung jawab:
  - Buka dash.cloudflare.com/sign-up
  - Isi email (via fill, bukan otomatisasi berlebihan)
  - Isi password
  - Selesaikan Turnstile sampai dapat token
  - Klik Sign up

TIDAK tanggung jawab:
  - Verifikasi email
  - Ambil API key
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

    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password

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
        time.sleep(15.0)
        url = page.url
        log.info("  URL setelah signup: %s", url)

        # Cek berhasil masuk dashboard
        aid = extract_account_id_from_url(url)
        if aid:
            log.info("✓✓✓ SIGNUP BERHASIL ═══")
            log.info("  Account ID: %s", aid)
            return aid

        # Mungkin masih loading, tunggu lagi
        for _ in range(5):
            time.sleep(2.0)
            aid = extract_account_id_from_url(page.url)
            if aid:
                log.info("✓✓✓ SIGNUP BERHASIL ═══")
                log.info("  Account ID: %s", aid)
                return aid

        log.error("✗ Signup gagal — tidak masuk dashboard")
        log.info("  URL: %s", page.url)
        return None
