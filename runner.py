"""
runner.py — Runner yang gabungkan 3 module:
  1. cf_signup       — Signup Cloudflare + Turnstile
  2. cf_confirm_email — Konfirmasi email via Workers & Pages (tab sama)
  3. cf_get_apikey    — Ambil Global API Key

Tidak mengubah test_cf_worker.py atau cf_automation.py.
"""
from __future__ import annotations
import json
import os
import sys
import logging
import argparse

# Tambah path agar bisa import cf-modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from camoufox.sync_api import Camoufox
from camoufox import DefaultAddons

from cf_modules.cf_helpers import random_password, log
from cf_modules.cf_signup import CloudflareSignup
from cf_modules.cf_confirm_email import ConfirmEmail
from cf_modules.cf_get_apikey import GetApiKey
from cf_modules.cf_workers_ai import GetWorkersAiToken

# Temp mail adapter (pakai TempMailByJhopanstore API)
MAIL_BASE = "https://tempmail.renunganbot.qzz.io"
MAIL_API_KEY = "e763e811971502063b94be13707b3d9990c921493a7234469293c73bc289176f"
MAIL_DOMAIN = "renunganbot.qzz.io"


class TempMailAdapter:
    """Adapter untuk TempMailByJhopanstore API."""

    def __init__(
        self,
        base_url: str = MAIL_BASE,
        api_key: str = MAIL_API_KEY,
        domain: str = MAIL_DOMAIN,
    ):
        import requests

        self.base = base_url.rstrip("/")
        self.headers = {"X-Email-API-Key": api_key}
        self.domain = domain
        self.s = requests.Session()

    def create_inbox(self, prefix: str = "cf") -> str:
        """Buat inbox baru, return email address."""
        import random
        import string

        username = f"{prefix}{''.join(random.choices(string.ascii_lowercase + string.digits, k=8))}"
        r = self.s.post(
            f"{self.base}/api/inbox",
            headers={**self.headers, "Content-Type": "application/json"},
            json={"username": username, "domain": self.domain},
            timeout=20,
        )
        r.raise_for_status()
        return r.json()["email"]

    def wait_for_email(
        self, email: str, timeout: int = 120
    ) -> dict:
        """Block sampai email masuk. Return message dict."""
        import urllib.parse
        import time

        encoded = urllib.parse.quote(email, safe="")
        deadline = time.time() + timeout
        while time.time() < deadline:
            r = self.s.get(
                f"{self.base}/api/inbox/{encoded}/wait",
                headers=self.headers,
                params={"timeout": min(30, int(deadline - time.time()))},
                timeout=35,
            )
            if r.status_code == 200:
                return r.json()
            time.sleep(2)
        raise TimeoutError(f"Tidak ada email masuk dalam {timeout}s")

    def delete_inbox(self, email: str) -> None:
        """Hapus semua pesan di inbox."""
        import urllib.parse

        encoded = urllib.parse.quote(email, safe="")
        self.s.delete(
            f"{self.base}/api/inbox/{encoded}",
            headers=self.headers,
            timeout=10,
        )


def main():
    parser = argparse.ArgumentParser(
        description="Runner: Signup CF + Confirm Email + Get API Key"
    )
    parser.add_argument(
        "--headless", action="store_true", help="Headless mode ( tidak disarankan di Windows)"
    )
    parser.add_argument(
        "--proxy", type=str, default=None, help="Proxy untuk browser"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # 1. Buat temp mail
    log.info("═══ Persiapan: Buat temp mail ═══")
    mail = TempMailAdapter()
    cf_email = mail.create_inbox(prefix="cf")
    cf_password = random_password()
    log.info("  Email    : %s", cf_email)
    log.info("  Password : %s", cf_password)

    # 2. Launch Camoufox
    log.info("═══ Launch Camoufox ═══")
    launch_kwargs = {
        "headless": args.headless,
        "humanize": True,
        "disable_coop": True,
        "geoip": True,
        "exclude_addons": [DefaultAddons.UBO],
        "i_know_what_im_doing": True,
    }
    if args.proxy:
        launch_kwargs["proxy"] = {"server": args.proxy}

    with Camoufox(**launch_kwargs) as browser:
        page = browser.new_page()
        page.set_default_timeout(30000)

        # === Module 1: Signup ===
        signup = CloudflareSignup(cf_email, cf_password)
        account_id = signup.run(page)

        if not account_id:
            log.error("✗ Signup gagal, stop.")
            return

        # === Module 2: Konfirmasi email ===
        confirm = ConfirmEmail(cf_email, cf_password, mail)
        confirm.run(page, account_id)

        # === Module 3: Ambil API Key ===
        apikey = GetApiKey(cf_email, cf_password, mail)
        api_key = apikey.run(page)

        if not api_key:
            log.error("✗ Gagal ambil API Key")
            return

        # === Module 4: Ambil Workers AI API Token ===
        workers_ai = GetWorkersAiToken(account_id)
        workers_ai_token = workers_ai.run(page)

        if not workers_ai_token:
            log.error("✗ Gagal ambil Workers AI API Token")
            return

    # Simpan hasil
    result = {
        "email": cf_email,
        "password": cf_password,
        "global_api_key": api_key,
        "account_id": account_id,
        "workers_ai_token": workers_ai_token,
    }
    with open("runner_result.json", "w") as f:
        json.dump(result, f, indent=2)

    log.info("═══ SELESAI ═══")
    log.info("Email      : %s", cf_email)
    log.info("Password   : %s", cf_password)
    log.info("API Key     : %s", api_key[:8] + "..." + api_key[-4:])
    log.info("Workers AI  : %s", workers_ai_token[:12] + "..." + workers_ai_token[-4:])
    log.info("Account ID  : %s", account_id)
    log.info("Disimpan   : runner_result.json")


if __name__ == "__main__":
    main()
