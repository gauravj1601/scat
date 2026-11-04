"""Answer-key CSV validation / scoring. No paper content is hardcoded in code."""
from __future__ import annotations
import csv
import io
import math
import re
from collections import defaultdict
from pathlib import Path

COLUMNS=['Exam_Type','Class','Paper_Code','Paper_Version','Question_No','Subject','Correct_Answer','Marks_Correct','Marks_Wrong']
CLASSES=['5th','6th','7th','8th','9th','10th','11th-NM','11th-Med','12th-NM','12th-Med']
EXAMS=['SCAT','SCIMED','YSTT']
CODES=list('ABCD')


def read_csv_bytes(data:bytes)->list[dict]:
    try:
        text=data.decode('utf-8-sig')
    except UnicodeDecodeError as e:
        raise ValueError('CSV must be UTF-8 encoded.') from e
    reader=csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:raise ValueError('CSV has no header.')
    missing=[x for x in COLUMNS if x not in reader.fieldnames]
    if missing:raise ValueError('Missing CSV columns: '+', '.join(missing))
    data_rows=[]
    for line,item in enumerate(reader,2):
        if not any(str(v or '').strip() for v in item.values()):continue
        item={k:str(item.get(k) or '').strip() for k in COLUMNS}
        item['Exam_Type']=item['Exam_Type'].upper()
        item['Paper_Code']=item['Paper_Code'].upper()
        item['Correct_Answer']=item['Correct_Answer'].upper()
        if item['Exam_Type'] not in EXAMS: raise ValueError(f'Row {line}: unknown exam type.')
        if item['Class'] not in CLASSES: raise ValueError(f'Row {line}: unknown class.')
        if item['Paper_Code'] not in CODES:raise ValueError(f'Row {line}: paper code must be A/B/C/D.')
        if not item['Paper_Version'] or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,60}',item['Paper_Version']):raise ValueError(f'Row {line}: invalid Paper_Version.')
        if not item['Subject']:raise ValueError(f'Row {line}: missing subject.')
        try:qn=int(item['Question_No'])
        except Exception as e:raise ValueError(f'Row {line}: invalid question number.') from e
        if qn<1 or qn>180:raise ValueError(f'Row {line}: questions must be numbered 1–180.')
        item['Question_No']=qn
        if item['Correct_Answer'] not in CODES and item['Correct_Answer'] not in ('BONUS','A|B','A|C','A|D','B|C','B|D','C|D','A|B|C|D'):
            # NOTE: multi-answer is supported through | with any unique A-D options.
            opts=item['Correct_Answer'].split('|')
            if not (len(opts)>=2 and len(opts)==len(set(opts)) and all(c in CODES for c in opts)):
                raise ValueError(f'Row {line}: Correct_Answer must be A-D, BONUS, or pipe-separated options.')
        for col in ('Marks_Correct','Marks_Wrong'):
            try:x=float(item[col])
            except Exception as e:raise ValueError(f'Row {line}: invalid {col}.') from e
            if not math.isfinite(x):raise ValueError(f'Row {line}: nonfinite {col}.')
            item[col]=x
        data_rows.append(item)
    if not data_rows:raise ValueError('CSV contains no questions.')
    groups=group_rows(data_rows)
    for k,rows in groups.items():
        nums=[r['Question_No'] for r in rows]
        if len(nums)!=len(set(nums)):
            raise ValueError(f'{k}: duplicate question numbers.')
        if sorted(nums)!=list(range(1,len(nums)+1)):
            raise ValueError(f'{k}: expected consecutive questions 1 to {len(nums)}.')
    return data_rows


def group_rows(rows):
    g=defaultdict(list)
    for row in rows:g[(row['Exam_Type'],row['Class'],row['Paper_Code'],row['Paper_Version'])].append(row)
    return dict(g)



def available_paper_versions(keys, exam, class_name, paper_code):
    """Return versions for an exact exam/class/code; keep version labels as text."""
    def natural_sort(label):
        return [(0, int(part)) if part.isdigit() else (1, part.casefold())
                for part in re.split(r'(\d+)', label)]

    return sorted({key[3] for key in keys
                   if key[:3] == (exam, class_name, paper_code)}, key=natural_sort)


def key_string(key):return '::'.join(key)


def key_tuple(value):return tuple(value.split('::'))


def load_bundled(folder='answer_keys'):
    data={}
    for p in sorted(Path(folder).glob('*.csv')):
        if p.name.lower().startswith('answer_key_blank'):continue
        try:
            for key,rows in group_rows(read_csv_bytes(p.read_bytes())).items():data[key]=rows
        except ValueError:
            continue
    return data


def to_csv(rows):
    out=io.StringIO();writer=csv.DictWriter(out,fieldnames=COLUMNS,lineterminator='\n');writer.writeheader()
    for row in rows:writer.writerow(row)
    return out.getvalue().encode('utf-8-sig')


def evaluate(answers:dict[int,str],rows:list[dict]):
    subjects={}
    rows_result=[]
    for q in sorted(rows,key=lambda r:r['Question_No']):
        n=q['Question_No']; ans=str(answers.get(n,'')).strip().upper()
        key=q['Correct_Answer']
        plus=float(q['Marks_Correct']);minus=float(q['Marks_Wrong'])
        if key=='BONUS':status='Bonus';marks=plus
        elif ans in ('UNREADABLE','MULTIPLE'):status='Needs review';marks=0.0
        elif ans=='INVALID':status='Invalid';marks=minus
        elif not ans:status='Unattempted';marks=0.0
        elif ans in key.split('|'):status='Correct';marks=plus
        else:status='Incorrect';marks=minus
        subj=q['Subject']
        x=subjects.setdefault(subj,{'marks':0.,'maximum':0.,'correct':0,'wrong':0,'blank':0,'review':0,'bonus':0})
        x['marks']+=marks;x['maximum']+=max(0,plus)
        x[{'Correct':'correct','Incorrect':'wrong','Unattempted':'blank','Needs review':'review','Invalid':'wrong','Bonus':'bonus'}[status]]+=1
        rows_result.append({'Question':n,'Subject':subj,'Marked':ans,'Correct':key,'Status':status,'Marks':marks})
    total=sum(s['marks'] for s in subjects.values());maximum=sum(s['maximum'] for s in subjects.values())
    return {'total':round(total,3),'maximum':round(maximum,3),'subjects':subjects,'rows':rows_result,'needs_review':sum(1 for r in rows_result if r['Status']=='Needs review')}
