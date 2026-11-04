"""Run: python -m unittest discover -s tests -v"""
import os
import tempfile
import unittest
from pathlib import Path
from answer_key_utils import read_csv_bytes,group_rows,evaluate,load_bundled
from storage import Store,DuplicateResult

class TestSCAT(unittest.TestCase):
    def test_bundled_keys(self):
        folder=Path(__file__).resolve().parents[1]/'answer_keys'
        keys=load_bundled(folder)
        self.assertEqual(len(keys),2)
        for k,v in keys.items():
            self.assertEqual(len(v),50)
            self.assertEqual(sum(x['Marks_Correct'] for x in v),50)
            self.assertEqual(set(x['Paper_Code'] for x in v),{'A'})

    def test_scoring(self):
        row={'Exam_Type':'SCAT','Class':'10th','Paper_Code':'A','Paper_Version':'test',
            'Subject':'Physics','Correct_Answer':'C','Marks_Correct':1.,'Marks_Wrong':0.,'Question_No':1}
        score=evaluate({1:'C'},[row]);self.assertEqual(score['total'],1)
        score=evaluate({1:'A'},[row]);self.assertEqual(score['total'],0)
        row['Correct_Answer']='BONUS'
        score=evaluate({1:''},[row]);self.assertEqual(score['total'],1)

    def test_db(self):
        with tempfile.TemporaryDirectory() as d:
            db=Store(local_path=os.path.join(d,'db.sqlite'))
            db.save_key('example','csv')
            self.assertEqual(db.list_keys()['example'],'csv')
            x={'image_hash':'hash','exam_date':'2026-11-03','exam_type':'SCAT','class_name':'10th',
               'paper_code':'A','paper_version':'v1','roll_number':'1','student_name':'Student',
               'total':22,'maximum':50,'verification_status':'reviewed'}
            db.save_result(x)
            self.assertEqual(len(db.list_results()),1)
            with self.assertRaises(DuplicateResult):db.save_result(x)

if __name__=='__main__':unittest.main()
