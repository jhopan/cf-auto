# Testing Strategy

## Scope

Test supported capabilities only:

- local config validation;
- self-hosted inbox API adapter;
- email link/OTP parsing;
- redaction;
- scoped Cloudflare API Token client;
- manual browser helper smoke test.

Do not test CAPTCHA bypass, signup automation, Global API Key extraction, or account verification automation.

## Test layers

| Layer | Tool | Network | Purpose |
|---|---|---|---|
| Unit | `pytest` | No | Parser, config, redaction, response normalization |
| Adapter | `pytest` + mocked `requests.Session` | No | HTTP request shape and errors |
| Integration | CLI + deployed mail platform | Yes | Receive/read own test email |
| Manual smoke | Headed browser | Yes | Open dashboard/inbox tabs for user-driven workflow |

## Fixtures

Use only redacted fixture data:

```text
docs/fixtures/
├── tempmail-inbox.json
├── tempmail-message.html
├── tempmail-message.json
└── cloudflare-token-verify.json
```

Forbidden in fixtures:

- live API tokens;
- passwords;
- full verification links with query token;
- real email body containing personal data;
- account IDs not owned by test environment.

## Required unit tests

### Config

```text
missing CF_API_TOKEN             -> ConfigError
malformed CF_ACCOUNT_ID          -> ConfigError
MAIL_API_BASE with http://       -> ConfigError for production mode
valid .env                       -> Settings object
```

### Self-hosted mail adapter

```text
login sends expected JSON
inbox request sends Bearer JWT
message response normalizes html list/string
401 becomes MailUnauthorized
404 becomes InboxNotFound
bad JSON becomes MailProtocolError
```

### Parser

```text
one allowed URL                  -> return URL
tracking + allowed URL           -> return allowed URL
two allowed URLs                 -> AmbiguousArtifact
7 digit OTP                      -> return exact OTP
6 digit text when 7 requested    -> NotFound
```

### Redaction

```text
Bearer abc                       -> Bearer [REDACTED]
?token=abc                       -> ?token=[REDACTED]
password=abc                     -> password=[REDACTED]
1234567 OTP                      -> [OTP_REDACTED]
```

### Cloudflare client

```text
verify endpoint uses Bearer auth
verify success false             -> TokenInvalid
account not in listed accounts   -> ScopeDenied
429 GET with Retry-After         -> bounded retry
mutation never auto-retries      -> one request
```

## Commands

Install development test dependency only when Phase 2 starts:

```bash
C:\Python314\python.exe -m pip install pytest
```

Run all:

```bash
cd C:\Users\ACER\cf-auto
C:\Python314\python.exe -m pytest -q
```

Run one file:

```bash
C:\Python314\python.exe -m pytest tests\test_email_parser.py -v
```

Syntax check:

```bash
C:\Python314\python.exe -m py_compile src\*.py
```

## Manual integration checklist

### Mail platform

1. Confirm MX and A DNS records resolve.
2. Confirm VPS accepts TCP/25.
3. Create a test inbox address.
4. Send a message from a separate legitimate mailbox.
5. Confirm Maddy and receiver logs show delivery.
6. Fetch message through authenticated inbox API.
7. Verify attachment metadata, HTML, and plaintext behavior.

### Cloudflare API

1. Create a least-privilege token manually.
2. Store token only in local `.env`.
3. Run `cf token verify`.
4. Run `cf accounts list`.
5. Confirm selected account ID is in response.
6. Execute one read-only call before any mutation.

### Browser helper

1. Start headed browser.
2. Open Cloudflare dashboard tab.
3. Open self-hosted inbox UI tab.
4. User manually handles login/challenges/verification.
5. Confirm browser helper never logs passwords, OTPs, or full URL query strings.

## Exit criteria

- All unit tests pass.
- Integration receive test passes twice from separate senders.
- Scoped token validation passes.
- Logs checked for secrets.
- Backup restore test completed before production use.

## Incident response

If credential leaks:

1. Revoke Cloudflare token immediately.
2. Change TempMail admin password.
3. Rotate mail API JWT secret if applicable.
4. Remove secret from Git history if committed.
5. Reissue only minimum-scope credentials.