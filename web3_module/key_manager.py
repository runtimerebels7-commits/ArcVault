"""Convenience helpers for the local Ed25519 demo key pair."""
from .generate_keys import generate_keys
from .rights_signer import PRIVATE_KEY_PATH, PUBLIC_KEY_PATH


def keys_exist() -> bool:
    return PRIVATE_KEY_PATH.exists() and PUBLIC_KEY_PATH.exists()


def ensure_keys() -> None:
    """Create a matching key pair only when neither key exists."""
    if keys_exist():
        return
    if PRIVATE_KEY_PATH.exists() or PUBLIC_KEY_PATH.exists():
        raise RuntimeError("Only one signing key exists; restore the matching pair before continuing.")
    generate_keys()
