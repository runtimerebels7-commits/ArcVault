import base64
import json
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from web3_module.rights_validator import (
    RightsValidationError,
    validate_rights_record,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
KEY_DIRECTORY = PROJECT_ROOT / "keys"

PRIVATE_KEY_PATH = KEY_DIRECTORY / "private_key.pem"
PUBLIC_KEY_PATH = KEY_DIRECTORY / "public_key.pem"


def canonical_json(data: dict[str, Any]) -> bytes:
    """
    Serialize JSON deterministically so the same record produces
    the same bytes when signed and verified.
    """

    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def load_private_key() -> Ed25519PrivateKey:
    """Load the local Ed25519 private key."""

    if not PRIVATE_KEY_PATH.exists():
        raise FileNotFoundError(
            "Private key not found. Run "
            "'python -m web3_module.generate_keys' first."
        )

    key_data = PRIVATE_KEY_PATH.read_bytes()

    key = serialization.load_pem_private_key(
        key_data,
        password=None,
    )

    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("The configured private key is not Ed25519.")

    return key


def load_public_key() -> Ed25519PublicKey:
    """Load the Ed25519 public key."""

    if not PUBLIC_KEY_PATH.exists():
        raise FileNotFoundError(
            "Public key not found. Generate the key pair first."
        )

    key_data = PUBLIC_KEY_PATH.read_bytes()

    key = serialization.load_pem_public_key(key_data)

    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("The configured public key is not Ed25519.")

    return key


def sign_rights_record(
    record: dict[str, Any],
) -> dict[str, Any]:
    """Validate and digitally sign a rights record."""

    validate_rights_record(record)

    private_key = load_private_key()

    payload = canonical_json(record)
    signature = private_key.sign(payload)

    return {
        "rights_record": record,
        "signature": base64.b64encode(signature).decode("ascii"),
        "algorithm": "Ed25519",
        "serialization": "canonical-json-v1",
    }


def verify_signature(
    signed_record: dict[str, Any],
) -> bool:
    """
    Verify a record's signature.

    Returns False if the signature is missing, malformed,
    or invalid. A valid signature does not establish that
    the licence is still active.
    """

    try:
        if not isinstance(signed_record, dict):
            return False

        if signed_record.get("algorithm") != "Ed25519":
            return False

        if (
            signed_record.get("serialization")
            != "canonical-json-v1"
        ):
            return False

        record = signed_record.get("rights_record")
        signature_text = signed_record.get("signature")

        if not isinstance(record, dict):
            return False

        if not isinstance(signature_text, str):
            return False

        signature = base64.b64decode(
            signature_text,
            validate=True,
        )

        public_key = load_public_key()

        public_key.verify(
            signature,
            canonical_json(record),
        )

        return True

    except (
        InvalidSignature,
        ValueError,
        TypeError,
        KeyError,
        UnicodeError,
        json.JSONDecodeError,
        OSError,
    ):
        return False


def verify_rights_record(
    signed_record: dict[str, Any],
) -> dict[str, Any]:
    """Verify the signature and validate the record's structure."""

    if not verify_signature(signed_record):
        return {
            "signature_valid": False,
            "record_valid": False,
            "message": "Signature verification failed.",
        }

    try:
        validate_rights_record(signed_record["rights_record"])

    except RightsValidationError as exc:
        return {
            "signature_valid": True,
            "record_valid": False,
            "message": str(exc),
        }

    return {
        "signature_valid": True,
        "record_valid": True,
        "message": "Signature verified and record structure is valid.",
    }