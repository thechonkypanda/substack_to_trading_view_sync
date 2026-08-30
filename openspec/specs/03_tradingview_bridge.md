# Spec 03: TradingView Bridge API & Access Management Contract

## 1. Overview
This specification defines the contract for interacting with TradingView's invite-only Pine Script access management endpoints.

---

## 2. Authentication & Session Management

TradingView's script access management is protected by session cookies:

### 2.1 Required Credentials
- `TRADINGVIEW_SESSIONID`: The active `sessionid` cookie string from an authenticated browser session (stored in `.env` / environment variable).
- `TRADINGVIEW_SESSIONID_SIGN`: The `sessionid_sign` cookie string (if present in modern TradingView sessions).
- `TRADINGVIEW_SCRIPT_ID`: The unique identifier or published publication ID of the invite-only indicator (e.g. `PUB_xxxxxxxx`).

---

## 3. Endpoints & Operations

### 3.1 Fetch Current Authorized Users
* **Endpoint**: `POST /pine_perm/list_users/` (or script manage modal API)
* **Headers**:
  * `User-Agent`: Standard modern browser User-Agent
  * `Cookie`: `sessionid={TRADINGVIEW_SESSIONID}; ...`
  * `Origin`: `https://www.tradingview.com`
* **Response**: List of objects containing `username`, `expiration` (timestamp or null).

---

### 3.2 Add User Access (Grant)
* **Endpoint**: `POST /pine_perm/add_user/`
* **Payload (JSON / Form Encoded)**:
  ```json
  {
    "pine_id": "{TRADINGVIEW_SCRIPT_ID}",
    "username": "{username}",
    "expiration": null
  }
  ```
* **Success Criteria**: HTTP 200 with status `ok` or user listed in updated permissions.
* **Error Handling**:
  - `404 / user_not_found`: The TradingView username does not exist on TradingView. Flag as `INVALID_USERNAME` and continue without failing the entire batch.
  - `429 / rate_limit`: Exponential backoff and retry up to 3 times before stopping.

---

### 3.3 Remove User Access (Revoke)
* **Endpoint**: `POST /pine_perm/remove_user/`
* **Payload**:
  ```json
  {
    "pine_id": "{TRADINGVIEW_SCRIPT_ID}",
    "username": "{username}"
  }
  ```
* **Success Criteria**: HTTP 200 with status `ok`.

---

## 4. Bridge Modes

1. **`DryRunBridge` (Default)**:
   - Does not send any modifying network requests.
   - Logs simulated grant and revoke actions.
2. **`LiveHttpBridge`**:
   - Executes real HTTP requests against TradingView endpoints using valid session cookies.
3. **`MockBridge` (Testing)**:
   - In-memory mock for automated unit and integration tests.
