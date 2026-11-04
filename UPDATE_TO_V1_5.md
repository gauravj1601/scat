# SCAT OMR Streamlit — Version 1.5 update

## What was fixed

1. After selecting a correction, including **Multiple marked**, click **Confirm answers & show result**. Confirmed multiple marks are recorded as `INVALID` and scored according to the CSV's `Marks_Wrong` rule (zero for the supplied 9th/10th SCAT keys).
2. A missing student name or roll number no longer prevents the **result preview** from being calculated. To **save** a result to the database, enter the real name and roll number in the review form and confirm again. Do not invent a roll number.
3. The Gemini front-photo response now also requests student/parent phone numbers, school name/city, gender and examination centre/city. These are **suggestions**, not guaranteed optical readings. Staff must review/correct them before saving. Unclear fields remain empty; missing optional fields do not block result preview or saving.
4. The same review and saving restrictions are preserved; a second-reader failure is not labelled as independent verification.
5. Database schema, scoring engine, answer key files and login configuration have not been changed.

## Applying the patch (recommended if V1.4 currently launches)

1. Press **Ctrl+C** in the terminal running Streamlit.
2. Back up the current project folder.
3. From `SCAT_OMR_V1_5_Review_and_Details_Fix.zip`, copy **app.py**, **gemini_verify.py**, and **verification.py** into the **same folder** as the existing `app.py`.
4. Select **Replace** when Windows asks.
5. Do **not** replace `.streamlit/secrets.toml`, `data/`, `answer_keys/`, or any student records.
6. Restart with `py -m streamlit run app.py`.
7. Upload the two photos. Press **Evaluate OMR**. Correct the questions, if any. Press **Confirm answers & show result**. The total and subjectwise marks appear. Enter missing identity information and confirm again before **Save verified result**.

## Notes

- New front-data suggestions require a live Gemini request, and should be reviewed against the original photograph.
- Local unit tests and Python image tests passed, but no end-to-end Streamlit browser or live Gemini test was possible in this environment. Validate the updated version with several manually checked OMRs before production use.
- Never paste API keys, portal passwords, or personal student details into screenshots when seeking support.
