"""
cf_config.py — Helper untuk load/save config.json dan accounts.json.

Mendukung 3 format output:
  1. accounts.json  — semua field (JSON, dedup, append)
  2. workers_ai.txt — format name|apiKey|accountId (1 baris per akun, dedup, append)
  3. accounts.csv   — semua field sebagai kolom (CSV, dedup, append)

Dedup: cek field dedupe_field (default email) di SEMUA 3 file.
Kalau sudah ada di salah satu → skip di semua.

Config diatur via menucfauto.py. Runner membaca config ini saat start.
"""
import csv
import json
import os
import random
import string
from datetime import datetime
from typing import Optional

_BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(_BASE, "config.json")

DEFAULTS = {
    "temp_mail": {
        "base_url": "https://tempmail.renunganbot.qzz.io",
        "api_key": "",
        "domains": ["renunganbot.qzz.io"],
        "prefix": "cf",
        "email_format": "{prefix}{rand8}",
        "naming_mode": "format",
        "wordlist_file": "",
        "wordlist_index": 0,
    },
    "password": {"mode": "random", "fixed": "", "length": 16},
    "browser": {"headless": False, "proxy": ""},
    "storage": {
        "accounts_file": "accounts.json",
        "csv_file": "accounts.csv",
        "workers_ai_file": "workers_ai.txt",
        "workers_ai_format": "{name}|{apiKey}|{accountId}",
        "csv_enabled": True,
        "workers_ai_enabled": True,
        "append": True,
        "dedupe_field": "email",
    },
}

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


def _wai_path(cfg: dict) -> str:
    return _path(cfg, "workers_ai_file", "workers_ai.txt")


# ---------------------------------------------------------------------------
# Email format
# ---------------------------------------------------------------------------
def generate_username(cfg: dict) -> str:
    """
    Buat username sesuai aturan config.

    Mode:
      - 'format'  : pakai email_format dengan placeholder {prefix} {rand8} {rand6} {randnum}
      - 'wordlist': baca dari CSV wordlist, cari baris status kosong, tandai 'used'
    """
    tm = cfg["temp_mail"]
    mode = tm.get("naming_mode", "format")

    if mode == "wordlist":
        wl_path = tm.get("wordlist_file", "")
        if not wl_path:
            raise RuntimeError("naming_mode=wordlist tapi wordlist_file kosong")

        if not os.path.isabs(wl_path):
            wl_path = os.path.join(_BASE, wl_path)

        if not os.path.exists(wl_path):
            raise RuntimeError(f"file wordlist tidak ada: {wl_path}")

        # Baca CSV wordlist
        rows = []
        fieldnames = []
        with open(wl_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = [fn for fn in (reader.fieldnames or []) if fn.strip()]
            # Pastikan minimal 3 kolom: nomor, nama, status
            if "nama" not in fieldnames:
                raise RuntimeError("wordlist CSV harus punya kolom: nomor,nama,status")
            for row in reader:
                rows.append(row)

        if not rows:
            raise RuntimeError("wordlist kosong")

        # Cari baris pertama yang status-nya kosong (belum dipakai)
        chosen_idx = None
        for i, row in enumerate(rows):
            status = (row.get("status") or "").strip().lower()
            if status == "" or status == "available":
                chosen_idx = i
                break

        if chosen_idx is None:
            # Semua nama sudah dipakai → fallback ke random format
            prefix = tm.get("prefix", "cf")
            rand8 = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
            return f"{prefix}{rand8}"

        username = (rows[chosen_idx].get("nama") or "").strip()
        if not username:
            raise RuntimeError(f"nama kosong di baris {chosen_idx + 1}")

        # Tandai baris sebagai 'used'
        rows[chosen_idx]["status"] = "used"

        # Tulis ulang CSV dengan hanya 3 kolom: nomor, nama, status
        clean_fields = ["nomor", "nama", "status"]
        with open(wl_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=clean_fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

        return username

    # Mode 'format' (default)
    fmt = tm.get("email_format", "{prefix}{rand8}")
    prefix = tm.get("prefix", "cf")
    rand8 = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    rand6 = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    randnum = "".join(random.choices(string.digits, k=6))
    out = fmt
    out = out.replace("{prefix}", prefix)
    out = out.replace("{rand8}", rand8)
    out = out.replace("{rand6}", rand6)
    out = out.replace("{randnum}", randnum)
    return out


def wordlist_stats(cfg: dict) -> dict:
    """Baca wordlist CSV, return statistik: total, used, available."""
    tm = cfg.get("temp_mail", {})
    wl_path = tm.get("wordlist_file", "")
    if not wl_path:
        return {"total": 0, "used": 0, "available": 0, "error": "wordlist_file kosong"}

    if not os.path.isabs(wl_path):
        wl_path = os.path.join(_BASE, wl_path)

    if not os.path.exists(wl_path):
        return {"total": 0, "used": 0, "available": 0, "error": f"file tidak ada: {wl_path}"}

    total = 0
    used = 0
    available = 0
    with open(wl_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            nama = (row.get("nama") or "").strip()
            if not nama:
                continue
            total += 1
            status = (row.get("status") or "").strip().lower()
            if status == "used":
                used += 1
            else:
                available += 1

    return {"total": total, "used": used, "available": available}


def wordlist_reset(cfg: dict) -> int:
    """Reset semua status wordlist menjadi kosong. Return jumlah yang di-reset."""
    tm = cfg.get("temp_mail", {})
    wl_path = tm.get("wordlist_file", "")
    if not wl_path:
        return 0
    if not os.path.isabs(wl_path):
        wl_path = os.path.join(_BASE, wl_path)
    if not os.path.exists(wl_path):
        return 0

    count = 0
    rows = []
    with open(wl_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("status") or "").strip().lower() == "used":
                row["status"] = ""
                count += 1
            rows.append(row)

    clean_fields = ["nomor", "nama", "status"]
    with open(wl_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=clean_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    return count


# ---------------------------------------------------------------------------
# Dedup: cek SEMUA 3 file
# ---------------------------------------------------------------------------
def _existing_values_json(cfg: dict, field: str) -> set:
    """Baca nilai field dari JSON."""
    vals = set()
    for a in load_accounts(cfg):
        v = a.get(field)
        if v:
            vals.add(v)
    return vals


def _existing_values_csv(cfg: dict, field: str) -> set:
    """Baca nilai field dari CSV."""
    path = _csv_path(cfg)
    vals = set()
    if not os.path.exists(path):
        return vals
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                v = row.get(field)
                if v:
                    vals.add(v)
    except Exception:
        pass
    return vals


def _existing_values_wai(cfg: dict, field: str) -> set:
    """Baca nilai field dari workers_ai.txt.

    Format: name|apiKey|accountId
    field 'email' tidak ada langsung, tapi 'name' = prefix email.
    Jadi untuk dedup email, kita cek apakah name (baris pertama) cocok
    dengan prefix email akun baru.
    """
    path = _wai_path(cfg)
    vals = set()
    if not os.path.exists(path):
        return vals
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("|")
                if not parts:
                    continue
                # name = parts[0], apiKey = parts[1], accountId = parts[2]
                # Untuk dedup email: kita simpan name (prefix email)
                # dan nanti cek apakah email baru dimulai dengan name yang sudah ada
                if field == "email":
                    vals.add(parts[0])  # simpan name sebagai prefix
                elif field == "account_id" and len(parts) >= 3:
                    vals.add(parts[2])
                elif field == "workers_ai_token" and len(parts) >= 2:
                    vals.add(parts[1])
    except Exception:
        pass
    return vals


def _is_duplicate(cfg: dict, account: dict) -> bool:
    """Cek apakah akun sudah ada di salah satu dari 3 file."""
    field = cfg.get("storage", {}).get("dedupe_field", "email")
    val = account.get(field)
    if not val:
        return False

    # Cek JSON
    if val in _existing_values_json(cfg, field):
        return True

    # Cek CSV
    if val in _existing_values_csv(cfg, field):
        return True

    # Cek workers_ai.txt
    # Untuk email: name = prefix sebelum @
    if field == "email":
        name = val.split("@")[0] if "@" in val else val
        existing_names = _existing_values_wai(cfg, "email")
        if name in existing_names:
            return True
    else:
        if val in _existing_values_wai(cfg, field):
            return True

    return False


# ---------------------------------------------------------------------------
# Load accounts (JSON)
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


# ---------------------------------------------------------------------------
# Append: tulis ke SEMUA 3 file (dedup + append)
# ---------------------------------------------------------------------------
def _append_json(cfg: dict, account: dict) -> None:
    """Append ke accounts.json."""
    accounts = load_accounts(cfg)
    accounts.append(account)
    with open(_accounts_path(cfg), "w", encoding="utf-8") as f:
        json.dump(accounts, f, indent=2, ensure_ascii=False)


def _append_csv(cfg: dict, account: dict) -> None:
    """Append ke accounts.csv (dengan header, dedup, tidak hapus lama)."""
    path = _csv_path(cfg)
    row = {c: account.get(c, "") for c in CSV_COLUMNS}

    if os.path.exists(path):
        # Baca yang ada, tambah baris baru
        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        rows.append(row)
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    else:
        # File baru: tulis header + 1 baris
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            writer.writerow(row)


def _append_wai(cfg: dict, account: dict) -> None:
    """Append ke workers_ai.txt (format name|apiKey|accountId, 1 baris, no header)."""
    path = _wai_path(cfg)
    fmt = cfg.get("storage", {}).get("workers_ai_format", "{name}|{apiKey}|{accountId}")

    # Isi placeholder
    email = account.get("email", "")
    name = email.split("@")[0] if "@" in email else email
    line = fmt
    line = line.replace("{name}", name)
    line = line.replace("{apiKey}", account.get("workers_ai_token", ""))
    line = line.replace("{accountId}", account.get("account_id", ""))

    # Append (tambah baris di akhir, tidak hapus lama)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def append_account(cfg: dict, account: dict) -> dict:
    """
    Append satu akun ke SEMUA 3 file (JSON + CSV + workers_ai.txt).

    Aturan:
      - Dedup: cek field dedupe_field (default email) di SEMUA 3 file.
        Kalau sudah ada di salah satu → SKIP semua.
      - Append: tidak hapus data lama, hanya tambah baris baru.
      - workers_ai.txt: 1 akun = 1 baris, format name|apiKey|accountId.

    Returns:
        {'added': bool, 'reason': str}
    """
    dedupe_field = cfg.get("storage", {}).get("dedupe_field", "email")
    key = account.get(dedupe_field)

    if not key:
        return {"added": False, "reason": f"field dedupe '{dedupe_field}' kosong"}

    # Cek duplikat di SEMUA 3 file
    if _is_duplicate(cfg, account):
        return {"added": False, "reason": f"duplikat: {key}"}

    # Tambah timestamp
    account["created_at"] = account.get("created_at") or datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # Tulis ke SEMUA 3 file
    stor = cfg.get("storage", {})

    # 1. JSON (selalu)
    _append_json(cfg, account)

    # 2. CSV (jika enabled)
    if stor.get("csv_enabled", True):
        _append_csv(cfg, account)

    # 3. workers_ai.txt (jika enabled)
    if stor.get("workers_ai_enabled", True):
        _append_wai(cfg, account)

    return {"added": True, "reason": "ok"}


def accounts_open_count(cfg: dict) -> int:
    return len(load_accounts(cfg))
