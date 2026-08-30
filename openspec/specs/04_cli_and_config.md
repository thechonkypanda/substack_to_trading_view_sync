# Spec 04: CLI Interface & Configuration

## 1. Overview
This specification defines the Command Line Interface (CLI), environment variables, and execution commands for the fully automated sync engine.

---

## 2. Environment & Configuration

Configuration is loaded from a `.env` file or environment variables:

```bash
# Substack Configuration
SUBSTACK_SUBDOMAIN=yourpublication
SUBSTACK_SESSION_COOKIE=s%3Ayoursecretcookie...

# Google Sheets Configuration
GOOGLE_SHEET_ID=your_google_sheet_id
GOOGLE_SERVICE_ACCOUNT_PATH=./credentials/google_service_account.json

# TradingView Configuration
TRADINGVIEW_SESSIONID=your_tradingview_sessionid
TRADINGVIEW_SESSIONID_SIGN=your_tradingview_sessionid_sign
TRADINGVIEW_SCRIPT_ID=PUB_xxxxxxxx
```

---

## 3. CLI Commands

### 3.1 `diff` (Calculate and Preview Changes)
Fetches live data directly from Substack and Google Sheets, checks current TradingView permissions, and prints the proposed diff plan.

```bash
python -m src.cli diff
```

**Output Report**:
- 🟢 **Pending Grants**: Active paid subscribers with a registered TradingView handle.
- 🔴 **Pending Revocations**: Canceled/expired subscribers or handles updated in the Sheet.
- 📋 **Unregistered Paid Subscribers**: Paid subscribers who have not yet submitted the form.
- ⚠️ **Unmatched Form Submissions**: Form submissions from emails without an active paid subscription.

---

### 3.2 `sync` (Apply Changes to TradingView)
Synchronizes permissions with TradingView. Defaults to a safe dry-run preview unless the `--apply` flag is provided.

```bash
# Dry run simulation (safe default)
python -m src.cli sync

# Live execution (applies verified grants and revokes to TradingView)
python -m src.cli sync --apply
```

---

### 3.3 `verify-auth` (Health Check Connections)
Verifies connectivity and authentication with Substack, Google Sheets, and TradingView.

```bash
python -m src.cli verify-auth
```

**Expected Output**:
- `Substack API`: `[OK]` (Connected to `yourpublication.substack.com`)
- `Google Sheets API`: `[OK]` (Retrieved `X` form submissions)
- `TradingView Bridge`: `[OK]` (Authenticated to script `PUB_xxxxxxxx`)
