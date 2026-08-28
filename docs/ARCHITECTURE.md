# Architecture

## Scope

Cloudflare Workspace Helper uses a custom-domain inbox and Cloudflare official API. Browser use is optional and manual at trust boundaries.

```text
                         DNS
                          │
                  MX mail.example.com
                          │
Internet SMTP ───────────► VPS public IP:25
                          │
                       Maddy SMTP
                          │ LMTP :8024
                          ▼
                 TempMailByJhopanstore
                   Go receiver + Postgres
                          │ HTTPS + JWT
                          ▼
                 Inbox API / SSE endpoint
                          │
                    Local helper (Python)
                  ┌───────┴────────┐
                  │                │
            CLI / polling     Browser headed
                  │                │
                  ▼                ▼
          parsed email      User-controlled Cloudflare UI

Local helper ── HTTPS ──► Cloudflare official API
                           (scoped API Token)
```

## Components

| Component | Responsibility | Must not do |
|---|---|---|
| `TempMailByJhopanstore` | Receive SMTP, persist inbox/message, serve authenticated API | Public unauthenticated inbox access |
| Maddy | Accept inbound SMTP port 25, pass message to LMTP receiver | Outbound bulk mail |
| PostgreSQL | Store inboxes/messages/attachments | Store raw Cloudflare secrets |
| Nginx | TLS, reverse proxy UI/API | Proxy SMTP |
| Helper CLI | Generate address, poll/read inbox, call official CF API | Bypass CAPTCHA, account signup automation |
| Camoufox headed browser | User-visible dashboard/inbox helper tabs | Solve challenges programmatically |
| Cloudflare API | Manage owner-approved resources | Use Global API Key |

## Network requirements

### VPS

| Port | Direction | Service | Required |
|---|---|---|---|
| 25/TCP | inbound | Maddy SMTP | Yes, for direct MX delivery |
| 80/TCP | inbound | Nginx / ACME | Recommended |
| 443/TCP | inbound | Nginx UI/API | Yes |
| 8024/TCP | localhost only | LMTP receiver | Yes |
| 8080/TCP | localhost only | Go receiver API | Yes |
| 5432/TCP | localhost only | PostgreSQL | Yes |

Do not expose 8024, 8080, or 5432 to Internet.

### Cloudflare Tunnel limitation

Cloudflare Tunnel supports HTTP/HTTPS/TCP application use cases. It cannot act as public SMTP MX receiver. DNS MX must resolve to a public mail host accepting TCP/25.

## DNS

Example domain `mail.example.com`:

```dns
mail.example.com.     A      VPS_PUBLIC_IP
example.com.          MX 10  mail.example.com.
example.com.          TXT    "v=spf1 mx -all"
_dmarc.example.com.   TXT    "v=DMARC1; p=none; rua=mailto:dmarc@example.com"
```

Start with `p=none`; move to stricter DMARC only after legitimate mail flow is confirmed. SMTP host A record must be DNS-only, never proxied through Cloudflare.

## Data flow

### Receive email

1. Sender resolves domain MX.
2. Sender connects VPS TCP/25.
3. Maddy accepts recipient at configured local domain.
4. Maddy forwards MIME message to Go LMTP receiver.
5. Receiver parses message and stores normalized fields in PostgreSQL.
6. Receiver API exposes inbox and message data to authenticated caller.

### Read verification artifact

1. Helper generates `cf-<random>@domain`.
2. User enters address in an authorized workflow.
3. Helper polls own inbox API using JWT/API token.
4. Helper filters by sender/subject supplied by user.
5. Helper extracts link or OTP from matching message.
6. User decides whether to open link or enter code.

### Call Cloudflare API

1. User creates scoped token manually in Cloudflare dashboard.
2. Helper loads token from `.env`.
3. Helper validates token via official verify endpoint.
4. Helper performs allowlisted API operation for specified account/zone.
5. Helper logs redacted result locally.

## Proposed Python modules

```text
src/
├── config.py             # load and validate .env
├── mail_client.py        # protocol/adapter interface
├── mail_selfhosted.py    # TempMailByJhopanstore API adapter
├── mail_tm.py            # development-only adapter; eventually remove
├── email_parser.py       # link/OTP extraction, URL filtering
├── cf_client.py          # official CF API Token client
├── redact.py             # secret redaction
├── cli.py                # argparse commands
└── browser_helper.py     # opens headed tabs only

tests/
├── test_config.py
├── test_email_parser.py
├── test_redact.py
├── test_mail_selfhosted.py
└── test_cf_client.py
```

No class hierarchy unless adapter replacement needs it. A small `Protocol` or two functions is enough.

## Secrets

```dotenv
CF_API_TOKEN=
CF_ACCOUNT_ID=
MAIL_API_BASE=https://mail.example.com/api
MAIL_API_TOKEN=
MAIL_DOMAIN=example.com
```

- `.env` local only.
- `.env.example` has blank values only.
- Token values redacted in logs.
- Rotate token after accidental terminal/chat/Git exposure.

## API authentication

Temp mail platform already exposes auth and inbox endpoints. Before integration, confirm actual route response payloads against deployed version. Client must not rely on stale README assumptions.

Expected client operations:

```text
POST /api/auth/login
GET  /api/inbox/{email}
GET  /api/message/{id}
GET  /api/health
```

See `API_CONTRACT.md` for proposed normalized interface.

## Failure handling

| Failure | Client behavior |
|---|---|
| Mail API 401/403 | Stop; ask user to refresh auth config |
| Mail API 404 inbox | Return explicit inbox-not-found error |
| No message before timeout | Return timeout with sender/subject filters shown |
| Multiple matching messages | Return candidates; never guess silently |
| CF token invalid | Stop before resource mutation |
| CF API 429 | Honor `Retry-After`, bounded retry on safe GET only |
| SMTP port 25 blocked | Deployment health check fails with remediation |

## Observability

- Nginx access/error logs.
- `journalctl -u maddy -f`.
- `journalctl -u tempmail-receiver -f`.
- `journalctl -u tempmail-frontend -f`.
- Postgres backup before migration.
- Helper JSONL audit events with redaction.

## Security boundaries

| Boundary | Owner action | Automation action |
|---|---|---|
| Account signup | User | None |
| Login / MFA / CAPTCHA | User | Open visible browser only |
| Email verification | User approves link/code use | Read own inbox only |
| API permission | User creates scoped token | Validate/use token only |
| Domain/DNS | User owns domain and authorizes DNS change | Apply explicit requested record change only |

## Upgrade path

Initial release uses polling. Add SSE inbox stream only after polling adapter and tests are stable. Add webhook only when one real consumer requires it.