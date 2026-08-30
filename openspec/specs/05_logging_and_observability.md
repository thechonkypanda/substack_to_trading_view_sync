# Spec 05: Logging, Error Handling & Observability

## 1. Overview
This specification defines the error handling, structured logging, and observability standards across all sync engine components, ensuring that any service interruption, schema drift, or expired credential is immediately logged with actionable remediation steps.

---

## 2. Log Destinations & Format

### 2.1 File & Console Output
- **Log Files**:
  - `logs/sync.log`: Standard runtime logs (INFO, WARNING, ERROR).
  - `logs/sync_errors.log`: Detailed error tracebacks and payload drift dumps.
- **Log Format (JSON Lines or Standard Structured)**:
  ```text
  [2026-08-29 21:25:00] [ERROR] [SubstackClient] AuthError: Substack session cookie expired (HTTP 401). Remediation: Update SUBSTACK_SESSION_COOKIE in .env.
  ```

### 2.2 Security & Credential Redaction
- Loggers must **never** write raw session tokens or secret keys in plain text.
- Tokens must be masked: `substack.sid=s%3A***` and `sessionid=abc***`.

---

## 3. Error Categories & Handling Rules

### 3.1 Authentication & Session Expiration (`AUTH_EXPIRED` - Fail-Fast Policy)
* **Triggers**: Substack or TradingView returns HTTP `401 Unauthorized` or `403 Forbidden`.
* **Behavior (Strict Fail-Fast)**:
  1. **Zero Retries for Auth Errors**: Unlike network glitches or rate limits (429), session expiration (401/403) must **never retry**. The client aborts immediately on the very first 401 response.
  2. **Pre-Flight Check**: Live execution (`sync --apply`) performs a lightweight pre-flight authentication verification before modifying any users.
  3. **Immediate Loop Halting**: If a session expires mid-sync while iterating over grants/revokes, execution halts instantly to avoid spamming the API with failed requests.
  4. Write an `ERROR` entry to `logs/sync_errors.log` and console with actionable remediation instructions.
  5. Output clean remediation guidance:
     ```text
     ❌ [ERROR] Authentication Failed: Session cookie expired (HTTP 401).
     👉 Solution: Refresh your session cookie in your browser and update .env.
     ```

---

### 3.2 API Schema Drift & Contract Changes (`SCHEMA_DRIFT`)
* **Triggers**: Substack, Google Sheets, or TradingView API returns an unexpected payload structure, missing keys, or modified data types that fail schema validation.
* **Behavior**:
  1. Log the exact schema discrepancy and dump the unrecognized payload structure to `logs/sync_errors.log`.
  2. Output a warning to the operator indicating the endpoint and field that changed:
     ```text
     ⚠️ [WARNING] API Response Schema Drift Detected on endpoint: GET /api/v1/subscribers
     👉 Details: Missing expected key 'membership_state'. Full raw payload saved to logs/sync_errors.log.
     ```
  3. Prevent silent failures or bad data propagation.

---

### 3.3 Invalid TradingView Usernames (`INVALID_HANDLE`)
* **Triggers**: TradingView returns `user_not_found` when attempting to grant invite-only access.
* **Behavior**:
  1. Log a `WARNING` entry with the subscriber's email and submitted username.
  2. Record the entry in the diff output under `⚠️ Invalid TradingView Usernames`.
  3. Continue processing the remainder of the subscriber batch without crashing.

---

### 3.4 Rate Limits & Network Retries (`RATE_LIMITED` / `NETWORK_RETRY`)
* **Triggers**: HTTP `429 Too Many Requests` or connection timeouts.
* **Behavior**:
  1. Log retry attempt count and backoff delay (e.g. `[WARNING] Rate limit reached. Retrying in 2.0s (Attempt 1/3)...`).
  2. Max 3 exponential retries before failing gracefully.
