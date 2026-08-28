"""
test_workers_ai.py — Test Module 4: Ambil Workers AI API Token
Pakai akun yang sudah berhasil dibuat sebelumnya.

Akun:
  Email      : cfyoyf3o9b@renunganbot.qzz.io  (atau ganti sesuai akun Anda)
  Account ID : dari URL dashboard setelah login

Flow:
  1. Launch Camoufox
  2. Login ke Cloudflare (email + password)
  3. Navigasi ke workers-ai/api-quick-start
  4. Klik "Create a Workers AI API Token"
  5. Ubah Token name → "jhopanstore"
  6. Klik "Create API Token"
  7. Copy token (cfut_...)
  8. Simpan ke file
"""
import sys
import os
import json
import time
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_CF_MODULES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cf-modules")
sys.path.insert(0, _CF_MODULES)

from camoufox.sync_api import Camoufox
from camoufox import DefaultAddons

# cf-modules folder sudah di sys.path, import langsung
from cf_helpers import (
    log, fill_input, wait_and_click, wait_for_turnstile,
    dismiss_cookie_banner, extract_account_id_from_url,
    SEL_EMAIL, SEL_PASSWORD, random_password,
)
from cf_workers_ai import GetWorkersAiToken

# === CONFIG — ganti sesuai akun Anda ===
CF_EMAIL = "cfyoyf3o9b@renunganbot.qzz.io"
CF_PASSWORD = "ap$u6Vut2OM#3p"
# =======================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    log.info("═══ Test Module 4: Workers AI API Token ═══")
    log.info("  Email: %s", CF_EMAIL)

    with Camoufox(
        headless=False,
        humanize=True,
        disable_coop=True,
        geoip=True,
        exclude_addons=[DefaultAddons.UBO],
        i_know_what_im_doing=True,
    ) as browser:
        page = browser.new_page()
        page.set_default_timeout(30000)

        # === Step 1: Login ke Cloudflare ===
        log.info("═══ Step 1: Login Cloudflare ═══")
        page.goto("https://dash.cloudflare.com/login", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        dismiss_cookie_banner(page)

        # Isi email
        for esel in SEL_EMAIL:
            try:
                el = page.wait_for_selector(esel, timeout=10000, state="visible")
                if el:
                    el.click(timeout=3000)
                    el.fill(CF_EMAIL, timeout=5000)
                    log.info("✓ Email terisi: %s", CF_EMAIL)
                    break
            except Exception:
                continue

        # Isi password
        for psel in SEL_PASSWORD:
            try:
                el = page.wait_for_selector(psel, timeout=10000, state="visible")
                if el:
                    el.click(timeout=3000)
                    el.fill(CF_PASSWORD, timeout=5000)
                    log.info("✓ Password terisi")
                    break
            except Exception:
                continue

        page.wait_for_timeout(1000)

        # Klik "Continue with password" atau "Sign in" (skip SSO)
        login_clicked = False
        for bsel in [
            'button:has-text("Continue with password")',
            'button:has-text("Sign in")',
            'button:has-text("Continue")',
            'button[type="submit"]',
        ]:
            try:
                el = page.wait_for_selector(bsel, timeout=5000, state="visible")
                if el:
                    txt = el.text_content() or ""
                    if "sso" in txt.lower():
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

        # Tunggu dashboard load
        page.wait_for_timeout(8000)
        log.info("  URL setelah login: %s", page.url)

        # Cek apakah login berhasil
        aid = extract_account_id_from_url(page.url)
        if not aid:
            log.error("✗ Login gagal — tidak masuk dashboard")
            log.info("  URL: %s", page.url)
            return

        log.info("✓✓✓ LOGIN BERHASIL! Account ID: %s", aid)

        # === Step 2: Run Module 4 ===
        workers_ai = GetWorkersAiToken(aid)
        token = workers_ai.run(page)

        if not token:
            log.error("✗ Gagal ambil Workers AI API Token")
            return

        log.info("✓✓✓ WORKERS AI API TOKEN DIDAPAT! ✓✓✓")
        log.info("  Token: %s", token)

        # Simpan hasil
        result = {
            "email": CF_EMAIL,
            "password": CF_PASSWORD,
            "account_id": aid,
            "workers_ai_token": token,
        }
        with open("test_workers_ai_result.json", "w") as f:
            json.dump(result, f, indent=2)
        log.info("✓ Hasil disimpan: test_workers_ai_result.json")

        # Tunggu user tekan Ctrl+C
        log.info("═══ Selesai. Browser tetap terbuka. Tekan Ctrl+C untuk keluar. ═══")
        try:
            while True:
                page.wait_for_timeout(10000)
        except KeyboardInterrupt:
            log.info("Keluar...")


if __name__ == "__main__":
    main()
