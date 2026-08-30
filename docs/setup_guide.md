# Operational Setup Guide

This guide walks you through setting up the Google Form, configuring privacy settings, distributing the form to your paid Substack subscribers, and managing ongoing subscriber updates.

---

## 1. Google Form Creation & Privacy Configuration

### Step 1: Create the Google Form
1. Go to [Google Forms](https://forms.google.com/) and create a **Blank form**.
2. **Title**: `TradingView Indicator Access Request`
3. **Description**: 
   > *"As an active paid subscriber to [Your Substack Name], you get complimentary access to our invite-only TradingView indicator. Please provide your details below to activate your access."*

### Step 2: Add Form Questions
Create exactly two short-answer fields:
1. **Question 1**: `Substack Email Address`
   - Type: **Short answer**
   - Required: **Yes**
   - Description / Helper text: *"The email address associated with your paid Substack subscription."*
2. **Question 2**: `TradingView Username`
   - Type: **Short answer**
   - Required: **Yes**
   - Description / Helper text: *"Your exact TradingView username (found on your TradingView profile, case-sensitive)."*

*(Note: Google Forms automatically creates and populates **Column A: Timestamp** for every submission).*

---

### Step 3: Privacy & Security Checklist (CRITICAL)
To ensure respondents cannot see other subscribers' information:

1. Click the **Settings** tab at the top of the Google Form.
2. Under **Responses**:
   - ❌ **"Allow response editing"**: Optional (leave ON if you want users to fix typos, or OFF).
   - ❌ **"Limit to 1 response"**: Optional (requires Google login; leave OFF if you want users without a Google account to still submit).
3. Under **Presentation**:
   - 🔒 **"Share results summary with respondents" / "View summary charts and text responses"**: **MUST BE OFF** (Disabled by default).
4. Link to Google Sheet:
   - Click the **Responses** tab $\rightarrow$ click **Link to Sheets** $\rightarrow$ **Create a new spreadsheet**.
   - Open the newly created Google Sheet.
   - Click **Share** (top right) and verify that **General access** is set to **"Restricted"** (only your account has access). **Do NOT** set to "Anyone with the link can view".

---

## 2. Communicating with Existing Paid Subscribers

Broadcast an email exclusively to your current paid members:

1. In your Substack dashboard, click **New post**.
2. Draft the post using the template below.
3. Click **Continue** to go to the publish screen.
4. Set **Audience** to: **Paid subscribers only**.
5. Check: **Send via email** (optionally check *"Send as email only (don't publish on website)"*).
6. Click **Send now**.

### Email Template: Existing Subscribers

```text
Subject: [Action Required] Claim your private TradingView indicator access

Hi everyone,

Thank you for being a paid subscriber to [Publication Name]! 

As part of your subscription, you have exclusive access to our custom TradingView indicator: [Indicator Name].

### How to Claim Your Access:
1. Fill out this quick 30-second form: [INSERT GOOGLE FORM LINK HERE]
2. Provide your Substack email and your exact TradingView username.

Once submitted, your invite will be activated within 72 hours. You will find the indicator on TradingView under:
Charts -> Indicators -> Invite-Only Scripts -> [Indicator Name].

If you don't have a TradingView account yet, you can create a free one at https://www.tradingview.com.

Best regards,
[Your Name / Publication Name]
```

---

## 3. Automating for Future Paid Subscribers

Ensure any new member joining in the future automatically receives the form link:

1. In your Substack dashboard, go to **Settings** $\rightarrow$ **Welcome Emails** (or search for *"Welcome email to paid subscribers"*).
2. Edit the **Welcome email to paid subscribers** to include the section below.

### Welcome Email Snippet:

```text
---
### 📈 Claim Your TradingView Indicator Perk
As an active paid subscriber, you get free access to our private TradingView indicator: [Indicator Name].

👉 Submit your TradingView username here: [INSERT GOOGLE FORM LINK HERE]

Access will be granted within 72 hours of submission.
---
```

---

## 4. Automated Sync Configuration

The sync engine automatically pulls paid subscribers from Substack and form submissions from Google Sheets.

### Step 1: Substack Session Cookie
1. In your browser, log into your Substack publication dashboard (`https://yourpublication.substack.com/publish`).
2. Open Developer Tools (**Cmd + Option + I** on Mac, or **F12** on Windows/Linux).
3. Go to **Application** (Chrome/Brave) or **Storage** (Firefox) $\rightarrow$ **Cookies** $\rightarrow$ `https://substack.com`.
4. Copy the value of `substack.sid`.
5. Set in `.env`:
   ```env
   SUBSTACK_SUBDOMAIN=yourpublication
   SUBSTACK_SESSION_COOKIE=s%3A...
   ```

### Step 2: TradingView Credentials
1. Log into TradingView (`https://www.tradingview.com`).
2. Open Developer Tools $\rightarrow$ **Application** $\rightarrow$ **Cookies** $\rightarrow$ `https://www.tradingview.com`.
3. Copy `sessionid`.
4. Set in `.env`:
   ```env
   TRADINGVIEW_SESSIONID=your_sessionid
   TRADINGVIEW_SCRIPT_ID=PUB_xxxxxxxx
   ```

### Step 3: Google Sheets Secure Web App Endpoint (Takes 60 Seconds)
Because your Google Sheet is strictly private and restricted, create a private Web App endpoint with a secret passphrase:

1. Open your linked Google Sheet.
2. In the top menu, click **Extensions $\rightarrow$ Apps Script**.
3. Replace any code in the editor with this 7-line snippet:
   ```javascript
   function doGet(e) {
     var secret = e.parameter.key;
     if (secret !== "YOUR_SECRET_PASSPHRASE") {
       return ContentService.createTextOutput("Unauthorized").setMimeType(ContentService.MimeType.TEXT);
     }
     var data = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet().getDataRange().getValues();
     return ContentService.createTextOutput(JSON.stringify(data)).setMimeType(ContentService.MimeType.JSON);
   }
   ```
4. Replace `"YOUR_SECRET_PASSPHRASE"` with any random secret string (e.g. `tv_sync_pass_987654`).
5. Click **Deploy (top right) $\rightarrow$ New Deployment**:
   - Select type: **Web app** (click the gear icon $\rightarrow$ Web app).
   - **Execute as**: `Me (<your_email>)`.
   - **Who has access**: `Anyone`. *(Note: Your sheet remains 100% private; only requests with your secret passphrase can retrieve the data).*
   - Click **Deploy** and authorize access.
6. Copy the **Web App URL** and add your secret key:
   ```env
   GOOGLE_SHEET_WEBAPP_URL=https://script.google.com/macros/s/AKfycb.../exec?key=YOUR_SECRET_PASSPHRASE
   ```

### Step 4: Run the Sync Engine
```bash
# Verify authentication
python3 -m src.cli verify-auth

# Preview proposed access changes
python3 -m src.cli diff

# Apply changes automatically
python3 -m src.cli sync --apply
```

---

## 5. How to Handle Subscriber Username Updates

Google Forms automatically records an auto-generated **Timestamp** in Column A for every submission. Because the sync engine uses the earliest submission to lock the handle against form spam, follow these steps to update a subscriber's handle upon request:

1. Open your private Google Sheet.
2. Press **Cmd + F** (or **Ctrl + F**) to search for the subscriber's email.
3. Update their handle:
   - **If the email appears in 1 row**: Update the **TradingView Username** cell in that row.
   - **If the email appears in multiple rows** (from past duplicate submissions): Update the **top-most row (earliest Timestamp)**, or simply delete the extra duplicate rows below it.
4. Run the sync command:
   ```bash
   python -m src.cli sync --apply
   ```
   *The sync engine will detect your update in the Sheet, automatically revoke access from their old TradingView username, and grant access to their new username.*
