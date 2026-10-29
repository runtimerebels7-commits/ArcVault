from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)


# Project root: member3_web3/
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Private key is stored locally and excluded from Git.
KEY_DIRECTORY = PROJECT_ROOT / "keys"
PRIVATE_KEY_PATH = KEY_DIRECTORY / "private_key.pem"
PUBLIC_KEY_PATH = KEY_DIRECTORY / "public_key.pem"


def generate_keys():
    """Generate an Ed25519 key pair without overwriting existing keys."""

    KEY_DIRECTORY.mkdir(parents=True, exist_ok=True)

    if PRIVATE_KEY_PATH.exists() or PUBLIC_KEY_PATH.exists():
        raise FileExistsError(
            "A key file already exists. Refusing to overwrite it. "
            "Back up your existing keys before generating new ones."
        )

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    # Use exclusive creation so existing files are never overwritten.
    try:
        with PRIVATE_KEY_PATH.open("xb") as file:
            file.write(private_bytes)

        with PUBLIC_KEY_PATH.open("xb") as file:
            file.write(public_bytes)

    except Exception:
        # Remove newly created files if generating the pair fails.
        PRIVATE_KEY_PATH.unlink(missing_ok=True)
        PUBLIC_KEY_PATH.unlink(missing_ok=True)
        raise

    # Restrict private-key file permissions where supported.
    try:
        PRIVATE_KEY_PATH.chmod(0o600)
    except OSError:
        pass

    print("Ed25519 key pair generated successfully.")
    print(f"Private key: {PRIVATE_KEY_PATH}")
    print(f"Public key:  {PUBLIC_KEY_PATH}")
    print("Keep the private key secret and out of GitHub.")


if __name__ == "__main__":
    generate_keys()