"""Independent-reading comparison with conservative Python-only fallback."""
from __future__ import annotations
import re
from dataclasses import dataclass

@dataclass(frozen=True)
class VerificationPlan:
    accepted: dict
    issues: list
    remote_ok: bool
    status: str
    note: str

VALID={'','A','B','C','D'}
BAD={'UNREADABLE','MULTIPLE','UNCERTAIN','?'}


def canonical(value):
    v=str(value or '').upper().strip()
    return v if v in VALID else 'UNCERTAIN'


def normalized_name(value):
    return re.sub(r'[^A-Z]','',str(value or '').upper())


def make_review(python_answers, gemini_answers, count, confidence=None):
    """Only auto-approve when both independent readings are valid and identical.

    No answer key is used in deciding whether two readings agree.
    """
    confidence=confidence or {}
    final={};questions=[]
    for q in range(1,count+1):
        first=canonical(python_answers.get(q,'UNCERTAIN'))
        second=canonical(gemini_answers.get(q,'UNCERTAIN'))
        low_conf=float(confidence.get(q,1.0))<0.20
        if first in VALID and first==second and not low_conf:
            final[q]=first
        else:
            reason=('Low image clarity' if low_conf or first=='UNCERTAIN' or second=='UNCERTAIN'
                    else 'Marking needs confirmation')
            questions.append({'question':q,'reason':reason,'first':first,'second':second})
    return final,questions


def parse_manual(selection):
    opts={'Unattempted':'','A':'A','B':'B','C':'C','D':'D','Multiple marked':'INVALID'}
    if selection not in opts:raise ValueError('Please select a marked option.')
    return opts[selection]


def assess_second_reader(local_answers, second_answers, count):
    """Catch pathological AI responses before generating operator questions.

    This is a quality gate, NOT a reason to claim two-reader agreement.
    Returns (is_reliable, note). Never sees the answer key.
    """
    local=[canonical(local_answers.get(q,'UNCERTAIN')) for q in range(1,count+1)]
    other=[canonical(second_answers.get(q,'UNCERTAIN')) for q in range(1,count+1)]
    comparable=[(a,b) for a,b in zip(local,other) if a in VALID and b in VALID]
    disagreements=sum(a!=b for a,b in comparable)
    if len(comparable)<max(8,int(count*.60)):
        return False,'Second image reading returned too few valid responses.'
    if disagreements > max(5, int(count*.20)):
        return False,f'Second image reader disagreed on {disagreements} questions; possible image-reading failure.'
    valid_other=[x for x in other if x in 'ABCD']
    if valid_other and len(set(valid_other))==1 and len(valid_other)>=int(count*.70):
        return False,'Second reader repeated one option for most questions.'
    return True,''


def python_only_review(python_answers, count, confidence=None):
    """When independent AI fails its quality gate, do not generate spurious
    remote disagreements. Operator reviews ONLY uncertain local answers.
    This outcome must be recorded as single-reader, NOT double-verified.
    """
    confidence=confidence or {}
    accepted={};issues=[]
    for q in range(1,count+1):
        a=canonical(python_answers.get(q,'UNCERTAIN'))
        if a in VALID and float(confidence.get(q,1))>=.20:
            accepted[q]=a
        else:
            issues.append({'question':q,'reason':'Bubble needs confirmation',
                           'first':a,'second':'UNCERTAIN'})
    return accepted,issues


def finalize_review(accepted, issues, selections, question_count):
    """Merge staff decisions, including an intentionally invalid multi-mark.

    A confirmed multiple answer is represented by INVALID (and scored according
    to the CSV marking rules), never left as the unresolved MULTIPLE token.
    """
    results = dict(accepted)
    missing = []
    for issue in issues:
        q = int(issue['question'])
        choice = selections.get(q, 'Select answer')
        if choice == 'Select answer':
            missing.append(q)
        else:
            results[q] = parse_manual(choice)
    if missing:
        raise ValueError('Please confirm '+', '.join('Q'+str(q) for q in missing))
    if set(results) != set(range(1, question_count+1)):
        raise ValueError('Not all question readings are resolved.')
    return results


def plan_verification(local_answers, count, confidence=None, *, remote_answers=None, remote_error=None):
    """Plan safe review without requiring an administrator for AI-only failures.

    Successful independent agreement is labelled double checked. An absent,
    failed, or pathological second reading falls back to Python's confident
    bubbles only. Every uncertain local bubble still needs staff selection.
    No answer key is involved in this decision.
    """
    if remote_error is not None or remote_answers is None:
        accepted, issues = python_only_review(local_answers, count, confidence)
        note = ('Independent checking unavailable: ' + str(remote_error)
                if remote_error is not None else 'Independent checking is not configured.')
        return VerificationPlan(accepted, issues, False,
                                'Python checked; independent check unavailable', note)
    reliable, note = assess_second_reader(local_answers, remote_answers, count)
    if reliable:
        accepted, issues = make_review(local_answers, remote_answers, count, confidence)
        return VerificationPlan(accepted, issues, True, 'Double checked', '')
    accepted, issues = python_only_review(local_answers, count, confidence)
    return VerificationPlan(accepted, issues, False,
                            'Python checked; independent check inconclusive', note)
