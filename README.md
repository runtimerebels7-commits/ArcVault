# ArcVault — integrated hackathon prototype

ArcVault is a local prototype for a rights-aware regional-language dataset marketplace. This package combines the latest uploaded frontend, the updated Flask backend, the Web3 rights/signature module, publisher API/database, and a budget optimisation module.

## What is included

- `Frontend/`: HTML, CSS, marketplace JavaScript, publisher portal, and a budget optimiser UI.
- `Backend/`: Flask application, SQLite database schema, service layer, and tests.
- `web3_module/`: rights records, Ed25519 signing/verification, rights validation, and hash-linked local audit log.
- `optimization/`: deterministic budget-constrained dataset selection.
- `publisher_api.py` + `publisher_db.py`: the separate Member 3 publisher API service, on port 5001.
- `keys/`: intentionally empty. A local key pair is generated on your machine; private keys are not included in this ZIP.
- `data/`: supporting data and audit log location. The shared SQLite database is at the project root as `arcvault.db` by default.

## Requirements

- Windows with Python 3.10+ installed.
- Internet connection for installing Python dependencies.
- A browser and VS Code.

## Quick start (Windows)

1. Extract the ZIP.
2. Open the extracted `ArcVault_Integrated` folder in VS Code.
3. Copy `.env.example` to a new file named `.env` in the project root. The ZIP intentionally does not include private credentials. Keep `QPIAI_OPT_MODE=local` for the first run.
4. Double-click `start_all.bat` or run it from File Explorer. It opens three terminals:
   - Main backend: `http://127.0.0.1:5000`
   - Publisher API: `http://127.0.0.1:5001`
   - Frontend: `http://127.0.0.1:5500`
5. Open `http://127.0.0.1:5500` in your browser.
6. Test backend health at `http://127.0.0.1:5000/api/health` and publisher API health at `http://127.0.0.1:5001/api/health`.
7. Run `run_tests.bat` to execute the automated test suite after dependencies install. The external QpiAI connection checks are manual because they need your account and are not part of the offline unit tests.

If `start_all.bat` cannot create the environment, run in the VS Code terminal:
```powershell
py -m venv Backend/.venv
Backend\.venv\Scripts\python.exe -m pip install -r requirements.txt -r Backend\requirements.txt
```

## Create local signing keys

The private signing key is intentionally not included in the ZIP. From the project root, run:
```powershell
Backend\.venv\Scripts\python.exe -m web3_module.generate_keys
```
Keep `keys/private_key.pem` secret and do not commit it to GitHub. The matching public key is also created in `keys/`.

## Optimisation

The main backend exposes `POST /api/optimization/run` with JSON such as:
```json
{"budget": 5000, "intended_use": "research"}
```
The backend checks permissions first and passes only approved publications to the optimiser. The result is checked again for unknown dataset IDs and budget violations. The current included solver is local (exact knapsack for up to 22 eligible datasets; deterministic heuristic for larger lists). The UI reports the engine used.

### QpiAI Opt configuration and status

The project includes a REST adapter in `optimization/qpiai_adapter.py`. Local optimisation is the default and does not need a QpiAI credential. Remote mode has not been verified against your account: a previous connection check returned HTTP 401 `Invalid token`, so do not set `QPIAI_OPT_MODE=remote` until you have an Opt API token that is accepted by the Opt API.

To configure remote mode, edit the root `.env` file (create it by copying `.env.example`):
- `QPIAI_OPT_API_KEY`: token/JWT issued for QpiAI Opt. Do not assume the QCloud Quantum SDK API key is interchangeable.
- `QPIAI_OPT_EXPERIMENT_ID`: experiment UUID accepted by QpiAI Opt. Do not assume a QCloud Quantum experiment UUID is valid for Opt.
- `QPIAI_OPT_COMPUTE_RESOURCE_ID`: optional resource ID, only if your Opt account/API requires it.
- Change `QPIAI_OPT_MODE=local` to `remote` only after the token and experiment have been verified.

Never commit `.env`, private keys, or account tokens. The ZIP contains `.env.example`, not a real `.env`.

## Important prototype notes

- The marketplace and publisher portal now use the APIs and shared SQLite database. Publisher views and purchases are demo records only.
- The main backend and publisher API use separate route sets but share one SQLite database file. Publisher listing changes are synchronised into the marketplace publication table.
- The publisher API is on port 5001 to avoid conflicting with the main backend's port 5000.
- The rights audit file is a local hash-linked log, not a blockchain and not tamper-proof against an administrator.
- Transactions in the project are demos, not real payments.
- Use fictional/demo datasets for testing. Review security, session/CSRF handling, deployment configuration, and legal rights evidence before any production use.

## Useful API routes

Main backend:
- `GET /api/health`
- `GET /api/marketplace`
- `POST /api/permissions/check`
- `POST /api/optimization/run`
- `POST /api/manifests/evaluate`
- `POST /api/publications/<publication_id>/rights-record/demo-sign` (publisher login required)

Publisher API (port 5001):
- `GET /api/health`
- Publisher registration/login and dataset CRUD endpoints in `publisher_api.py`
- `GET /api/audit/verify`

See `Backend/README.md` and `FRONTEND_INTEGRATION.md` for additional endpoint details.

## Shared database integration

Both the publisher API (port 5001) and main backend (port 5000) use the same SQLite database file, `arcvault.db` by default (or the same path configured in `DATABASE_PATH`). Publisher portal accounts, sessions, dataset records and activity use namespaced `portal_*` tables so they do not conflict with the main backend's publisher schema. Publishing, editing, or withdrawing a listing synchronises the signed rights record and publication fields into the main `publications` table in that same database. The user marketplace and budget optimiser read from that main publication table, so portal changes are reflected there.

The user marketplace now loads listings from `GET /api/marketplace` instead of using hardcoded fictional records. The publisher portal calls the Publisher API and stores its session token in browser local storage. Demo transactions remain simulated and are not real payments.

Run `run_tests.bat` from the project root after installing dependencies. The shared database regression test publishes a temporary test listing, confirms it appears in the user marketplace and optimizer, and verifies that withdrawing it removes it from active marketplace results.
