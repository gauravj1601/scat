"""Optional, one-time migration of previous local saved results and keys.

Run from the app folder: py migrate_sqlite_to_sheets.py
Your local database is never modified or deleted. Duplicate image hashes are skipped.
"""
import json
import sqlite3
import tomllib
from pathlib import Path

from sheets_storage import SheetsStore
from storage import DuplicateResult


def main():
    config = Path('.streamlit/secrets.toml')
    db = Path('data/scat_results.db')
    if not config.is_file():
        raise SystemExit('Cannot find .streamlit/secrets.toml')
    if not db.is_file():
        raise SystemExit('No existing local SQLite database to migrate.')
    creds = tomllib.loads(config.read_text(encoding='utf-8-sig'))
    if not creds.get('GSHEETS_SPREADSHEET_ID'):
        raise SystemExit('Configure GSHEETS_SPREADSHEET_ID in secrets.toml first.')
    store = SheetsStore(creds['GSHEETS_SPREADSHEET_ID'], creds.get('gcp_service_account', {}))
    with sqlite3.connect(f'file:{db.absolute().as_posix()}?mode=ro', uri=True) as cn:
        res = cn.execute('SELECT payload FROM omr_results ORDER BY id').fetchall()
        keys = cn.execute('SELECT key_id,csv_text FROM omr_answer_keys').fetchall()
    saved = skipped = 0
    for (raw,) in res:
        try:
            store.save_result(json.loads(raw))
            saved += 1
        except DuplicateResult:
            skipped += 1
    for key_id, csv_text in keys:
        store.save_key(key_id, csv_text)
    print(f'Migration complete. Copied {saved} results, skipped {skipped} duplicates, copied {len(keys)} answer keys.')
    print('Your original SQLite file was not changed.')


if __name__ == '__main__':
    main()
