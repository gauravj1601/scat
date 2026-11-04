# SCAT OMR — Fix for `cannot import name 'compare' from 'gemini_verify'`

## Cause
The running `app.py` belongs to an earlier version, while `gemini_verify.py` belongs to Version 1.2. The old app imports `compare`; Version 1.2 compares readings using `verification.make_review` instead.

## Fix on Windows (no reinstall needed)
1. Stop the running Streamlit process in Command Prompt with **Ctrl+C**.
2. Back up your current project folder, including your local saved results.
3. Extract `SCAT_OMR_IMPORT_FIX_V1_2.zip`.
4. Open the extracted `SCAT_OMR_IMPORT_FIX_V1_2` folder. Copy **all eight `.py` files** plus `requirements.txt` into the folder containing your current `app.py` (shown in the screenshot as `D:\Codes\SCAT Checking\SCAT Evaluation v 0`). Choose **Replace the files**.
5. **Do not delete or overwrite** `.streamlit/secrets.toml`, `data/`, or `answer_keys/`.
6. In the project's terminal run:

   ```bat
   py -m pip install -r requirements.txt
   py -m streamlit run app.py
   ```

7. Refresh the webpage. The updated application should show the heading **SCAT / SCIMED / YSTT — OMR Results** and the **Evaluate OMR** button.

## Quick check if the same error appears
Open `app.py` and check the import line. The correct Version 1.2 lines are:

```python
from gemini_verify import verify
from verification import make_review, parse_manual, normalized_name
```

If your `app.py` still says `from gemini_verify import verify,compare`, you are running the old file. Check the active working directory (the actual path printed in the Streamlit error); update the files in **that folder**. Do not fix only the import and keep an older app, because the rest of the code may also be mismatched.

## Gemini configuration
In `.streamlit/secrets.toml`, add these lines without a leading `#`:

```toml
GEMINI_API_KEY = "YOUR_NEW_PRIVATE_KEY"
GEMINI_MODEL = "gemini-2.5-flash"
```

**Security:** An earlier screenshot exposed a Gemini key and staff passwords. Revoke/rotate the exposed key and change your login passwords. Never share or commit `secrets.toml`.

In Version 1.2, one `Evaluate OMR` click triggers the Python and Gemini checks in parallel. If verification fails, no marks are published. Disagreements require user confirmation. The app has not been live-tested with your Gemini API key in this environment.

The source files were syntax-checked and 7 non-browser unit tests passed. This repair addresses the import incompatibility; it does not prove that every photographed OMR is accurately read or that the external API will always be available.
