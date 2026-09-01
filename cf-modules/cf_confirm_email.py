"""
cf_confirm_email.py — Module 2: Konfirmasi email via Workers & Pages

Tanggung jawab:
  - Buka /{account_id}/workers-and-pages (trigger email verifikasi)
  - Klik "Resend email" jika ada
  - Tunggu email dari Cloudflare di temp mail
  - Ambil link verifikasi asli (skip link dokumentasi)
  - Buka link verifikasi di TAB YANG SAMA (bukan tab baru!)
  - Jika redirect ke login, isi email+password
  - Klik Verify/Continue

TIDAK tanggung jawab:
  - Signup
  - Ambil API key

Aturan penting:
  - JANGAN buka tab baru! Pakai page yang sama dengan signup.
    Karena satu session = cookie shared = Cloudflare auto-recognize login.
"""
from __future__ import annotations
import re
import time
import logging
from typing import Optional

from playwright.sync_api import Page

from cf_helpers import (
    log,
    SEL_EMAIL,
    SEL_PASSWORD,
    fill_input,
    wait_and_click,
    dismiss_cookie_banner,
    extract_account_id_from_url,
)

__all__ = ["ConfirmEmail"]


class ConfirmEmail:
    """Module 2: Konfirmasi email via Workers & Pages."""

    def __init__(self, email: str, password: str, mail_client):
        """
        Args:
            email: Email Cloudflare (dari signup)
            password: Password Cloudflare (dari signup)
            mail_client: Instance dari TempMailAdapter (punya method
                         wait_for_email dan delete_inbox)
        """
        self.email = email
        self.password = password
        self.mail = mail_client

    def run(self, page: Page, account_id: str) -> bool:
        """Jalankan konfirmasi email flow.

        Returns:
            True jika verifikasi berhasil/ter-trigger, False jika gagal.
        """
        log.info("═══ Module 2: Konfirmasi email ═══")

        # --- Step A: Buka workers-and-pages untuk trigger email ---
        workers_url = (
            f"https://dash.cloudflare.com/{account_id}/workers-and-pages"
        )
        log.info("→ Navigasi ke: %s", workers_url)

        # Retry navigasi (NS_BINDING_ABORTED bisa terjadi)
        for attempt in range(3):
            try:
                page.goto(
                    workers_url,
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                break
            except Exception as e:
                log.warning(
                    "⚠ Navigasi gagal (attempt %d): %s",
                    attempt + 1, str(e)[:80],
                )
                time.sleep(3.0)

        time.sleep(5.0)
        dismiss_cookie_banner(page)
        log.info("  URL: %s", page.url)

        # Cek apakah halaman "Verify your account" muncul
        try:
            body_text = page.inner_text("body")
            if "verify" in body_text.lower():
                log.info("✓ Halaman verifikasi muncul — email akan dikirim")
            else:
                log.info("→ Halaman workers-and-pages loaded")
        except Exception:
            pass

        # Klik "Resend email" jika ada
        wait_and_click(
            page,
            [
                'button:has-text("Resend email")',
                'button:has-text("Resend")',
            ],
            timeout=5000, force=True,
        )
        time.sleep(2.0)

        # --- Step B: Tunggu email verifikasi ---
        log.info("→ Menunggu email verifikasi...")
        msg = self.mail.wait_for_email(self.email, timeout=120)
        log.info("✓ From   : %s", msg.get("from", ""))
        log.info("✓ Subject: %s", msg.get("subject", ""))

        # Ambil link verifikasi asli
        links = msg.get("links", [])
        verify_link = None
        for l in links:
            if (
                "developers.cloudflare.com" not in l.lower()
                and "cloudflare.com" in l.lower()
            ):
                verify_link = l
                break
        if not verify_link and links:
            verify_link = links[0]

        if not verify_link:
            log.error("✗ Link verifikasi tidak ditemukan")
            log.info("  Links: %s", links)
            return False

        log.info("✓ Link verifikasi: %s", verify_link[:100])

        # --- Step C: Buka link di TAB YANG SAMA ---
        # ATURAN: JANGAN buka tab baru!
        # Pakai page yang sama dengan signup → session cookie terbawa
        log.info("→ Buka link verifikasi di tab yang sama...")

        dashboard_url = page.url
        log.info("  Dashboard URL (untuk kembali): %s", dashboard_url)

        page.goto(verify_link, wait_until="domcontentloaded", timeout=60000)
        time.sleep(5.0)
        log.info("  URL setelah buka verify link: %s", page.url)

        # --- Step D: Jika redirect ke login, isi credentials ---
        if "/login" in page.url:
            log.info("→ Redirect ke login, isi credentials...")
            dismiss_cookie_banner(page)

            # Isi email
            email_filled = False
            for esel in SEL_EMAIL:
                try:
                    el = page.wait_for_selector(
                        esel, timeout=5000, state="visible"
                    )
                    if el:
                        el.click(timeout=3000)
                        el.fill(self.email, timeout=5000)
                        email_filled = True
                        log.info("✓ Email terisi (%s)", esel)
                        break
                except Exception:
                    continue

            if not email_filled:
                page.evaluate("""() => {
                    const el = document.querySelector(
                        'input[type="email"], input[name="email"]'
                    );
                    if (el) el.focus();
                }""")
                page.keyboard.type(self.email, delay=50)
                log.info("→ Email diketik via keyboard")

            # Isi password
            for psel in SEL_PASSWORD:
                try:
                    el = page.wait_for_selector(
                        psel, timeout=5000, state="visible"
                    )
                    if el:
                        el.click(timeout=3000)
                        el.fill(self.password, timeout=5000)
                        log.info("✓ Password terisi")
                        break
                except Exception:
                    continue

            time.sleep(1.0)

            # Klik tombol submit
            # "Continue with password" atau "Sign in"
            # JANGAN klik "Continue with SSO"
            login_clicked = False
            for bsel in [
                'button:has-text("Continue with password")',
                'button:has-text("Sign in")',
                'button:has-text("Continue")',
                'button[type="submit"]',
            ]:
                try:
                    el = page.wait_for_selector(
                        bsel, timeout=5000, state="visible"
                    )
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

            time.sleep(5.0)
            log.info("  URL setelah login: %s", page.url)

        # --- Step E: Klik Verify/Continue ---
        for sel in [
            'a:has-text("Verify your email")',
            'button:has-text("Verify your email")',
            'button:has-text("Verify")',
            'a:has-text("Verify")',
            'button:has-text("Continue")',
            'a:has-text("Continue")',
        ]:
            try:
                el = page.wait_for_selector(
                    sel, timeout=5000, state="visible"
                )
                if el:
                    el.click(force=True, timeout=5000)
                    log.info("✓ Verify diklik (%s)", sel)
                    break
            except Exception:
                continue

        time.sleep(5.0)
        log.info("  URL setelah verify: %s", page.url)

        # --- Step F: Verifikasi dengan buka workers-and-pages lagi ---
        # Jika halaman workers-and-pages tidak minta verifikasi lagi,
        # artinya email sudah terverifikasi
        # Tunggu 5 detik dulu biar redirect Cloudflare selesai (hindari NS_ERROR_ABORT)
        log.info("→ Tunggu 5s biar redirect Cloudflare selesai...")
        time.sleep(5)

        log.info("→ Cek verifikasi: buka workers-and-pages...")
        workers_url = f"https://dash.cloudflare.com/{account_id}/workers-and-pages"

        # Kalau URL sekarang sudah workers-and-pages, tidak perlu goto lagi
        current_url = page.url
        if "workers-and-pages" in current_url:
            log.info("→ Sudah di workers-and-pages, cek langsung...")
        else:
            # Retry navigasi karena NS_ERROR_ABORT bisa terjadi
            for attempt in range(3):
                try:
                    page.goto(workers_url, wait_until="domcontentloaded", timeout=60000)
                    break
                except Exception as e:
                    log.warning("⚠ Navigasi gagal (attempt %d): %s", attempt + 1, str(e)[:60])
                    time.sleep(5)  # jeda 5 detik sebelum retry

        time.sleep(5)  # jeda 5 detik setelah navigasi biar page stabil

        try:
            body_text = page.inner_text("body")
            body_lower = body_text.lower()
            # Kalau tidak ada "verify your email" atau "action required",
            # dan halaman workers-and-pages normal → verifikasi berhasil
            if "verify your email" in body_lower or "action required" in body_lower:
                log.warning("⚠ Email belum terverifikasi - masih diminta verifikasi")
                return False
            else:
                log.info("✓✓✓ VERIFIKASI BERHASIL! (workers-and-pages normal) ✓✓✓")
        except Exception:
            # Kalau tidak bisa baca body, cek URL saja
            if "workers-and-pages" in page.url:
                log.info("✓✓✓ VERIFIKASI BERHASIL! (URL workers-and-pages) ✓✓✓")
            else:
                log.warning("⚠ Tidak bisa cek status verifikasi, lanjut saja...")

        return True
