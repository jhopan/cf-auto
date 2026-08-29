"""
cf_config.py — Helper untuk load/save config.json dan accounts.json.

Config diatur via menucfauto.py. Runner membaca config ini saat start.
"""
import json
import os
from datetime import datetime
from typing import Optional

# Path relatif ke folder project (script biasa, bukan package)
_BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(_BASE, "config.json")
DEFAULT_STORAGE = {"accounts_file": "accounts.json", "append": True}

DEFAULTS = {
    "temp_mail": {
        "base_url": "https://tempmail.renunganbot.qzz.io",
        "api_key": "",
        "domains": ["renunganbot.qzz.io"],
        "prefix": "cf",
    },
    "password": {"mode": "random", "fixed": "", "length": 16},
    "browser": {"headless": False, "proxy": ""},
    "storage": DEFAULT_STORAGE,
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Gabung dict nested: nilai override menang, sisanya pakai default."""
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config() -> dict:
    """Load config.json. Kalau tidak ada, return default. Field yang hilang diisi default."""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            user = json.load(f)
        return _deep_merge(DEFAULTS, user)
    return json.loads(json.dumps(DEFAULTS))


def save_config(cfg: dict) -> None:
    """Simpan config ke config.json (pretty print)."""
    merged = _deep_merge(DEFAULTS, cfg)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)


def _accounts_path(cfg: dict) -> str:
    stor = cfg.get("storage", {})
    f = stor.get("accounts_file", "accounts.json")
    if os.path.isabs(f):
        return f
    return os.path.join(_BASE, f)


def load_accounts(cfg: dict) -> list:
    """Load daftar akun dari accounts.json. Return [] kalau kosong/tidak ada."""
    path = _accounts_path(cfg)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []


def append_account(cfg: dict, account: dict) -> list:
    """Append satu akun ke accounts.json. Return daftar lengkap."""
    accounts = load_accounts(cfg)
    account["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    accounts.append(account)
    path = _accounts_path(cfg)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(accounts, f, indent=2, ensure_ascii=False)
    return accounts
