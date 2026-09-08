<div align="center">

# ☁️ cf-auto

**Cloudflare account factory — signup sampai semua credential, satu perintah.**

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Camoufox](https://img.shields.io/badge/Browser-Camoufox-orange)](https://github.com/daijro/camoufox)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)](#per-os)
[![License](https://img.shields.io/badge/Use-Personal%20Only-red)](#license)

</div>

---

Automation berbasis **Camoufox** (anti-detect Firefox) + **TempMailByJhopanstore** (temp mail self-hosted).
Jalan **headed** di Windows, **virtual display (Xvfb)** di server Linux — tanpa monitor, tanpa minimize-masalah.

## ✨ Apa yang Dilakukan

Satu perintah, 5 modul berurutan, semua credential terkumpul:

```mermaid
flowchart LR
    A[1. Signup\n+ Turnstile] --> B[2. Konfirmasi\nEmail]
    B --> C[3. Global\nAPI Key]
    C --> D[4. Workers AI\nToken]
    D --> E[5. Worker\nToken]
    E --> F[(accounts.json\ncsv + txt)]
```

| # | Modul | Hasil |
|---|---|---|
| 1 | Signup | Akun CF baru + solve Turnstile otomatis |
| 2 | Konfirmasi Email | Verify via workers-and-pages (satu tab, tanpa tab baru) |
| 3 | Global API Key | Kode verifikasi email → modal View → API Key |
| 4 | Workers AI Token | Token `cfut_...` (nama sesuai config) |
| 5 | Worker Token | Template "Edit Cloudflare Workers" + resources otomatis |

## 📦 Output — 3 Format Sinkron

```
cf-auto/
├── accounts.json     ← JSON lengkap (semua field)
├── accounts.csv      ← CSV untuk Excel/Sheets
└── workers_ai.txt    ← name|apiKey|accountId (siap copas)
```

**workers_ai.txt** (1 akun = 1 baris):
```
michael|cfut_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX|022c8d2a183e0f78c9c05187ff726f76
emily|cfut_YYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY|aff95feb33528e6f04cdee01100d3bdf
```

✅ **Dedup** — email dobel ditolak di semua format
✅ **Append** — data lama tidak pernah dihapus
✅ **Konsisten** — ketiga file selalu sinkron

## 🚀 Quick Start

```bash
git clone https://github.com/jhopan/cf-auto.git
cd cf-auto
bash install.sh
python menu.py    # isi API key temp mail + pilih mode browser
```

Buat akun:

```bash
python runner.py --count 1     # 1 akun
python runner.py --count 5     # 5 akun
```

Contoh output:

```text
═══ Akun #1 SELESAI ═══
  Email         : emily@renunganbot.qzz.io
  Global API Key: cfk_PgW0...xxxx
  Workers AI    : cfut_cZbk...xxxx
  Worker Token  : cfut_vG2Y...xxxx
  Account ID    : aff95feb33528e6f04cdee01100d3bdf
  → accounts.json
  → accounts.csv
  → workers_ai.txt (format: name|apiKey|accountId)
```

## 🖥️ Super Menu

```bash
python menu.py
```

```text
====================================================
       MENU CFAUTO
====================================================
  Mode: wordlist | wordlist: 17/20 available
====================================================
  1. Lihat config sekarang
  2. Atur Temp Mail (endpoint/domain/key)
  3. Atur Password (random/fixed)
  4. Atur Browser (visible/headless/virtual)
  5. Atur Penamaan Email (format/wordlist)
  6. Atur Storage (file output)
  7. Lihat akun tersimpan
  8. Jalankan runner (1/multi/wordlist)
  9. Keluar
```

## 🔤 Penamaan Email

Dua mode, diatur via **menu 5**:

**Format** — template dengan placeholder:

| Placeholder | Hasil | Contoh |
|---|---|---|
| `{prefix}` | dari config | `cf` |
| `{rand8}` | 8 char acak | `8g13m7dq` |
| `{rand6}` | 6 char acak | `a3f9x2` |
| `{randnum}` | 6 digit angka | `739214` |

```json
"email_format": "{prefix}{rand8}"   → cfw2sf4s6q@domain.com
```

**Wordlist** — baca `wordlist.csv`, bisa diedit di Excel:

```csv
nomor,nama,status
1,jhon,
2,michael,used
3,sarah,
```

- Baris `status` kosong = available → dipakai → otomatis ditandai `used`
- Habis semua? → fallback random otomatis (tidak pernah berhenti)
- Sub-menu: lihat statistik / reset status

## 🌐 Mode Browser (menu 4)

| Mode | Kegunaan | Turnstile |
|---|---|---|
| `visible` | Windows — lihat browser jalan | ✅ terbaik |
| `virtual` | **Linux/VPS/home server** — Xvfb 1920×1080 otomatis | ✅ terbukti |
| `headless` | tanpa window | ⚠️ lebih sulit, hindari |

> Mode `virtual` memulai Xvfb resolusi penuh sendiri (bukan 1×1 bawaan Camoufox),
> browser headed di atasnya → `visibilityState` selalu `visible` → Turnstile solved
> tanpa dipantau. Xvfb di-kill otomatis setelah selesai.

## ⚙️ Config Reference

<details>
<summary><b>config.json</b> (klik untuk expand)</summary>

```json
{
  "temp_mail": {
    "base_url": "https://tempmail.example.com",
    "api_key": "",
    "domains": ["example.com"],
    "prefix": "cf",
    "email_format": "{prefix}{rand8}",
    "naming_mode": "format",
    "wordlist_file": "wordlist.csv"
  },
  "password": { "mode": "random", "fixed": "", "length": 16 },
  "browser": { "headless": "virtual", "proxy": "" },
  "storage": {
    "accounts_file": "accounts.json",
    "csv_file": "accounts.csv",
    "workers_ai_file": "workers_ai.txt",
    "workers_ai_format": "{name}|{apiKey}|{accountId}",
    "csv_enabled": true,
    "workers_ai_enabled": true,
    "append": true,
    "dedupe_field": "email"
  }
}
```

</details>

<details>
<summary><b>API Temp Mail</b> (TempMailByJhopanstore)</summary>

Header: `X-Email-API-Key: <api_key>`

| Endpoint | Fungsi |
|---|---|
| `POST /api/inbox` | Buat inbox `{username, domain}` |
| `GET /api/inbox/{email}/wait` | Tunggu email masuk (long-poll) |
| `DELETE /api/inbox/{email}` | Hapus inbox |
| `GET /health` | Cek server |

</details>

## 🖥️ Per OS

| | Windows | Linux/VPS |
|---|---|---|
| Mode | `visible` | `virtual` |
| Xvfb | — | ✅ auto-install via install.sh |
| Python deps | global | venv otomatis (PEP 668) |
| Minimize window | ❌ jangan (Turnstile suspend) | tidak relevan — virtual selalu visible |
| Jalankan | `python runner.py` | `./venv/bin/python runner.py` |

## 🏠 Deploy di Home Server

```bash
ssh server-anda
git clone https://github.com/jhopan/cf-auto.git && cd cf-auto
bash install.sh            # venv + camoufox + Xvfb + playwright deps
python menu.py       # menu 2: api key → menu 4: pilih 3 (virtual)
./venv/bin/python runner.py --count 10
```

Bonus: IP residential rumah = trust Cloudflare tinggi = Turnstile lebih ramah daripada VPS datacenter.

## 🧰 Troubleshooting

| Masalah | Solusi |
|---|---|
| `externally-managed-environment` | Sudah otomatis — install.sh buat venv; jalankan via `./venv/bin/python` |
| Turnstile stuck di virtual | Pastikan Xvfb 1920×1080 (runner sudah handle) + jangan headless |
| `Tidak ada domain mail yang berhasil membuat inbox` | Cek `api_key` di config & server up (`/health`) |
| `wordlist CSV harus punya kolom` | Header harus persis: `nomor,nama,status` |
| `NS_ERROR_ABORT` saat navigasi | Retry otomatis 3× + jeda 5s — biarkan script jalan |
| Klik meleset / elemen bergeser | Viewport mismatch — pastikan pakai mode `virtual` (runner set windowSize 1920×1080) |
| Banyak task asyncio error saat exit | Normal saat browser ditutup, abaikan |

## 📁 Struktur Project

```
cf-auto/
├── runner.py              # Flow lengkap 5 modul
├── menu.py          # Super menu interaktif
├── cf_config.py           # Config + storage + wordlist engine
├── install.sh             # Installer cross-platform
├── config.example.json    # Template config
├── wordlist.csv           # Nama email (nomor,nama,status)
├── cf-modules/
│   ├── cf_helpers.py      # Shared: Turnstile solver, fill, click
│   ├── cf_signup.py       # Modul 1
│   ├── cf_confirm_email.py# Modul 2
│   ├── cf_get_apikey.py   # Modul 3
│   ├── cf_workers_ai.py   # Modul 4
│   └── cf_worker_token.py # Modul 5
└── docs/                  # PRD, arsitektur, testing
```

## 🔒 Security

- `config.json`, `accounts.*`, `workers_ai.txt`, `runner_result.json` → **gitignored**, tidak pernah masuk repo
- Password & token hanya tersimpan lokal
- Rotasi API key temp mail jika terpapar log/screenshot
- Gunakan **hanya untuk akun & domain milik sendiri** — ikuti [Cloudflare Terms](https://www.cloudflare.com/terms/)
- Bukan alat untuk mass-abuse; rate Cloudflare & temp mail tetap Anda tanggung jawab

---

<div align="center">

**Credit: JhopanStore** · Temp mail: [TempMailByJhopanstore](https://github.com/jhopan/TempMailByJhopanstore)

</div>
