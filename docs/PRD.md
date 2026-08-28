# Cloudflare Workspace Helper — PRD

**Status:** Draft

**Owner:** JhopanStore

**Target:** Local Windows client + optional VPS self-hosted temp mail

## 1. Ringkasan

Cloudflare Workspace Helper membantu owner akun Cloudflare mengelola email domain sendiri dan resource Cloudflare melalui API resmi. Sistem mengganti ketergantungan pada provider disposable public dengan domain email milik user dan inbox self-hosted.

Produk tidak membuat akun massal, tidak menghindari deteksi anti-abuse, tidak memecahkan CAPTCHA/Turnstile, dan tidak mengambil Global API Key.

## 2. Problem

- Provider temporary email publik mudah masuk daftar disposable-email dan gagal dipakai pada layanan penting.
- Owner butuh alamat random pada domain sendiri untuk testing inbox dan menerima email verifikasi sah.
- Membaca inbox dan mengambil link/kode secara manual lambat.
- Global API Key terlalu luas untuk automation; API Token scoped lebih aman.
- Temp mail self-hosted sudah tersedia di repo `TempMailByJhopanstore`, tetapi belum punya adapter ke helper lokal.

## 3. Goal

1. Pakai domain milik user untuk address random/catch-all.
2. Terima dan baca email melalui API self-hosted.
3. Ekstrak link atau OTP dari email milik user secara deterministik.
4. Validasi Cloudflare API Token scoped.
5. Jalankan task Cloudflare resmi pada account/zone yang user pilih.
6. Simpan secret lokal dan minimalkan permission.

## 4. Non-goal

- Signup akun Cloudflare otomatis.
- Bypass Turnstile, CAPTCHA, anti-bot, atau email-verification control.
- Mengambil Global API Key dari UI.
- Menjual/menjadi public disposable mail provider.
- Mengirim outbound email massal.
- Menyediakan SMTP lewat Cloudflare Tunnel.

## 5. Persona

### Owner/admin

Punya domain, VPS, dan akun Cloudflare sah. Butuh workflow cepat untuk testing atau mengelola resource sendiri.

### Developer

Membangun integration yang perlu inbox test address serta API Token dengan permission minimum.

## 6. User stories

### US-01 — Konfigurasi domain

Sebagai owner, saya memasukkan domain dan Mail API endpoint agar helper mengetahui sumber inbox.

**Acceptance criteria**
- Validasi domain dengan format DNS valid.
- Validasi HTTPS API base URL.
- Secret disimpan di `.env` lokal.

### US-02 — Generate inbox address

Sebagai owner, saya membuat address `prefix-random@domain.tld` untuk test.

**Acceptance criteria**
- Local-part hanya lowercase alphanumeric dan `-`.
- Tidak overwrite inbox existing tanpa flag explicit.
- Address dicetak tanpa password/secret lain.

### US-03 — Poll inbox

Sebagai owner, saya menunggu email pada address tertentu.

**Acceptance criteria**
- Timeout configurable.
- Filter sender dan subject optional.
- Tampilkan subject, sender, received time.
- Tidak log isi email penuh secara default.

### US-04 — Extract verification artifact

Sebagai owner, saya membaca link atau OTP dari email yang saya terima.

**Acceptance criteria**
- Link extraction skip tracking/unsubscribe/documentation link bila pattern tujuan disediakan.
- OTP extraction hanya dari message yang match filter.
- Return error jelas jika banyak candidate atau tidak ada candidate.

### US-05 — Validate Cloudflare API Token

Sebagai owner, saya memastikan token scoped valid sebelum task berjalan.

**Acceptance criteria**
- Request ke endpoint verify resmi Cloudflare API.
- Tidak pernah print full token.
- Tampilkan token status dan expiry jika tersedia.

### US-06 — Select account

Sebagai owner, saya memilih satu account Cloudflare yang diizinkan token.

**Acceptance criteria**
- Account ID dapat berasal dari `.env` atau CLI flag.
- Validasi account ID format 32 hex chars.
- API client menolak account di luar scope token.

### US-07 — Browser helper

Sebagai owner, saya membuka browser headed untuk task UI manual.

**Acceptance criteria**
- Browser tidak menjalankan bypass challenge.
- Browser dapat membuka dashboard dan tab inbox terpisah.
- User melakukan login/challenge/verification sendiri.

### US-08 — Audit lokal

Sebagai owner, saya melihat event log tanpa leak secret.

**Acceptance criteria**
- Log timestamp, operation, status.
- Redact token, password, full OTP, dan URL query token.
- File log dapat dimatikan.

## 7. Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-01 | Read `.env` custom-domain mail config | Must |
| FR-02 | Generate random inbox address | Must |
| FR-03 | Poll self-hosted inbox API | Must |
| FR-04 | Read message detail and attachment metadata | Should |
| FR-05 | Extract link/OTP with filters | Must |
| FR-06 | Validate Cloudflare scoped API Token | Must |
| FR-07 | List scoped accounts via official API | Should |
| FR-08 | Browser headed helper tabs | Should |
| FR-09 | Local redacted JSON event log | Should |
| FR-10 | Replace mail.tm adapter without changing callers | Must |

## 8. Non-functional requirements

- Python stdlib first; `requests` existing dependency accepted.
- No secret in source, README example, test fixture, screenshots, or Git.
- 10 second default HTTP timeout; retry only idempotent GET.
- Inbox polling interval >= 3 seconds.
- Windows-first commands supported.
- All network boundary responses validated before use.

## 9. Security requirements

- Use Cloudflare API Token, never request Global API Key.
- `.env` must be gitignored before real secrets are added.
- Redact `Authorization`, `token`, password, OTP, and URL query values in logs.
- Self-hosted mail API must require auth when public.
- Nginx UI/API should be HTTPS.
- SMTP port 25 only on VPS public IP; no local tunnel workaround.

## 10. Success metrics

- Owner can receive one test email at generated custom-domain address.
- Helper detects matching message within 30 seconds under normal delivery.
- Token validation succeeds with a least-privilege token.
- No full secret appears in default logs.
- Unit tests cover parser and redaction logic.

## 11. Dependencies

- Domain registered by user.
- Public VPS if receiving SMTP directly.
- `TempMailByJhopanstore` deployed and healthy.
- DNS MX/A/SPF/DMARC records.
- Existing verified Cloudflare account and scoped API Token.

## 12. Risks and mitigation

| Risk | Impact | Mitigation |
|---|---|---|
| VPS port 25 blocked | No inbound email | Verify provider policy before deploy; use provider that permits port 25 |
| New domain reputation | Service verification may still reject it | Use domain for legitimate workflow; do not automate abuse |
| Mail API exposed publicly | Inbox disclosure | JWT/API auth, HTTPS, firewall, strong admin password |
| Broad CF token leaked | Account compromise | Least privilege, `.env`, rotate immediately on exposure |
| UI selectors change | Browser helper breaks | Keep browser helper optional; use API for supported operations |

## 13. Release criteria

- `docs/API_CONTRACT.md` approved.
- `.env.example` complete and secret-free.
- Unit tests pass.
- Health check succeeds against deployed TempMailByJhopanstore.
- Manual test: create inbox, receive test email, extract known link/OTP.
- Manual test: validate scoped Cloudflare token.