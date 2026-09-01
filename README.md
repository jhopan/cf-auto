# cf-auto

Automation Cloudflare berbasis **Camoufox** (anti-detect browser) + **TempMailByJhopanstore** (temp mail self-hosted). Dari signup sampai dapat semua credential dalam 1 perintah.

## Apa yang Dilakukan

1 akun Cloudflare lengkap, otomatis:

| Step | Modul | Hasil |
|---|---|---|
| 1 | Signup | Email + password + solve Turnstile |
| 2 | Konfirmasi Email | Verify via workers-and-pages (tab sama) |
| 3 | Global API Key | Kode verifikasi email + Turnstile → API Key |
| 4 | Workers AI Token | Token `cfut_...` (nama: jhopanstore) |
| 5 | Worker Token | Token "Edit Cloudflare Workers" |

Output 3 format (dedup, append, tidak hapus data lama):

- `accounts.json` — JSON lengkap semua field
- `accounts.csv` — CSV untuk spreadsheet
- `workers_ai.txt` — format `name|apiKey|accountId` per baris

## Struktur

```text
cf-auto/
├── runner.py              # Jalankan flow lengkap (1 atau multi akun)
├── menucfauto.py          # Menu interaktif atur semua config
├── cf_config.py           # Load/save config + storage + wordlist
├── config.json            # Config utama (gitignored)
├── config.example.json    # Template config
├── wordlist.csv           # Wordlist nama email (nomor,nama,status)
├── install.sh             # Installer cross-platform
├── requirements.txt
├── cf-modules/
│   ├── cf_helpers.py      # Shared: Turnstile solver, fill_input, dll
│   ├── cf_signup.py       # Modul 1: Signup + Turnstile
│   ├── cf_confirm_email.py# Modul 2: Konfirmasi email
│   ├── cf_get_apikey.py   # Modul 3: Global API Key
│   ├── cf_workers_ai.py   # Modul 4: Workers AI Token
│   └── cf_worker_token.py # Modul 5: Worker Token
└── docs/
```

## Install

```bash
git clone https://github.com/jhopan/cf-auto.git
cd cf-auto
bash install.sh
```

`install.sh` otomatis:
- Deteksi OS (Windows git-bash / Linux / macOS)
- Cari Python (skip alias palsu Microsoft Store)
- `pip install -r requirements.txt` — camoufox[geoip], playwright, requests
- `python -m camoufox fetch` — download binary browser
- Linux: `playwright install-deps`
- Copy `config.example.json` → `config.json`

## Setup Config

```bash
python menucfauto.py
```

Menu:
```text
1. Lihat config sekarang
2. Atur Temp Mail (endpoint/domain/key)
3. Atur Password (random/fixed)
4. Atur Browser (headless/proxy)
5. Atur Penamaan Email (format/wordlist)
6. Atur Storage (file output)
7. Lihat akun tersimpan
8. Jalankan runner (1/multi/wordlist)
9. Keluar
```

### Penamaan Email (menu 5)

2 mode:

- **format** — template dengan placeholder:
  - `{prefix}{rand8}` → `cfw2sf4s6q`
  - Placeholder: `{prefix}` `{rand8}` `{rand6}` `{randnum}`
- **wordlist** — baca `wordlist.csv`, kolom `nomor,nama,status`:
  - Cari baris status kosong → pakai nama → tandai `used`
  - Edit di Excel: tambah baris, kolom status kosong
  - Sub-menu: lihat stats, lihat semua nama, reset status
  - Kalau semua `used` → fallback random otomatis

### Storage (menu 6)

| File | Format |
|---|---|
| `accounts.json` | JSON array semua field |
| `accounts.csv` | CSV header semua kolom |
| `workers_ai.txt` | `name\|apiKey\|accountId` per baris, no header |

Dedup by `email` — kalau sudah ada di salah satu file, skip di semua. Data lama tidak pernah dihapus.

## Jalankan

```bash
# Via menu
python menucfauto.py
# → menu 8: pilih 1 akun / jumlah N / sampai wordlist habis

# Atau langsung
python runner.py               # 1 akun
python runner.py --count 5    # 5 akun
```

Contoh hasil:

```text
═══ Akun #1 SELESAI ═══
  Email         : citra@renunganbot.qzz.io
  Global API Key: cfk_2WNc...33e8
  Workers AI    : cfut_1EsU828...ab8f
  Worker Token  : cfut_3OWzlwI...5f96
  Account ID    : 923926bdabb3b4f5af5df988cb4bffda
  → accounts.json
  → accounts.csv
  → workers_ai.txt (format: name|apiKey|accountId)
```

## Config Reference

`config.json`:

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
  "browser": { "headless": false, "proxy": "" },
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

Temp mail API butuh header `X-Email-API-Key`. Endpoint yang dipakai: `POST /api/inbox`, `GET /api/inbox/{email}/wait`, `DELETE /api/inbox/{email}`.

## Per-OS Notes

| OS | headless | Catatan |
|---|---|---|
| Windows | `false` (headed) | Headless Camoufox bisa crash GPU compositor |
| Linux/VPS | `true` | Set via `menucfauto.py` menu 4 |
| macOS | `false` | Sama Windows |

Binary Camoufox tersimpan global di `AppData\Local\camoufox` (Windows) atau `~/.cache/camoufox` (Linux) — dipakai semua project, tidak per-user project.

## Security

- `config.json`, `accounts.json`, `accounts.csv`, `workers_ai.txt`, `runner_result.json` → **gitignored**
- Jangan commit credential
- Ganti API key temp mail jika bocor
- Gunakan hanya untuk akun dan domain milik sendiri; ikuti ToS Cloudflare

## Troubleshooting

| Masalah | Solusi |
|---|---|
| `NS_ERROR_ABORT` saat navigasi | Retry otomatis 3x + jeda 5s; biasanya timing redirect CF |
| Turnstile tidak solved | Solver klik iframe (28,28) → retry; kalau gagal tunggu manual |
| `Tidak ada domain mail yang berhasil membuat inbox` | Cek `api_key` di config + server temp mail up |
| `wordlist CSV harus punya kolom` | Format: header `nomor,nama,status` |
| Login gagal | Password random tiap akun; cek `accounts.json` untuk password akun |
