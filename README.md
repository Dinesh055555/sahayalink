# SahayaLink

A working follow-up-assurance app for the INFINUM 2026 case. Backend (FastAPI) +
database (SQLite) + phone-style web frontend, all wired together and seeded from the
real risk-model output.

## Run it (one command)

```bash
cd sahayalink
bash run.sh
```

Then open **http://127.0.0.1:8000** in your browser.

(If `bash run.sh` doesn't work on your system, run the three steps by hand:
`pip install -r requirements.txt`, then `python3 seed.py`, then
`python3 -m uvicorn app:app --port 8000`.)

## Demo logins

| Role | Username | PIN | What they see |
|------|----------|-----|----------------|
| ASHA worker | `asha13` | `1234` | Her own region's ranked worklist, rewards, leaderboard |
| CHO | `cho3` | `4321` | Clinical queue + coverage |
| Supervisor | `supervisor` | `0000` | District coverage, worker stats, nightly reassignment |

Other ASHA logins are `asha1`…`asha18` (PIN `1234`); CHOs `cho3`, `cho6`, `cho9`… (PIN `4321`).

## What it does

- **Login + region scoping** — each ASHA sees only the villages she covers, not all 47.
- **Live worklist** — patients ranked by dropout risk, with the reason and the recommended action, served from the database.
- **Action logging** — mark each patient Resolved / Unreachable / Escalate; it persists.
- **Incentive program** — difficulty-weighted points (Critical resolved = 10, High = 6, +3 bonus for far/weak-signal patients), Bronze/Silver/Gold tiers, and a leaderboard.
- **Unreachable reassignment** — a patient marked unreachable is handed to a *different* worker the next day; after 3 failed attempts the case escalates to a CHO. Trigger it from the supervisor's "Run tonight's reassignment" button.
- **Supervisor coverage** — resolution rate, villages needing attention, per-worker progress.
- **Governance** — privacy, role-based access, audit trail, fairness (see the Governance tab).

## The nightly data flow (how it works in production)

Every night your team drops the new day's data, the risk model scores each patient, and
each case is assigned to the ASHA covering that village — written into the `worklist`
table for the next morning. In this prototype that assignment is done by `seed.py`, and
the reassignment step is the `POST /api/admin/run-nightly` endpoint (the supervisor
button). In production both run automatically on a scheduler.

## Files

- `app.py` — FastAPI backend (login, worklist, action, points, leaderboard, supervisor, nightly).
- `seed.py` — builds `sahayalink.db` from `app_data.json` + `geography_reference.csv`.
- `static/index.html` — the frontend (single file, works offline once loaded).
- `sahayalink.db` — the SQLite database (created on first run).

## Tech

Python FastAPI, SQLite, plain HTML/CSS/JS. No build step. Swap SQLite for PostgreSQL by
changing the connection in `app.py` when you deploy.

## Not yet built (roadmap)

Real offline sync (service worker), OTP login, Telugu UI, and the model feeding back
from logged outcomes into the next night's scores. These are described as next steps for
the competition rather than built, to keep the working slice solid.
