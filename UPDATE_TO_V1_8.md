# SCAT OMR V1.8 — phone-photograph alignment fix

## Problem diagnosed
All eight newly supplied backside photos failed both the old pink-divider search and timing-rail fallback, despite clearly visible answer bubbles. Their camera perspective, margins, brightness and row spacing differ from the original three samples.

## Fix
- Adds `template_alignment.py`: identifies printed elements on the fixed OMR using SIFT feature matching and RANSAC geometric registration. Two **signature-free answer-grid reference images** are included in `assets`.
- Updates `app.py`: use the previous working scanners first; only if both reject the image, automatically use the new reference-photo alignment.
- Updates `bubble_sheet.py`: allows Gemini's independent bubble review crops to use the same geometric positions when the old grid detector fails. Gemini receives the *image crops only*, not Python's selected answers or the answer key.
- Existing answer-key CSVs, Google Sheets database connection, one-click saving, and result PDF are unchanged.
- Scanner does **not** silently choose an answer if bubbles are multiply marked or unclear. Those cases still go to the staff review page.

## Windows installation (drop-in update)
1. Close the running Streamlit process (Ctrl+C).
2. Back up your existing project folder.
3. Extract `SCAT_OMR_V1_8_Photo_Alignment_Fix.zip`.
4. Copy `app.py`, `bubble_sheet.py`, and `template_alignment.py` into your **existing application folder** (the one containing `app.py`). Replace matching files.
5. Copy `assets/back_template_1.jpg` and `assets/back_template_2.jpg` into the existing application's `assets` folder (create it if missing). **Do not delete the existing Sri Chaitanya logo.**
6. Keep `.streamlit/secrets.toml`, `answer_keys`, `data`, and the Google Sheet unchanged.
7. Restart from the project directory: `py -m streamlit run app.py`.
8. Test with `Front-1.jpeg` and `Back-1.jpeg`. Repeat with the others and verify the marks manually before relying on them.

## What was tested
- Both fallback scanners failed on all eight new back photographs in the previous V1.7 implementation.
- The new fallback successfully registered the 50 question positions for all eight new backs.
- Sample 5 flagged Question 43 as multiple-marked; Sample 8 flagged Question 46 as multiple-marked. Sample 7 included one blank answer. All must still be confirmed against original paper/known manual checking.
- Contact sheets for Gemini rendered successfully on all eight.
- Existing 19 automated project tests passed.
- The three old back-side photographs also still generated contact sheets.

## Scope and limitations
This is an offline code-level test, **not** a verified 100%-accurate evaluation against manually checked answers. The Streamlit UI and live Gemini API were not run end-to-end in this environment. Staff must confirm student names/roll numbers, particularly when the front-side boxes were left blank. In the event of insufficient image registration confidence, the app will ask for a new photo rather than invent an answer.
