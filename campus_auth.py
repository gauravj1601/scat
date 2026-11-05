"""Password-only campus login helpers. Never log or persist password values.

Every configured campus secret corresponds to a login identity. The selected
OMR campus may be different (e.g., staff helping another campus), and both
fields are stored for traceability.
"""
from __future__ import annotations

import hmac
from dataclasses import dataclass

CAMPUSES = ('Chandigarh', 'Panchkula', 'Patiala', 'Hisar')


@dataclass(frozen=True)
class LoginIdentity:
    role: str
    label: str
    home_campus: str


def clean_campus_secrets(raw) -> dict[str, str]:
    """Normalize the Streamlit TOML section without exposing secrets."""
    raw = dict(raw or {})
    unexpected = set(raw) - set(CAMPUSES)
    if unexpected:
        raise ValueError('Unknown campus password key(s): ' + ', '.join(sorted(unexpected)))
    return {campus: str(raw.get(campus) or '') for campus in CAMPUSES if raw.get(campus)}


def validate_passwords(admin_password: str, campus_passwords: dict[str, str],
                       legacy_password: str = '') -> None:
    """Reject shared passwords that would make campus attribution ambiguous."""
    used = {}
    for name, password in [('Admin', admin_password), *list(campus_passwords.items()),
                           ('Legacy Staff', legacy_password if not campus_passwords else '')]:
        if not password:
            continue
        if password in used:
            raise ValueError(f'Passwords for {used[password]} and {name} must be different.')
        used[password] = name


def authenticate(entered: str, admin_password: str, campus_passwords: dict[str, str],
                 legacy_password: str = '') -> LoginIdentity | None:
    """Return role and login label; secret is never returned to callers."""
    if not entered:
        return None
    if admin_password and hmac.compare_digest(entered, admin_password):
        return LoginIdentity('admin', 'Admin', '')
    for campus in CAMPUSES:
        password = campus_passwords.get(campus)
        if password and hmac.compare_digest(entered, password):
            return LoginIdentity('staff', campus, campus)
    # Compatibility with existing APP_PASSWORD during migration. Once campus
    # passwords are configured, it cannot bypass campus-specific credentials.
    if not campus_passwords and legacy_password and hmac.compare_digest(entered, legacy_password):
        return LoginIdentity('staff', 'Legacy Staff', '')
    return None
