"""
test_signup.py — Test signup Cloudflare + Turnstile saja
Fokus: pastikan signup berhasil dan Turnstile ter-solve
"""
import sys
import time
import logging
from camoufox.sync_api import Camoufox
from camoufox import DefaultAddons

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("test")

# Import dari cf_automation
sys.path.insert(0, ".")
from cf_automation import (
    TempMail, random_password, fill_input, wait_and_click, wait_for_turnstile,
    dismiss_cookie_banner, SEL_EMAIL, SEL_PASSWORD, SEL_SIGNUP_BTN,
    extract_account_id_from_url,
)
from temp_mail import TempMail as TM

def main():
    # 1. Buat temp mail
    log.info("═══ Step 1: Buat temp mail ═══")
    mail = TM()
    acct = mail.create_account()
    email = acct.address
    password = random_password()
    log.info("  Email    : %s", email)
    log.info("  Password : %s", password)

    # 2. Launch Camoufox
    log.info("═══ Step 2: Launch Camoufox ═══")
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

        log.info("═══ Step 3: Signup Cloudflare ═══")
        page.goto("https://dash.cloudflare.com/sign-up", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        dismiss_cookie_banner(page)

        # Isi email
        if not fill_input(page, SEL_EMAIL, email, timeout=15000):
            log.error("Field email tidak ditemukan")
            return
        log.info("✓ Email terisi")

        # Isi password
        if not fill_input(page, SEL_PASSWORD, password, timeout=10000):
            log.error("Field password tidak ditemukan")
            return
        log.info("✓ Password terisi")

        # Uncheck checkbox
        try:
            page.uncheck('input[type="checkbox"]', timeout=3000)
        except Exception:
            pass

        # Solve Turnstile
        solved = wait_for_turnstile(page, timeout=90)
        if not solved:
            log.warning("⚠ Turnstile belum solved otomatis! Menunggu manual...")
            try:
                page.wait_for_function(
                    """() => {
                        const el = document.querySelector('input[name="cf_challenge_response"]');
                        return el && el.value && el.value.length > 20;
                    }""",
                    timeout=120000,  # 2 menit untuk manual
                )
                log.info("✓ Turnstile solved (manual)")
                solved = True
            except Exception:
                log.error("✗ Turnstile tidak solved dalam 2 menit")
                return

        # Klik Sign up
        page.wait_for_timeout(1000)
        if not wait_and_click(page, SEL_SIGNUP_BTN, timeout=10000, force=True):
            page.keyboard.press("Enter")
        log.info("✓ Tombol Sign up diklik")

        # Tunggu navigasi
        page.wait_for_timeout(8000)
        log.info("  URL setelah signup: %s", page.url)

        # Cek berhasil
        aid = extract_account_id_from_url(page.url)
        if aid:
            log.info("✓✓✓ SIGNUP BERHASIL! ✓✓✓")
            log.info("  Account ID: %s", aid)
            log.info("  Email      : %s", email)
            log.info("  Password   : %s", password)

            # Navigasi ke workers-and-pages
            log.info("═══ Step 4: Buka workers-and-pages ═══")
            workers_url = f"https://dash.cloudflare.com/{aid}/workers-and-pages"
            page.goto(workers_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            log.info("  URL: %s", page.url)

            # Klik Resend email jika ada
            wait_and_click(page, ['button:has-text("Resend email")',
                                  'button:has-text("Resend")'], timeout=5000, force=True)
            page.wait_for_timeout(2000)

            # Tunggu email verifikasi
            log.info("═══ Step 5: Tunggu email verifikasi ═══")
            msg = mail.wait_for_email(
                token=acct.token,
                from_contains="cloudflare",
                timeout=120,
            )
            log.info("✓ Email dari: %s", msg.get("from", {}).get("address", "?"))
            log.info("✓ Subject: %s", msg.get("subject", "?"))

            # Buka link verifikasi di tab baru
            import re
            from temp_mail import TempMail as TM2
            html_raw = msg.get("html") or ""
            if isinstance(html_raw, list):
                html = "\n".join(str(h) for h in html_raw)
            else:
                html = str(html_raw) if html_raw else ""

            link = TM2.extract_link(html)
            if not link:
                links = re.findall(r"https?://\S+", html)
                real_links = [l.rstrip(".,)") for l in links
                             if "developers.cloudflare.com" not in l.lower()
                             and "cloudflare.com" in l.lower()]
                link = real_links[0] if real_links else None

            if link:
                log.info("✓ Link verifikasi: %s", link[:100])
                verify_page = browser.new_page()
                verify_page.goto(link, wait_until="domcontentloaded", timeout=60000)
                verify_page.wait_for_timeout(5000)
                log.info("  URL: %s", verify_page.url)

                # Klik Verify
                wait_and_click(verify_page, [
                    'a:has-text("Verify your email")',
                    'button:has-text("Verify")',
                    'a:has-text("Verify")',
                    'button:has-text("Continue")',
                ], timeout=10000, force=True)
                verify_page.wait_for_timeout(5000)
                log.info("✓ Tombol Verify diklik")
                verify_page.close()
                log.info("✓✓✓ VERIFIKASI EMAIL SELESAI! ✓✓✓")
            else:
                log.error("Link verifikasi tidak ditemukan")
        else:
            log.error("✗ Signup gagal - tidak masuk dashboard")

        # Simpan hasil
        import json
        result = {
            "email": email,
            "password": password,
            "account_id": aid,
        }
        with open("test_signup_result.json", "w") as f:
            json.dump(result, f, indent=2)
        log.info("Hasil disimpan: test_signup_result.json")

        # Tunggu user tekan Ctrl+C
        log.info("═══ Selesai. Browser tetap terbuka. Tekan Ctrl+C untuk keluar. ═══")
        try:
            while True:
                page.wait_for_timeout(10000)
        except KeyboardInterrupt:
            log.info("Keluar...")

if __name__ == "__main__":
    main()
