import json
import sqlite3
import uuid
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from database import connect
from web3_module.rights_record import create_rights_record
from web3_module.rights_signer import sign_rights_record, verify_rights_record
from web3_module.rights_validator import check_permission as check_signed_rights_permission


def now():
    return datetime.now(timezone.utc).isoformat()


def uid(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def audit(action, result, publisher_id=None, publication_id=None, details=None):
    with connect() as conn:
        conn.execute(
            """INSERT INTO audit_logs
            (log_id, publisher_id, publication_id, action, result, details_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (uid("AUD"), publisher_id, publication_id, action, result,
             json.dumps(details or {}), now())
        )


def register_publisher(name, email, password):
    name, email = (name or "").strip(), (email or "").strip().lower()
    if not name or "@" not in email:
        raise ValueError("A name and valid email are required")
    if not isinstance(password, str) or len(password) < 8:
        raise ValueError("Password must contain at least 8 characters")
    publisher = {"publisher_id": uid("PUB"), "name": name, "email": email}
    try:
        with connect() as conn:
            conn.execute(
                "INSERT INTO publishers VALUES (?, ?, ?, ?, ?)",
                (publisher["publisher_id"], name, email, generate_password_hash(password), now())
            )
    except sqlite3.IntegrityError:
        raise ValueError("An account with this email already exists")
    audit("publisher_registered", "SUCCESS", publisher["publisher_id"])
    return publisher


def authenticate_publisher(email, password):
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM publishers WHERE email = ?", ((email or "").strip().lower(),)
        ).fetchone()
    if not row or not check_password_hash(row["password_hash"], password or ""):
        return None
    publisher = {"publisher_id": row["publisher_id"], "name": row["name"], "email": row["email"]}
    audit("publisher_login", "SUCCESS", publisher["publisher_id"])
    return publisher


def get_publisher_by_id(publisher_id):
    with connect() as conn:
        row = conn.execute(
            "SELECT publisher_id, name, email FROM publishers WHERE publisher_id = ?",
            (publisher_id,)
        ).fetchone()
    return dict(row) if row else None


def _publication_dict(row):
    if not row:
        return None
    d = dict(row)
    d["allowed_uses"] = json.loads(d.pop("allowed_uses_json"))
    signed_json = d.pop("rights_record_json", None)
    d["signed_rights_record"] = json.loads(signed_json) if signed_json else None
    d["rights_verified"] = bool(d["rights_verified"])
    # Signed rights are public verification material; never expose private keys.
    return d


def create_publication(publisher_id, data):
    required = ["title", "language", "licence_type", "licence_terms"]
    if any(not isinstance(data.get(k), str) or not data[k].strip() for k in required):
        raise ValueError("title, language, licence_type, and licence_terms are required")
    try:
        cost = float(data.get("licensing_cost", 0))
        value = float(data.get("value_score", 0))
        if cost < 0 or value < 0:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("licensing_cost and value_score must be non-negative numbers")
    allowed = data.get("allowed_uses", [])
    if not isinstance(allowed, list) or any(not isinstance(x, str) for x in allowed):
        raise ValueError("allowed_uses must be a list of strings")
    publication_id, timestamp = uid("DS"), now()
    with connect() as conn:
        conn.execute("""INSERT INTO publications
            (publication_id, publisher_id, title, language, description, licence_type,
             licence_terms, licensing_cost, value_score, allowed_uses_json, status,
             rights_verified, signature_status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 0, 'UNVERIFIED', ?, ?)""",
            (publication_id, publisher_id, data["title"].strip(), data["language"].strip(),
             (data.get("description") or "").strip(), data["licence_type"].strip(),
             data["licence_terms"].strip(), cost, value, json.dumps(allowed), timestamp, timestamp)
        )
        row = conn.execute("SELECT * FROM publications WHERE publication_id = ?", (publication_id,)).fetchone()
    audit("publication_created", "SUCCESS", publisher_id, publication_id)
    return _publication_dict(row)


def list_publisher_publications(publisher_id):
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM publications WHERE publisher_id = ? ORDER BY created_at DESC",
            (publisher_id,)
        ).fetchall()
    return [_publication_dict(r) for r in rows]


def get_publication(publication_id):
    with connect() as conn:
        row = conn.execute(
            "SELECT p.*, u.name AS publisher_name FROM publications p JOIN publishers u ON u.publisher_id=p.publisher_id WHERE p.publication_id=?",
            (publication_id,)
        ).fetchone()
    return _publication_dict(row)


def update_publication(publication_id, publisher_id, data):
    allowed_fields = {"title", "language", "description", "licence_type", "licence_terms", "licensing_cost", "value_score", "allowed_uses"}
    updates = {k: v for k, v in data.items() if k in allowed_fields}
    if not updates:
        raise ValueError("No supported fields to update")
    if "licensing_cost" in updates:
        try:
            updates["licensing_cost"] = float(updates["licensing_cost"])
            if updates["licensing_cost"] < 0: raise ValueError
        except (TypeError, ValueError):
            raise ValueError("licensing_cost must be non-negative")
    if "value_score" in updates:
        try:
            updates["value_score"] = float(updates["value_score"])
            if updates["value_score"] < 0: raise ValueError
        except (TypeError, ValueError):
            raise ValueError("value_score must be non-negative")
    if "allowed_uses" in updates:
        if not isinstance(updates["allowed_uses"], list):
            raise ValueError("allowed_uses must be a list")
        updates["allowed_uses_json"] = json.dumps(updates.pop("allowed_uses"))
    if any(not isinstance(v, str) or not v.strip() for k, v in updates.items() if k not in {"licensing_cost", "value_score", "allowed_uses_json"} and k != "description"):
        raise ValueError("Text fields must be non-empty strings")
    updates["updated_at"] = now()
    with connect() as conn:
        current = conn.execute("SELECT * FROM publications WHERE publication_id=? AND publisher_id=?", (publication_id, publisher_id)).fetchone()
        if not current:
            return None
        # Any licence change invalidates the previous rights verification state.
        if any(k in updates for k in ("title", "licence_type", "licence_terms", "allowed_uses_json")):
            updates["rights_verified"] = 0
            updates["signature_status"] = "UNVERIFIED"
            updates["rights_record_json"] = None
        sql = "UPDATE publications SET " + ", ".join(f"{k}=?" for k in updates) + " WHERE publication_id=? AND publisher_id=?"
        conn.execute(sql, (*updates.values(), publication_id, publisher_id))
        row = conn.execute("SELECT * FROM publications WHERE publication_id=?", (publication_id,)).fetchone()
    audit("publication_updated", "SUCCESS", publisher_id, publication_id, {"fields": list(updates)})
    return _publication_dict(row)


def update_publication_status(publication_id, publisher_id, status):
    if status not in {"active", "inactive", "pending", "withdrawn"}:
        return None
    with connect() as conn:
        cur = conn.execute(
            "UPDATE publications SET status=?, updated_at=? WHERE publication_id=? AND publisher_id=?",
            (status, now(), publication_id, publisher_id)
        )
        if cur.rowcount != 1:
            return None
        row = conn.execute("SELECT * FROM publications WHERE publication_id=?", (publication_id,)).fetchone()
    audit("publication_status_changed", "SUCCESS", publisher_id, publication_id, {"status": status})
    return _publication_dict(row)


def list_marketplace():
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM publications WHERE status='active' ORDER BY created_at DESC"
        ).fetchall()
    return [_publication_dict(r) for r in rows]


def record_activity(publication_id, publisher_id, event_type, details=None):
    with connect() as conn:
        conn.execute(
            "INSERT INTO activity_events VALUES (?, ?, ?, ?, ?, ?)",
            (uid("EVT"), publication_id, publisher_id, event_type, json.dumps(details or {}), now())
        )
    audit(f"activity_{event_type}", "SUCCESS", publisher_id, publication_id, details)


def verify_and_store_signed_rights(publication_id, publisher_id, signed_record):
    """Verify a supplied Ed25519 rights record and store it only when it matches this publication."""
    verification = verify_rights_record(signed_record)
    if not verification.get("signature_valid") or not verification.get("record_valid"):
        audit("rights_verification", "FAILED", publisher_id, publication_id, verification)
        return {"verified": False, **verification}

    record = signed_record["rights_record"]
    publication = get_publication(publication_id)
    if not publication or publication.get("publisher_id") != publisher_id:
        return {"verified": False, "message": "Publication not found or not owned by you."}

    matches = (
        record.get("dataset_id") == publication_id
        and record.get("owner_id") == publisher_id
        and record.get("name") == publication.get("title")
        and record.get("allowed_uses") == publication.get("allowed_uses")
    )
    if not matches:
        result = {"verified": False, "message": "Signed rights record does not match this publication's ID, owner, title, or allowed uses."}
        audit("rights_verification", "FAILED", publisher_id, publication_id, result)
        return result

    with connect() as conn:
        conn.execute(
            "UPDATE publications SET rights_verified=1, signature_status='VALID', rights_record_json=?, updated_at=? WHERE publication_id=? AND publisher_id=?",
            (json.dumps(signed_record), now(), publication_id, publisher_id)
        )
    result = {"verified": True, **verification}
    audit("rights_verification", "SUCCESS", publisher_id, publication_id, {"algorithm": signed_record.get("algorithm")})
    return result


def create_demo_signed_rights(publication, publisher_id, expiry_date="2027-12-31",
                              allowed_regions=None, restricted_regions=None,
                              derivative_works_allowed=False, redistribution_allowed=False):
    """Hackathon-only helper: signs an owner-attested record with this local server key."""
    allowed_uses = publication.get("allowed_uses", [])
    record = create_rights_record(
        dataset_id=publication["publication_id"],
        name=publication["title"],
        owner_id=publisher_id,
        allowed_uses=allowed_uses,
        expiry_date=expiry_date,
        allowed_regions=allowed_regions or ["India"],
        restricted_regions=restricted_regions or [],
        derivative_works_allowed=bool(derivative_works_allowed),
        redistribution_allowed=bool(redistribution_allowed),
        commercial_training=("commercial_training" in allowed_uses),
    )
    signed = sign_rights_record(record)
    return verify_and_store_signed_rights(publication["publication_id"], publisher_id, signed)


def check_permission(publication, intended_use):
    # Fail closed and re-check the stored signature rather than trusting a flag alone.
    signed_record = publication.get("signed_rights_record")
    verification = verify_rights_record(signed_record) if signed_record else {
        "signature_valid": False, "record_valid": False, "message": "No signed rights record is stored."
    }
    record = signed_record.get("rights_record", {}) if isinstance(signed_record, dict) else {}
    matches_publication = (
        record.get("dataset_id") == publication.get("publication_id")
        and record.get("owner_id") == publication.get("publisher_id")
        and record.get("name") == publication.get("title")
        and record.get("allowed_uses") == publication.get("allowed_uses")
    )
    if (not publication.get("rights_verified")
        or publication.get("signature_status") != "VALID"
        or not verification.get("signature_valid")
        or not verification.get("record_valid")
        or not matches_publication):
        result = {"decision": "VERIFICATION_FAILED", "reason": "Rights record signature, schema, or dataset match verification failed"}
    elif publication.get("status") != "active":
        result = {"decision": "REJECTED", "reason": "Publication is not active"}
    else:
        permitted, rights_reason = check_signed_rights_permission(record, intended_use, "India")
        if not permitted:
            result = {"decision": "REJECTED", "reason": rights_reason}
        elif intended_use not in publication.get("allowed_uses", []):
            result = {"decision": "REJECTED", "reason": "Licence does not permit this intended use"}
        else:
            result = {"decision": "APPROVED", "reason": "Verified signature and rights permit this intended use"}
    with connect() as conn:
        conn.execute(
            "INSERT INTO permission_checks VALUES (?, ?, ?, ?, ?, ?)",
            (uid("CHK"), publication["publication_id"], intended_use, result["decision"], result["reason"], now())
        )
    audit("permission_check", result["decision"], publication.get("publisher_id"), publication["publication_id"], {"intended_use": intended_use, "reason": result["reason"]})
    return {"publication_id": publication["publication_id"], "intended_use": intended_use, **result}


def create_access_request(publication, intended_use, decision, buyer_reference=None):
    request_id = uid("REQ")
    with connect() as conn:
        conn.execute(
            "INSERT INTO access_requests VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (request_id, publication["publication_id"], publication["publisher_id"],
             intended_use, decision["decision"], decision["reason"],
             (str(buyer_reference)[:120] if buyer_reference else None), now())
        )
    record_activity(publication["publication_id"], publication["publisher_id"], "access_request", {"decision": decision["decision"]})
    return request_id


def list_access_requests(publisher_id):
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM access_requests WHERE publisher_id=? ORDER BY created_at DESC",
            (publisher_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def create_demo_transaction(publication, amount):
    if amount is None:
        amount = publication["licensing_cost"]
    try:
        amount = float(amount)
        if amount < 0 or amount != float(publication["licensing_cost"]):
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("Amount must match the listed licensing cost")
    transaction = {
        "transaction_id": uid("TXN"),
        "publication_id": publication["publication_id"],
        "publisher_id": publication["publisher_id"],
        "amount": amount,
        "status": "DEMO_COMPLETED",
        "is_demo": True,
        "created_at": now()
    }
    with connect() as conn:
        conn.execute(
            "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, 1, ?)",
            (transaction["transaction_id"], transaction["publication_id"],
             transaction["publisher_id"], amount, transaction["status"], transaction["created_at"])
        )
    record_activity(publication["publication_id"], publication["publisher_id"], "purchase_demo", {"amount": amount})
    return transaction


def publisher_analytics(publisher_id):
    with connect() as conn:
        pubs = conn.execute("SELECT publication_id FROM publications WHERE publisher_id=?", (publisher_id,)).fetchall()
        ids = [r["publication_id"] for r in pubs]
        if not ids:
            return {"totals": {"views": 0, "access_requests": 0, "purchases": 0, "demo_revenue": 0}, "publications": []}
        marks = ",".join("?" for _ in ids)
        activity = conn.execute(
            f"SELECT publication_id, event_type, COUNT(*) AS n FROM activity_events WHERE publisher_id=? AND publication_id IN ({marks}) GROUP BY publication_id,event_type",
            (publisher_id, *ids)
        ).fetchall()
        txns = conn.execute(
            f"SELECT publication_id, COUNT(*) AS n, COALESCE(SUM(amount),0) AS revenue FROM transactions WHERE publisher_id=? AND is_demo=1 AND publication_id IN ({marks}) GROUP BY publication_id",
            (publisher_id, *ids)
        ).fetchall()
        titles = {r["publication_id"]: r["title"] for r in conn.execute(
            f"SELECT publication_id,title FROM publications WHERE publication_id IN ({marks})", ids
        ).fetchall()}
    stats = {pid: {"publication_id": pid, "title": titles.get(pid), "views": 0, "access_requests": 0, "purchases": 0, "demo_revenue": 0} for pid in ids}
    for row in activity:
        if row["event_type"] == "view": stats[row["publication_id"]]["views"] = row["n"]
        if row["event_type"] == "access_request": stats[row["publication_id"]]["access_requests"] = row["n"]
    for row in txns:
        stats[row["publication_id"]]["purchases"] = row["n"]
        stats[row["publication_id"]]["demo_revenue"] = row["revenue"]
    all_stats = list(stats.values())
    totals = {k: sum(x[k] for x in all_stats) for k in ("views", "access_requests", "purchases", "demo_revenue")}
    return {"totals": totals, "publications": all_stats, "revenue_note": "Demo transaction totals only; no real payments processed."}


def run_optimization(eligible_datasets, budget):
    """Run budget selection on candidates already approved by rights checks."""
    from optimization.optimizer import optimize_datasets

    result = optimize_datasets(eligible_datasets, budget)
    with connect() as conn:
        conn.execute(
            "INSERT INTO optimisation_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (uid("RUN"), budget, json.dumps(result["selected_dataset_ids"]),
             result["total_cost"], result["total_value"], result["status"],
             result["engine"], now())
        )
    audit("optimisation_run", result["status"], details={
        "engine": result["engine"], "selected": result["selected_dataset_ids"]
    })
    return result


def create_manifest(result, rejected, intended_use):
    manifest = {
        "manifest_id": uid("MAN"),
        "intended_use": intended_use,
        "accepted_dataset_ids": result.get("selected_dataset_ids", []),
        "rejected_datasets": rejected,
        "created_at": now()
    }
    with connect() as conn:
        conn.execute(
            "INSERT INTO corpus_manifests VALUES (?, ?, ?, ?, ?, ?)",
            (manifest["manifest_id"], intended_use, json.dumps(manifest["accepted_dataset_ids"]),
             json.dumps(rejected), None, manifest["created_at"])
        )
    audit("corpus_manifest_created", "SUCCESS", details={"manifest_id": manifest["manifest_id"]})
    return manifest


def list_audit_logs(publisher_id):
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_logs WHERE publisher_id=? ORDER BY created_at DESC LIMIT 200",
            (publisher_id,)
        ).fetchall()
    return [{**dict(r), "details": json.loads(r["details_json"])} for r in rows]


def list_datasets():
    return list_marketplace()
