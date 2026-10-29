from datetime import date
from typing import Any


ALLOWED_USES = {
    "research",
    "education",
    "commercial_training",
}

VALID_STATUSES = {
    "active",
    "revoked",
    "superseded",
}

REQUIRED_FIELDS = {
    "dataset_id",
    "version",
    "name",
    "owner_id",
    "allowed_uses",
    "commercial_training",
    "geographical_restrictions",
    "derivative_works_allowed",
    "redistribution_allowed",
    "expiry_date",
    "status",
}


class RightsValidationError(ValueError):
    """Raised when a rights record is invalid."""


def validate_rights_record(
    record: dict[str, Any],
) -> bool:
    """Validate the structure and values of a rights record."""

    if not isinstance(record, dict):
        raise RightsValidationError(
            "Rights record must be a JSON object."
        )

    missing_fields = REQUIRED_FIELDS - set(record.keys())

    if missing_fields:
        raise RightsValidationError(
            f"Missing required fields: {sorted(missing_fields)}"
        )

    # Validate identifiers and name.
    for field in ("dataset_id", "name", "owner_id"):
        value = record[field]

        if not isinstance(value, str) or not value.strip():
            raise RightsValidationError(
                f"{field} must be a non-empty string."
            )

    # bool is a subclass of int in Python, so reject it explicitly.
    version = record["version"]

    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or version < 1
    ):
        raise RightsValidationError(
            "version must be a positive integer."
        )

    # Validate permitted uses.
    allowed_uses = record["allowed_uses"]

    if not isinstance(allowed_uses, list):
        raise RightsValidationError(
            "allowed_uses must be a list."
        )

    if len(allowed_uses) != len(set(allowed_uses)):
        raise RightsValidationError(
            "allowed_uses cannot contain duplicates."
        )

    if not all(isinstance(use, str) for use in allowed_uses):
        raise RightsValidationError(
            "Every allowed use must be a string."
        )

    unsupported_uses = set(allowed_uses) - ALLOWED_USES

    if unsupported_uses:
        raise RightsValidationError(
            f"Unsupported uses: {sorted(unsupported_uses)}"
        )

    # Validate boolean permissions.
    boolean_fields = (
        "commercial_training",
        "derivative_works_allowed",
        "redistribution_allowed",
    )

    for field in boolean_fields:
        if not isinstance(record[field], bool):
            raise RightsValidationError(
                f"{field} must be true or false."
            )

    # Keep the explicit commercial-training flag consistent
    # with the allowed_uses list.
    if (
        record["commercial_training"]
        != ("commercial_training" in allowed_uses)
    ):
        raise RightsValidationError(
            "commercial_training must match allowed_uses."
        )

    # Validate geographic restrictions.
    geography = record["geographical_restrictions"]

    if not isinstance(geography, dict):
        raise RightsValidationError(
            "geographical_restrictions must be an object."
        )

    required_geo_fields = {
        "allowed_regions",
        "restricted_regions",
    }

    if not required_geo_fields.issubset(geography):
        raise RightsValidationError(
            "Geographic restrictions require allowed_regions "
            "and restricted_regions."
        )

    for field in required_geo_fields:
        regions = geography[field]

        if not isinstance(regions, list):
            raise RightsValidationError(
                f"{field} must be a list."
            )

        if not all(
            isinstance(region, str) and region.strip()
            for region in regions
        ):
            raise RightsValidationError(
                f"{field} must contain non-empty strings."
            )

        if len(regions) != len(set(regions)):
            raise RightsValidationError(
                f"{field} cannot contain duplicates."
            )

    # Validate expiry date.
    expiry = record["expiry_date"]

    if not isinstance(expiry, str):
        raise RightsValidationError(
            "expiry_date must use YYYY-MM-DD format."
        )

    try:
        parsed_expiry = date.fromisoformat(expiry)
    except ValueError as exc:
        raise RightsValidationError(
            "expiry_date must be a valid YYYY-MM-DD date."
        ) from exc

    if parsed_expiry.isoformat() != expiry:
        raise RightsValidationError(
            "expiry_date must use YYYY-MM-DD format."
        )

    # Validate status.
    status = record["status"]

    if status not in VALID_STATUSES:
        raise RightsValidationError(
            f"Invalid licence status: {status}"
        )

    return True


def get_permission_status(
    record: dict[str, Any],
    today: date | None = None,
) -> tuple[bool, str]:
    """Check whether the licence is currently active."""

    validate_rights_record(record)

    if today is None:
        today = date.today()

    if record["status"] == "revoked":
        return False, "Licence has been revoked."

    if record["status"] == "superseded":
        return False, "This rights record has been superseded."

    expiry = date.fromisoformat(record["expiry_date"])

    if expiry < today:
        return False, "Licence has expired."

    return True, "Licence is active."


def check_permission(
    record: dict[str, Any],
    intended_use: str,
    region: str,
    today: date | None = None,
) -> tuple[bool, str]:
    """Determine whether a specific use and region are permitted."""

    validate_rights_record(record)

    if intended_use not in ALLOWED_USES:
        return False, "Unsupported intended use."

    if not isinstance(region, str) or not region.strip():
        return False, "A valid region must be provided."

    active, reason = get_permission_status(record, today=today)

    if not active:
        return False, reason

    if intended_use not in record["allowed_uses"]:
        return False, (
            f"The licence does not permit '{intended_use}'."
        )

    geography = record["geographical_restrictions"]

    allowed_regions = geography["allowed_regions"]
    restricted_regions = geography["restricted_regions"]

    # Exact region matching is deliberate for this prototype.
    if region in restricted_regions:
        return False, f"The region '{region}' is restricted."

    # An empty allowed_regions list means no region is explicitly
    # allowlisted; this prototype treats that as unrestricted,
    # except for explicitly restricted regions.
    if allowed_regions and region not in allowed_regions:
        return False, f"The region '{region}' is not allowlisted."

    if (
        intended_use == "commercial_training"
        and not record["commercial_training"]
    ):
        return False, "Commercial AI training is not permitted."

    return True, "The requested use is permitted."