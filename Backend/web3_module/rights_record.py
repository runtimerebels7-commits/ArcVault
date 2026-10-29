from datetime import date
from typing import Any


SUPPORTED_USES = {
    "research",
    "education",
    "commercial_training",
}

SUPPORTED_STATUSES = {
    "active",
    "revoked",
    "superseded",
}


def create_rights_record(
    dataset_id: str,
    name: str,
    owner_id: str,
    allowed_uses: list[str],
    expiry_date: str,
    allowed_regions: list[str] | None = None,
    restricted_regions: list[str] | None = None,
    derivative_works_allowed: bool = False,
    redistribution_allowed: bool = False,
    commercial_training: bool = False,
    version: int = 1,
) -> dict[str, Any]:
    """
    Create a structured dataset rights record.

    This function creates the record; validation and signing
    are handled by separate modules.
    """

    if allowed_regions is None:
        allowed_regions = ["India"]

    if restricted_regions is None:
        restricted_regions = []

    return {
        "dataset_id": dataset_id,
        "version": version,
        "name": name,
        "owner_id": owner_id,
        "allowed_uses": allowed_uses,
        "commercial_training": commercial_training,
        "geographical_restrictions": {
            "allowed_regions": allowed_regions,
            "restricted_regions": restricted_regions,
        },
        "derivative_works_allowed": derivative_works_allowed,
        "redistribution_allowed": redistribution_allowed,
        "expiry_date": expiry_date,
        "status": "active",
    }


def sample_rights_record() -> dict[str, Any]:
    """Return a sample record for local testing and demonstration."""

    return create_rights_record(
        dataset_id="DATASET001",
        name="Kannada Education Dataset",
        owner_id="PUBLISHER001",
        allowed_uses=["research", "education"],
        commercial_training=False,
        allowed_regions=["India"],
        restricted_regions=[],
        derivative_works_allowed=False,
        redistribution_allowed=False,
        expiry_date="2027-12-31",
        version=1,
    )