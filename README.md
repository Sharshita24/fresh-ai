# FreshChain AI — backend

> **Full guide** (both repos, every page, data sources, AI, maths, PostgreSQL, deploy, Git, troubleshooting): [FRESHCHAIN_GUIDE.md](FRESHCHAIN_GUIDE.md)

FastAPI service behind the FreshChain AI control tower. It watches perishable stock through sensors, camera checks and sales, predicts how much sellable life is really left, and when a batch is at risk it decides and executes what to do: markdown, transfer to a nearby hub, B2B offload or donation. Every decision ships with its evidence and a measured impact.

```
IoT readings · POS sales · footfall · shelf photos · batch intake (CSV / API)
        │
        ▼
 rule-based checks ──(only when a rule fires)──► Quality · Pricing · Logistics agents
        │                                                   │
  monitor sweep (cron)                              Coordinator (rules, optional Gemini)
        │                                                   │
        └──────────────► decision (evidence, options, plan) ─┴─► approve / hold / reject
                                                                     │
                     ledger + ESL / transfer / purchasing / facilities webhooks
                                                                     │
                                         impact (₹, kg, CO₂e) ──► BigQuery export
```

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000     # API docs at http://localhost:8000/docs
```

There's nothing else to set up. It uses a local SQLite file and loads demo data on first start. Rebuild the demo data any time with `python -m app.services.seed` or `POST /api/demo/reset`.

**Use PostgreSQL** by setting `DATABASE_URL=postgresql+psycopg://user@localhost:5432/freshchain`. If that database still has tables from the first prototype, run `python -m app.services.seed` once to recreate them.

**Turn on Gemini** by putting `GEMINI_API_KEY=...` in `.env`. Without a key, the deterministic rules engine makes every decision. With a key, Gemini picks among the top options and writes the rationale. Photos uploaded to `/api/batches/{id}/images` are scored by Gemini Vision.

See [.env.example](.env.example) for every setting: monitor interval, autonomous mode, CORS, webhook and BigQuery.

## The 40-second demo

```bash
curl -X POST localhost:8000/api/demo/reset
curl -X POST localhost:8000/api/demo/incident          # chiller warms 4.0 → 7.2 °C, agents decide
curl localhost:8000/api/decisions/current              # evidence, options, plan
curl -X POST localhost:8000/api/decisions/<id>/approve # executes: transfer, ESL, purchasing, maintenance
curl localhost:8000/api/network/impact                 # ₹ / kg / CO₂e, today and the last 7 days
```

What the incident produces, entirely from data:

| Signal | Evidence | Impact |
|---|---|---|
| Environment | Chiller C-03 at 7.2 °C vs 4.0 °C baseline | Shelf life −7 h |
| Visual quality | 4 of 24 punnets flagged (17% early bruising) | Shelf life −7 h → 31 h becomes 17 h |
| Demand | Selling 4.2/h, 10.8/h needed · footfall −24% | Won't clear before expiry |
| Network | Whitefield Micro-Hub, 2.4 km, ETA 18 min, headroom 6.5/h | Can sell 84 in ~13 h |

**Decision:** transfer 84 punnets and mark the other 100 down 20% (₹180 → ₹144), at 92% confidence. Expected waste drops from 113 punnets to 0, preserving **₹16,290** compared with doing nothing (28 kg of food, 71 kg CO₂e). The plan also trims the next purchase order by 12% and raises a maintenance ticket for the chiller.

## How decisions are made

**Shelf life.** The printed expiry assumes ideal storage. FreshChain projects the real remaining life with
`printed hours × Q10^(−(T − T_ref)/10) × (1 − defect weight × defect %)`.
Q10 values and storage ranges per product come from USDA Agriculture Handbook 66 and UC Davis postharvest guidance. See [app/data/reference.py](app/data/reference.py).

**Demand.** Sales velocity comes from the stock ledger (`inventory_movements`). Footfall is compared with the usual level for that hour of day. A live rain forecast from Open-Meteo adjusts expected footfall.

**Risk.** `expected waste = on hand − velocity × hours left`. The risk score combines the waste share, how severe any anomaly is, and urgency.

**When the AI runs.**
- Sensor anomalies (temperature or ethylene beyond each product's rule) trigger agents immediately.
- Slower risks, like weak demand or approaching expiry, are caught by the monitor sweep every `MONITOR_INTERVAL_SECONDS`.
- If the batch is hot and its photo is more than 30 minutes old, a fresh vision check runs first.

**Options and the choice.** The coordinator costs every option against doing nothing: markdowns from 10% to 40%, a transfer sized to the best destination's spare demand and cold space, transfer plus markdown, and B2B offload. It picks the option that wastes the least food (within a 2% tolerance), and among those, the one that preserves the most value.

**Gemini's role.** Gemini can only pick from a shortlist of options the code has already costed, and every number in the response comes from code. One call per decision, with structured JSON output, no thinking tokens on Flash, and low-resolution images.

**Execution.** Every action writes the stock ledger and stores the exact webhook payload it sent. Set `WEBHOOK_URL` and a summary is also posted to Slack or Discord. Transferred stock becomes a traceable child batch at the destination, keeping the same lot code.

## API

| Area | Endpoints |
|---|---|
| Dashboard | `GET /api/store/overview` · `/api/inventory/items?status=&q=` · `/api/batches/{id}` · `/api/batches/{id}/movements` · `/api/batches/{id}/images` · `/api/sensors/{id}` · `/api/history/events` · `/api/network/graph?batch_id=` · `/api/network/impact` · `/api/weather` |
| Operations | `POST /api/sensors/readings` · `/api/sensors/simulate` · `/api/sales` · `/api/footfall` · `/api/intake/batches` · `/api/intake/batches/csv` · `/api/batches/{id}/images` · `/api/batches/{id}/inspect` |
| Decisions | `GET /api/decisions` · `/api/decisions/current` · `/api/decisions/{id}` · `POST /api/decisions/{batch}/run` · `/api/decisions/score` (what-if) · `/api/decisions/{id}/approve` · `/hold` · `/reject` · `GET /api/executions/{id}` |
| System | `GET /health` · `POST /api/monitor/run` · `/api/demo/reset` · `/api/demo/incident` · `/api/analytics/export` |

The first prototype's endpoints still work: `/api/inventory`, `/api/inventory/summary`, `/api/decisions/confirm` and the `recommendedPlan` / `alternatives` fields.

## Data

| Table | What it holds |
|---|---|
| `stores` | Stores, micro-hubs, dark stores, B2B buyers and food banks, at real Bengaluru East coordinates. Each has cold capacity and per-SKU demand. |
| `products` | SKU master: storage range, Q10, defect weight, humidity and ethylene limits, price elasticity |
| `batches` | Traceability (supplier, lot, harvest, received and expiry dates) plus a cached risk snapshot |
| `inventory_movements` | The stock ledger: receive, sale, transfer in/out, B2B sale, donation, loss |
| `sensor_readings` · `footfall` · `batch_images` | IoT telemetry, door counts, vision checks |
| `decisions` · `agent_assessments` · `actions` · `executions` · `events` | Decisions with evidence and options, per-agent output, webhook payloads, impact, and the audit trail |

**Analytics.** PostgreSQL (or SQLite) is the operational store. `POST /api/analytics/export` loads decisions, actions, executions and the ledger into BigQuery when `BIGQUERY_DATASET` is set. Otherwise it writes NDJSON files that `bq load` accepts.

**Real data.** Weather is fetched live from [Open-Meteo](https://open-meteo.com), with a bundled real snapshot for offline use. Product storage science comes from published postharvest references. Distances and ETAs are computed from locality coordinates. Store sensors, sales and door counts are simulated, like a store's IoT feed would be.

## Tests

```bash
pytest
```

27 tests cover the shelf-life maths, the full incident (decision → approve → ledger, prices, child batch, impact), hold, reject and double-approve, CSV and JSON intake validation, image uploads, sales updating velocity, the monitor, analytics export, and the Gemini path with a fake model (one call per decision; made-up options are rejected).
