# ArcVault shared-database integration test report

## Results

- Automated pytest suite: **18 passed**.
- Python compile check: **passed** for backend, publisher API/database, optimizer, and rights modules.
- JavaScript syntax checks: **passed** for `Frontend/script.js`, `Frontend/portals.js`, and `Frontend/optimization.js`.
- Shared SQLite schema check: **passed**; both services resolve to the same database path and the shared database contains the main backend tables plus namespaced `portal_*` tables.
- End-to-end shared-data regression: **passed**. The test registers a publisher, publishes a dataset, confirms the signed publication appears in `/api/marketplace`, changes its price/title and confirms the change appears there, runs the optimizer and confirms it selects the eligible listing, then withdraws it and confirms it disappears from active marketplace results.

## Boundaries

- These tests use Flask test clients and syntax/schema checks; they do not claim a separate browser-driven UI automation run.
- QpiAI Opt remote execution is not part of this shared-database change and remains unverified. `QPIAI_OPT_MODE=local` is the safe default.
- Demo purchases are records only; no real payment processor is connected.
