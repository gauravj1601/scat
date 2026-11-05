"""Local SQLite or optional Supabase PostgREST persistent storage.

If SUPABASE_URL/SUPABASE_SERVICE_KEY configured, records and keys are saved
remotely. Private photos are *not* stored by this application.
"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
import requests

class DuplicateResult(Exception):pass

class Store:
    def __init__(self,local_path='data/scat_results.db',url='',key=''):
        self.url=url.rstrip('/')
        self.key=key
        self.local_path=local_path
        if not (url and key):self._init_local()

    @property
    def is_cloud(self):return bool(self.url and self.key)

    def _headers(self):return {'apikey':self.key,'Authorization':f'Bearer {self.key}','Content-Type':'application/json','Prefer':'return=representation'}

    def _post(self,table,payload,upsert=False):
        h=self._headers()
        if upsert:h['Prefer']='resolution=merge-duplicates,return=representation'
        r=requests.post(f'{self.url}/rest/v1/{table}',json=payload,headers=h,timeout=20)
        if r.status_code==409:raise DuplicateResult('A matching record already exists.')
        if not r.ok:raise RuntimeError('Remote database error: '+r.text[:350])
        return r.json()

    def _get(self,table,params=None):
        r=requests.get(f'{self.url}/rest/v1/{table}',headers=self._headers(),params=params or {},timeout=20)
        if not r.ok:raise RuntimeError('Remote database error: '+r.text[:350])
        return r.json()

    def _con(self):
        c=sqlite3.connect(self.local_path,timeout=15)
        c.execute('PRAGMA busy_timeout=15000')
        return c

    def _init_local(self):
        Path(self.local_path).parent.mkdir(parents=True,exist_ok=True)
        with self._con() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS omr_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT, submitted_at TEXT DEFAULT CURRENT_TIMESTAMP,
                image_hash TEXT UNIQUE, exam_date TEXT, exam_type TEXT, class_name TEXT,
                paper_code TEXT, paper_version TEXT, roll_number TEXT, student_name TEXT,
                total REAL, maximum REAL, verification_status TEXT, payload TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS omr_answer_keys (
                key_id TEXT PRIMARY KEY, csv_text TEXT NOT NULL, saved_at TEXT DEFAULT CURRENT_TIMESTAMP)''')

    def save_result(self,payload):
        rec={
            'image_hash':payload['image_hash'],'exam_date':payload['exam_date'],
            'exam_type':payload['exam_type'],'class_name':payload['class_name'],
            'paper_code':payload['paper_code'],'paper_version':payload['paper_version'],
            'roll_number':payload['roll_number'],'student_name':payload['student_name'],
            'total':payload['total'],'maximum':payload['maximum'],
            'verification_status':payload['verification_status'],
            'payload':payload,
        }
        if self.is_cloud:return self._post('omr_results',rec)
        try:
            with self._con() as c:
                cols=['image_hash','exam_date','exam_type','class_name','paper_code','paper_version','roll_number','student_name','total','maximum','verification_status','payload']
                c.execute('INSERT INTO omr_results ('+','.join(cols)+') VALUES ('+','.join('?'*len(cols))+')',
                    [json.dumps(rec[v]) if v=='payload' else rec[v] for v in cols])
        except sqlite3.IntegrityError as e:raise DuplicateResult('This exact OMR image was saved previously.') from e
        return True

    def update_result(self, payload):
        """Update an already saved OMR by its image hash (no duplicate rows)."""
        h = str(payload.get('image_hash') or '')
        if not h:
            raise ValueError('Missing image fingerprint; cannot update result.')
        fields = ('exam_date', 'exam_type', 'class_name', 'paper_code',
                  'paper_version', 'roll_number', 'student_name', 'total',
                  'maximum', 'verification_status')
        if self.is_cloud:
            rec = {k: payload.get(k) for k in fields}
            rec['payload'] = payload
            response = requests.patch(
                f'{self.url}/rest/v1/omr_results', params={'image_hash': 'eq.' + h},
                json=rec, headers=self._headers(), timeout=20)
            if not response.ok:
                raise RuntimeError('Remote database update error: ' + response.text[:350])
            if not response.json():
                raise LookupError('Previously saved OMR row could not be found.')
            return True
        columns = ', '.join(f'{name}=?' for name in fields)
        values = [payload.get(k) for k in fields]
        values.append(json.dumps(payload))
        with self._con() as c:
            cur = c.execute(
                f'UPDATE omr_results SET {columns}, payload=? WHERE image_hash=?',
                values + [h])
            if cur.rowcount != 1:
                raise LookupError('Previously saved OMR row could not be found.')
        return True

    def list_results(self,limit=500):
        if self.is_cloud:
            return self._get('omr_results',{'select':'id,submitted_at,exam_date,exam_type,class_name,paper_code,paper_version,roll_number,student_name,total,maximum,verification_status','order':'submitted_at.desc','limit':min(limit,1000)})
        with self._con() as c:
            c.row_factory=sqlite3.Row
            return [dict(row) for row in c.execute('SELECT id,submitted_at,exam_date,exam_type,class_name,paper_code,paper_version,roll_number,student_name,total,maximum,verification_status FROM omr_results ORDER BY id DESC LIMIT ?', (limit,))]


    def get_result_by_image_hash(self, image_hash):
        if self.is_cloud:
            rows = self._get('omr_results', {'select': 'payload', 'image_hash': 'eq.' + image_hash, 'limit': 1})
            return rows[0]['payload'] if rows else None
        with self._con() as c:
            row = c.execute('SELECT payload FROM omr_results WHERE image_hash=?', (image_hash,)).fetchone()
        return json.loads(row[0]) if row else None

    def get_result_by_id(self, record_id):
        if self.is_cloud:
            rows = self._get('omr_results', {'select': 'payload', 'id': 'eq.' + str(record_id), 'limit': 1})
            return rows[0]['payload'] if rows else None
        with self._con() as c:
            row = c.execute('SELECT payload FROM omr_results WHERE id=?', (record_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def save_key(self,key_id,csv_text):
        if self.is_cloud:return self._post('omr_answer_keys',{'key_id':key_id,'csv_text':csv_text},True)
        with self._con() as c:
            c.execute('INSERT INTO omr_answer_keys(key_id,csv_text) VALUES (?,?) ON CONFLICT(key_id) DO UPDATE SET csv_text=excluded.csv_text, saved_at=CURRENT_TIMESTAMP',(key_id,csv_text))
        return True

    def list_keys(self):
        if self.is_cloud:return {r['key_id']:r['csv_text'] for r in self._get('omr_answer_keys',{'select':'key_id,csv_text','limit':1000})}
        with self._con() as c:return dict(c.execute('SELECT key_id,csv_text FROM omr_answer_keys'))
