"""End-to-end regression test: publisher listings appear in the user marketplace and optimiser."""
from uuid import uuid4

from publisher_api import app as publisher_app
from Backend.app import app as backend_app


def test_publisher_listing_flows_into_marketplace_and_optimizer():
    publisher_app.config.update(TESTING=True)
    backend_app.config.update(TESTING=True)
    publisher_client = publisher_app.test_client()
    backend_client = backend_app.test_client()

    suffix = uuid4().hex[:10]
    email = f"shared-db-{suffix}@example.test"
    password = "TestPass-12345"

    registered = publisher_client.post("/api/publishers/register", json={
        "name": "Shared DB Test Publisher", "email": email, "password": password
    })
    assert registered.status_code == 201, registered.get_json()

    logged_in = publisher_client.post("/api/publishers/login", json={
        "email": email, "password": password
    })
    assert logged_in.status_code == 200, logged_in.get_json()
    token = logged_in.get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    created = publisher_client.post("/api/datasets", headers=headers, json={
        "name": f"Shared database integration {suffix}",
        "language": "Tamil",
        "category": "Education",
        "format": "CSV",
        "size": "100 records",
        "price": 100,
        "licence": "Research only",
        "description": "Automated shared database integration test.",
        "expiry_date": "2099-12-31",
        "allowed_uses": ["research"],
        "allowed_regions": ["India"],
        "restricted_regions": [],
        "derivative_works_allowed": False,
        "redistribution_allowed": False
    })
    assert created.status_code == 201, created.get_json()
    dataset_id = created.get_json()["dataset"]["id"]

    marketplace = backend_client.get("/api/marketplace")
    assert marketplace.status_code == 200, marketplace.get_json()
    matching = [p for p in marketplace.get_json()["publications"]
                if p["title"] == f"Shared database integration {suffix}"]
    assert len(matching) == 1
    publication = matching[0]
    assert publication["rights_verified"] is True
    assert publication["signature_status"] == "VALID"

    # Editing the publisher listing must update the marketplace record and optimiser input.
    updated_name = f"Shared database integration updated {suffix}"
    updated = publisher_client.put(f"/api/datasets/{dataset_id}", headers=headers, json={
        "name": updated_name,
        "language": "Tamil",
        "category": "Education",
        "format": "CSV",
        "size": "120 records",
        "price": 120,
        "licence": "Research only",
        "description": "Updated integration test listing.",
        "expiry_date": "2099-12-31",
        "allowed_uses": ["research"],
        "allowed_regions": ["India"],
        "restricted_regions": [],
        "derivative_works_allowed": False,
        "redistribution_allowed": False
    })
    assert updated.status_code == 200, updated.get_json()
    marketplace_updated = backend_client.get("/api/marketplace").get_json()["publications"]
    updated_matches = [p for p in marketplace_updated if p["title"] == updated_name]
    assert len(updated_matches) == 1
    publication = updated_matches[0]
    assert publication["licensing_cost"] == 120
    assert publication["rights_verified"] is True

    optimized = backend_client.post("/api/optimization/run", json={
        "budget": 120,
        "intended_use": "research"
    })
    assert optimized.status_code == 200, optimized.get_json()
    assert publication["publication_id"] in optimized.get_json()["selected_dataset_ids"]

    withdrawn = publisher_client.delete(f"/api/datasets/{dataset_id}", headers=headers)
    assert withdrawn.status_code == 200, withdrawn.get_json()
    marketplace_after = backend_client.get("/api/marketplace").get_json()["publications"]
    assert all(p["publication_id"] != publication["publication_id"] for p in marketplace_after)
