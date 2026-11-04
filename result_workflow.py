"""Save verified OMRs exactly once, and only unlock previously persisted results.

Both the successful write and duplicate reopening paths return the durable record.
The caller must not render marks/PDF until this function returns successfully.
"""
from __future__ import annotations

from storage import DuplicateResult


class ExistingResultConflict(ValueError):
    """The same images are already associated with a different saved result."""


def _answer_map(answers):
    if not isinstance(answers, dict):
        return {}
    return {str(k): str(v or '').upper().strip() for k, v in answers.items()}


def _matches_saved(existing: dict, current: dict) -> bool:
    """Never show a freshly recomputed result as though it were the old saved result."""
    fields = ('image_hash', 'exam_date', 'exam_type', 'class_name',
              'paper_code', 'paper_version', 'roll_number', 'student_name')
    for field in fields:
        if str(existing.get(field, '')).strip().casefold() != str(current.get(field, '')).strip().casefold():
            return False
    if _answer_map(existing.get('answers')) != _answer_map(current.get('answers')):
        return False
    for num in ('total', 'maximum'):
        try:
            if abs(float(existing.get(num, 0)) - float(current.get(num, 0))) > 0.00001:
                return False
        except (TypeError, ValueError):
            return False
    return True


def save_verified_result(store, payload: dict) -> tuple[dict, bool]:
    """Return (saved_payload, previously_saved).

    A successful write must finish before result rendering. If an uncertain
    network append succeeded but raised, a later retry uses the image hash
    to retrieve the persisted record instead of creating duplicate rows.
    """
    if not str(payload.get('student_name') or '').strip() or not str(payload.get('roll_number') or '').strip():
        raise ValueError('Student name and roll number must be confirmed before saving.')
    if not payload.get('image_hash'):
        raise ValueError('Missing image fingerprint; cannot save the result.')
    if payload.get('needs_review'):
        raise ValueError('Unresolved answers must be confirmed before saving.')

    try:
        store.save_result(payload)
        return payload, False
    except DuplicateResult:
        existing = store.get_result_by_image_hash(payload['image_hash'])
        if not existing:
            raise ExistingResultConflict(
                'This OMR was saved before, but its stored result could not be retrieved. '
                'Please check the Saved Results tab or ask an administrator.'
            )
        if not _matches_saved(existing, payload):
            raise ExistingResultConflict(
                'This OMR photograph is already in the database with different details, '
                "answers, or paper settings. To prevent overwriting a student's result, "
                'please review the existing record with an administrator.'
            )
        return existing, True
