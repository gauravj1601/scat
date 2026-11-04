# SCAT OMR — Version 2.0: Answer key versions update immediately

This update fixes answer-key paper version selection. It **does not** change OMR scanning, Gemini verification, Google Sheets credentials, saving, or PDF generation.

## What was happening

The uploaded `SCAT_8th_Answer_Key.csv` specifies **SCAT / 8th / Code A / Paper_Version 1**. The earlier Evaluate tab defaulted to Class 10 and showed only its `2026-v1`. The version selector was also inside a form, so changing class did not refresh the versions until the form was submitted. Additionally, a CSV being validated did **not** mean it had been published to Google Sheets.

## Update existing Windows project

1. Stop Streamlit (Ctrl+C).
2. Back up your working project directory.
3. Copy the **two files** from this update into the project folder that contains your existing `app.py`:
   - `app.py`
   - `answer_key_utils.py`
   Choose **Replace files**.
4. Do not replace `.streamlit/secrets.toml`, `data/`, `assets/`, or `answer_keys/`.
5. Run `py -m streamlit run app.py`.

## How to publish Class 8

1. Log in as Admin and open **Answer Key Admin**.
2. Upload your `SCAT_8th_Answer_Key.csv`.
3. The app displays **CSV format validated**. This means only that the file is readable.
4. Click **Publish answer key**. For a brand-new exam/class/code/version, no replacement checkbox is necessary.
5. After a successful Google Sheets write, the app refreshes and automatically selects **SCAT → 8th → A → 1**.
6. The Answer Key Admin table will show the Class 8 key as well.

If you had already successfully published the file, simply select **SCAT → 8th → A** in Evaluate OMR and the version dropdown will show **1**.

To upload the **next Class 8 paper** as another key, change `Paper_Version` for **all questions** in the new CSV to `2` (or another unique label). Reusing `1` means replacing existing Class 8 version 1, for which the application asks for confirmation.

## GitHub / Streamlit Cloud

If you have deployed online, commit and push these same two updated Python files to GitHub. Streamlit Cloud will rebuild from the repository. Keep credentials in Streamlit Secrets only.

## Validation

- Parsed the user-supplied Class 8 CSV: 50 questions, one key for `SCAT/8th/A/1`.
- Existing key `SCAT/10th/A/2026-v1` remains separate.
- 30 automated Python unit tests passed.
- Live Google Sheets and Streamlit browser were not available for an end-to-end test here.
