"""The data key is a keyring apart from the session secret, and unset it is the old key.

🔴 THE DEFECT THIS CLOSES (28 Sept 2026). The key of the investors' IBANs was derived from
`SECRET_KEY`: rotating the secret that signs sessions made every IBAN unreadable, and no
tool could re-encrypt them. `DATA_ENCRYPTION_KEYS` now holds an ordered list of keys; these
tests pin the four promises the rotation procedure stands on:

  * unset, the keyring is exactly the old derived key, byte for byte, and the fingerprint
    is exactly the old salted hash: a deployment changes nothing by upgrading;
  * the first key encrypts, every key decrypts;
  * once the keyring is explicit, `SECRET_KEY` no longer touches the data, and the session
    tokens are still signed by `SECRET_KEY` alone;
  * a malformed key stops the application instead of reading every IBAN as absent.
"""

from __future__ import annotations

import base64
import hashlib

import pytest
from cryptography.fernet import Fernet
from jose import jwt

from app.config import get_settings
from app.core import crypto, security
from app.models.base import Base
from app.services import reencrypt

SECRET = "a-session-secret-for-the-tests"
IBAN = "FR76 3000 6000 0112 3456 7890 189"
NORMALISED = "FR7630006000011234567890189"


@pytest.fixture
def keys(monkeypatch):
    """Set the two settings for one test, and never let the cached keyring leak."""
    settings = get_settings()

    def use(*, secret: str = SECRET, data_keys: str = "") -> None:
        monkeypatch.setattr(settings, "SECRET_KEY", secret)
        monkeypatch.setattr(settings, "DATA_ENCRYPTION_KEYS", data_keys)
        crypto.reset()

    use()
    yield use
    crypto.reset()


def _legacy(secret: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()).decode()


def test_unset_the_keyring_is_the_old_derived_key_byte_for_byte(keys):
    keys(secret=f"  {SECRET} ")  # the old code stripped the secret: so does the new one
    assert crypto.keyring() == (_legacy(SECRET),)
    assert not crypto.is_explicit()

    old = Fernet(_legacy(SECRET).encode())
    written_before = old.encrypt(NORMALISED.encode()).decode()
    assert crypto.decrypt(written_before) == NORMALISED
    assert old.decrypt(crypto.encrypt(NORMALISED).encode()).decode() == NORMALISED
    assert crypto.fingerprint(IBAN) == (
        hashlib.sha256(f"{SECRET}|{NORMALISED}".encode()).hexdigest()
    )


def test_the_first_key_encrypts_and_every_key_decrypts(keys):
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    keys(data_keys=old)
    under_old = crypto.encrypt(NORMALISED)

    keys(data_keys=f"{new}, {old}")
    assert crypto.decrypt(under_old) == NORMALISED
    assert not crypto.is_current(under_old)
    under_new = crypto.encrypt(NORMALISED)
    assert crypto.is_current(under_new)
    assert Fernet(new.encode()).decrypt(under_new.encode()).decode() == NORMALISED
    assert crypto.is_current(crypto.rotate(under_old))

    keys(data_keys=new)
    assert crypto.decrypt(under_new) == NORMALISED
    assert crypto.decrypt(under_old) is None


def test_once_explicit_rotating_the_session_secret_leaves_the_data_readable(keys):
    keys()
    explicit = crypto.legacy_key()
    written = crypto.encrypt(NORMALISED)

    keys(secret="another-session-secret-entirely", data_keys=explicit)
    assert crypto.decrypt(written) == NORMALISED


def test_session_tokens_are_signed_by_the_session_secret_alone(keys):
    data_key = Fernet.generate_key().decode()
    keys(data_keys=data_key)
    token = security.create_access_token("someone", "manager")
    assert jwt.decode(token, SECRET, algorithms=["HS256"])["sub"] == "someone"
    assert security.read_access_token(token)["role"] == "manager"
    with pytest.raises(Exception):  # noqa: B017 - any refusal will do
        jwt.decode(token, data_key, algorithms=["HS256"])


def test_a_malformed_key_stops_instead_of_reading_every_value_as_absent(keys):
    good = Fernet.generate_key().decode()
    keys(data_keys=f"{good},not-a-key")
    with pytest.raises(RuntimeError) as refused:
        crypto.decrypt("anything")
    assert "#2" in str(refused.value)
    assert good not in str(refused.value), "the refusal must never show a key"

    keys(data_keys=f"{good},{good}")
    with pytest.raises(RuntimeError):
        crypto.keyring()


def test_the_fingerprint_follows_the_data_key_and_matching_covers_the_window(keys):
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    keys()
    legacy_form = crypto.fingerprint(IBAN)

    keys(data_keys=old)
    under_old = crypto.fingerprint(IBAN)
    assert under_old != legacy_form
    assert legacy_form in crypto.fingerprints(IBAN), (
        "the window after making it explicit"
    )

    keys(data_keys=f"{new},{old}")
    under_new = crypto.fingerprint(IBAN)
    assert under_new not in (under_old, legacy_form)
    assert crypto.fingerprints(IBAN)[:2] == [under_new, under_old]


def test_a_key_is_named_without_being_shown(keys):
    key = Fernet.generate_key().decode()
    assert len(crypto.key_id(key)) == 8
    assert crypto.key_id(key) not in key


def test_every_encrypted_column_is_known_to_the_pass():
    """A column holding ciphertext is named `*_encrypted` or `*_enc`; each one must be
    walked by the re-encryption pass, or the rotation leaves it on the retired key."""
    import app.models  # noqa: F401  (registers every table)

    declared = {
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if column.name.endswith(("_encrypted", "_enc"))
    }
    walked = {f.name for f in reencrypt.FIELDS}
    assert declared == walked, f"declared={sorted(declared)} walked={sorted(walked)}"
