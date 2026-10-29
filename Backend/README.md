# ArcVault Backend — corrected starter (Member 2)

This ZIP contains a clean copy of the ArcVault Flask backend. It is intended for a local hackathon demo. It is not a guaranteed merge with any other team member's existing frontend/backend.

## Fast start on Windows
1. Extract this ZIP into a NEW folder, for example `Desktop\ArcVault_Backend_FIXED`.
2. Open that folder in VS Code.
3. In VS Code, choose **Terminal → New Terminal**.
4. Run `start_backend.bat` (type `start_backend.bat` in the terminal and press Enter).
5. Wait until the terminal says it is running at `http://127.0.0.1:5000`.
6. Keep that terminal open.
7. Open Edge/Chrome and visit `http://127.0.0.1:5000/api/health`. Expected: `{"service":"ArcVault backend","status":"ok"}`.

If Windows blocks the `.bat` file, run these commands one by one in the VS Code terminal:
```
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```
If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` once in that terminal, then activate again.

## Important fixes / common mistakes
- **Email already exists** during `/api/auth/register`: this is not a server crash. The email is already registered. Use `/api/auth/login` with that same email and password, or register with a different email.
- **405 Method Not Allowed** at `GET /api/publications`: this route is for `POST` (creating a publication). To list the logged-in publisher's items, use `GET /api/publications/mine`; to see public items use `GET /api/marketplace`.
- **Not Found** at a route not listed below means the URL/path is incorrect. Use the exact routes below.
- `/api/datasets` is a read-only listing; it does not verify rights.
- A new publication intentionally starts with `rights_verified: false` and `signature_status: "UNVERIFIED"`. Do not manually treat it as verified.
- If you use an older folder/database, existing email registrations remain there. This ZIP is clean because the database is created locally when first run; do not copy an old `arcvault.db` into it.

## Dependencies
Python 3.10 or newer. Dependencies are listed in `requirements.txt`.

## API routes
- `GET /api/health`
- `POST /api/auth/register` — JSON: `{"name":"Demo Publisher","email":"demo@example.com","password":"demo12345"}`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `POST /api/publications` — create publication (login required)
- `GET /api/publications/mine` — own publications (login required)
- `GET /api/publications/<publication_id>` — one public publication
- `PATCH /api/publications/<publication_id>` — edit own publication
- `PATCH /api/publications/<publication_id>/status` — activate/revoke own publication
- `GET /api/marketplace`
- `POST /api/publications/<publication_id>/view`
- `POST /api/access-requests`
- `GET /api/access-requests/mine` — login required
- `POST /api/transactions/demo` — demo record only, no payment
- `GET /api/publisher/analytics` — login required
- `POST /api/permissions/check`
- `POST /api/optimization/run`
- `POST /api/manifests/evaluate`
- `GET /api/audit-logs`
- `GET /api/datasets`

## Demo limitations
- Member 3's real cryptographic signature verifier still needs to be integrated and tested; the starter placeholder is not proof of ownership or legal rights.
- The optimiser uses a local fallback unless Member 4 integrates and verifies QpiAI Opt. Do not claim QpiAI Opt is running until tested.
- Transactions are demo records, not real payments.
- Use only for local prototyping. Before deployment, add proper production security, CSRF protection, HTTPS, secret management, and tests.


## Member 3 Web3 rights verification integration

This version includes `web3_module/` and the following routes:

- `POST /api/publications/<publication_id>/rights-record/demo-sign` — login required; creates and signs a local **hackathon demo** rights record for a publication.
- `POST /api/publications/<publication_id>/rights-record/verify` — login required; verifies a supplied signed rights record and checks that its dataset ID, owner ID, title, and allowed uses match the publication.
- Permission checks re-verify the stored Ed25519 signature and check the signed record's status, expiry date, allowed use, and India region rule. New or changed licence data stays unverified until verified again.

### First-time setup for signature keys

After extracting the ZIP and installing requirements, run this once in the backend terminal:

```
python -m web3_module.generate_keys
```

Then start the server normally. This creates a local Ed25519 key pair under `keys/`. **Never upload `keys/private_key.pem` to GitHub or share it publicly.** The ZIP intentionally does not include any key files.

### Important demo limitation

`/rights-record/demo-sign` is for demonstrating the integration only: the local backend signs an owner-attested record. It is not independent proof of legal ownership or a production publisher-signing workflow. For a real deployment, the publisher should sign with their own private key and ArcVault should verify against a trusted publisher public key. Do not claim this prototype establishes legal ownership.
