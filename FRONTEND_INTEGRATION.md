# ArcVault Publisher Backend — Integration Guide

## Files to add
Copy `publisher_api.py`, `publisher_db.py` and `requirements-additions.txt` into the root folder of the extracted Member 3 project (the same folder that contains `demo.py`, `requirements.txt`, and `web3_module/`).

## 1. Install dependencies
Open VS Code terminal in that root folder and run:

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-additions.txt
```

Do not delete or replace Member 3's `web3_module/` folder. The API imports and uses it for rights record validation, Ed25519 signing/verification, and audit logging.

## 2. Start the API
From the project root:

```powershell
python publisher_api.py
```

In the integrated ArcVault project, the publisher API starts at `http://127.0.0.1:5001`; the main backend is on port 5000. Both services share the root `arcvault.db` file (or the same `DATABASE_PATH` setting). The publisher portal writes namespaced `portal_*` tables and synchronises active signed listings into the backend `publications` table. The marketplace and optimiser read from that same publication table.

## 3. API routes
- `POST /api/publishers/register` — JSON: `{ "name": "Example Publisher", "email": "publisher@example.com", "password": "a-long-demo-password" }`
- `POST /api/publishers/login` — JSON: `{ "email": "publisher@example.com", "password": "a-long-demo-password" }`. Save the returned `token`.
- `POST /api/publishers/logout` — requires `Authorization: Bearer TOKEN`
- `GET /api/publishers/me` — current publisher
- `POST /api/datasets` — create and sign a dataset rights record; requires bearer token
- `GET /api/datasets` — public active dataset catalogue
- `GET /api/datasets/<id>` — public dataset details
- `GET /api/publishers/datasets` — current publisher's own datasets; requires bearer token
- `PUT /api/datasets/<id>` — update own dataset; requires bearer token; signs a new version
- `DELETE /api/datasets/<id>` — revoke own dataset; requires bearer token
- `POST /api/datasets/<id>/view` — record a view
- `POST /api/datasets/<id>/transactions` — record a demo purchase/sale; requires bearer token and dataset owner
- `GET /api/publishers/analytics` — views, listings, transaction totals and daily timeline; requires bearer token
- `GET /api/publishers/transactions` — publisher's transaction list; requires bearer token
- `GET /api/datasets/<id>/verify` — verify signed rights record
- `GET /api/audit/verify` — verify Member 3's local audit hash chain; requires bearer token

## 4. Frontend integration example
Use this in your frontend JavaScript to call the backend. Replace `API_BASE` if the server is hosted elsewhere.

```javascript
const API_BASE = "http://127.0.0.1:5001/api";
let publisherToken = localStorage.getItem("publisherToken") || "";

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(publisherToken ? { Authorization: `Bearer ${publisherToken}` } : {}),
      ...(options.headers || {})
    }
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "API request failed");
  return data;
}

async function registerPublisher(name, email, password) {
  return apiRequest("/publishers/register", {
    method: "POST",
    body: JSON.stringify({ name, email, password })
  });
}

async function loginPublisher(email, password) {
  const result = await apiRequest("/publishers/login", {
    method: "POST",
    body: JSON.stringify({ email, password })
  });
  publisherToken = result.token;
  localStorage.setItem("publisherToken", publisherToken);
  return result.publisher;
}

async function createDataset(dataset) {
  return apiRequest("/datasets", { method: "POST", body: JSON.stringify(dataset) });
}

async function loadMyDatasets() {
  return (await apiRequest("/publishers/datasets")).datasets;
}

async function loadAnalytics() {
  return (await apiRequest("/publishers/analytics")).analytics;
}

async function logoutPublisher() {
  try { await apiRequest("/publishers/logout", { method: "POST" }); }
  finally {
    publisherToken = "";
    localStorage.removeItem("publisherToken");
  }
}
```

Example dataset object for `createDataset`:

```javascript
{
  "name": "Kannada Speech Dataset",
  "language": "Kannada",
  "category": "Speech",
  "format": "WAV",
  "size": "25000 clips",
  "price": 1200,
  "licence": "Research and education",
  "description": "Curated Kannada speech clips for permitted research and education use.",
  "expiry_date": "2027-12-31",
  "allowed_uses": ["research", "education"],
  "allowed_regions": ["India"],
  "restricted_regions": [],
  "derivative_works_allowed": false,
  "redistribution_allowed": false
}
```

## 5. Important
- This is a hackathon prototype. The login uses a locally stored SQLite database and bearer tokens; deploy behind HTTPS and improve session expiry, rate limiting, CSRF/CORS policy, and secret/key handling before production.
- A recorded transaction is only a demo record. No payment processor is connected.
- `views` are event counts, not unique visitors.
- The API uses Member 3's signing key pair. Keep the private key secret; never commit it to GitHub.
- `DELETE` revokes a listing rather than physically deleting it so the history is retained.
- In this integrated project, install the root `requirements.txt` and `Backend/requirements.txt` using `install_dependencies.bat`.
