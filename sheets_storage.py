"""Private Google Sheets persistence for the internal SCAT OMR Streamlit app.

Two tabs are created automatically in an existing PRIVATE spreadsheet:
  Results    : one row per accepted OMR, including scores and answer details
  AnswerKeys : saved/uploaded key CSVs, keyed by paper version

The service-account JSON stays in Streamlit secrets, not in source code.
Images are NOT uploaded to Google Sheets.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone

from storage import DuplicateResult

RESULT_HEADERS = [
    'Record_ID', 'Saved_At_UTC', 'Exam_Date', 'Exam_Type', 'Class',
    'Paper_Code', 'Paper_Version', 'Roll_No', 'Student_Name',
    'School', 'School_City', 'Student_Phone', 'Parent_Phone', 'Gender',
    'Exam_Center', 'Total', 'Maximum', 'Percentage', 'Verification_Status',
    'Review_Questions', 'Physics', 'Chemistry', 'Maths', 'Biology', 'IQ',
    'Image_Hash', 'Subjects_JSON', 'Answers_JSON', 'Question_Evaluation_JSON',
]
KEY_HEADERS = ['Key_ID', 'Saved_At_UTC', 'CSV_Text']


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _as_text(value):
    if value is None:
        return ''
    return str(value)


def _safe_call(fn, *args, **kwargs):
    """Only retry READ calls; never blindly retry an uncertain append."""
    for attempt in range(3):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            status = getattr(getattr(exc, 'response', None), 'status_code', None)
            if status not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            time.sleep(1.25 * (2 ** attempt))


class SheetsStore:
    is_cloud = True
    is_sheets = True

    def __init__(self, sheet_id: str, service_info: dict, client=None):
        if not sheet_id.strip():
            raise ValueError('GSHEETS_SPREADSHEET_ID is required.')
        if client is None:
            import gspread
            from google.oauth2.service_account import Credentials
            if not service_info or not service_info.get('client_email') or not service_info.get('private_key'):
                raise ValueError('The [gcp_service_account] secrets section is incomplete.')
            creds = Credentials.from_service_account_info(
                service_info, scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            client = gspread.authorize(creds)
        self.client = client
        try:
            self.book = _safe_call(client.open_by_key, sheet_id.strip())
        except Exception as exc:
            raise RuntimeError(
                'Could not open the private Google Sheet. Check spreadsheet ID, '
                'Google Sheets API, and Editor sharing with the service-account email.'
            ) from exc
        self.results = self._tab('Results', RESULT_HEADERS)
        self.keys = self._tab('AnswerKeys', KEY_HEADERS)
        self.sheet_id = sheet_id.strip()

    def _tab(self, title, expected_headers):
        try:
            ws = self.book.worksheet(title)
        except Exception as exc:
            # Only create for a missing tab; propagate permissions/API failures.
            if exc.__class__.__name__ != 'WorksheetNotFound':
                raise
            ws = self.book.add_worksheet(title=title, rows=5000,
                                         cols=max(len(expected_headers) + 2, 12))
        existing = _safe_call(ws.row_values, 1)
        if not existing:
            ws.update(range_name='A1', values=[expected_headers], value_input_option='RAW')
            try:
                ws.freeze(rows=1)
                ws.format('1:1', {'textFormat': {'bold': True},
                                  'backgroundColor': {'red': 0.88, 'green': 0.92, 'blue': 0.98}})
            except Exception:
                pass  # Formatting is optional; persistence must still work.
        elif existing != expected_headers:
            raise RuntimeError(
                f'Tab "{title}" has unexpected columns. Please use a new empty '
                'Google Sheet or retain the generated header row unchanged.'
            )
        return ws

    def _result_row(self, payload):
        subjects = payload.get('subjects') or {}
        def marks(name):
            data = subjects.get(name, {})
            return data.get('marks', '') if isinstance(data, dict) else ''
        maximum = float(payload.get('maximum') or 0)
        total = float(payload.get('total') or 0)
        vals = [
            uuid.uuid4().hex, _now(), payload.get('exam_date', ''),
            payload.get('exam_type', ''), payload.get('class_name', ''),
            payload.get('paper_code', ''), payload.get('paper_version', ''),
            payload.get('roll_number', ''), payload.get('student_name', ''),
            payload.get('school', ''), payload.get('school_city', ''),
            payload.get('student_phone', ''), payload.get('parent_phone', ''),
            payload.get('gender', ''), payload.get('exam_center', ''),
            total, maximum, round(total / maximum * 100, 2) if maximum else '',
            payload.get('verification_status', ''),
            ','.join(map(str, payload.get('reviewed_questions', []))),
            marks('Physics'), marks('Chemistry'), marks('Maths'),
            marks('Biology'), marks('IQ'), payload['image_hash'],
            _json(subjects), _json(payload.get('answers', {})),
            _json(payload.get('question_evaluation', [])),
        ]
        assert len(vals) == len(RESULT_HEADERS)
        # RAW means spreadsheet will not execute a student's name as a formula.
        return [_as_text(v) for v in vals]

    def save_result(self, payload):
        hashval = _as_text(payload.get('image_hash', ''))
        if not hashval:
            raise ValueError('Missing image fingerprint; cannot save result.')
        hashcol = RESULT_HEADERS.index('Image_Hash') + 1
        existing = _safe_call(self.results.col_values, hashcol)
        if hashval in existing[1:]:
            raise DuplicateResult('This exact OMR image was already saved to Google Sheets.')
        # append_row is the only write. Any exception is shown in Streamlit,
        # while the next attempt checks the hash again before writing.
        self.results.append_row(self._result_row(payload), value_input_option='RAW',
                                insert_data_option='INSERT_ROWS')
        return True

    def update_result(self, payload):
        """Replace the existing photo's saved evaluation without appending a row.

        Preserve the record ID and original creation timestamp, so saved-result
        links continue to work after a recheck. No spreadsheet columns change.
        """
        image_hash = _as_text(payload.get('image_hash', ''))
        if not image_hash:
            raise ValueError('Missing image fingerprint; cannot update result.')
        hashes = _safe_call(self.results.col_values, RESULT_HEADERS.index('Image_Hash') + 1)
        try:
            row_idx = len(hashes) - hashes[::-1].index(image_hash)
        except ValueError as exc:
            raise LookupError('Previously saved OMR row could not be found.') from exc
        if row_idx < 2:
            raise LookupError('Previously saved OMR row could not be found.')
        old = _safe_call(self.results.row_values, row_idx)
        if not old or not old[0]:
            raise LookupError('Previously saved OMR row has no record ID.')
        row = self._result_row(payload)
        row[0] = old[0]  # record ID
        row[1] = old[1] if len(old) > 1 else ''  # initial save time
        end_col = 'AC'  # 29 existing columns; do not change the Sheets schema
        self.results.update(range_name=f'A{row_idx}:{end_col}{row_idx}',
                            values=[row], value_input_option='RAW')
        return True

    def list_results(self, limit=500):
        values = _safe_call(self.results.get_all_values)
        if len(values) <= 1:
            return []
        head = {x: i for i, x in enumerate(RESULT_HEADERS)}
        out = []
        for ix, row in reversed(list(enumerate(values[1:], start=2))):
            def get(name):
                i = head[name]
                return row[i] if len(row) > i else ''
            out.append({
                'id': get('Record_ID'), 'submitted_at': get('Saved_At_UTC'),
                'exam_date': get('Exam_Date'), 'exam_type': get('Exam_Type'),
                'class_name': get('Class'), 'paper_code': get('Paper_Code'),
                'paper_version': get('Paper_Version'), 'roll_number': get('Roll_No'),
                'student_name': get('Student_Name'), 'total': get('Total'),
                'maximum': get('Maximum'), 'verification_status': get('Verification_Status'),
                'school': get('School'), 'school_city': get('School_City'),
                'sheet_row': ix,
            })
            if len(out) >= min(limit, 1000):
                break
        return out


    def _saved_payload(self, row):
        """Reconstruct the exact, already-persisted result for PDF or duplicate reuse."""
        h = {name: i for i, name in enumerate(RESULT_HEADERS)}
        def col(name):
            i = h[name]
            return row[i] if i < len(row) else ''
        def parsed(name, default):
            raw = col(name)
            try:
                return json.loads(raw) if raw else default
            except (TypeError, ValueError):
                return default
        return {
            'record_id': col('Record_ID'), 'saved_at_utc': col('Saved_At_UTC'),
            'image_hash': col('Image_Hash'),
            'exam_date': col('Exam_Date'), 'exam_type': col('Exam_Type'),
            'class_name': col('Class'), 'paper_code': col('Paper_Code'),
            'paper_version': col('Paper_Version'),
            'roll_number': col('Roll_No'), 'student_name': col('Student_Name'),
            'school': col('School'), 'school_city': col('School_City'),
            'student_phone': col('Student_Phone'), 'parent_phone': col('Parent_Phone'),
            'gender': col('Gender'), 'exam_center': col('Exam_Center'),
            'total': float(col('Total') or 0), 'maximum': float(col('Maximum') or 0),
            'verification_status': col('Verification_Status'),
            'reviewed_questions': [int(x) for x in col('Review_Questions').split(',') if x.strip().isdigit()],
            'subjects': parsed('Subjects_JSON', {}),
            'answers': parsed('Answers_JSON', {}),
            'question_evaluation': parsed('Question_Evaluation_JSON', []),
        }

    def get_result_by_image_hash(self, image_hash: str):
        """Return the saved record for duplicate handling, or None."""
        values = _safe_call(self.results.col_values, RESULT_HEADERS.index('Image_Hash') + 1)
        try:
            row_idx = len(values) - values[::-1].index(image_hash)
        except ValueError:
            return None
        if row_idx < 2:
            return None
        return self._saved_payload(_safe_call(self.results.row_values, row_idx))

    def get_result_by_id(self, record_id: str):
        """Allow an authorized user to redownload a report from Google Sheets."""
        values = _safe_call(self.results.col_values, RESULT_HEADERS.index('Record_ID') + 1)
        try:
            row_idx = len(values) - values[::-1].index(str(record_id))
        except ValueError:
            return None
        if row_idx < 2:
            return None
        return self._saved_payload(_safe_call(self.results.row_values, row_idx))

    def save_key(self, key_id, csv_text):
        existing = _safe_call(self.keys.col_values, 1)
        values = [str(key_id), _now(), str(csv_text)]
        if key_id in existing[1:]:
            idx = existing.index(key_id) + 1
            self.keys.update(range_name=f'A{idx}:C{idx}',
                             values=[values], value_input_option='RAW')
        else:
            self.keys.append_row(values, value_input_option='RAW',
                                 insert_data_option='INSERT_ROWS')
        return True

    def list_keys(self):
        values = _safe_call(self.keys.get_all_values)
        return {row[0]: row[2] for row in values[1:] if len(row) >= 3 and row[0]}
