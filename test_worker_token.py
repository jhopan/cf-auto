"""
test_worker_token.py — Test Module 5: Edit Cloudflare Workers API Token
Pakai akun yang sudah ada.
"""
import sys
import os
import json
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_CF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cf-modules")
sys.path.insert(0, _CF)

from camoufox.sync_api import Camoufox
from camoufox import DefaultAddons

from cf_helpers import (
    log, fill_input, wait_and_click, wait_for_turnstile,
    dismiss_cookie_banner, extract_account_id_from_url,
    SEL_EMAIL, SEL_PASSWORD,
)
from cf_worker_token import GetWorkerToken

# === CONFIG ===
CF_EMAIL = "cfyoyf3o9b@renunganbot.qzz.io"
CF_PASSWORD = "ap$u6Vut2OM#3p"
# Fallback credentials
CF_EMAIL2 = "agathatia44@gmail.com"
CF_PASSWORD2 = "sukadukabersamau"
# ==============

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    log.info("═══ Test Module 5: Worker API Token ═══")

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

        # Login
        log.info("═══ Login Cloudflare ═══")
        page.goto("https://dash.cloudflare.com/login", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        dismiss_cookie_banner(page)

        # Coba login dengan kedua credentials
        login_ok = False
        for email, pwd in [(CF_EMAIL, CF_PASSWORD), (CF_EMAIL2, CF_PASSWORD2)]:
            log.info("→ Coba login: %s", email)
            for esel in SEL_EMAIL:
                try:
                    el = page.wait_for_selector(esel, timeout=10000, state="visible")
                    if el:
                        el.click(timeout=3000)
                        el.fill(email, timeout=5000)
                        log.info("✓ Email terisi")
                        break
                except Exception:
                    continue
            for psel in SEL_PASSWORD:
                try:
                    el = page.wait_for_selector(psel, timeout=10000, state="visible")
                    if el:
                        el.click(timeout=3000)
                        el.fill(pwd, timeout=5000)
                        log.info("✓ Password terisi")
                        break
                except Exception:
                    continue
            page.wait_for_timeout(1000)
            for bsel in ['button:has-text("Continue with password")',
                         'button:has-text("Sign in")',
                         'button:has-text("Continue")',
                         'button[type="submit"]']:
                try:
                    el = page.wait_for_selector(bsel, timeout=5000, state="visible")
                    if el:
                        txt = el.text_content() or ""
                        if "sso" in txt.lower():
                            continue
                        el.click(force=True, timeout=5000)
                        log.info("✓ Login diklik (%s)", bsel)
                        break
                except Exception:
                    continue
            page.wait_for_timeout(8000)
            url = page.url
            log.info("  URL: %s", url)
            aid = extract_account_id_from_url(url)
            if not aid:
                for _ in range(10):
                    page.wait_for_timeout(2000)
                    url = page.url
                    aid = extract_account_id_from_url(url)
                    if aid:
                        break
            if not aid:
                try:
                    aid = page.evaluate("""() => {
                        const links = document.querySelectorAll('a[href*="/"]');
                        for (const a of links) {
                            const m = a.href.match(/dash\\.cloudflare\\.com\\/([a-f0-9]{20,})/);
                            if (m) return m[1];
                        }
                        return null;
                    }""")
                except Exception:
                    pass
            if aid:
                log.info("✓ Account ID: %s", aid)
                login_ok = True
                CF_EMAIL_USED = email
                break
            else:
                log.warning("⚠ Login gagal dengan %s, coba credentials lain...", email)
                page.goto("https://dash.cloudflare.com/login", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(3000)

        if not login_ok:
            log.error("✗ Login gagal dengan semua credentials")
            return

        # Run Module 5
        worker = GetWorkerToken(CF_EMAIL_USED)
        token = worker.run(page)

        if not token:
            log.error("✗ Gagal ambil Worker API Token")
            return

        log.info("✓✓✓ WORKER API TOKEN: %s ✓✓✓", token)

        result = {
            "email": CF_EMAIL_USED,
            "account_id": aid,
            "worker_api_token": token,
        }
        with open("test_worker_token_result.json", "w") as f:
            json.dump(result, f, indent=2)
        log.info("✓ Disimpan: test_worker_token_result.json")

        log.info("═══ Selesai. Ctrl+C untuk keluar. ═══")
        try:
            while True:
                page.wait_for_timeout(10000)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
