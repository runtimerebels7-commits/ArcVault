"""
ArcVault Publisher Portal API.

Run from the extracted project root:
    python -m pip install -r requirements.txt
    python publisher_api.py

Uses the existing Member 3 Web3 rights module for rights validation,
Ed25519 signing, signature verification and audit events.
"""
from __future__ import annotations
import hashlib
import json
import os
import secrets
from datetime import date
from functools import wraps
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass  # Environment variables can also be supplied by the shell.

from flask import Flask, jsonify, request, g
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

from publisher_db import connect, init_db
from Backend.database import connect as backend_connect, init_db as init_backend_db

# These imports are from Member 3's existing folder. Do not duplicate them.
from web3_module.generate_keys import generate_keys
from web3_module.rights_record import create_rights_record
from web3_module.rights_signer import sign_rights_record, verify_rights_record
from web3_module.rights_validator import validate_rights_record, RightsValidationError
from web3_module.audit_logger import log_event, verify_audit_log

app = Flask(__name__)
CORS(app)  # For local frontend integration; restrict origins before deployment.
app.config["JSON_SORT_KEYS"] = False
init_backend_db()
init_db()

def response_error(message, status=400):
    return jsonify({"ok": False, "error": message}), status

def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def ensure_keys():
    from web3_module.rights_signer import PRIVATE_KEY_PATH, PUBLIC_KEY_PATH
    if PRIVATE_KEY_PATH.exists() and PUBLIC_KEY_PATH.exists():
        return
    if PRIVATE_KEY_PATH.exists() or PUBLIC_KEY_PATH.exists():
        raise RuntimeError("Only one signing key exists. Restore the matching key pair.")
    generate_keys()

def current_publisher():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    digest = token_digest(header[7:].strip())
    with connect() as db:
        row = db.execute(
            """SELECT p.id, p.name, p.email FROM portal_publishers p
               JOIN portal_sessions s ON s.publisher_id=p.id WHERE s.token_hash=?""",
            (digest,),
        ).fetchone()
    return dict(row) if row else None

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        publisher = current_publisher()
        if not publisher:
            return response_error("Login required. Send Authorization: Bearer <token>.", 401)
        g.publisher = publisher
        return fn(*args, **kwargs)
    return wrapper

def log_safely(event, details):
    # Member 3's audit log verifies the hash chain before appending.
    try:
        log_event(event, details)
    except Exception as exc:
        app.logger.exception("Audit logging failed: %s", exc)
        # Do not expose secrets or filesystem details to the client.

def row_to_dataset(row):
    d = dict(row)
    for key in ("allowed_uses_json", "allowed_regions_json", "restricted_regions_json",
                "rights_record_json", "signature_json"):
        value_key = key.removesuffix("_json")
        raw = d.pop(key, None)
        try:
            d[value_key] = json.loads(raw) if raw else None
        except (TypeError, json.JSONDecodeError):
            d[value_key] = None
    d["derivative_works_allowed"] = bool(d["derivative_works_allowed"])
    d["redistribution_allowed"] = bool(d["redistribution_allowed"])
    return d

def validate_dataset_payload(data):
    required = ["name", "language", "category", "format", "size", "licence", "description", "expiry_date"]
    missing = [field for field in required if not isinstance(data.get(field), str) or not data[field].strip()]
    if missing:
        raise ValueError("Required fields missing: " + ", ".join(missing))
    try:
        price = float(data.get("price", 0))
    except (TypeError, ValueError):
        raise ValueError("price must be a number.")
    if price < 0:
        raise ValueError("price cannot be negative.")
    try:
        expiry = date.fromisoformat(data["expiry_date"])
    except ValueError:
        raise ValueError("expiry_date must use YYYY-MM-DD.")
    if expiry.isoformat() != data["expiry_date"]:
        raise ValueError("expiry_date must use YYYY-MM-DD.")
    uses = data.get("allowed_uses", ["research"])
    if not isinstance(uses, list):
        raise ValueError("allowed_uses must be a list.")
    allowed_regions = data.get("allowed_regions", ["India"])
    restricted_regions = data.get("restricted_regions", [])
    if not isinstance(allowed_regions, list) or not isinstance(restricted_regions, list):
        raise ValueError("allowed_regions and restricted_regions must be lists.")
    for name in ("derivative_works_allowed", "redistribution_allowed"):
        if name in data and not isinstance(data[name], bool):
            raise ValueError(f"{name} must be true or false.")
    commercial = "commercial_training" in uses
    return {
        "name": data["name"].strip(), "language": data["language"].strip(),
        "category": data["category"].strip(), "format": data["format"].strip(),
        "size": data["size"].strip(), "price": price, "licence": data["licence"].strip(),
        "description": data["description"].strip(), "expiry_date": data["expiry_date"],
        "allowed_uses": uses, "allowed_regions": allowed_regions,
        "restricted_regions": restricted_regions,
        "derivative_works_allowed": data.get("derivative_works_allowed", False),
        "redistribution_allowed": data.get("redistribution_allowed", False),
        "commercial_training": commercial,
    }

def build_signed_rights(dataset_id, publisher_id, payload, version=1, status="active"):
    record = create_rights_record(
        dataset_id=str(dataset_id), name=payload["name"], owner_id=str(publisher_id),
        allowed_uses=payload["allowed_uses"], expiry_date=payload["expiry_date"],
        allowed_regions=payload["allowed_regions"],
        restricted_regions=payload["restricted_regions"],
        derivative_works_allowed=payload["derivative_works_allowed"],
        redistribution_allowed=payload["redistribution_allowed"],
        commercial_training=payload["commercial_training"], version=version,
    )
    record["status"] = status
    validate_rights_record(record)
    ensure_keys()
    signed = sign_rights_record(record)
    return record, signed


def _ensure_backend_publisher(portal_publisher_id: int) -> str:
    """Create/link the corresponding account row required by the marketplace schema."""
    with connect() as portal_db:
        portal = portal_db.execute("SELECT * FROM portal_publishers WHERE id=?", (portal_publisher_id,)).fetchone()
        if not portal:
            raise ValueError("Publisher account was not found")
        if portal["backend_publisher_id"]:
            backend_id = portal["backend_publisher_id"]
            with backend_connect() as backend_db:
                found = backend_db.execute("SELECT publisher_id FROM publishers WHERE publisher_id=?", (backend_id,)).fetchone()
                if found:
                    return backend_id
        backend_id = f"PORTAL_{portal_publisher_id}"
        synthetic_email = f"portal-publisher-{portal_publisher_id}@arcvault.local"
        with backend_connect() as backend_db:
            existing = backend_db.execute("SELECT publisher_id FROM publishers WHERE publisher_id=?", (backend_id,)).fetchone()
            if not existing:
                from datetime import datetime, timezone
                from werkzeug.security import generate_password_hash
                backend_db.execute(
                    "INSERT INTO publishers(publisher_id,name,email,password_hash,created_at) VALUES(?,?,?,?,?)",
                    (backend_id, portal["name"], synthetic_email, generate_password_hash(secrets.token_urlsafe(32)), datetime.now(timezone.utc).isoformat())
                )
        with connect() as portal_db:
            portal_db.execute("UPDATE portal_publishers SET backend_publisher_id=? WHERE id=?", (backend_id, portal_publisher_id))
        return backend_id

def _sync_dataset_to_marketplace(dataset_row):
    """Mirror a portal listing into the shared marketplace table in the SAME SQLite file."""
    dataset = dict(dataset_row)
    portal_publisher_id = int(dataset["publisher_id"])
    backend_publisher_id = _ensure_backend_publisher(portal_publisher_id)
    publication_id = dataset.get("backend_publication_id") or f"DS_PORTAL_{int(dataset['id']):08d}"
    allowed_uses = json.loads(dataset.get("allowed_uses_json") or "[]")
    active = dataset.get("status") == "active"
    payload = {
        "name": dataset["name"],
        "expiry_date": dataset["expiry_date"],
        "allowed_uses": allowed_uses,
        "allowed_regions": json.loads(dataset.get("allowed_regions_json") or '["India"]'),
        "restricted_regions": json.loads(dataset.get("restricted_regions_json") or "[]"),
        "derivative_works_allowed": bool(dataset.get("derivative_works_allowed")),
        "redistribution_allowed": bool(dataset.get("redistribution_allowed")),
        "commercial_training": "commercial_training" in allowed_uses,
    }
    signed_record = build_signed_rights(publication_id, backend_publisher_id, payload, version=int(dataset.get("version") or 1), status="active" if active else "revoked")[1]
    now_value = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    licence_terms = (f"Category: {dataset['category']}; Format: {dataset['format']}; Size: {dataset['size']}; "
                     f"Expiry: {dataset['expiry_date']}; Description: {dataset['description']}")
    value_score = 75.0
    with backend_connect() as backend_db:
        exists = backend_db.execute("SELECT publication_id FROM publications WHERE publication_id=?", (publication_id,)).fetchone()
        if exists:
            backend_db.execute(
                """UPDATE publications SET publisher_id=?,title=?,language=?,description=?,licence_type=?,licence_terms=?,
                   licensing_cost=?,value_score=?,allowed_uses_json=?,status=?,rights_verified=1,signature_status='VALID',
                   rights_record_json=?,updated_at=? WHERE publication_id=?""",
                (backend_publisher_id,dataset["name"],dataset["language"],dataset["description"],dataset["licence"],licence_terms,
                 float(dataset["price"]),value_score,json.dumps(allowed_uses),"active" if active else "withdrawn",json.dumps(signed_record),now_value,publication_id)
            )
        else:
            backend_db.execute(
                """INSERT INTO publications(publication_id,publisher_id,title,language,description,licence_type,licence_terms,
                   licensing_cost,value_score,allowed_uses_json,status,rights_verified,signature_status,rights_record_json,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (publication_id,backend_publisher_id,dataset["name"],dataset["language"],dataset["description"],dataset["licence"],
                 licence_terms,float(dataset["price"]),value_score,json.dumps(allowed_uses),"active" if active else "withdrawn",1,"VALID",
                 json.dumps(signed_record),dataset.get("created_at") or now_value,now_value)
            )
    with connect() as portal_db:
        portal_db.execute("UPDATE portal_datasets SET backend_publication_id=? WHERE id=?", (publication_id, dataset["id"]))

def _sync_all_datasets():
    with connect() as db:
        rows = db.execute("SELECT * FROM portal_datasets ORDER BY id").fetchall()
    for row in rows:
        _sync_dataset_to_marketplace(row)

@app.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "ArcVault Publisher API", "database": "sqlite"})

@app.post("/api/publishers/register")
def register_publisher():
    data = request.get_json(silent=True) or {}
    name, email, password = data.get("name"), data.get("email"), data.get("password")
    if not all(isinstance(x, str) and x.strip() for x in (name, email, password)):
        return response_error("name, email and password are required.")
    if len(password) < 8:
        return response_error("Password must be at least 8 characters.")
    try:
        with connect() as db:
            cur = db.execute(
                "INSERT INTO portal_publishers(name,email,password_hash) VALUES(?,?,?)",
                (name.strip(), email.strip().lower(), generate_password_hash(password)),
            )
            publisher_id = cur.lastrowid
        log_safely("PUBLISHER_REGISTERED", {"publisher_id": publisher_id})
        return jsonify({"ok": True, "publisher": {"id": publisher_id, "name": name.strip(), "email": email.strip().lower()}}), 201
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            return response_error("An account with this email already exists.", 409)
        app.logger.exception("Publisher registration failed")
        return response_error("Could not register publisher.", 500)

@app.post("/api/publishers/login")
def login():
    data = request.get_json(silent=True) or {}
    email, password = data.get("email"), data.get("password")
    if not isinstance(email, str) or not isinstance(password, str):
        return response_error("email and password are required.")
    with connect() as db:
        publisher = db.execute("SELECT * FROM portal_publishers WHERE email=? COLLATE NOCASE", (email.strip(),)).fetchone()
        if not publisher or not check_password_hash(publisher["password_hash"], password):
            return response_error("Invalid email or password.", 401)
        token = secrets.token_urlsafe(32)
        db.execute("INSERT INTO portal_sessions(token_hash,publisher_id) VALUES(?,?)",
                   (token_digest(token), publisher["id"]))
    log_safely("PUBLISHER_LOGIN", {"publisher_id": publisher["id"]})
    return jsonify({"ok": True, "token": token, "publisher": {"id": publisher["id"], "name": publisher["name"], "email": publisher["email"]}})

@app.post("/api/publishers/logout")
@login_required
def logout():
    header = request.headers.get("Authorization", "")
    with connect() as db:
        db.execute("DELETE FROM portal_sessions WHERE token_hash=?", (token_digest(header[7:].strip()),))
    log_safely("PUBLISHER_LOGOUT", {"publisher_id": g.publisher["id"]})
    return jsonify({"ok": True, "message": "Logged out."})

@app.get("/api/publishers/me")
@login_required
def me():
    return jsonify({"ok": True, "publisher": g.publisher})

@app.post("/api/datasets")
@login_required
def create_dataset():
    data = request.get_json(silent=True) or {}
    try:
        payload = validate_dataset_payload(data)
        # Insert first to obtain a stable database ID, then sign rights for that ID.
        with connect() as db:
            cur = db.execute("""INSERT INTO portal_datasets
                (publisher_id,name,language,category,format,size,price,licence,description,expiry_date,
                 allowed_uses_json,allowed_regions_json,restricted_regions_json,derivative_works_allowed,
                 redistribution_allowed,status)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'active')""",
                (g.publisher["id"], payload["name"], payload["language"], payload["category"],
                 payload["format"], payload["size"], payload["price"], payload["licence"],
                 payload["description"], payload["expiry_date"], json.dumps(payload["allowed_uses"]),
                 json.dumps(payload["allowed_regions"]), json.dumps(payload["restricted_regions"]),
                 int(payload["derivative_works_allowed"]), int(payload["redistribution_allowed"])))
            dataset_id = cur.lastrowid
            record, signed = build_signed_rights(dataset_id, g.publisher["id"], payload)
            db.execute("""UPDATE portal_datasets SET rights_record_json=?, signature_json=? WHERE id=?""",
                       (json.dumps(record), json.dumps(signed), dataset_id))
            row = db.execute("SELECT * FROM portal_datasets WHERE id=?", (dataset_id,)).fetchone()
        _sync_dataset_to_marketplace(row)
        log_safely("DATASET_PUBLISHED", {"publisher_id": g.publisher["id"], "dataset_id": dataset_id})
        return jsonify({"ok": True, "dataset": row_to_dataset(row)}), 201
    except (ValueError, RightsValidationError) as exc:
        return response_error(str(exc))
    except Exception:
        app.logger.exception("Dataset creation failed")
        return response_error("Could not publish dataset. Check server logs and Member 3 signing keys.", 500)

@app.get("/api/datasets")
def list_public_datasets():
    with connect() as db:
        rows = db.execute("""SELECT d.*, p.name AS publisher_name FROM portal_datasets d
                             JOIN portal_publishers p ON p.id=d.publisher_id
                             WHERE d.status='active' ORDER BY d.created_at DESC""").fetchall()
    return jsonify({"ok": True, "datasets": [row_to_dataset(r) for r in rows]})

@app.get("/api/datasets/<int:dataset_id>")
def get_dataset(dataset_id):
    with connect() as db:
        row = db.execute("""SELECT d.*, p.name AS publisher_name FROM portal_datasets d
                            JOIN portal_publishers p ON p.id=d.publisher_id WHERE d.id=?""", (dataset_id,)).fetchone()
    if not row:
        return response_error("Dataset not found.", 404)
    return jsonify({"ok": True, "dataset": row_to_dataset(row)})

@app.get("/api/publishers/datasets")
@login_required
def my_datasets():
    with connect() as db:
        rows = db.execute("""SELECT d.*,
            (SELECT COUNT(*) FROM portal_activity a WHERE a.dataset_id=d.id AND a.event_type='view') AS views,
            (SELECT COUNT(*) FROM portal_activity a WHERE a.dataset_id=d.id AND a.event_type IN ('purchase','sale')) AS purchases,
            (SELECT COALESCE(SUM(a.amount),0) FROM portal_activity a WHERE a.dataset_id=d.id AND a.event_type IN ('purchase','sale')) AS revenue
            FROM portal_datasets d WHERE d.publisher_id=? ORDER BY d.created_at DESC""", (g.publisher["id"],)).fetchall()
    return jsonify({"ok": True, "datasets": [row_to_dataset(r) for r in rows]})

@app.put("/api/datasets/<int:dataset_id>")
@login_required
def update_dataset(dataset_id):
    data = request.get_json(silent=True) or {}
    try:
        payload = validate_dataset_payload(data)
        with connect() as db:
            old = db.execute("SELECT * FROM portal_datasets WHERE id=? AND publisher_id=?", (dataset_id, g.publisher["id"])).fetchone()
            if not old:
                return response_error("Dataset not found in your publications.", 404)
            version = old["version"] + 1
            record, signed = build_signed_rights(dataset_id, g.publisher["id"], payload, version=version)
            db.execute("""UPDATE portal_datasets SET name=?,language=?,category=?,format=?,size=?,price=?,licence=?,
                description=?,expiry_date=?,allowed_uses_json=?,allowed_regions_json=?,restricted_regions_json=?,
                derivative_works_allowed=?,redistribution_allowed=?,version=?,rights_record_json=?,signature_json=?,
                updated_at=CURRENT_TIMESTAMP WHERE id=? AND publisher_id=?""",
                (payload["name"],payload["language"],payload["category"],payload["format"],payload["size"],
                 payload["price"],payload["licence"],payload["description"],payload["expiry_date"],
                 json.dumps(payload["allowed_uses"]),json.dumps(payload["allowed_regions"]),
                 json.dumps(payload["restricted_regions"]),int(payload["derivative_works_allowed"]),
                 int(payload["redistribution_allowed"]),version,json.dumps(record),json.dumps(signed),
                 dataset_id,g.publisher["id"]))
            row = db.execute("SELECT * FROM portal_datasets WHERE id=?", (dataset_id,)).fetchone()
        _sync_dataset_to_marketplace(row)
        log_safely("DATASET_UPDATED", {"publisher_id": g.publisher["id"], "dataset_id": dataset_id, "version": version})
        return jsonify({"ok": True, "dataset": row_to_dataset(row)})
    except (ValueError, RightsValidationError) as exc:
        return response_error(str(exc))
    except Exception:
        app.logger.exception("Dataset update failed")
        return response_error("Could not update dataset.", 500)

@app.delete("/api/datasets/<int:dataset_id>")
@login_required
def delete_dataset(dataset_id):
    with connect() as db:
        row = db.execute("SELECT id,name FROM portal_datasets WHERE id=? AND publisher_id=?", (dataset_id,g.publisher["id"])).fetchone()
        if not row:
            return response_error("Dataset not found in your publications.", 404)
        db.execute("UPDATE portal_datasets SET status='revoked', updated_at=CURRENT_TIMESTAMP WHERE id=? AND publisher_id=?", (dataset_id,g.publisher["id"]))
        # Revoke the rights record and re-sign the new version.
        full = db.execute("SELECT * FROM portal_datasets WHERE id=?", (dataset_id,)).fetchone()
        payload = {
            "name":full["name"], "expiry_date":full["expiry_date"],
            "allowed_uses":json.loads(full["allowed_uses_json"]),
            "allowed_regions":json.loads(full["allowed_regions_json"]),
            "restricted_regions":json.loads(full["restricted_regions_json"]),
            "derivative_works_allowed":bool(full["derivative_works_allowed"]),
            "redistribution_allowed":bool(full["redistribution_allowed"]),
            "commercial_training":"commercial_training" in json.loads(full["allowed_uses_json"]),
        }
        record, signed = build_signed_rights(dataset_id,g.publisher["id"],payload,version=full["version"]+1,status="revoked")
        db.execute("UPDATE portal_datasets SET version=?, rights_record_json=?, signature_json=? WHERE id=?",
                   (full["version"]+1,json.dumps(record),json.dumps(signed),dataset_id))
    with connect() as db:
        revoked_row = db.execute("SELECT * FROM portal_datasets WHERE id=?", (dataset_id,)).fetchone()
    _sync_dataset_to_marketplace(revoked_row)
    log_safely("DATASET_REVOKED", {"publisher_id":g.publisher["id"],"dataset_id":dataset_id})
    return jsonify({"ok":True,"message":"Dataset listing revoked (soft-deleted)."})

@app.post("/api/datasets/<int:dataset_id>/view")
def record_view(dataset_id):
    with connect() as db:
        row = db.execute("SELECT id,publisher_id FROM portal_datasets WHERE id=? AND status='active'", (dataset_id,)).fetchone()
        if not row:
            return response_error("Active dataset not found.",404)
        db.execute("INSERT INTO portal_activity(publisher_id,dataset_id,event_type,details_json) VALUES(?,?,?,?)",
                   (row["publisher_id"],dataset_id,"view","{}"))
    log_safely("DATASET_VIEW_RECORDED", {"dataset_id":dataset_id})
    return jsonify({"ok":True,"message":"View recorded."}), 201

@app.post("/api/datasets/<int:dataset_id>/transactions")
@login_required
def record_transaction(dataset_id):
    data = request.get_json(silent=True) or {}
    kind = data.get("type", "purchase")
    if kind not in ("purchase", "sale"):
        return response_error("type must be purchase or sale.")
    with connect() as db:
        row = db.execute("SELECT id,price,name,publisher_id FROM portal_datasets WHERE id=? AND status='active'", (dataset_id,)).fetchone()
        if not row:
            return response_error("Active dataset not found.",404)
        if row["publisher_id"] != g.publisher["id"]:
            return response_error("Only the publisher who owns this dataset can record a demo transaction.",403)
        amount = float(data.get("amount", row["price"]))
        if amount < 0:
            return response_error("amount cannot be negative.")
        cur = db.execute("INSERT INTO portal_activity(publisher_id,dataset_id,event_type,details_json,amount) VALUES(?,?,?,?,?)",
                         (g.publisher["id"],dataset_id,kind,json.dumps({"transaction_ref":secrets.token_hex(6),"note":"Prototype record only; no payment processed."}),amount))
        tx_id = cur.lastrowid
    log_safely("TRANSACTION_RECORDED", {"publisher_id":g.publisher["id"],"dataset_id":dataset_id,"transaction_id":tx_id,"amount":amount})
    return jsonify({"ok":True,"transaction":{"id":tx_id,"dataset_id":dataset_id,"dataset_name":row["name"],"type":kind,"amount":amount,"status":"demo_only"}}),201

@app.get("/api/publishers/analytics")
@login_required
def analytics():
    pid = g.publisher["id"]
    with connect() as db:
        datasets = db.execute("SELECT COUNT(*) n FROM portal_datasets WHERE publisher_id=? AND status='active'",(pid,)).fetchone()["n"]
        views = db.execute("SELECT COUNT(*) n FROM portal_activity WHERE publisher_id=? AND event_type='view'",(pid,)).fetchone()["n"]
        transactions = db.execute("SELECT COUNT(*) n FROM portal_activity WHERE publisher_id=? AND event_type IN ('purchase','sale')",(pid,)).fetchone()["n"]
        revenue = db.execute("SELECT COALESCE(SUM(amount),0) n FROM portal_activity WHERE publisher_id=? AND event_type IN ('purchase','sale')",(pid,)).fetchone()["n"]
        timeline = db.execute("""SELECT substr(created_at,1,10) day,
            SUM(CASE WHEN event_type='view' THEN 1 ELSE 0 END) views,
            SUM(CASE WHEN event_type IN ('purchase','sale') THEN 1 ELSE 0 END) purchases,
            SUM(CASE WHEN event_type IN ('purchase','sale') THEN amount ELSE 0 END) revenue
            FROM portal_activity WHERE publisher_id=? GROUP BY substr(created_at,1,10) ORDER BY day""",(pid,)).fetchall()
    return jsonify({"ok":True,"analytics":{"published_datasets":datasets,"views":views,"transactions":transactions,
        "revenue":revenue,"timeline":[dict(r) for r in timeline]}})

@app.get("/api/publishers/transactions")
@login_required
def transactions():
    with connect() as db:
        rows = db.execute("""SELECT a.id AS transaction_id,a.dataset_id,d.name AS dataset_name,a.event_type,
            a.amount,a.details_json,a.created_at FROM portal_activity a LEFT JOIN portal_datasets d ON d.id=a.dataset_id
            WHERE a.publisher_id=? AND a.event_type IN ('purchase','sale') ORDER BY a.id DESC""",
            (g.publisher["id"],)).fetchall()
    result=[]
    for row in rows:
        item=dict(row)
        item["details"]=json.loads(item.pop("details_json") or "{}")
        item["status"]="demo_only"
        result.append(item)
    return jsonify({"ok":True,"transactions":result})

@app.get("/api/datasets/<int:dataset_id>/verify")
def verify_dataset_rights(dataset_id):
    with connect() as db:
        row=db.execute("SELECT id,status,rights_record_json,signature_json FROM portal_datasets WHERE id=?",(dataset_id,)).fetchone()
    if not row:
        return response_error("Dataset not found.",404)
    try:
        signed=json.loads(row["signature_json"] or "{}")
        result=verify_rights_record(signed)
        result["licence_status"]=row["status"]
        result["dataset_id"]=dataset_id
        return jsonify({"ok":True,"verification":result})
    except Exception:
        app.logger.exception("Rights verification failed")
        return response_error("Could not verify rights record.",500)

@app.get("/api/audit/verify")
@login_required
def audit_verify():
    return jsonify({"ok":True,"audit_log_valid":verify_audit_log()})

@app.errorhandler(404)
def not_found(_):
    return response_error("API route not found.",404)

@app.errorhandler(405)
def method_not_allowed(_):
    return response_error("HTTP method not allowed for this route.",405)


if __name__ == "__main__":
    init_backend_db()
    init_db()
    _sync_all_datasets()
    app.run(host="127.0.0.1", port=int(os.environ.get("PUBLISHER_API_PORT", "5001")), debug=False)
