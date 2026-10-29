import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass  # Environment variables can also be supplied by the shell.
BACKEND_DIRECTORY = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, jsonify, request, session
from flask_cors import CORS

from database import init_db
from services import (
    register_publisher, authenticate_publisher, get_publisher_by_id,
    create_publication, list_publisher_publications, get_publication,
    update_publication, list_marketplace, record_activity, create_access_request,
    list_access_requests, create_demo_transaction, publisher_analytics,
    check_permission, run_optimization, create_manifest, list_audit_logs,
    list_datasets, update_publication_status, verify_and_store_signed_rights,
    create_demo_signed_rights
)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "FLASK_SECRET_KEY", "dev-only-change-this-secret-before-deployment"
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# For production HTTPS deployments set SESSION_COOKIE_SECURE=True.
app.config["SESSION_COOKIE_SECURE"] = False

CORS(app, supports_credentials=True, origins=os.environ.get(
    "FRONTEND_ORIGIN", "http://127.0.0.1:5500"
).split(","))

init_db()


def body_json():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        publisher_id = session.get("publisher_id")
        if not publisher_id:
            return jsonify({"error": "Login required"}), 401
        publisher = get_publisher_by_id(publisher_id)
        if not publisher:
            session.clear()
            return jsonify({"error": "Session is invalid; please log in again"}), 401
        request.publisher = publisher
        return fn(*args, **kwargs)
    return wrapper


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "ArcVault backend"})


@app.post("/api/auth/register")
def register():
    data = body_json()
    if not data:
        return jsonify({"error": "Send a JSON object"}), 400
    try:
        publisher = register_publisher(
            data.get("name", ""), data.get("email", ""), data.get("password", "")
        )
        session["publisher_id"] = publisher["publisher_id"]
        return jsonify({"message": "Publisher registered", "publisher": publisher}), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/auth/login")
def login():
    data = body_json()
    if not data:
        return jsonify({"error": "Send a JSON object"}), 400
    publisher = authenticate_publisher(data.get("email", ""), data.get("password", ""))
    if not publisher:
        return jsonify({"error": "Invalid email or password"}), 401
    session.clear()
    session["publisher_id"] = publisher["publisher_id"]
    return jsonify({"message": "Login successful", "publisher": publisher})


@app.post("/api/auth/logout")
def logout():
    session.clear()
    return jsonify({"message": "Logged out"})


@app.get("/api/auth/me")
@login_required
def me():
    return jsonify({"publisher": request.publisher})


@app.post("/api/publications")
@login_required
def add_publication():
    data = body_json()
    if not data:
        return jsonify({"error": "Send a JSON object"}), 400
    try:
        publication = create_publication(request.publisher["publisher_id"], data)
        return jsonify({"publication": publication}), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/publications/mine")
@login_required
def my_publications():
    return jsonify({"publications": list_publisher_publications(request.publisher["publisher_id"])})


@app.get("/api/publications/<publication_id>")
def publication_detail(publication_id):
    publication = get_publication(publication_id)
    if not publication:
        return jsonify({"error": "Publication not found"}), 404
    # Public details omit internal signature fields and publisher email.
    return jsonify({"publication": publication})


@app.patch("/api/publications/<publication_id>")
@login_required
def edit_publication(publication_id):
    data = body_json()
    if not data:
        return jsonify({"error": "Send a JSON object"}), 400
    try:
        result = update_publication(
            publication_id, request.publisher["publisher_id"], data
        )
        if not result:
            return jsonify({"error": "Publication not found or not owned by you"}), 404
        return jsonify({"publication": result})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.patch("/api/publications/<publication_id>/status")
@login_required
def publication_status(publication_id):
    data = body_json()
    if not data or not isinstance(data.get("status"), str):
        return jsonify({"error": "Provide status"}), 400
    result = update_publication_status(
        publication_id, request.publisher["publisher_id"], data["status"]
    )
    if not result:
        return jsonify({"error": "Publication not found, not owned by you, or invalid status"}), 400
    return jsonify({"publication": result})


@app.post("/api/publications/<publication_id>/rights-record/verify")
@login_required
def verify_publication_rights(publication_id):
    data = body_json()
    if not data or not isinstance(data.get("signed_record"), dict):
        return jsonify({"error": "signed_record JSON object is required"}), 400
    result = verify_and_store_signed_rights(
        publication_id, request.publisher["publisher_id"], data["signed_record"]
    )
    return jsonify(result), (200 if result.get("verified") else 400)


@app.post("/api/publications/<publication_id>/rights-record/demo-sign")
@login_required
def demo_sign_publication_rights(publication_id):
    """Hackathon demo only: server signs an owner-attested rights record using its local key."""
    publication = get_publication(publication_id)
    if not publication or publication.get("publisher_id") != request.publisher["publisher_id"]:
        return jsonify({"error": "Publication not found or not owned by you"}), 404
    data = body_json() or {}
    try:
        result = create_demo_signed_rights(
            publication,
            request.publisher["publisher_id"],
            expiry_date=data.get("expiry_date", "2027-12-31"),
            allowed_regions=data.get("allowed_regions", ["India"]),
            restricted_regions=data.get("restricted_regions", []),
            derivative_works_allowed=data.get("derivative_works_allowed", False),
            redistribution_allowed=data.get("redistribution_allowed", False),
        )
    except (ValueError, FileNotFoundError, OSError) as exc:
        return jsonify({"verified": False, "error": str(exc),
                        "hint": "Generate a local Ed25519 key pair with: python -m web3_module.generate_keys"}), 400
    return jsonify(result), (200 if result.get("verified") else 400)


@app.get("/api/marketplace")
def marketplace():
    return jsonify({"publications": list_marketplace()})


@app.post("/api/publications/<publication_id>/view")
def publication_view(publication_id):
    publication = get_publication(publication_id)
    if not publication or publication["status"] != "active":
        return jsonify({"error": "Active publication not found"}), 404
    record_activity(publication_id, publication["publisher_id"], "view")
    return jsonify({"message": "View recorded"}), 201


@app.post("/api/access-requests")
def access_request():
    data = body_json()
    if not data or not data.get("publication_id") or not data.get("intended_use"):
        return jsonify({"error": "publication_id and intended_use are required"}), 400
    publication = get_publication(data["publication_id"])
    if not publication or publication["status"] != "active":
        return jsonify({"error": "Active publication not found"}), 404
    decision = check_permission(publication, data["intended_use"])
    request_id = create_access_request(
        publication, data["intended_use"], decision, data.get("buyer_reference")
    )
    return jsonify({"request_id": request_id, "decision": decision}), 201


@app.get("/api/access-requests/mine")
@login_required
def my_access_requests():
    return jsonify({"access_requests": list_access_requests(request.publisher["publisher_id"])})


@app.post("/api/transactions/demo")
@login_required
def demo_transaction():
    data = body_json()
    if not data or not data.get("publication_id"):
        return jsonify({"error": "publication_id is required"}), 400
    publication = get_publication(data["publication_id"])
    if not publication or publication["publisher_id"] != request.publisher["publisher_id"]:
        return jsonify({"error": "Publication not found or not owned by you"}), 404
    try:
        transaction = create_demo_transaction(publication, data.get("amount"))
        return jsonify({"transaction": transaction, "notice": "DEMO ONLY: no real payment was processed"}), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/publisher/analytics")
@login_required
def analytics():
    return jsonify(publisher_analytics(request.publisher["publisher_id"]))


@app.post("/api/permissions/check")
def permission_check():
    data = body_json()
    if not data or not data.get("publication_id") or not data.get("intended_use"):
        return jsonify({"error": "publication_id and intended_use are required"}), 400
    publication = get_publication(data["publication_id"])
    if not publication:
        return jsonify({"decision": "REJECTED", "reason": "Publication not found"}), 404
    decision = check_permission(publication, data["intended_use"])
    return jsonify(decision)


@app.post("/api/optimization/run")
def optimize():
    data = body_json()
    if not data or "budget" not in data:
        return jsonify({"error": "budget is required"}), 400
    try:
        budget = float(data["budget"])
        if budget < 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "budget must be a non-negative number"}), 400

    use = data.get("intended_use", "commercial_training")
    candidates = []
    rejected = []
    for pub in list_marketplace():
        decision = check_permission(pub, use)
        if decision["decision"] == "APPROVED":
            candidates.append({
                "dataset_id": pub["publication_id"],
                "licensing_cost": pub["licensing_cost"],
                "value_score": pub["value_score"]
            })
        else:
            rejected.append({"dataset_id": pub["publication_id"], "reason": decision["reason"]})

    result = run_optimization(candidates, budget)
    # Never trust the optimiser blindly; check IDs and budget in backend.
    allowed_ids = {x["dataset_id"] for x in candidates}
    selected = result.get("selected_dataset_ids", [])
    if any(x not in allowed_ids for x in selected):
        return jsonify({"status": "ERROR", "message": "Optimiser returned an ineligible or unknown dataset"}), 502
    chosen = [x for x in candidates if x["dataset_id"] in selected]
    total_cost = sum(float(x["licensing_cost"]) for x in chosen)
    total_value = sum(float(x["value_score"]) for x in chosen)
    if total_cost > budget:
        return jsonify({"status": "ERROR", "message": "Optimiser result exceeds budget"}), 502
    result.update({
        "selected_dataset_ids": selected,
        "total_cost": total_cost,
        "total_value": total_value,
        "budget": budget,
        "rejected_datasets": rejected
    })
    manifest = create_manifest(result, rejected, use)
    result["manifest"] = manifest
    return jsonify(result)


@app.post("/api/manifests/evaluate")
def evaluate_manifest():
    data = body_json()
    if not data or not isinstance(data.get("dataset_ids"), list) or not data.get("intended_use"):
        return jsonify({"error": "dataset_ids list and intended_use are required"}), 400
    accepted, rejected = [], []
    all_publications = {p["publication_id"]: p for p in list_marketplace()}
    for dataset_id in data["dataset_ids"]:
        pub = all_publications.get(dataset_id)
        if not pub:
            rejected.append({"dataset_id": dataset_id, "reason": "Not found or not active"})
            continue
        decision = check_permission(pub, data["intended_use"])
        (accepted if decision["decision"] == "APPROVED" else rejected).append(
            {"dataset_id": dataset_id, **({"reason": decision["reason"]} if decision["decision"] != "APPROVED" else {})}
        )
    manifest = create_manifest({"selected_dataset_ids": [x["dataset_id"] for x in accepted]}, rejected, data["intended_use"])
    return jsonify({"manifest": manifest, "accepted_datasets": accepted, "rejected_datasets": rejected})


@app.get("/api/audit-logs")
@login_required
def audit_logs():
    return jsonify({"audit_logs": list_audit_logs(request.publisher["publisher_id"])})


@app.get("/api/datasets")
def datasets():
    return jsonify({"datasets": list_datasets()})


if __name__ == "__main__":
    app.run(debug=True)
