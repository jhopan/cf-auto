# Development Plan

> Goal: replace public disposable-mail dependency with self-hosted custom-domain inbox and official Cloudflare API Token workflow.

## Phase 0 — Clean baseline

### Task 0.1 — Protect local secrets

**Files**
- Create: `.gitignore`
- Create: `.env.example`

**Actions**

```gitignore
.env
cf_accounts.json
test_signup_result.json
debug/
__pycache__/
*.pyc
```

```dotenv
CF_API_TOKEN=
CF_ACCOUNT_ID=
MAIL_API_BASE=
MAIL_API_TOKEN=
MAIL_DOMAIN=
```

**Verify**

```bash
git check-ignore .env debug/step4_verify_page.png
```

Expected: both paths printed after Git init.

### Task 0.2 — Deprecate unsafe experimental entry points

**Files**
- Modify: `cf_automation.py`
- Modify: `test_signup.py`

**Actions**

- Add top-level warning that file is experimental and not production.
- Remove any claim that it bypasses or solves security challenges.
- Do not run it against accounts/services unless user has explicit authorization.

**Verify**

```bash
C:\Python314\python.exe -m py_compile cf_automation.py test_signup.py
```

Expected: exit 0.

## Phase 1 — Deploy custom-domain mail

### Task 1.1 — Provision VPS

**Files**
- No project code.

**Actions**

- Use fresh Ubuntu 22.04/24.04 VPS, minimum 1GB RAM.
- Confirm inbound TCP/25 allowed before installing.
- Apply firewall: public 25, 80, 443 only.

**Verify**

```bash
sudo ss -lntp
sudo ufw status verbose
```

Expected: only required public listeners.

### Task 1.2 — Deploy TempMailByJhopanstore

**Files**
- External repo: `/opt/TempMailByJhopanStore`

**Actions**

```bash
cd /opt
sudo git clone https://github.com/jhopan/TempMailByJhopanstore.git TempMailByJhopanStore
cd TempMailByJhopanStore
sudo bash scripts/setup.sh
sudo bash scripts/start.sh
```

Change default admin password immediately. Do not retain documented default credential.

**Verify**

```bash
curl --fail https://mail.example.com/api/health
sudo systemctl status maddy tempmail-receiver tempmail-frontend nginx --no-pager
```

Expected: healthy HTTP response; services active.

### Task 1.3 — Configure DNS

**Files**
- DNS provider records.

**Actions**

- `A mail.example.com → VPS IP` DNS-only.
- `MX example.com → mail.example.com`.
- SPF and DMARC from `ARCHITECTURE.md`.

**Verify**

```bash
dig +short MX example.com
dig +short A mail.example.com
```

Expected: MX resolves to mail hostname and hostname resolves to VPS.

### Task 1.4 — Receive a real test email

**Files**
- None.

**Actions**

- Create inbox address using platform UI.
- Send email from a separate real mailbox.

**Verify**

```bash
sudo journalctl -u maddy -n 50 --no-pager
sudo journalctl -u tempmail-receiver -n 50 --no-pager
```

Expected: accepted SMTP delivery and persisted message.

## Phase 2 — Add self-hosted adapter

### Task 2.1 — Capture actual API payloads

**Files**
- Create: `docs/fixtures/tempmail-inbox.json`
- Create: `docs/fixtures/tempmail-message.json`

**Actions**

- Use redacted copies only.
- Fetch deployed `/api/inbox/{email}` and `/api/message/{id}`.
- Update `API_CONTRACT.md` if response differs.

**Verify**

```bash
python -m json.tool docs/fixtures/tempmail-inbox.json > NUL
python -m json.tool docs/fixtures/tempmail-message.json > NUL
```

Expected: both parse.

### Task 2.2 — Write failing adapter tests

**Files**
- Create: `tests/test_mail_selfhosted.py`
- Create: `src/mail_selfhosted.py`

**Test cases**

```python
def test_list_messages_normalizes_provider_payload(): ...
def test_get_message_raises_for_missing_id(): ...
def test_authorization_header_is_bearer_token(): ...
```

**Verify failure**

```bash
C:\Python314\python.exe -m pytest tests/test_mail_selfhosted.py -v
```

Expected: fail because adapter does not exist.

### Task 2.3 — Implement minimum self-hosted adapter

**Files**
- Create: `src/mail_selfhosted.py`

**Actions**

- Use `requests.Session`.
- One request timeout constant.
- Validate response JSON type.
- Normalize to types in `API_CONTRACT.md`.
- No retries on POST/DELETE.

**Verify**

```bash
C:\Python314\python.exe -m pytest tests/test_mail_selfhosted.py -v
```

Expected: pass.

## Phase 3 — Email parser

### Task 3.1 — Write parser tests

**Files**
- Create: `tests/test_email_parser.py`
- Create: `src/email_parser.py`

**Cases**

```python
def test_extracts_one_allowed_https_link(): ...
def test_rejects_documentation_and_unsubscribe_links(): ...
def test_returns_ambiguity_for_two_allowed_links(): ...
def test_extracts_exact_length_otp(): ...
def test_does_not_log_otp_value(): ...
```

### Task 3.2 — Implement minimum parser

**Rules**

- Standard library `html`, `re`, `urllib.parse` only.
- Parse HTML anchors and plaintext URL candidates.
- Require `allowed_hosts` for sensitive action link parsing.
- Return structured result/error; never silently choose among duplicates.

**Verify**

```bash
C:\Python314\python.exe -m pytest tests/test_email_parser.py -v
```

Expected: pass.

## Phase 4 — Cloudflare API Token client

### Task 4.1 — Add config validation tests

**Files**
- Create: `tests/test_config.py`
- Create: `src/config.py`

**Cases**

```python
def test_rejects_missing_cf_api_token(): ...
def test_rejects_invalid_account_id(): ...
def test_rejects_non_https_mail_base_url(): ...
```

### Task 4.2 — Add token validation tests

**Files**
- Create: `tests/test_cf_client.py`
- Create: `src/cf_client.py`

**Cases**

```python
def test_verify_uses_bearer_auth_header(): ...
def test_list_accounts_requires_success_true(): ...
def test_mutation_rejects_unapproved_account_id(): ...
```

### Task 4.3 — Implement official API client

**Rules**

- `GET /client/v4/user/tokens/verify` before operations.
- List `/client/v4/accounts` and require selected ID exists.
- No Global API Key headers.
- GET retry only for transient network errors / 429 with bounded retry.

**Verify**

```bash
C:\Python314\python.exe -m pytest tests/test_cf_client.py -v
```

Expected: pass.

## Phase 5 — CLI

### Task 5.1 — Add command skeleton

**Files**
- Create: `src/cli.py`

Commands:

```text
mail address create --prefix cf
mail inbox wait --address ... --from ... --subject ... --timeout 120
mail message read --id ...
cf token verify
cf accounts list
browser open-dashboard
```

No `signup`, `solve-challenge`, `get-global-api-key`, or equivalent command.

### Task 5.2 — Add redaction

**Files**
- Create: `src/redact.py`
- Create: `tests/test_redact.py`

Redact Bearer tokens, password values, OTPs, query token values, and email bodies by default.

### Task 5.3 — Manual E2E

1. Create custom-domain inbox.
2. Send test email.
3. Poll/read it through CLI.
4. Extract known test OTP/link.
5. Validate user-created scoped Cloudflare token.

## Definition of done

```bash
C:\Python314\python.exe -m pytest -q
C:\Python314\python.exe -m py_compile src\*.py
```

- Tests green.
- `.env` ignored.
- No full secrets in fixtures/logs.
- Real self-hosted mail receive test passed.
- Cloudflare API request uses only scoped token.
- Docs match deployed route payloads.

## Commit plan

```text
chore: add local secret ignore rules
feat: add self-hosted mail adapter
feat: add email artifact parser
feat: add scoped cloudflare api client
feat: add helper cli
Docs: document custom domain deployment
```