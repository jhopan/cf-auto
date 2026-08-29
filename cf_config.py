"""
cf_config.py — Helper untuk load/save config.json dan accounts.json.

Mendukung penyimpanan ganda JSON + CSV, dedup berdasarkan field, dan
aturan pembuatan nama email (email_format).

Config diatur via menucfauto.py. Runner membaca config ini saat start.
"""
import csv
import json
import os
import random
import string
from datetime import datetime
from typing import Optional

# Path relatif ke folder project (script biasa, bukan package)
_BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(_BASE, "config.json")

DEFAULTS = {
    "temp_mail": {
        "base_url": "https://tempmail.renunganbot.qzz.io",
        "api_key": "",
        "domains": ["renunganbot.qzz.io"],
        "prefix": "cf",
        "email_format": "{prefix}{rand8}",
    },
    "password": {"mode": "random", "fixed": "", "length": 16},
    "browser": {"headless": False, "proxy": ""},
    "storage": {
        "accounts_file": "accounts.json",
        "csv_file": "accounts.csv",
        "csv_enabled": True,
        "append": True,
        "dedupe_field": "email",
    },
}

# Kolom tetap urutan CSV
CSV_COLUMNS = [
    "email", "password", "account_id",
    "global_api_key", "workers_ai_token", "worker_api_token",
    "created_at",
]


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            user = json.load(f)
        return _deep_merge(DEFAULTS, user)
    return json.loads(json.dumps(DEFAULTS))


def save_config(cfg: dict) -> None:
    merged = _deep_merge(DEFAULTS, cfg)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)


def _path(cfg: dict, key: str, fallback: str) -> str:
    stor = cfg.get("storage", {})
    f = stor.get(key, fallback)
    if os.path.isabs(f):
        return f
    return os.path.join(_BASE, f)


def _accounts_path(cfg: dict) -> str:
    return _path(cfg, "accounts_file", "accounts.json")


def _csv_path(cfg: dict) -> str:
    return _path(cfg, "csv_file", "accounts.csv")


# ---------------------------------------------------------------------------
# Email format
# ---------------------------------------------------------------------------
def generate_username(cfg: dict) -> str:
    """Buat username sesuai aturan email_format di config."""
    tm = cfg["temp_mail"]
    fmt = tm.get("email_format", "{prefix}{rand8}")
    prefix = tm.get("prefix", "cf")
    # Placeholder yang didukung
    rand8 = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    rand6 = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    randnum = "".join(random.choices(string.digits, k=6))
    out = fmt
    out = out.replace("{prefix}", prefix)
    out = out.replace("{rand8}", rand8)
    out = out.replace("{rand6}", rand6)
    out = out.replace("{randnum}", randnum)
    return out


# ---------------------------------------------------------------------------
# Accounts: JSON + CSV (dedup + append)
# ---------------------------------------------------------------------------
def load_accounts(cfg: dict) -> list:
    path = _accounts_path(cfg)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []


def _existing_emails(cfg: dict) -> set:
    emails = set()
    for a in load_accounts(cfg):
        if a.get("email"):
            emails.add(a["email"])
    return emails


def _read_csv_emails(cfg: dict) -> set:
    """Baca email yang sudah ada di CSV (untuk dedup)."""
    path = _csv_path(cfg)
    emails = set()
    if not os.path.exists(path):
        return emails
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("email"):
                    emails.add(row["email"])
    except Exception:
        pass
    return emails


def _write_csv(path: str, accounts: list) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for a in accounts:
            writer.writerow({c: a.get(c, "") for c in CSV_COLUMNS})


def append_account(cfg: dict, account: dict) -> dict:
    """
    Append satu akun ke JSON + CSV dengan dedup (tidak boleh duplikat).

    - Cek field dedupe (default email): kalau sudah ada, jangan tambah.
    - Tidak pernah menghapus data lama; hanya menambah yang baru.
    - Update BOTH accounts.json dan accounts.csv secara konsisten.

    Returns:
        {'added': bool, 'reason': str} — status penambahan.
    """
    dedupe_field = cfg.get("storage", {}).get("dedupe_field", "email")
    key = account.get(dedupe_field)

    if not key:
        return {"added": False, "reason": f"field dedupe '{dedupe_field}' kosong"}

    # Cek duplikat di JSON + CSV
    if key in _existing_emails(cfg) or key in _read_csv_emails(cfg):
        return {"added": False, "reason": f"duplikat: {key}"}

    # Tambahkan timestamp
    account["created_at"] = account.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Update JSON (append)
    accounts = load_accounts(cfg)
    accounts.append(account)
    with open(_accounts_path(cfg), "w", encoding="utf-8") as f:
        json.dump(accounts, f, indent=2, ensure_ascii=False)

    # Update CSV (append, jangan hapus)
    stor = cfg.get("storage", {})
    if stor.get("csv_enabled", True):
        csv_path = _csv_path(cfg)
        if os.path.exists(csv_path):
            # Baca yang ada, tambah baris baru
            with open(csv_path, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            rows.append({c: account.get(c, "") for c in CSV_COLUMNS})
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
        else:
            _write_csv(csv_path, accounts)

    return {"added": True, "reason": "ok"}


def accounts_open_count(cfg: dict) -> int:
    return len(load_accounts(cfg))
