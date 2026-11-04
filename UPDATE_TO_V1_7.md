# SCAT OMR Portal V1.7 - Auto-Save and Sri Chaitanya PDF Reports

This update is for the **working V1.6 Google Sheets app**. It does **not** change the OMR scanner, Gemini checker, classwise answer keys, passwords or spreadsheet structure.

## What changes for staff

1. Upload the front and back OMR photographs and click **Evaluate OMR**.
2. Review the suggested student information and any doubtful questions, including a **Multiple marked** answer if needed.
3. Click **Confirm details & save result** **once**.
4. The application writes the accepted result to the already-connected Google Sheet **automatically**; there is **no second checkbox or Save button**.
5. **Only after Google Sheets accepts the save**, the marks, percentage and subjectwise scores appear alongside **Download Sri Chaitanya Result PDF**.
6. Previously saved results can be downloaded from **Saved Results > Download a previously saved student result PDF**.

The PDF is a branded A4 report featuring the original Sri Chaitanya logo, exam name, student name, roll number, class, exam date, paper code, marks obtained, maximum marks, percentage and subjectwise performance.

## Install the drop-in update

1. Stop Streamlit (`Ctrl + C`). Make a backup of your current project folder.
2. Extract `SCAT_OMR_V1_7_AutoSave_PDF_Drop_In.zip`.
3. Copy the following **six files** beside the existing `app.py`:
   - `app.py`
   - `result_workflow.py` (**new**)
   - `pdf_report.py` (**new**)
   - `sheets_storage.py`
   - `storage.py`
   - `requirements.txt`
4. Copy the entire new `assets` folder, containing `sri_chaitanya_logo.png`, into your project folder. If the folder exists already, merge rather than delete it.
5. **Do not replace** `.streamlit/secrets.toml`, `answer_keys/`, `data/`, or your current Google Sheet. The deployed answer key and database stay intact.
6. Open the project folder in Command Prompt / VS Code Terminal. Run:
   ```powershell
   py -m pip install -r requirements.txt
   py -m streamlit run app.py
   ```
7. Sign in, scan an OMR, review answers/details, and click **Confirm details & save result**. Check that one new row appears in the `Results` tab. Download its PDF.

## Important safeguards

- **Name and roll number are required before saving.** If either is missing, the operator must fill it in. No fake data will be generated.
- The app **does not show a result or PDF when saving fails**. It shows an error and leaves the review form available for retry.
- Reprocessing the *exact same photograph pair* uses the previously saved result and does not append a duplicate row, but only if identity, exam selection, marks and answers match the stored record. Conflicting cases are sent for administrator attention.
- If the independent check is inconclusive, existing V1.6 policy remains: only an administrator can approve and save that OMR.
- PDF files are generated on demand from saved data, not uploaded as attachments to Google Sheets. The database still stores the same information as before.
- Original OMR photographs are still **not** stored in Google Sheets.

## Testing

- Python compilation and 19 automated tests passed using an in-memory simulated Google Sheets database, including save-once, duplicate reopening, connection failures, and PDF generation.
- The sample PDF was rendered and inspected as a **single A4 page**.
- Live Streamlit browser testing and a real Google Sheet write have **not** been performed in this environment, so please verify the full flow with one sample OMR before broader staff use.
