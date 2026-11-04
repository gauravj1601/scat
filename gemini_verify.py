"""Independent Gemini image evaluation, called automatically alongside Python.

The API never receives Python's readings or the correct answer key. Keys are
read from Streamlit server secrets, not embedded in client code.
"""
from __future__ import annotations
import json
import re


def verify(front_bytes,back_bytes,num_questions,api_key,model='gemini-2.5-flash', bubble_sheet_bytes=None):
    if not api_key:raise ValueError('Missing Gemini API key in Streamlit secrets.')
    from google import genai
    from google.genai import types
    client=genai.Client(api_key=api_key,http_options={'timeout':65000})
    instructions=(
        'You are an OMR visual checker. The SECOND image is a numbered contact sheet '
        'showing an enlarged close-up of FOUR bubbles for each question. '
        'Every row begins Qxx, then bubbles numbered 1, 2, 3, 4 from left to right. '
        'Number 1 means A; 2 means B; 3 means C; 4 means D. '
        'Read the ACTUAL black-filled bubble for EACH row separately. '
        'Do not default to B or assume consecutive questions share an answer. '
        'Pink outlines are empty circles, not selected bubbles. '
        'If every circle is unfilled return empty string. '
        'If multiple are filled or you cannot distinguish a black mark, return UNCERTAIN. '
        'Do not use the answer key, common-sense correctness, or patterns. '
        'The FIRST photo is the student-front side. Independently read its student '
        'information as well as possible: student_name, roll_number, student_phone, '
        'parent_phone, school_name, school_city, gender and exam_center. '
        'The name/roll are handwritten in boxes AND marked as bubbles underneath. '
        'For phone numbers, read the top handwritten digits and/or clearly darkened '
        'number bubbles. Preserve every digit, including leading zeroes. '
        'Do not guess missing digits, names or addresses. Return empty strings if unclear. '
        f'Return results for Q1 to Q{num_questions}, exactly once each. '
        'Return ONLY JSON with student_name, roll_number, student_phone, '
        'parent_phone, school_name, school_city, gender, exam_center, '
        'answers: mapping question-number strings to A/B/C/D/empty/UNCERTAIN. '
        'Carefully distinguish Q labels and number labels in the second image.'
    )
    answer_part=(types.Part.from_bytes(data=bubble_sheet_bytes,mime_type='image/png')
                 if bubble_sheet_bytes else types.Part.from_bytes(data=back_bytes,mime_type='image/jpeg'))
    try:
        response=client.models.generate_content(
            model=model,
            contents=[instructions,types.Part.from_bytes(data=front_bytes,mime_type='image/jpeg'),
                      answer_part],
            config=types.GenerateContentConfig(response_mime_type='application/json',temperature=0),
        )
    except Exception as error:
        message=str(error)
        low=message.lower()
        if '429' in message or 'resource_exhausted' in low or 'quota' in low:
            cause='Quota/rate limit exceeded (429). Check API limits and billing.'
        elif '401' in message or 'api_key_invalid' in low or 'invalid api key' in low:
            cause='API key is invalid (401). Replace the key in secrets.toml.'
        elif '403' in message or 'permission_denied' in low:
            cause='Access denied (403). Check the API key, project restrictions and billing.'
        elif '404' in message or 'not_found' in low:
            cause=f'Model {model} not available (404). Check GEMINI_MODEL.'
        elif 'timeout' in low or 'deadline' in low:
            cause='The Gemini request timed out. Try again with a clear photo.'
        else:
            cause=f'Gemini request error ({type(error).__name__}). Check server logs and model access.'
        raise RuntimeError(cause) from error
    raw=getattr(response,'text',None)
    if not raw:raise ValueError('Verification service returned no readable result.')
    obj=json.loads(raw)
    if not isinstance(obj,dict) or not isinstance(obj.get('answers'),dict):
        raise ValueError('Verification service returned an invalid answer format.')
    raw_answers=obj['answers']
    norm={}
    for n in range(1,num_questions+1):
        v=str(raw_answers.get(str(n),'UNCERTAIN')).strip().upper()
        norm[n]=v if v in ('','A','B','C','D','UNCERTAIN') else 'UNCERTAIN'
    def cleaned(field, maxlen=120):
        return str(obj.get(field) or '').strip()[:maxlen]
    def number(field):
        digits=re.sub(r'\D','',cleaned(field,40))
        # Phone numbers in the printed form are 10 digits. Reject invented or
        # incomplete values rather than silently storing a wrong contact.
        return digits if len(digits)==10 else ''
    return {
        'student_phone':number('student_phone'),
        'parent_phone':number('parent_phone'),
        'school_name':cleaned('school_name'),
        'school_city':cleaned('school_city'),
        'gender':cleaned('gender'),
        'exam_center':cleaned('exam_center'),
        'student_name':str(obj.get('student_name') or '').strip(),
        'roll_number':re.sub(r'\D','',str(obj.get('roll_number') or '')),
        'answers':norm,
    }
