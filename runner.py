"""
runner.py — Jalankan alur pembuatan 1 akun Cloudflare lengkap.

Membaca config.json (diatur via menucfauto.py) dan menyimpan hasil
ke accounts.json (append, tidak menimpa).

Alur:
  1. Signup Cloudflare + Turnstile
  2. Konfirmasi email via Workers & Pages (tab sama)
  3. Ambil Global API Key
  4. Ambil Workers AI API Token
  5. Ambil Worker API Token (Edit Cloudflare Workers)
"""
from __future__ import annotations
import json
import os
import sys
import time
import random
import logging
import argparse

# Tambah path agar bisa import cf-modules + config
_BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _BASE)
sys.path.insert(0, os.path.join(_BASE, "cf-modules"))

from camoufox.sync_api import Camoufox
from camoufox import DefaultAddons

import importlib.util as _ilu

def _import_module(name):
    spec = _ilu.spec_from_file_location(name, os.path.join(_BASE, "cf-modules", name + ".py"))
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

from cf_config import load_config, append_account, generate_username

_h = _import_module("cf_helpers")
log = _h.log
random_password = _h.random_password
if not random_password:
    from cf_helpers import random_password
CloudflareSignup = _import_module("cf_signup").CloudflareSignup
ConfirmEmail = _import_module("cf_confirm_email").ConfirmEmail
GetApiKey = _import_module("cf_get_apikey").GetApiKey
GetWorkersAiToken = _import_module("cf_workers_ai").GetWorkersAiToken
GetWorkerToken = _import_module("cf_worker_token").GetWorkerToken


class TempMailAdapter:
    """Adapter untuk TempMailByJhopanstore API. Konfigurasi dari config.json."""

    def __init__(self, cfg: dict):
        import requests

        tm = cfg["temp_mail"]
        self.base = tm["base_url"].rstrip("/")
        self.headers = {"X-Email-API-Key": tm["api_key"]} if tm["api_key"] else {}
        self.domains = tm["domains"]
        self.prefix = tm["prefix"]
        self.cfg = cfg  # simpan config penuh untuk generate_username
        self.s = requests.Session()

    def create_inbox(self) -> str:
        """Buat inbox baru, return email address. Username sesuai email_format dari config."""
        for domain in self.domains:
            username = generate_username(self.cfg)
            try:
                r = self.s.post(
                    f"{self.base}/api/inbox",
                    headers={**self.headers, "Content-Type": "application/json"},
                    json={"username": username, "domain": domain},
                    timeout=20,
                )
                if r.status_code in (200, 201):
                    return r.json()["email"]
            except Exception as e:
                log.warning("⚠ Gagal buat inbox di %s: %s", domain, str(e)[:60])
        raise RuntimeError("Tidak ada domain mail yang berhasil membuat inbox")

    def wait_for_email(self, email: str, timeout: int = 120) -> dict:
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
        import urllib.parse

        encoded = urllib.parse.quote(email, safe="")
        self.s.delete(f"{self.base}/api/inbox/{encoded}", headers=self.headers, timeout=10)


def make_password(cfg: dict) -> str:
    """Buat password sesuai config."""
    pw = cfg["password"]
    if pw["mode"] == "fixed":
        return pw["fixed"]
    return random_password(pw["length"])


def main():
    parser = argparse.ArgumentParser(description="Runner: buat 1 akun CF lengkap.")
    parser.add_argument("--headless", action="store_true", help="Headless mode")
    parser.add_argument("--proxy", type=str, default=None, help="Proxy untuk browser")
    parser.add_argument("--count", type=int, default=1, help="Jumlah akun")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    cfg = load_config()

    for n in range(max(1, args.count)):
        log.info("═══ Akun #%d ═══", n + 1)
        try:
            create_one(cfg, args, n)
        except Exception as e:
            log.error("✗ Akun #%d gagal: %s", n + 1, str(e)[:120])


def create_one(cfg: dict, args, idx: int):
    # 1. Buat temp mail
    log.info("  Persiapan temp mail...")
    mail = TempMailAdapter(cfg)
    cf_email = mail.create_inbox()
    cf_password = make_password(cfg)
    log.info("  Email    : %s", cf_email)
    log.info("  Password : %s", cf_password)

    # 2. Launch Camoufox
    launch_kwargs = {
        "headless": cfg["browser"]["headless"],
        "humanize": True,
        "disable_coop": True,
        "geoip": True,
        "exclude_addons": [DefaultAddons.UBO],
        "i_know_what_im_doing": True,
    }
    proxy = args.proxy or cfg["browser"]["proxy"]
    if proxy:
        launch_kwargs["proxy"] = {"server": proxy}

    with Camoufox(**launch_kwargs) as browser:
        page = browser.new_page()
        page.set_default_timeout(30000)

        # Module 1: Signup
        signup = CloudflareSignup(cf_email, cf_password)
        account_id = signup.run(page)
        if not account_id:
            log.error("✗ Signup gagal, stop akun ini.")
            return

        time.sleep(3)  # jeda antar module

        # Module 2: Konfirmasi email
        confirm = ConfirmEmail(cf_email, cf_password, mail)
        confirm.run(page, account_id)

        time.sleep(3)  # jeda antar module

        # Module 3: Global API Key
        apikey = GetApiKey(cf_email, cf_password, mail)
        api_key = apikey.run(page)
        if not api_key:
            log.error("✗ Gagal ambil API Key, stop akun ini.")
            return

        time.sleep(3)  # jeda antar module

        # Module 4: Workers AI API Token
        workers_ai = GetWorkersAiToken(account_id)
        workers_ai_token = workers_ai.run(page)
        if not workers_ai_token:
            log.error("✗ Gagal ambil Workers AI API Token, stop akun ini.")
            return

        time.sleep(3)  # jeda antar module

        # Module 5: Worker API Token
        worker_tok = GetWorkerToken(cf_email)
        worker_token = worker_tok.run(page)
        if not worker_token:
            log.error("✗ Gagal ambil Worker API Token, stop akun ini.")
            return

    # Simpan hasil (append, dedup, JSON + CSV + workers_ai.txt)
    account = {
        "email": cf_email,
        "password": cf_password,
        "global_api_key": api_key,
        "workers_ai_token": workers_ai_token,
        "worker_api_token": worker_token,
        "account_id": account_id,
    }
    res = append_account(cfg, account)

    # Path file output
    stor = cfg.get("storage", {})
    json_file = stor.get("accounts_file", "accounts.json")
    csv_file = stor.get("csv_file", "accounts.csv")
    wai_file = stor.get("workers_ai_file", "workers_ai.txt")

    log.info("═══ Akun #%d SELESAI ═══", idx + 1)
    log.info("  Email         : %s", cf_email)
    log.info("  Global API Key: %s", api_key[:8] + "..." + api_key[-4:])
    log.info("  Workers AI    : %s", workers_ai_token[:12] + "..." + workers_ai_token[-4:])
    log.info("  Worker Token  : %s", worker_token[:12] + "..." + worker_token[-4:])
    log.info("  Account ID    : %s", account_id)
    log.info("  Disimpan      : %s", res["reason"])
    if res["added"]:
        log.info("  → %s", json_file)
        log.info("  → %s", csv_file)
        log.info("  → %s (format: name|apiKey|accountId)", wai_file)
    else:
        log.info("  → Skip (sudah ada): %s", res["reason"])


if __name__ == "__main__":
    main()
