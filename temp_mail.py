"""
temp_mail.py — Wrapper mail.tm API
Membuat akun email sementara, memverifikasi, dan menunggu email masuk.
Dokumentasi: https://docs.mail.tm
"""
from __future__ import annotations
import re
import time
import random
import string
import logging
from dataclasses import dataclass
from typing import Optional

import requests

log = logging.getLogger("temp_mail")

BASE_URL = "https://api.mail.tm"
# Rate limit mail.tm: 8 QPS per IP. Kita conservative.
POLL_INTERVAL = 6.0
REQUEST_TIMEOUT = 20


@dataclass
class TempMailAccount:
    address: str
    password: str
    token: str
    account_id: str


class TempMail:
    """Client untuk mail.tm API."""

    def __init__(self, proxy: Optional[str] = None):
        self.s = requests.Session()
        self.s.headers.update({"Content-Type": "application/json",
                               "Accept": "application/json"})
        if proxy:
            self.s.proxies = {"http": proxy, "https": proxy}

    # ------------------------------------------------------------------
    # Low-level
    # ------------------------------------------------------------------
    def _req(self, method: str, path: str, **kw) -> requests.Response:
        url = f"{BASE_URL}{path}"
        r = self.s.request(method, url, timeout=REQUEST_TIMEOUT, **kw)
        return r

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_domain(self) -> str:
        r = self._req("GET", "/domains")
        r.raise_for_status()
        data = r.json()
        # mail.tm bisa return dict (hydra:Collection) atau list langsung
        if isinstance(data, dict):
            members = data.get("hydra:member", [])
        elif isinstance(data, list):
            members = data
        else:
            members = []
        active = [d for d in members if d.get("isActive")]
        if not active:
            raise RuntimeError("Domain mail.tm tidak tersedia")
        return active[0]["domain"]

    def create_account(self, address: Optional[str] = None,
                       password: Optional[str] = None) -> TempMailAccount:
        domain = self.get_domain()
        if not address:
            user = "cf" + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
            address = f"{user}@{domain}"
        if not password:
            password = "Cf" + "".join(random.choices(string.ascii_letters + string.digits, k=12)) + "1!"

        # Buat akun
        r = self._req("POST", "/accounts", json={"address": address, "password": password})
        if r.status_code == 422:
            # Address sudah dipakai, ulang dengan random baru
            log.warning("Address %s sudah dipakai, coba ulang...", address)
            return self.create_account(password=password)
        r.raise_for_status()
        account_id = r.json().get("id")
        log.info("✓ Akun mail.tm dibuat: %s", address)

        # Ambil token
        r = self._req("POST", "/token", json={"address": address, "password": password})
        r.raise_for_status()
        token = r.json()["token"]
        return TempMailAccount(address=address, password=password,
                               token=token, account_id=account_id)

    def wait_for_email(self, token: str,
                       subject_contains: Optional[str] = None,
                       from_contains: Optional[str] = None,
                       timeout: int = 180) -> dict:
        """Poll inbox sampai email masuk. Return message JSON."""
        headers = {"Authorization": f"Bearer {token}"}
        deadline = time.time() + timeout
        seen_ids: set[str] = set()
        log.info("⏳ Menunggu email masuk (timeout %ds)...", timeout)
        while time.time() < deadline:
            r = self._req("GET", "/messages", headers=headers)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict):
                    msgs = data.get("hydra:member", [])
                elif isinstance(data, list):
                    msgs = data
                else:
                    msgs = []
                for m in msgs:
                    if m["id"] in seen_ids:
                        continue
                    seen_ids.add(m["id"])
                    subj = m.get("subject", "")
                    frm = m.get("from", {}).get("address", "")
                    if subject_contains and subject_contains.lower() not in subj.lower():
                        continue
                    if from_contains and from_contains.lower() not in frm.lower():
                        continue
                    # Ambil full message
                    r2 = self._req("GET", f"/messages/{m['id']}", headers=headers)
                    if r2.status_code == 200:
                        log.info("✓ Email ditemukan: %s", subj)
                        return r2.json()
            time.sleep(POLL_INTERVAL)
        raise TimeoutError("Tidak ada email masuk dalam timeout")

    @staticmethod
    def extract_otp(text: str, length: int = 6) -> Optional[str]:
        """Ekstrak kode OTP (angka) dari teks email."""
        # Pattern: kode 6 digit (atau disesuaikan)
        patterns = [
            rf"\b(\d{{{length}}})\b",
            r"(?:code|otp|verification)[^0-9]*?(\d{4,8})",
            r"<strong[^>]*>(\d{4,8})</strong>",
            r"font-size:\s*\d+[^>]*>(\d{4,8})<",
            r">\s*(\d{4,8})\s*<",
        ]
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                return m.group(1)
        # Fallback: cari angka berurutan
        nums = re.findall(r"\b\d{4,8}\b", text)
        if nums:
            return nums[0]
        return None

    @staticmethod
    def extract_link(text: str) -> Optional[str]:
        """Ekstrak verification link dari email HTML.
        
        Penting: Skip link dokumentasi (developers.cloudflare.com) dan
        prioritaskan link dash.cloudflare.com (verifikasi asli).
        """
        links = re.findall(r'href="(https?://[^"]+)"', text)
        if not links:
            return None
        
        # Filter: skip link dokumentasi dan link "delete"
        valid_links = []
        for l in links:
            l_lower = l.lower()
            # Skip link dokumentasi
            if "developers.cloudflare.com" in l_lower:
                continue
            # Skip link "delete"
            if "delete" in l_lower:
                continue
            # Skip link unsubscribe
            if "unsubscribe" in l_lower or "notify" in l_lower:
                continue
            valid_links.append(l)
        
        if not valid_links:
            # Fallback: return link pertama yang bukan docs
            for l in links:
                if "developers.cloudflare.com" not in l.lower():
                    return l
            return None
        
        # Prioritaskan link ke dash.cloudflare.com (verifikasi asli)
        priority = [l for l in valid_links if "dash.cloudflare.com" in l.lower()]
        if priority:
            return priority[0]
        
        # Prioritaskan link dengan kata "verify" / "confirm"
        priority = [l for l in valid_links if any(k in l.lower() for k in
                     ("verify", "confirm", "activate"))]
        if priority:
            return priority[0]
        
        return valid_links[0]
