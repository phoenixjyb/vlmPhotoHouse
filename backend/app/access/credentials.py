"""Standard password hashing and canonical login identifiers; no network identity claims."""
import hashlib
import hmac
import re
import secrets

SCRYPT_N = 2**17
SCRYPT_R = 8
SCRYPT_P = 1
# Fixed, non-account dummy record keeps unknown-account checks on the same KDF path.
DUMMY_HASH = f'scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}$' + '00' * 16 + '$' + '00' * 32


def phone_login(value: str) -> str:
    """Canonical +country-code username, NOT proof of telephone ownership.

    Accept common ASCII display separators. No implicit country or Unicode digits.
    The UI can preselect +86 but must submit the explicit country code.
    """
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError('Use a phone login with explicit country code')
    normalized = re.sub(r'[ ()-]', '', value)
    if not re.fullmatch(r'\+[1-9][0-9]{7,14}', normalized, flags=re.ASCII):
        raise ValueError('Use a phone login with explicit country code')
    return normalized


def hash_password(password: str) -> str:
    if not isinstance(password, str) or not 15 <= len(password) <= 128:
        raise ValueError('Use a password or passphrase of 15 to 128 characters')
    salt = secrets.token_bytes(16)
    derived = _derive(password, salt)
    return f'scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${derived.hex()}'


def _derive(password, salt):
    return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=SCRYPT_N,
                          r=SCRYPT_R, p=SCRYPT_P, maxmem=256 * 1024 * 1024, dklen=32)


def verify_password(password: str, encoded: str) -> bool:
    if not isinstance(password, str) or not 1 <= len(password) <= 128:
        return False
    try:
        algorithm, n, r, p, salt, expected = encoded.split('$')
        if (algorithm, n, r, p) != ('scrypt', str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P)):
            return False
        if len(salt) != 32 or len(expected) != 64:
            return False
        salt_bytes, expected_bytes = bytes.fromhex(salt), bytes.fromhex(expected)
    except (AttributeError, TypeError, ValueError):
        return False
    try:
        derived = _derive(password, salt_bytes)
    except UnicodeError:
        return False
    return hmac.compare_digest(derived, expected_bytes)


def invitation_code() -> str:
    raw = secrets.token_hex(16)  # 128 random bits; copy/paste, not a guessable short PIN.
    return '-'.join(raw[i:i + 8] for i in range(0, 32, 8))


def invitation_digest(code: str) -> str:
    if not isinstance(code, str) or len(code) > 80:
        raise ValueError('Invalid invitation')
    raw = code.replace('-', '').replace(' ', '').lower()
    if not re.fullmatch('[0-9a-f]{32}', raw, flags=re.ASCII):
        raise ValueError('Invalid invitation')
    return hashlib.sha256(raw.encode('ascii')).hexdigest()


def session_digest(token: str) -> str:
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token, flags=re.ASCII):
        raise ValueError('Invalid session')
    return hashlib.sha256(token.encode('ascii')).hexdigest()
