# Cloudflare Workspace Helper

Tool lokal untuk membantu workflow Cloudflare milik sendiri:

- menerima email pada domain milik sendiri;
- membaca inbox melalui API temp-mail self-hosted;
- membuka dashboard dalam browser visible;
- memakai Cloudflare API Token scoped yang dibuat user sendiri;
- menyimpan hasil lokal tanpa mengirim credential ke layanan lain.

Project ini **bukan** alat mass-signup, bypass Turnstile/CAPTCHA, atau pengambilan Global API Key otomatis. Pembuatan akun, verifikasi identitas, dan challenge Cloudflare harus dilakukan user di UI resmi.

## Status

| Area | Status |
|---|---|
| Camoufox headed browser smoke test | Ada |
| Temp mail mail.tm test adapter | Ada, hanya development |
| Temp mail domain sendiri | Direncanakan |
| Inbox API adapter | Direncanakan |
| Cloudflare API Token workflow | Direncanakan |
| Global API Key automation | Tidak didukung |
| Turnstile bypass | Tidak didukung |

Lihat `docs/PRD.md`, `docs/ARCHITECTURE.md`, dan `docs/DEVELOPMENT.md`.

## Prinsip desain

1. **Domain sendiri.** Jangan bergantung pada domain publik disposable seperti mail.tm untuk workflow penting.
2. **API Token scoped.** Pakai token dengan permission minimum. Jangan simpan Global API Key.
3. **Manual trust boundary.** Signup, login, email verification, CAPTCHA, pembayaran, dan challenge dilakukan user.
4. **Local secret storage.** `.env` dan output credential tidak masuk Git.
5. **Browser visible.** Mode headed untuk langkah interaktif. Tidak ada klaim bypass challenge.

## Struktur

```text
cf-auto/
├── cf_automation.py       # Eksperimen browser lama; jangan gunakan untuk bypass challenge
├── temp_mail.py           # Adapter mail.tm development; akan diganti adapter self-hosted
├── test_signup.py         # Smoke test lama; bukan flow produksi
├── requirements.txt
├── README.md
└── docs/
    ├── PRD.md
    ├── ARCHITECTURE.md
    ├── API_CONTRACT.md
    ├── DEVELOPMENT.md
    └── TESTING.md
```

## Prasyarat

- Windows 10/11 atau Linux.
- Python 3.11+.
- Akun Cloudflare milik user yang sudah verified.
- Cloudflare API Token scoped yang dibuat manual.
- Domain milik user dengan MX record valid.
- Temp mail self-hosted atau email forwarder yang menerima domain tersebut.

## Install development

```bash
cd C:\Users\ACER\cf-auto
C:\Python314\python.exe -m pip install -r requirements.txt
C:\Python314\python.exe -m camoufox fetch
```

Windows: gunakan browser headed. Headless Camoufox dapat crash karena GPU/software compositor host.

## Credential model

Buat Cloudflare API Token di dashboard resmi:

1. Profile → API Tokens → Create Token.
2. Pilih template atau custom permission sesuai task.
3. Batasi account dan zone yang memang dipakai.
4. Simpan token ke `.env`, bukan source code atau `cf_accounts.json`.

Contoh `.env` lokal:

```dotenv
CF_API_TOKEN=replace_me
CF_ACCOUNT_ID=replace_me
MAIL_API_BASE=https://mail.example.com/api
MAIL_API_TOKEN=replace_me
MAIL_DOMAIN=example.com
```

Jangan commit `.env`.

## Domain email sendiri

Rekomendasi: deploy `TempMailByJhopanstore` pada VPS Ubuntu dengan domain baru milik sendiri. Domain harus punya:

- `A` record untuk UI/API;
- `MX` record ke hostname mail;
- port SMTP 25 terbuka inbound;
- SPF dan DMARC;
- TLS jika menyediakan UI publik.

Cloudflare Tunnel tidak dapat menerima SMTP. Tunnel hanya cocok HTTP/HTTPS. MX harus menunjuk ke host dengan IP publik yang menerima port 25.

Detail integrasi: `docs/ARCHITECTURE.md`.

## Pengembangan berikutnya

```text
1. Deploy TempMailByJhopanstore + domain sendiri.
2. Tambah self-hosted inbox adapter.
3. Tambah API Token config validation.
4. Tambah CLI inbox polling dan email-link extraction.
5. Tambah Cloudflare API client untuk resource milik user.
```

Rencana task lengkap: `docs/DEVELOPMENT.md`.

## Security

- Rotasi token jika pernah masuk terminal log, screenshot, Git, atau chat.
- Gunakan `.gitignore` untuk `.env`, `*.token`, `cf_accounts.json`, `debug/`, dan result files.
- Batasi token berdasarkan account/zone dan permission.
- Jangan menjalankan mail server di host tanpa firewall, update security, dan backup database.

## License dan penggunaan

Gunakan hanya untuk akun, domain, token, dan email yang Anda miliki atau punya izin eksplisit. Ikuti Cloudflare Terms dan kebijakan provider email.