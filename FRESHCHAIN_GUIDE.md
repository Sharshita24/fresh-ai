# FreshChain AI — Complete Project Guide

This guide covers the whole project: the **frontend** (the dashboard people see) and the **backend** (the server that holds the data and makes decisions). The same file lives in both repositories.

| Repository | What it is | Tech |
|---|---|---|
| `freshchain-ai` | Frontend: landing page and 7 dashboard screens | Next.js 16, React 19, TypeScript, Tailwind CSS |
| `fresh-ai` | Backend: data, AI agents, decisions, actions | Python, FastAPI, SQLAlchemy, SQLite or PostgreSQL |

## Contents

1. [What FreshChain does](#1-what-freshchain-does)
2. [How the two parts fit together](#2-how-the-two-parts-fit-together)
3. [Every page, explained](#3-every-page-explained)
4. [The 40-second demo, step by step](#4-the-40-second-demo-step-by-step)
5. [Where the data comes from](#5-where-the-data-comes-from)
6. [How AI is used](#6-how-ai-is-used)
7. [How decisions are calculated](#7-how-decisions-are-calculated)
8. [Backend in detail](#8-backend-in-detail)
9. [Frontend in detail](#9-frontend-in-detail)
10. [Running it on your computer](#10-running-it-on-your-computer)
11. [Using PostgreSQL instead of SQLite](#11-using-postgresql-instead-of-sqlite)
12. [Turning on Gemini](#12-turning-on-gemini)
13. [Testing](#13-testing)
14. [Deploying](#14-deploying)
15. [Git and GitHub workflow](#15-git-and-github-workflow)
16. [Secrets and API keys](#16-secrets-and-api-keys)
17. [Troubleshooting](#17-troubleshooting)
18. [Glossary](#18-glossary)
19. [What is real and what is demo](#19-what-is-real-and-what-is-demo)

---

## 1. What FreshChain does

**The problem.** Grocery stores throw away a lot of perishable food. Most systems trust the printed expiry date, but that date assumes perfect storage. If a chiller warms up for an hour, the strawberries inside spoil faster than the label says, and nobody finds out until they're mouldy.

**The idea.** FreshChain watches the food continuously and closes the loop in five steps:

1. **SEE** — sensors (temperature, humidity, ethylene gas), camera checks and sales.
2. **UNDERSTAND** — work out how many hours of sellable life are really left.
3. **DECIDE** — compare options: discount, move stock to a busier store, sell to a juice maker, donate.
4. **ACT** — change the price on the shelf label, book the transfer, adjust the next order, raise a repair ticket.
5. **MEASURE** — record the money, food and CO₂ saved.

The header of every dashboard page shows these five steps and lights up the current one.

## 2. How the two parts fit together

```
 Browser (manager)
      │
      ▼
 Frontend  — Next.js (freshchain-ai)
   • draws the pages and animations
   • /backend/*  ──proxy──►  Backend — FastAPI (fresh-ai)
                               • database: SQLite file or PostgreSQL
                               • rules + 4 agents (+ Gemini, optional)
                               • monitor sweep every 5 min
                               • live weather from Open-Meteo
```

- The frontend talks to the backend through its own address, `/backend/...`. Next.js forwards those requests to `BACKEND_URL`. Because of that, there's no CORS setup, and you only need one port open in the browser.
- **Live mode:** the backend is reachable, so every number on screen comes from the backend.
- **Offline mode:** no backend is configured or it isn't reachable. The frontend plays the same story from bundled data, with the same numbers. Mode is detected automatically when the page loads. Check **System health** (top-right) to see which one you're in.

## 3. Every page, explained

### Landing page — `/`
The pitch: the problem, the five-step loop, the four agents, target outcomes. The **Watch a live incident** button opens the dashboard and plays the demo automatically. The small animated card on the right is a looping mini-version of the incident.

### Operations side (for the store manager)

**Overview — `/tower`**
- Three counters: **Healthy / At risk / Critical** SKUs. Click one to see those items in Inventory.
- **Attention card.** It says "All clear" when nothing is wrong, then changes as an incident unfolds: watching → analysing → needs attention (with **Approve**) → executing → resolved.
- **Today's impact:** rupees saved, kg of food saved, CO₂e avoided, number of actions. Click **Details** for the impact page.
- **Cold chain:** temperature of each chiller zone, with a live mini-graph for the one being watched.
- **Live activity:** the latest events. Click one to open it in History.

**Inventory — `/inventory`**
- Every tracked batch, riskiest first. Each row shows risk %, hours left (FreshChain's estimate against the label), signals (Temp ↑, Vision, Demand ↓, Expiry), stock value, and what FreshChain is doing (Monitor, Markdown, Transfer, …).
- Search box and status filters. Click a row to open that batch.

**History — `/history`**
- An audit trail of everything FreshChain noticed, decided and did, newest first.
- Filter by Actions, AI decisions or Sensors. Click an entry to see its evidence.

### AI Control Tower side (for "why did it do that?")

**Investigation — `/batch/STB-042`** (works for any batch)
- Header: product, units, location, supplier, **lot code, harvest date, printed expiry** (traceability).
- Three signal cards: Environment (temperature against its normal level), Visual quality (bruising %), Demand (selling rate against the rate needed to sell out in time).
- Charts:
  - Temperature over the last 60 minutes, with the safe band and the alert line.
  - A camera inspection grid with flagged items.
  - Shelf life, FreshChain's estimate against the printed date.
  - Sales per hour for the last 12 hours.

**Decision — `/decision`**
- **Decision evidence:** four rows, each showing *signal → evidence → impact* and the agent that produced it.
- **Options evaluated:** every plan compared on sell-through, waste and value against doing nothing. The chosen one is ticked.
- **AI decision card:** the plan, confidence, value preserved, a one-line rationale, and the fallback plan.
  - **Execute now** runs the plan. **Hold for review** pauses it. With no action, it auto-executes after 10 s.
  - At the bottom, the engine that decided ("Rules engine · 0 tokens" or the Gemini model with token counts). Click it to see the structured output.

**Execution — `/execution`**
- **Redistribution:** a truck moving from the store to the hub, with steps Created → Picked → Dispatched → Delivered.
- **Dynamic pricing:** an e-paper shelf label flipping from ₹180 to ₹144.
- **Actions sent:** each message sent to a store system (transfer, shelf labels, purchasing, maintenance). Click a row to see the exact payload.
- **Value preserved:** click for the calculation, line by line.

**Network & impact — `/network`**
- A map of nearby stores, hubs, a dark store, a B2B buyer and a food bank, using real Bengaluru East coordinates. The chosen route is animated.
- **Destination scoring:** why the hub won (spare demand, cold space, distance).
- **Impact today:** big totals, food saved per day for the last 7 days, a 30-day run-rate, and ESG notes.

### Things on every dashboard page
- **Mode switch:** Operations / AI Control Tower.
- **Loop indicator:** SEE · UNDERSTAND · DECIDE · ACT · MEASURE.
- **System health:** shows whether the backend is connected and which engine decides.
- **Bottom dock:** start the demo (**Simulate spike**), see status, **Review decision**, **Replay**, reset (↺), and **Auto-tour** (moves through the pages for you).
- Keyboard shortcuts: `S` start, `A` approve, `H` hold, `R` reset.

## 4. The 40-second demo, step by step

1. **SEE (0–7 s).** Chiller C-03 warms up: 4.5, 4.9, 5.4, 5.8, 6.3, 6.7, 7.2 °C. In live mode each reading is sent to the backend. At 7.2 °C the strawberry rule (5 °C storage maximum + 2 °C margin = 7.0 °C) fires.
2. **UNDERSTAND (7–17 s).**
   - A fresh camera check finds 17% early bruising.
   - **Quality:** shelf life is really 17 h, not 31 h.
   - **Pricing:** selling 4.2 an hour, but 10.8 an hour is needed. Footfall is −24%.
   - **Logistics:** Whitefield Micro-Hub, 2.4 km away, ETA 18 min, can sell 84 more punnets.
3. **DECIDE (~17 s).** The Coordinator compares the options and picks **transfer 84 + mark the other 100 down 20%**, with 92% confidence.
4. **ACT (~27 s).** It sends four actions:
   - transfer TO-xxxx to the hub
   - 2 shelf labels changed from ₹180 to ₹144
   - next strawberry order trimmed 12%
   - maintenance ticket MT-xxxx for the chiller
5. **MEASURE (~32 s).** Value preserved is **₹16,290**. Expected waste drops from 113 punnets to 0, which is 28 kg of food and 71 kg CO₂e.

## 5. Where the data comes from

**Real data**

| Data | Source | Used for |
|---|---|---|
| Weather (rain, temperature, humidity) | [Open-Meteo](https://open-meteo.com) live API for Bengaluru East, cached 30 min. A real snapshot is bundled for offline use. | Rain lowers expected footfall; cited in decision evidence |
| Storage science per product | USDA Agriculture Handbook 66 and UC Davis Postharvest guidance | Safe temperature range, humidity limit, how much faster food spoils when warm (Q10) |
| Locations | Real coordinates of Brookefield, Whitefield, Marathahalli, KR Puram, Kadugodi, Hoodi, Mahadevapura | Distances, ETAs and transfer costs are calculated, not typed in |

**Simulated** (standing in for store hardware we don't have)
- Chiller sensor readings (one a minute)
- Sales from the till (point of sale)
- Door-counter footfall
- Camera inspections, unless you upload a real photo
- The store systems that receive actions (shelf labels, logistics, purchasing, facilities). The exact messages are stored, and can also be sent to a real Slack or Discord webhook (see `WEBHOOK_URL`).

**Calculated** (by the backend, from the above)
- Real shelf life left
- Sales speed
- Expected waste
- Risk score
- Every option's value
- Confidence
- Impact

The demo store's data (13 batches, 7 locations, 9 suppliers, today's earlier actions) is created by `app/services/seed.py` from `app/data/reference.py`.

## 6. How AI is used

FreshChain uses three layers, from cheapest to smartest.

**Layer 1 — Rules (always on, free).** Simple checks watch every reading, for example "strawberries above 7.0 °C?". Nothing expensive runs until a rule fires.

**Layer 2 — Four agents (always on).** Today these are transparent Python calculations, so every number can be explained:

| Agent | Question it answers | Example output |
|---|---|---|
| Quality | How much sellable life is really left? | 31 h → 17 h, 17% bruising |
| Pricing | What discount sells it in time? | −20% lifts sales from 4.2 to 6.4 per hour |
| Logistics | Where else could it sell? | Whitefield hub can take 84 (2.4 km, 18 min) |
| Coordinator | Which plan is best overall? | Transfer 84 + markdown 100 by 20% |

**Layer 3 — Gemini (when `GEMINI_API_KEY` is set).**
- **Gemini Vision** looks at an uploaded shelf photo and returns the percentage of items with defects, plus a short list of what it saw.
- **Gemini decision.** The Coordinator sends one request with the verified evidence and the shortlist of already-costed options. Gemini picks one option and writes a one-sentence rationale for the manager.

**Guardrails**
- Gemini can only choose an option ID from the list. If it returns anything else, the rules engine's choice is used.
- Every number in the evidence comes from code, never from the model.
- If the key is missing, or a call fails or times out (15 s), the rules engine decides. The page says which engine was used.

**Cost controls** (from the pitch doc)
- The AI is only called when a rule fires.
- One call per decision.
- Strict JSON output.
- Low temperature.
- No "thinking" tokens on Flash.
- Short prompts.
- Low-resolution images.

## 7. How decisions are calculated

All of this lives in the backend (`app/services/` and `app/agents/`).

### Shelf life (`shelf_life.py`)
The printed expiry assumes ideal storage. FreshChain adjusts it for temperature and visible damage:

```
remaining hours = printed hours × temperature factor × quality factor
temperature factor = Q10 ^ ( −(current °C − reference °C) / 10 )
quality factor     = 1 − defect weight × defect %
```

**Example — strawberries** (Q10 = 3.1, reference = 2 °C, defect weight = 1.38, label says 40 h):
- Normal, 4.0 °C, 2% defects: 40 × 0.80 × 0.97 ≈ **31 h**
- Incident, 7.2 °C, 17% defects: 40 × 0.56 × 0.77 ≈ **17 h**

### Demand (`demand.py`)
- **Sales speed:** units sold in the last 5 hours ÷ 5, read from the stock ledger.
- **Footfall ratio:** last 3 hours of door counts compared with what's normal for those hours of the day.
- **Markdown lift:** 1 + elasticity × discount. For strawberries, 20% off gives 1 + 2.6 × 0.20 = 1.52, so sales rise by about 52%.
- **Rain:** the next 3 hours of rain forecast reduce expected footfall: 1 − 0.35 × (1 − e^(−mm/3)).

### Risk (`risk.py`)
```
expected sold  = min(on hand, sales speed × hours left)
expected waste = on hand − expected sold
risk score     = 100 × (0.85 × waste share + 0.22 × anomaly severity + 0.30 × urgency)
urgency        = 1 − hours left / 48
```
A score of 80 or more is **critical** and 50 or more is **at risk**. Batches FreshChain has already acted on show as **managed**.

### When the agents run
- **Immediately**, on a sensor anomaly: temperature above the product's maximum + 2 °C, or ethylene above its limit.
- **On the monitor sweep** (default every 5 minutes):
  - less than 12 h left with some waste expected, or
  - 35% or more of the stock expected to be wasted.
- If a batch is hot and its last photo is older than 30 minutes, a new vision check runs first.
- A new anomaly replaces an older open decision that was made on weaker evidence.

### Options and the choice (`decision_coordinator.py`)
**Options costed:**
- do nothing
- markdown 10/20/30/40% on everything
- transfer only
- transfer + markdown 10/20/30/40% on the rest
- B2B offload of everything now

**Transfer size:** the best destination's spare demand × 80% of the remaining life (stock must look fresh on arrival), minus travel time, capped by its cold space and rounded down to whole cases (12 punnets).

**Transfer cost and ETA:** ₹300 + ₹62.5 per km. ETA is 10 min loading + driving at 20 km/h.

**Value against doing nothing** = money from the option − its cost − money if nothing is done.

**The choice:** among options that waste 2% of the stock or less, take the highest value. If none get there, take the least waste.

**Confidence** = 0.60, plus:
- +0.12 if there's a recent camera check
- +0.12 if three independent signals agree (temperature, vision, demand, expected waste)
- +0.08 if there's sales history

It is capped at 0.97. When Gemini is used, its confidence is averaged in.

**The incident's numbers:**
- Do nothing: 71 sold × ₹180 = ₹12,780. 113 wasted.
- Chosen plan: 84 × ₹180 at the hub + 100 × ₹144 in store − ₹450 transfer = ₹29,070.
- Value preserved = ₹29,070 − ₹12,780 = **₹16,290**.

**Extra plan steps:**
- When the do-nothing waste share is 20% or more, trim the next order by about waste share × 20%, between 5% and 25%. Here that's 12%.
- When the trigger was heat, raise a maintenance ticket.

**Impact:** CO₂e = 2.5 kg per kg of food saved.

## 8. Backend in detail

### Folder structure (`fresh-ai/`)

```
app/
  main.py                 app startup: creates tables, seeds demo data, starts the monitor, CORS
  config.py               every setting, read from environment variables / .env
  models.py               database tables (SQLAlchemy)
  presenters.py           turns database rows into the JSON the dashboard reads
  db/database.py          database connection (SQLite or PostgreSQL)
  data/reference.py       products, suppliers, stores and demo batches, with sources
  data/weather_snapshot_bengaluru_east.json   real Open-Meteo snapshot for offline use
  agents/                 quality_agent.py · pricing_agent.py · logistics_agent.py
  routers/                dashboard.py (reads) · operations.py (writes) · decisions.py · system.py
  schemas/                request bodies (api.py) and agent outputs (agents.py)
  services/
    shelf_life.py         remaining-life model
    demand.py             sales speed, footfall, markdown lift
    anomaly_engine.py     rule checks per product
    risk.py               the risk snapshot + "should the agents run?"
    decision_coordinator.py  options, choice, evidence, confidence, saving decisions
    gemini_agent.py       the only file that talks to Gemini
    vision.py             photo checks (Gemini Vision or simulated)
    executor.py           carries out a decision: ledger, prices, transfers, messages
    pipeline.py           event flow: reading / sale / photo → refresh → maybe decide
    monitor.py            the periodic sweep ("cron")
    weather.py            Open-Meteo client + snapshot fallback
    intake.py             create batches from JSON or CSV
    analytics.py          export to BigQuery or NDJSON files
    seed.py               demo data; `python -m app.services.seed` rebuilds the database
    events.py             writes the audit trail
samples/batches.csv       example CSV for bulk intake
tests/                    28 automated tests
Dockerfile                container for Cloud Run / any host
```

### Database tables

| Table | One row is… |
|---|---|
| `stores` | a location: store, hub, dark store, B2B buyer or food bank (coordinates, cold space, per-product demand) |
| `suppliers` | a supplier (Nandi Hills Farms, Hosur Greens, …) |
| `products` | a product type (SKU) with its storage science and price |
| `batches` | one delivery: SKU + supplier + lot + received date, with quantity on hand and a cached risk snapshot |
| `inventory_movements` | one change to stock: receive, sale, transfer in/out, B2B sale, donation, loss. **This is the source of truth for quantities.** |
| `sensor_readings` | one sensor reading (temperature, humidity, ethylene, battery, flags) |
| `footfall` | door count for one hour at one store |
| `batch_images` | one camera check (reference or alert) and its result |
| `decisions` | one decision: trigger, options, evidence, plan, confidence, expected impact, model used, status |
| `agent_assessments` | what each agent said for a decision |
| `actions` | one executed step and the exact message it sent |
| `executions` | the record of carrying out a decision, with the impact |
| `events` | one line of the audit trail (the History page) |

### API reference
Interactive docs are at **http://localhost:8000/docs** while the backend runs.

**Read (dashboard)**
| Method & path | Returns |
|---|---|
| `GET /api/store/overview` | counters, active incident, today's impact, cold-chain zones, weather |
| `GET /api/inventory/items?status=&q=` | inventory list, riskiest first |
| `GET /api/batches/{id}` | everything about one batch (traceability, 60 readings, vision, demand, shelf life) |
| `GET /api/batches/{id}/movements` | the stock ledger for a batch |
| `GET /api/batches/{id}/images` | its camera checks |
| `GET /api/sensors/{id}?limit=` | recent sensor readings |
| `GET /api/history/events?kind=&batch_id=` | the audit trail |
| `GET /api/network/graph?batch_id=` | map nodes, distances, scores, chosen destination |
| `GET /api/network/impact` | value, kg, CO₂e and actions for the last 24 h, plus the 7-day chart |
| `GET /api/weather` | live weather outlook for the store |
| `GET /api/incidents/active` | batches with an open decision |

**Write (operations)**
| Method & path | Does |
|---|---|
| `POST /api/sensors/readings` | ingest one reading; runs the agents if it's an anomaly |
| `POST /api/sensors/simulate` | create a scenario reading (NORMAL, TEMPERATURE_SPIKE, HUMIDITY_SPIKE, ETHYLENE_SPIKE) |
| `POST /api/sales` | record a till sale (lowers stock, updates sales speed) |
| `POST /api/footfall` | record a door count for an hour |
| `POST /api/intake/batches` | create one batch (JSON) |
| `POST /api/intake/batches/csv` | create many batches from a CSV file |
| `POST /api/batches/{id}/images` | upload a shelf photo (JPEG/PNG/WebP, ≤ 8 MB) |
| `POST /api/batches/{id}/inspect` | run a camera check without a photo |

**Decisions**
| Method & path | Does |
|---|---|
| `GET /api/decisions` · `GET /api/decisions/current` · `GET /api/decisions/{id}` | read decisions |
| `POST /api/decisions/{batch_id}/run` | run the agents for a batch now |
| `POST /api/decisions/score` | what-if: cost every option without saving |
| `POST /api/decisions/{id}/approve` · `/hold` · `/reject` | act on a decision |
| `GET /api/executions/{id}` | what was executed, step by step |

**System**
| Method & path | Does |
|---|---|
| `GET /health` | database status, which AI engine is active, monitor interval |
| `POST /api/monitor/run` | run the sweep now |
| `POST /api/demo/reset` | replace all data with fresh demo data |
| `POST /api/demo/incident` | play the chiller incident in one call |
| `POST /api/analytics/export` | export to BigQuery, or NDJSON files in `exports/` |

The first prototype's endpoints still work: `/api/inventory`, `/api/inventory/summary`, `/api/decisions/confirm`, plus the `recommendedPlan` and `alternatives` fields.

### Settings (environment variables, in `fresh-ai/.env`)

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./freshchain.db` | where data is stored; see section 11 for PostgreSQL |
| `GEMINI_API_KEY` | empty | turns on Gemini decisions and vision |
| `GEMINI_MODEL` | `gemini-2.5-flash` | which Gemini model to use |
| `GEMINI_TIMEOUT_MS` | `15000` | give up on a Gemini call after this many ms |
| `MONITOR_INTERVAL_SECONDS` | `300` | how often the sweep runs; `0` turns it off |
| `AUTO_EXECUTE` | `false` | `true` executes decisions with ≥ 85% confidence without approval |
| `SEED_DEMO_DATA` | `true` | load demo data on first start if the database is empty |
| `HOME_STORE_ID` | `store-042` | which store the dashboard shows |
| `CORS_ORIGINS` | `http://localhost:3000` | browser origins allowed to call the API directly |
| `WEBHOOK_URL` | empty | also post each executed action to this Slack or Discord webhook |
| `WEATHER_LIVE` | `true` | `false` uses the bundled weather snapshot only |
| `BIGQUERY_DATASET` | empty | e.g. `my-project.freshchain`, for analytics export |
| `UPLOAD_DIR` / `EXPORT_DIR` | `uploads` / `exports` | where photos and exports are saved |

## 9. Frontend in detail

### Folder structure (`freshchain-ai/`)

```
src/
  app/
    page.tsx              landing page
    layout.tsx            fonts, page title, global styles
    (app)/                the dashboard (shared header + dock)
      tower/ inventory/ history/ batch/[id]/ decision/ execution/ network/
      layout.tsx          header, demo dock, notifications, runtime
      template.tsx        page-transition animation
    opengraph-image.tsx   share preview image
    icon.svg, not-found.tsx
  components/
    shell.tsx             header, mode switch, loop indicator, system health, demo dock, runtime
    ui.tsx                buttons, cards, pills, risk meter, confidence ring, animated numbers
    charts.tsx            temperature, shelf-life, sales and weekly charts (hand-built SVG)
    landing.tsx           landing-page animations
    views/                one file per screen: tower, inventory, batch, vision, decision, execution, network, history
  lib/
    api.ts                typed client for every backend endpoint used
    sim.ts                the demo timeline and its state (Zustand); talks to the backend in live mode
    live.ts               helpers: useBackend (fetch + poll + cache), useIncident (the numbers every screen shows)
    data.ts               offline dataset (matches the backend's numbers)
    format.ts             ₹, hours, clock and time formatting
```

### How live mode works
1. When the page loads, `sim.ts` → `connect()` calls `/backend/health`. Success means live mode; failure means offline mode.
2. **Simulate spike** resets the backend to fresh demo data, then each temperature reading is posted to `/api/sensors/readings`.
3. When the backend returns a decision ID, the frontend fetches the decision. The Decision page then shows the backend's evidence, options, plan and rationale.
4. The on-screen agent animation is only pacing for people watching. The backend has already decided.
5. **Approve** calls `/api/decisions/{id}/approve`. The Execution page shows the real payloads and IDs it returns.
6. Every screen refetches from the backend every 2.5 s while an incident is running, and every 15 s otherwise.

### Frontend settings
| Variable | Meaning |
|---|---|
| `BACKEND_URL` | e.g. `http://127.0.0.1:8000`. Read at build/start time and turned into the `/backend/*` proxy. Leave it unset for the offline demo. |

## 10. Running it on your computer

You need **Python 3.11+** and **Node.js 20+**.

### Backend
```bash
cd fresh-ai
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
Open http://localhost:8000/docs. The first start creates `freshchain.db` and loads the demo data.

### Frontend (in a second terminal)
```bash
cd freshchain-ai
npm install
BACKEND_URL=http://127.0.0.1:8000 npm run dev
```
Open http://localhost:3000. Under **System health** it should say "Backend · FastAPI · connected".

To run only the frontend (offline demo), use `npm run dev` without `BACKEND_URL`.

### Handy commands
```bash
python -m app.services.seed          # rebuild the database from scratch (drops and recreates tables)
curl -X POST localhost:8000/api/demo/reset      # fresh demo data, keeps tables
curl -X POST localhost:8000/api/demo/incident   # play the incident without the browser
```

## 11. Using PostgreSQL instead of SQLite

**SQLite** is a single file (`freshchain.db`) with nothing to install, which is ideal for demos. **PostgreSQL** is a real database server, which you want for a shared or deployed setup. The code is the same for both, and all 28 tests pass on each (checked on PostgreSQL 16).

### Step 1 — Install and start PostgreSQL (Mac)
```bash
brew install postgresql@16          # skip if you already have it
brew services start postgresql@16   # runs it in the background
```
Check that it's running: `psql postgres -c "select version();"`

### Step 2 — Create the database
```bash
createdb freshchain
```

### Step 3 — Point the backend at it
In `fresh-ai/.env` (create the file if it doesn't exist):
```
DATABASE_URL=postgresql+psycopg://YOUR_MAC_USERNAME@localhost:5432/freshchain
```
- Find your username with `whoami`.
- If your database user has a password: `postgresql+psycopg://user:password@localhost:5432/freshchain`.
- The `psycopg` driver is already in `requirements.txt`.

### Step 4 — Create the tables and demo data
```bash
cd fresh-ai && source .venv/bin/activate
python -m app.services.seed
```

### Step 5 — Start and check
```bash
uvicorn app.main:app --reload --port 8000
curl localhost:8000/health          # "databaseEngine": "postgresql+psycopg"
psql freshchain -c "select batch_id, risk_tier, quantity_on_hand from batches order by batch_id;"
```

### Upgrading Harshita's old database
The first prototype created tables with different columns. Run `python -m app.services.seed` once; it drops and recreates every FreshChain table. Old tables the new code doesn't use can be removed:
```sql
DROP TABLE IF EXISTS inventory_batches, store_profiles, network_nodes, execution_records CASCADE;
```

### Running the tests on PostgreSQL
Use a separate database, because the tests wipe it:
```bash
createdb freshchain_test
TEST_DATABASE_URL=postgresql+psycopg://$(whoami)@localhost:5432/freshchain_test pytest
```

### Other options
- **Docker:** `docker run -d --name pg -e POSTGRES_PASSWORD=dev -p 5432:5432 postgres:16`, then use `DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/postgres`.
- **Google Cloud SQL:** create a PostgreSQL instance, then set `DATABASE_URL` on the backend service to its connection string.

**Switching back to SQLite:** remove `DATABASE_URL` from `.env`.

## 12. Turning on Gemini

1. Open **Google AI Studio → Get API key**, at https://aistudio.google.com/apikey, and create a key.
2. Put it in `fresh-ai/.env` (never in code):
   ```
   GEMINI_API_KEY=your-new-key
   GEMINI_MODEL=gemini-2.5-flash
   ```
3. Restart the backend. `GET /health` shows `"ai": {"provider": "gemini", ...}`.
4. Run the demo. The Decision page footer now shows the Gemini model, tokens and latency, and the rationale is written by Gemini.
5. To test vision, upload a photo:
   ```bash
   curl -F "file=@strawberries.jpg" -F image_type=alert localhost:8000/api/batches/STB-042/images
   ```

If Gemini errors (quota, network, bad output), the backend logs a warning and the rules engine decides instead. The demo never breaks.

## 13. Testing

**Backend.** 28 automated tests cover:
- the maths
- the full incident (decision → approve → stock ledger, prices, child batch at the hub, impact)
- hold, reject, double-approve
- intake validation
- photo upload
- sales updating demand
- the monitor
- the export
- Gemini with a fake model
- reading during a reset

```bash
cd fresh-ai && source .venv/bin/activate
pytest                       # SQLite, about 7 s
ruff check app tests         # code style (pip install ruff)
```

**Frontend**
```bash
cd freshchain-ai
npx tsc --noEmit             # type check
npm run build                # production build
```

**Manual checklist before a demo**
1. Backend up: `curl localhost:8000/health`.
2. Frontend shows "connected" under System health.
3. From the landing page, **Watch a live incident** tours all screens and ends on Network & impact at ₹26,940 for the day.
4. **Replay** works; **↺** resets.

## 14. Deploying

**Frontend → Vercel**
1. Push `freshchain-ai` to GitHub.
2. On vercel.com: **Add New → Project → import the repo → Deploy**.
3. For live data, add the environment variable `BACKEND_URL=https://your-backend-url` and redeploy. Without it, the site runs the offline demo.

**Backend → Google Cloud Run** (or any container host)
```bash
cd fresh-ai
gcloud run deploy freshchain-api --source . --region asia-south1 --allow-unauthenticated
```
- Then set the frontend's `BACKEND_URL` to the URL Cloud Run prints.
- SQLite inside a container resets on every redeploy. For lasting data, use Cloud SQL (section 11).
- Store `GEMINI_API_KEY` in Secret Manager or Cloud Run environment variables, never in the image.

**Test the container locally:** `docker build -t freshchain-api . && docker run -p 8080:8080 freshchain-api`

## 15. Git and GitHub workflow

**One-time setup per repository.** Use your personal identity, not your work email:
```bash
git config user.name "Your Name"
git config user.email "you@personal-email.com"
```

**Everyday loop**
```bash
git status                      # what changed?
git add -A                      # stage everything (new, changed, deleted)
git commit -m "Describe the change"
git push
```

**Sending the backend to Harshita's repo** (`Sharshita24/fresh-ai`)
- If she adds you as a collaborator (GitHub → Settings → Collaborators):
  ```bash
  cd fresh-ai
  git checkout -b backend-v1
  git add -A
  git commit -m "Rebuild backend: traceability, ledger, agents, monitor, vision, frontend API"
  git push -u origin backend-v1
  ```
  Then open the repo on GitHub and click **Compare & pull request**. She reviews and merges.
- Without access: click **Fork** on her repo, then `git remote set-url origin https://github.com/YOUR-USERNAME/fresh-ai.git`, push, and open a pull request from your fork.

**Before every push:** run `git status` and make sure `.env`, `*.db`, `.venv/`, `node_modules/` and `uploads/` are not listed. Both repositories' `.gitignore` files already exclude them.

## 16. Secrets and API keys

**What "rotating" a key means.** You delete the old key and create a new one. The old key stops working, and anyone who saw it can no longer use it. In Google AI Studio, open your API keys, **delete** the one that was shared, then **create** a new one.

**Why it matters.** A key works like a password for your Google account's AI quota. If it's pasted into a chat, a document or a commit, anyone who sees it can run up usage on your account. Deleting it from a file afterwards doesn't help, because copies may already exist. Only rotation makes the old key useless.

**Keeping keys out of commits**
- Keys go only in `.env`. It is listed in `.gitignore`, so git never commits it.
- `.env.example` is committed and shows the variable names with **empty** values.
- If a key ever gets committed: rotate it straight away. Removing it from git history doesn't undo the leak.

## 17. Troubleshooting

| Symptom | Fix |
|---|---|
| System health says "Offline demo" | The backend isn't running, or the frontend was started without `BACKEND_URL`. Start the backend, then restart `npm run dev` with `BACKEND_URL`. |
| `503 Store not configured` | Run `curl -X POST localhost:8000/api/demo/reset`. |
| `connection refused` on port 5432 | Start PostgreSQL: `brew services start postgresql@16`. |
| `column … does not exist` / `relation … does not exist` | The database has old tables. Run `python -m app.services.seed`. |
| `Address already in use` | Something else is on the port. Use `--port 8001` (and update `BACKEND_URL`) or stop the other process. |
| Decision page says "Rules engine" after adding a key | Restart the backend; check `GET /health`; check the backend log for "Gemini call failed". |
| Weather shows "open-meteo snapshot" | No internet from the backend, or `WEATHER_LIVE=false`. That's fine for demos. |
| `pip install pillow` fails | Pillow is optional, only for shrinking photos. Skip it. |
| Demo numbers look different after leaving it running for hours | Time moves on (labels get closer to expiry). Click ↺ or call `/api/demo/reset`. |

## 18. Glossary

| Term | Meaning |
|---|---|
| **SKU** | A product type, e.g. "Strawberry 250 g punnet". |
| **Batch / lot** | One delivery of a SKU from a supplier on a date. Same fruit + same supplier + same day = same batch. |
| **FEFO** | First-Expired, First-Out: sell the item that expires first. "Static FEFO" trusts the printed date only. |
| **Shelf life** | Hours until the food is no longer sellable. |
| **Q10** | How many times faster food spoils for every +10 °C. |
| **Ethylene** | A gas fruit gives off as it ripens; high levels speed up spoilage. |
| **Footfall** | Number of shoppers entering the store. |
| **Sales speed / velocity** | Units sold per hour. |
| **Markdown** | A price reduction to sell faster. |
| **ESL** | Electronic Shelf Label: an e-paper price tag the system can update remotely. |
| **Micro-hub / dark store** | Small warehouses that serve quick-delivery orders. |
| **B2B offload** | Selling surplus to another business (e.g. a juicery) at a lower price. |
| **Webhook** | A message one system sends to another when something happens. |
| **Stock ledger** | The list of every stock movement; quantities are calculated from it. |
| **CO₂e** | CO₂-equivalent emissions; saving 1 kg of food avoids about 2.5 kg CO₂e. |
| **Proxy** | The frontend forwarding `/backend/*` requests to the backend server. |

## 19. What is real and what is demo

**Real and working**
- Every calculation, decision, approval, execution, the stock ledger, the audit trail and the impact numbers
- Live weather
- Distances
- The Gemini integration (switches on with a key)
- CSV intake and photo uploads
- The analytics export
- Postgres support
- The tests

**Simulated for the demo**
- Sensor readings, sales and door counts
- The store systems that receive actions
- Demo prices
- Earlier actions from "this morning"
- The store-wide SKU counts (8,706). The 13 batches shown are tracked in detail.

**Natural next steps**
- Real sensors via MQTT
- Barcode or camera intake
- Learning each product's Q10 and price response from past sales
- Delivery-partner APIs for transfers
- A real ESL vendor API
- Multi-store dashboards
