# SCAT OMR V1.4: numbered bubble verification and AI quality gate

This update replaces **four Python files** in your current project directory:

- `app.py`
- `gemini_verify.py`
- `verification.py`
- `bubble_sheet.py` (new)

## Windows upgrade

1. Stop Streamlit with Ctrl+C in its terminal.
2. Copy your existing project folder as a backup.
3. Extract the patch ZIP; copy all four `.py` files to the **same directory** where your `app.py` is installed, replacing existing files.
4. **Do not replace** `.streamlit/secrets.toml`, `answer_keys/`, or any local `data/` folder.
5. Restart with `py -m streamlit run app.py`.
6. Select 10th > SCAT > Code A and upload the two OMR photos again.

## What's different

- The primary Python scanner is not replaced.
- A visual question-by-question contact sheet now shows all four bubbles separately for Gemini; bubble 1=A, 2=B, 3=C, 4=D.
- No Python answers or answer keys are sent to Gemini.
- The system catches implausible Gemini output (e.g., almost every answer B, or mass disagreement) and does **not** generate 36 individual review questions from that output.
- If Gemini's entire reading fails its quality checks, staff can inspect/confirm student details but **only an administrator** can approve and save the Python-based result. The saved record clearly states `Python checked; independent check inconclusive`.
- Real bubble ambiguity, unreadable bubbles, or isolated genuine disagreement still require manual review. There is no artificial cap of 1–2; correctness wins over convenience.
- Admin diagnostics show Gemini's readings and the image sent for checking.

## Limitations

This update passed syntax tests, local image-crop generation for the three supplied OMR samples, and synthetic tests simulating Gemini returning B for every question. The **live Gemini response was not tested** because no API credentials were available in this environment. The contact sheet shares geometry from the primary reader, so the Gemini component independently **classifies** bubbles but does not independently locate the grid. Do not treat two-reader agreement as proof of correctness until validated against manually checked sheets.

If Gemini produces 3–5 isolated disagreements, those may still prompt review. The goal is minimal **unnecessary** review, not automatically approving errors.
