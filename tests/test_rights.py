from copy import deepcopy
from datetime import date, timedelta

import pytest

from web3_module.generate_keys import generate_keys
from web3_module.rights_record import sample_rights_record
from web3_module.rights_signer import (
    sign_rights_record,
    verify_rights_record,
    verify_signature,
)
from web3_module.rights_validator import (
    RightsValidationError,
    check_permission,
    validate_rights_record,
)


@pytest.fixture(scope="session", autouse=True)
def ensure_keys_exist():
    """
    Ensure a local key pair exists before tests run.

    Existing keys are preserved.
    """

    from web3_module.rights_signer import (
        PRIVATE_KEY_PATH,
        PUBLIC_KEY_PATH,
    )

    if PRIVATE_KEY_PATH.exists() and PUBLIC_KEY_PATH.exists():
        return

    if PRIVATE_KEY_PATH.exists() or PUBLIC_KEY_PATH.exists():
        pytest.fail(
            "Only one key file exists. Restore the matching key pair "
            "before running the tests."
        )

    generate_keys()


def test_valid_record_passes_validation():
    record = sample_rights_record()

    assert validate_rights_record(record) is True


def test_valid_signature_verifies():
    record = sample_rights_record()
    signed = sign_rights_record(record)

    assert verify_signature(signed) is True

    result = verify_rights_record(signed)

    assert result["signature_valid"] is True
    assert result["record_valid"] is True


def test_tampered_record_fails_signature_verification():
    record = sample_rights_record()
    signed = sign_rights_record(record)

    tampered = deepcopy(signed)
    tampered["rights_record"]["allowed_uses"].append(
        "commercial_training"
    )

    assert verify_signature(tampered) is False


def test_missing_required_field_is_rejected():
    record = sample_rights_record()
    del record["owner_id"]

    with pytest.raises(RightsValidationError):
        validate_rights_record(record)


def test_expired_licence_is_denied():
    record = sample_rights_record()

    yesterday = date.today() - timedelta(days=1)
    record["expiry_date"] = yesterday.isoformat()

    permitted, reason = check_permission(
        record,
        intended_use="research",
        region="India",
    )

    assert permitted is False
    assert "expired" in reason.lower()


def test_revoked_licence_is_denied():
    record = sample_rights_record()
    record["status"] = "revoked"

    permitted, reason = check_permission(
        record,
        intended_use="research",
        region="India",
    )

    assert permitted is False
    assert "revoked" in reason.lower()


def test_superseded_licence_is_denied():
    record = sample_rights_record()
    record["status"] = "superseded"

    permitted, reason = check_permission(
        record,
        intended_use="research",
        region="India",
    )

    assert permitted is False
    assert "superseded" in reason.lower()


def test_commercial_training_is_denied():
    record = sample_rights_record()

    permitted, reason = check_permission(
        record,
        intended_use="commercial_training",
        region="India",
    )

    assert permitted is False
    assert "does not permit" in reason.lower()


def test_permitted_research_is_allowed():
    record = sample_rights_record()

    permitted, reason = check_permission(
        record,
        intended_use="research",
        region="India",
    )

    assert permitted is True
    assert "permitted" in reason.lower()


def test_restricted_region_is_denied():
    record = sample_rights_record()

    record["geographical_restrictions"]["restricted_regions"] = [
        "India"
    ]

    permitted, reason = check_permission(
        record,
        intended_use="research",
        region="India",
    )

    assert permitted is False
    assert "restricted" in reason.lower()


def test_unallowlisted_region_is_denied():
    record = sample_rights_record()

    permitted, reason = check_permission(
        record,
        intended_use="research",
        region="United States",
    )

    assert permitted is False
    assert "not allowlisted" in reason.lower()


def test_commercial_training_requires_consistent_fields():
    record = sample_rights_record()

    # The record says commercial training is not permitted,
    # so this flag must remain False.
    record["commercial_training"] = True

    with pytest.raises(RightsValidationError):
        validate_rights_record(record)


def test_invalid_status_is_rejected():
    record = sample_rights_record()
    record["status"] = "unknown"

    with pytest.raises(RightsValidationError):
        validate_rights_record(record)