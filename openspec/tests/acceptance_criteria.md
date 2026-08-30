# Spec Acceptance Criteria & Test Scenarios

## 1. Ingestion & Authentication Scenarios
- [ ] **Substack Direct API Ingestion**: Successfully fetch and parse paginated paid subscribers using the `substack.sid` session cookie.
- [ ] **Substack Auth Expiration Handling**: When Substack returns HTTP 401/403, the tool must catch the error gracefully, log it to `logs/sync_errors.log`, and prompt the user to refresh their cookie in `.env`.
- [ ] **Google Sheets Live Ingestion**: Successfully fetch form responses directly from Google Sheets API.

---

## 2. Data Normalization & Anti-Spam Scenarios
- [ ] **Email Lowercasing & Trimming**: An input email like `"  Subscriber@Domain.COM "` must normalize to `"subscriber@domain.com"`.
- [ ] **Username Cleanup**: An input handle like `"@trader_pro "` must normalize to `"trader_pro"`.
- [ ] **Deduplication (First Submission Locks Handle)**: When a subscriber submits the Google Form at `10:00 AM` with `tv_user_old` and later at `11:00 AM` with `tv_user_new`, the system locks to `tv_user_old` and silently ignores the duplicate submission.

---

## 3. Reconciliation & Diff Scenarios
- [ ] **New Paid Subscriber Granted Access**: Active paid subscriber in Substack + valid Google Form submission + not yet in TradingView $\rightarrow$ Action: `GRANT`.
- [ ] **Already Granted No-Op**: Active paid subscriber in Substack + valid Google Form submission + already in TradingView $\rightarrow$ Action: `NO_OP`.
- [ ] **Canceled Subscriber Revoked**: Canceled/expired subscriber in Substack + currently in TradingView $\rightarrow$ Action: `REVOKE`.
- [ ] **Free Subscriber Rejected**: Free subscriber who filled out the form $\rightarrow$ Action: `UNMATCHED_FORM_SUBMISSION` (no access granted).
- [ ] **Unregistered Paid Subscriber Flagged**: Paid subscriber who has not filled out the form $\rightarrow$ Action: `UNREGISTERED_PAID`.

---

## 4. Safety & Dry Run Scenarios
- [ ] **Dry-Run by Default**: Invoking `sync` without `--apply` must execute in simulation mode without making live API calls.
- [ ] **Live Execution**: Invoking `sync --apply` must execute grant and revoke operations via the TradingView bridge.

---

## 5. Observability & Logging Scenarios
- [ ] **Expired Session Cookie Logging**: Any 401 response from Substack or TradingView writes an error log entry with remediation instructions.
- [ ] **API Schema Drift Logging**: If an external API response fails expected schema validation, the raw payload and schema error are dumped to `logs/sync_errors.log`.
- [ ] **Credential Redaction**: Session tokens and cookies are masked in all generated log files.
