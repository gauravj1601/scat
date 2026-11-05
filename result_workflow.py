"""Persist the *current* confirmed evaluation before showing the result.

Re-evaluating an already saved photograph is allowed. If its evaluation or
confirmed student details have changed, the existing record is updated in
place rather than rejecting the scan or creating a second database row.
"""
from __future__ import annotations

from storage import DuplicateResult


class ExistingResultConflict(ValueError):
    """An existing OMR record could not be retrieved or updated safely."""


def _answer_map(answers):
    if not isinstance(answers, dict):
        return {}
    return {str(k): str(v or '').upper().strip() for k, v in answers.items()}


def _matches_saved(existing: dict, current: dict) -> bool:
    """Check that a stored record reflects this evaluation, not an older one."""
    text_fields = (
        'image_hash', 'exam_date', 'exam_type', 'class_name', 'paper_code',
        'paper_version', 'roll_number', 'student_name', 'school', 'school_city',
        'student_phone', 'parent_phone', 'gender', 'exam_center',
        'verification_status', 'campus', 'checked_by',
    )
    for field in text_fields:
        if str(existing.get(field) or '').strip().casefold() != str(current.get(field) or '').strip().casefold():
            return False
    if _answer_map(existing.get('answers')) != _answer_map(current.get('answers')):
        return False
    for num in ('total', 'maximum'):
        try:
            if abs(float(existing.get(num, 0)) - float(current.get(num, 0))) > 0.00001:
                return False
        except (TypeError, ValueError):
            return False
    if (existing.get('subjects') or {}) != (current.get('subjects') or {}):
        return False
    if (existing.get('question_evaluation') or []) != (current.get('question_evaluation') or []):
        return False
    if [int(x) for x in (existing.get('reviewed_questions') or [])] != [int(x) for x in (current.get('reviewed_questions') or [])]:
        return False
    return True


def save_verified_result(store, payload: dict) -> tuple[dict, bool]:
    """Return ``(persisted_payload, was_rechecked)`` after a successful write.

    A duplicate photo never blocks evaluation: a matching record is returned
    unchanged, or updated in place if newly confirmed fields/answers differ.
    On a failed write, no recomputed result is returned for display. This also
    protects retries after an uncertain network append or update outcome.
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
                'This OMR is already registered, but its record could not be retrieved. '
                'Please retry or contact an administrator.'
            )
        if _matches_saved(existing, payload):
            return existing, True

        # Update the *same* record so corrected answers, student information,
        # paper settings or a changed key can be re-evaluated without blocking.
        if not hasattr(store, 'update_result'):
            raise ExistingResultConflict('The configured database does not support rechecks.')
        store.update_result(payload)
        updated = store.get_result_by_image_hash(payload['image_hash'])
        if not updated or not _matches_saved(updated, payload):
            raise RuntimeError(
                'The rechecked result could not be verified in the database. '
                'Please retry; no new marks will be displayed.'
            )
        return updated, True
