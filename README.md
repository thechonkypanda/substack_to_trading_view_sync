# Substack to TradingView Sync

A Spec-Driven Development (SDD) tool for synchronizing paid Substack subscribers with invite-only TradingView Pine Script indicators via automated APIs.

---

## 📚 Project Structure

```text
.
├── docs/
│   └── setup_guide.md             # Manual operator guide (Google Forms, privacy, Substack email templates)
│
├── openspec/                      # Spec-Driven Development (SDD) source of truth
│   ├── project.md                 # Project architecture, scope & security boundaries
│   ├── specs/
│   │   ├── 01_data_contracts.md   # Google Sheets API & Substack API schemas
│   │   ├── 02_reconciliation_logic.md # Matching, deduplication, spam defense & diff rules
│   │   ├── 03_tradingview_bridge.md   # TradingView API & session auth specs
│   │   ├── 04_cli_and_config.md   # CLI commands & environment variables
│   │   └── 05_logging_and_observability.md # Error handling, session expiration & payload drift logging
│   └── tests/
│       └── acceptance_criteria.md # Test cases & validation rules
│
├── src/                           # Implementation (conforming to openspec/)
└── tests/                         # Automated test suite
```

---

## 🚀 Quick Start

### 1. Human Operator Setup (Google Form & Emails)
Follow the step-by-step instructions in [docs/setup_guide.md](file:///Users/royng/workspace/substack_to_trading_view_sync/docs/setup_guide.md) to:
1. Create your Google Form with privacy settings verified.
2. Send the broadcast email to existing paid subscribers.
3. Update your Substack automated welcome email for new members.

### 2. Configuration (`.env`)
Configure your credentials in `.env`:
```env
SUBSTACK_SUBDOMAIN=yourpublication
SUBSTACK_SESSION_COOKIE=s%3A...
GOOGLE_SHEET_ID=your_google_sheet_id
TRADINGVIEW_SESSIONID=your_tradingview_sessionid
TRADINGVIEW_SCRIPT_ID=PUB_xxxxxxxx
```

### 3. Running the Sync Engine
```bash
# Verify credentials and service reachability
python -m src.cli verify-auth

# Preview proposed access changes without modifying TradingView
python -m src.cli diff

# Apply access changes directly
python -m src.cli sync --apply
```
