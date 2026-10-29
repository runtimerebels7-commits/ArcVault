import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIRECTORY = PROJECT_ROOT / "data"
AUDIT_LOG_PATH = DATA_DIRECTORY / "audit.log"

GENESIS_HASH = "0" * 64


def canonical_json(data: dict[str, Any]) -> bytes:
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def calculate_entry_hash(entry: dict[str, Any]) -> str:
    """Calculate the SHA-256 hash of an audit entry."""

    return hashlib.sha256(canonical_json(entry)).hexdigest()


def _read_entries() -> list[dict[str, Any]]:
    """Read audit entries, rejecting malformed JSON lines."""

    if not AUDIT_LOG_PATH.exists():
        return []

    entries = []

    with AUDIT_LOG_PATH.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Malformed audit log at line {line_number}."
                ) from exc

            if not isinstance(entry, dict):
                raise ValueError(
                    f"Invalid audit entry at line {line_number}."
                )

            entries.append(entry)

    return entries


def verify_audit_log() -> bool:
    """
    Verify the audit log's hash chain.

    Returns False if entries have been altered, removed,
    reordered, or inserted into the existing chain.
    """

    try:
        entries = _read_entries()
        expected_previous_hash = GENESIS_HASH

        for entry in entries:
            if not isinstance(entry.get("event"), str):
                return False

            if not isinstance(entry.get("timestamp"), str):
                return False

            if not isinstance(entry.get("details"), dict):
                return False

            if entry.get("previous_hash") != expected_previous_hash:
                return False

            recorded_hash = entry.get("entry_hash")

            if not isinstance(recorded_hash, str):
                return False

            body = {
                "timestamp": entry["timestamp"],
                "event": entry["event"],
                "details": entry["details"],
                "previous_hash": entry["previous_hash"],
            }

            actual_hash = calculate_entry_hash(body)

            if actual_hash != recorded_hash:
                return False

            expected_previous_hash = recorded_hash

        return True

    except (OSError, ValueError, TypeError):
        return False


def log_event(
    event: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Append an event to the hash-linked audit log.

    This local implementation is for a single-process prototype.
    It is not a tamper-proof storage system.
    """

    if not isinstance(event, str) or not event.strip():
        raise ValueError("Event must be a non-empty string.")

    if details is None:
        details = {}

    if not isinstance(details, dict):
        raise ValueError("Audit details must be a dictionary.")

    # Prevent accidentally storing arbitrary non-JSON objects.
    try:
        canonical_json(details)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Audit details must contain valid JSON data."
        ) from exc

    DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)

    # Refuse to extend a log whose integrity check fails.
    if not verify_audit_log():
        raise ValueError(
            "Audit log integrity check failed. "
            "Do not append to the damaged log."
        )

    entries = _read_entries()

    previous_hash = (
        entries[-1]["entry_hash"]
        if entries
        else GENESIS_HASH
    )

    body = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "details": details,
        "previous_hash": previous_hash,
    }

    entry = {
        **body,
        "entry_hash": calculate_entry_hash(body),
    }

    # Append-only behaviour within this application.
    # Concurrent writers would need file locking or a database.
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(
            json.dumps(
                entry,
                sort_keys=True,
                ensure_ascii=False,
            )
            + "\n"
        )

    return entry


def configure_standard_logger() -> logging.Logger:
    """Configure a conventional application logger."""

    DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("veribhasha")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.FileHandler(
            DATA_DIRECTORY / "application.log",
            encoding="utf-8",
        )

        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(levelname)s - %(message)s"
            )
        )

        logger.addHandler(handler)

    return logger