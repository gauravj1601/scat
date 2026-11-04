# Sri Chaitanya Internal OMR Checking — Streamlit MVP

This is a **working first version** built around the actual fixed front/back OMR photos you supplied (two Class 10 student sheets) and the Class 9 / Class 10 SCAT 2026 Code A answer keys.

## What works now

- Browser-based, phone-friendly Streamlit interface with photo upload **or direct phone camera**.
- Select **SCAT / SCIMED / YSTT**, **class**, **paper code A-D**, and **paper version**. Class 9 and Class 10 SCAT Code A version `2026-v1` come preloaded; other combinations require an admin CSV upload.
- Python/OpenCV reads 1–180 bubble positions from the fixed pink-grid answer side; tested on the first 50 questions in both sample OMR photos.
- Python reads the student **name letters and roll-number digits from marked front-side bubbles**, not from unreliable handwriting OCR. Printed `Roll No.` text is located via Tesseract, so Tesseract should be installed.
- Editable student information and question-by-question answer review; **unreadable/multiple markings require correction** before saving.
- Evaluates total / subjectwise marks with the CSV marking rules, including optional bonus keys.
- Save to **local SQLite** or optional **Supabase** for persistence across Streamlit Cloud restarts. Result data is searchable/exportable as CSV.
- Admin uploads/replaces answer-key CSVs without changing Python code. One version is a distinct key. A question paper change should normally get **a new Paper_Version** so historical evaluations stay reproducible.
- Optional Gemini image double-check, **OFF by default**. Gemini receives both images **only after a user clicks the explicit button**. Differences are displayed; Gemini never silently overrides Python results.
- Authenticated access via shared staff/admin passwords, no third-party app analytics, and **original student images are not stored** by default.

## Tested samples (using Class 10 / Code A key)

| Uploaded example | Front name bubbles | Front roll bubbles | Back answers resolved | Preliminary marks |
| --- | --- | --- | --- | --- |
| Sample 1 | All read | All read | 50 / 50 | 22 / 50 |
| Sample 2 | All read | All read | 50 / 50 | 32 / 50 |

These are **automated readings**, not an independently verified accuracy percentage. Before relying on final marks, manually check a reasonable batch of OMRs and retakes with glare, tilt, shadows, multiple marks and light fills. The scanner estimates geometry from the printed red divider lines. If a new photo is significantly cropped, angled or warped, the scanner may fail or require manual correction. For nonstandard photos, use the preview to validate the result rather than treating green circles as definitive proof of correctness.

## Quick start (Windows)

Install **Python 3.11 or 3.12** and (for automatic front-name/roll extraction) **Tesseract OCR for Windows**. Ensure `tesseract.exe` is on `PATH`. Without it, the app still reads the back answers but will ask staff to type the identity details.

From this folder in Command Prompt or PowerShell:

```powershell
py -m pip install -r requirements.txt
mkdir .streamlit
copy secrets.example.toml .streamlit\secrets.toml
```

Edit `.streamlit/secrets.toml`: replace the example passwords. Then:

```powershell
py -m streamlit run app.py
```

Open `http://localhost:8501`. For phones on the same Wi-Fi network you may open `http://YOUR_COMPUTER_LOCAL_IP:8501` if your firewall permits it; for access from outside your local network, deploy the app securely. Never expose the server publicly without authentication.

**Mac/Linux:** use `python3 -m pip install -r requirements.txt`, copy secrets with `cp`, and `python3 -m streamlit run app.py`. Ubuntu's package name is `tesseract-ocr`.

## Streamlit Community Cloud

1. Upload the code files and bundled CSVs to a **private GitHub repository** (do **not** upload actual student OMR photos, API keys, `data/`, or `.streamlit/secrets.toml`).
2. Create a Streamlit Community Cloud app with entrypoint `app.py` and `requirements.txt` / `packages.txt`.
3. Set `APP_PASSWORD` and `ADMIN_PASSWORD` in app Secrets. Use strong distinct values.
4. **For persistent results**, create a Supabase project, run `supabase_schema.sql` in its SQL Editor, and add `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` to the **server-side Streamlit secrets**. This key has broad permissions. Never put it in Git, user-facing code, browser JavaScript or a CSV.
5. Optional: set `GEMINI_API_KEY`; otherwise the rest of the app works without Gemini.

**Important:** Streamlit Community Cloud does **not** guarantee persistence of local SQLite files or uploaded keys across rebuilds. Use Supabase for production internal records; free service tiers have limits and can change. Streamlit shared-password access is an MVP control, not enterprise identity management. Have your organization approve any storage of minors' personal data or sending OMR photos to Gemini.

## Answer key CSV format

Bundled examples: `answer_keys/SCAT_9th_Code_A_Answer_Key.csv`, `answer_keys/SCAT_10th_Code_A_Answer_Key.csv`; blank template: `answer_keys/Answer_Key_Blank_Template.csv`.

Columns:

```csv
Exam_Type,Class,Paper_Code,Paper_Version,Question_No,Subject,Correct_Answer,Marks_Correct,Marks_Wrong
SCAT,10th,A,2026-v1,1,Physics,C,1,0
SCAT,10th,A,2026-v1,2,Physics,A,1,0
```

Rules:
- Each exam+class+paper+version must have **unique, consecutive question numbers beginning at 1**, up to 180.
- `Correct_Answer`: `A`/`B`/`C`/`D`; `BONUS` (full marks regardless of marked answer); or pipe-separated correct answers such as `A|C` (any *single* option in that set is accepted).
- `Marks_Correct` and `Marks_Wrong` are numerical; for negative marking, use `-1` under `Marks_Wrong`. For these sample papers, it is `+1/0`.
- CSV uploads can contain one or more complete paper-version groups.
- Never reuse the old `Paper_Version` for a genuinely new paper unless you intentionally want to overwrite the answer key for that version.

## App flow

1. Log in with staff password.
2. Select exam, class, paper code, version, and exam date.
3. Upload/capture **front** and **back** pictures; keep them upright and fully visible.
4. Click **Scan OMR with Python**.
5. Check extracted name/roll and manually correct any questionable answer in the editable table.
6. Review subjectwise marks, optionally click **Run Gemini double-check**, reconcile any differences, and tick confirmation.
7. Save result to the database. Export a detailed question-level CSV or the summary of saved results.
8. Admins may upload CSV keys from **Answer Key Admin**.

## Limitations / planned improvements

- Verified **visually** on two provided examples only; accuracy on all camera conditions is **not established**.
- Printed `Roll No.` label OCR currently locates the student identity bubble regions. If its printed text is not detected, user must enter the identity manually. School/contact/state fields remain editable; they are **not yet automatically extracted**, unlike the name and roll number. This is intentional to avoid recording inaccurate personal data.
- Full photo and geometry normalization does **not yet** include arbitrary perspective-corner correction or multi-page batch scanning. 51–180 positions are supported by the layout logic, but only 1–50 have been tested against real filled samples.
- Gemini integration is implemented but **not live-tested** because no API key was supplied. API calls may incur cost and require a suitable data-processing agreement/approved tier.
- Local SQLite is for a single-machine prototype. Use Supabase for cloud durability.
- Saved records are not editable via the UI in this MVP. Re-evaluation, duplicate detection across different photographs of the same OMR, and PDF report cards can be added after verification.

## Project files

- `app.py`: Streamlit UI and workflow
- `omr_engine.py`: fixed-layout bubble detection and preview
- `front_reader.py`: name/roll marked bubble extraction
- `answer_key_utils.py`: CSV parsing/validation/marking
- `storage.py`: SQLite or Supabase result and key storage
- `gemini_verify.py`: optional independent second reading
- `supabase_schema.sql`: database setup
- `tests/test_smoke.py`: basic correctness tests

## Privacy

The OMR photos are processed in app server memory, and not written to disk or database by default. The result record stores the student name/roll, exam details, marks, answers, manually entered contact info and a SHA-256 image digest. Avoid putting actual student records into an openly accessible code repository. Network/cloud hosting still means **the uploaded photos reach your server**; click Gemini only if allowed to send photos to Google Gemini API.
