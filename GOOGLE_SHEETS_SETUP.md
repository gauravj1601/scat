# SCAT OMR V1.6 — Google Sheets database setup

This version keeps the tested V1.5 Python/Gemini OMR evaluation intact. Only persistence changes.
Your Google Spreadsheet stays **private**. It will contain the personal details of students, so do **not** make it public or use "Anyone with the link".

## 1. Make one Google Spreadsheet

Go to https://sheets.google.com and create a blank spreadsheet named **SCAT OMR Results**.
Copy its spreadsheet ID (the long string in the URL between `/d/` and `/edit`).
Leave it blank. The app creates two tabs: `Results` and `AnswerKeys` on first successful connection.

## 2. Create a Google Cloud service account

Open https://console.cloud.google.com/ and create/select a project.
Enable **Google Sheets API** under APIs & Services → Library.
Go to IAM & Admin → Service Accounts → Create Service Account. An ordinary service account is enough; you do not need a project-level Owner/Editor role.
Open the service account → **Keys** → **Add key** → **Create new key** → JSON. Keep the downloaded JSON private.
If your Google Workspace administrator blocks creation of service-account keys, contact them; do not bypass organizational restrictions.

## 3. Share ONLY the spreadsheet

Open your new Google Spreadsheet → **Share** → add the **`client_email`** address from the downloaded JSON → give that email **Editor** access. Keep **General access = Restricted**.

## 4. Edit your existing `.streamlit/secrets.toml`

Keep the existing `APP_PASSWORD`, `ADMIN_PASSWORD`, `GEMINI_API_KEY`, and `GEMINI_MODEL` values unchanged.
Add the following lines at the **bottom**, replacing placeholders with fields copied from the downloaded JSON:

```toml
GSHEETS_SPREADSHEET_ID = "PASTE_ID_FROM_GOOGLE_SHEET_URL"

[gcp_service_account]
type = "service_account"
project_id = "PROJECT_ID_FROM_JSON"
private_key_id = "PRIVATE_KEY_ID_FROM_JSON"
private_key = "-----BEGIN PRIVATE KEY-----\nPRIVATE_KEY_LINES_FROM_JSON\n-----END PRIVATE KEY-----\n"
client_email = "SERVICE_ACCOUNT_EMAIL_FROM_JSON"
client_id = "CLIENT_ID_FROM_JSON"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "CLIENT_CERT_URL_FROM_JSON"
```

For `private_key`, preserve the JSON key exactly, including its `\n` sequences; do not paste actual unescaped line breaks into an ordinary quoted TOML value. You may omit the optional `client_x509_cert_url` entry if it isn't provided in the JSON. If you copied the sample entries, **replace every placeholder**.

**Never send the JSON key or `.streamlit/secrets.toml` to anyone or commit them to GitHub.** The app ignores them via `.gitignore`.

## 5. Install and restart

Copy `app.py`, `sheets_storage.py`, and `requirements.txt` from the update ZIP into your app folder and replace existing files.

```powershell
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

Sign in as Admin. The sidebar should say **Database: Google Sheets (persistent)**.
Save one completed OMR result. It will appear in the `Results` tab of your private Google Spreadsheet. Publishing a key via **Answer Key Admin** will add a record in the `AnswerKeys` tab.

If it says it cannot open the private Google Sheet, first check (a) the spreadsheet ID, (b) Google Sheets API enabled, (c) the sheet shared with the exact service-account email as **Editor**, and (d) the JSON fields in secrets.

## 6. Old saved results (optional)

Your previous `data/scat_results.db` remains untouched. If you already saved results locally and want to copy those records into the new Google Sheet, run from the app folder:

```powershell
py migrate_sqlite_to_sheets.py
```

The migration checks the original image hash to avoid re-copying the same scanned sheet. It does not delete or update your local database. Do this only once after the cloud connection works.

## Important operational notes

- The main Google Sheet is your database. Do **not** edit or reorder the generated header columns in `Results` or `AnswerKeys`.
- It stores **no original OMR images**. It stores the student details, exam metadata, marks, answers, and questionwise evaluation as text.
- Results remain blocked until your existing verification/review and save flow is complete.
- An image-hash precheck prevents ordinary repeated saves; Google Sheets cannot guarantee transactional uniqueness if two operators submit the exact same image at precisely the same moment. This is acceptable for a small internal workflow but merits attention if usage scales.
- Keep only authorized staff on the sheet. Periodically make an offline backup (Google Sheets → File → Download → Excel).
- If using Streamlit Community Cloud later, copy the same secret settings into the app's Cloud secrets. Do not upload the private key to the repository.
