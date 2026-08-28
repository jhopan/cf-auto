# API Contract

This document defines the helper-facing interface. Verify deployed `TempMailByJhopanstore` payloads before coding; normalize differences in one adapter only.

## 1. Configuration

```dotenv
MAIL_API_BASE=https://mail.example.com/api
MAIL_API_TOKEN=replace_me
MAIL_DOMAIN=example.com
CF_API_TOKEN=replace_me
CF_ACCOUNT_ID=32_hex_chars
```

## 2. Normalized mail adapter

Python caller should use this minimal interface:

```python
class MailClient:
    def create_address(self, prefix: str = "cf") -> str: ...
    def list_messages(self, address: str) -> list["MessageSummary"]: ...
    def get_message(self, message_id: str) -> "Message": ...
```

Do not leak provider-specific JSON outside adapter.

## 3. Types

```json
{
  "message_summary": {
    "id": "string",
    "to": "user@example.com",
    "from": "noreply@example.net",
    "subject": "Verification code",
    "received_at": "2026-08-19T12:00:00Z",
    "seen": false
  },
  "message": {
    "id": "string",
    "from": "noreply@example.net",
    "to": ["user@example.com"],
    "subject": "Verification code",
    "text": "plain text body",
    "html": "html body",
    "received_at": "2026-08-19T12:00:00Z",
    "attachments": []
  }
}
```

## 4. TempMailByJhopanstore routes

Repo frontend currently proxies these routes to Go receiver:

| Operation | Helper route | Receiver route | Auth |
|---|---|---|---|
| Login | `POST /api/auth/login` | deployment-dependent | credentials/JWT |
| Current user | `GET /api/auth/me` | deployment-dependent | Bearer JWT |
| Inbox | `GET /api/inbox/{email}` | `GET /inbox/{email}` | Bearer JWT |
| Message | `GET /api/message/{id}` | deployment-dependent | Bearer JWT |
| Attachment | `GET /api/attachment/{id}` | deployment-dependent | Bearer JWT |
| Health | `GET /api/health` | deployment-dependent | none or restricted |
| Inbox events | `GET /api/sse/{email}` | deployment-dependent | Bearer JWT |

Use frontend `/api/*` over HTTPS. Do not expose receiver port 8080 publicly.

### Inbox request

```bash
curl --fail-with-body \
  -H "Authorization: Bearer $MAIL_API_TOKEN" \
  "$MAIL_API_BASE/inbox/user%40example.com"
```

### Message request

```bash
curl --fail-with-body \
  -H "Authorization: Bearer $MAIL_API_TOKEN" \
  "$MAIL_API_BASE/message/123"
```

## 5. Cloudflare API Token routes

Never use Global API Key.

### Validate token

```bash
curl --fail-with-body \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  https://api.cloudflare.com/client/v4/user/tokens/verify
```

Expected normalized result:

```json
{
  "success": true,
  "result": {
    "id": "token-id",
    "status": "active"
  }
}
```

### List accounts token can access

```bash
curl --fail-with-body \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  https://api.cloudflare.com/client/v4/accounts
```

The helper must compare user-selected `CF_ACCOUNT_ID` against this response before mutation.

## 6. Error contract

```json
{
  "error": {
    "code": "mail_timeout",
    "message": "No matching message before 120 seconds.",
    "details": {
      "address": "cf-abc@example.com",
      "sender_filter": "noreply@example.net",
      "subject_filter": "verification"
    }
  }
}
```

Error codes:

| Code | Meaning | Retry |
|---|---|---|
| `config_invalid` | Missing/malformed local config | No |
| `mail_unauthorized` | Mail JWT/API token invalid | No |
| `mail_inbox_not_found` | Address does not exist | No |
| `mail_timeout` | No matching message before deadline | Optional user retry |
| `mail_ambiguous` | More than one candidate | User selects |
| `cf_token_invalid` | CF token rejected | No |
| `cf_scope_denied` | Token lacks permission/account scope | No |
| `cf_rate_limited` | CF API 429 | GET only, bounded retry |
| `network_error` | Transport failure | Bounded retry safe GET only |

## 7. Link/OTP parsing contract

Input:

```python
extract_artifact(
    message: Message,
    kind: Literal["url", "otp"],
    sender_filter: str | None,
    allowed_hosts: set[str] | None,
    otp_length: int | None,
) -> str
```

Rules:

- Only parse matched message.
- URL allowed-host filter must be explicit for sensitive workflow.
- Drop `unsubscribe`, `privacy`, `help`, and documentation URLs only when caller asks for an action URL.
- Return ambiguity error for multiple allowed links.
- OTP is returned to caller but redacted in logs.

## 8. Browser helper contract

Browser helper only opens URLs:

```text
open-dashboard(account_id)
open-inbox(url)
open-url(url)
```

It must not automate CAPTCHA, Turnstile, login, email verification, or secret extraction.