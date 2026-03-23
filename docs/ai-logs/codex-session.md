# Codex Session Log

## Session Context

- Tool: Codex terminal agent
- Date: 2026-03-23
- Workspace: `C:\Users\SAYANTIKA\OneDrive\Desktop\f\context-graph-system`
- Goal: build a submission-ready graph-based SAP O2C data exploration system with a natural-language query interface, dataset guardrails, README, deployment path, and AI usage artifacts

## Initial Prompt

The project was started from the assignment brief asking for:

- graph construction over orders, deliveries, invoices, payments, customers, products, and addresses
- graph visualization UI
- conversational query interface grounded in data
- guardrails for off-topic prompts
- submission artifacts including a public repo, demo link, README, and AI session logs

## Chronological Work Log

### 1. Workspace setup

- created a separate repository folder instead of mixing the assignment into the existing workspace
- initialized a new Git repository
- created folders for `backend`, `frontend`, `data`, `scripts`, and `docs/ai-logs`

### 2. Dataset acquisition and inspection

- downloaded the dataset from the provided Google Drive link
- confirmed the payload was a ZIP archive containing `sap-o2c-data`
- extracted the archive into `data/raw/extracted`
- profiled the available tables and sampled keys from the JSONL files

Observed source tables:

- `sales_order_headers`
- `sales_order_items`
- `sales_order_schedule_lines`
- `outbound_delivery_headers`
- `outbound_delivery_items`
- `billing_document_headers`
- `billing_document_items`
- `billing_document_cancellations`
- `journal_entry_items_accounts_receivable`
- `payments_accounts_receivable`
- `business_partners`
- `business_partner_addresses`
- `products`
- `product_descriptions`
- `plants`
- plus assignment and storage tables

### 3. Architecture decisions

The implementation direction chosen during the session was:

- SQLite for local analytical storage and transparent SQL execution
- FastAPI backend for graph/query endpoints
- static frontend served by the backend to keep deployment simple
- graph model centered around:
  - `customer -> sales_order -> sales_order_item`
  - `sales_order_item -> delivery_item -> delivery`
  - `delivery_item -> billing_item -> billing_document`
  - `billing_document -> journal_entry -> payment`
  - supporting links to `product`, `plant`, and `address`
- template-driven natural-language query mapping for core business asks, with optional LLM SQL planning behind a read-only safety gate

### 4. Backend implementation

Implemented:

- dataset ingestion pipeline
- JSONL-to-SQLite normalization
- key normalization for document-item joins
- graph overview generation
- flow graph construction for traced documents
- query engine with guardrails and business query templates
- optional LLM planner with fail-closed behavior

Primary backend files created:

- `backend/app/database.py`
- `backend/app/domain.py`
- `backend/app/graph.py`
- `backend/app/query_engine.py`
- `backend/app/main.py`

### 5. Frontend implementation

Implemented:

- single-page interface with graph visualization
- conversational panel
- sample prompts
- SQL preview pane
- node inspector
- Cytoscape-based graph rendering

Primary frontend files created:

- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`

### 6. Issue encountered during ingestion

Problem:

- some SAP fields such as `creationTime` and `actualGoodsMovementTime` were nested JSON objects instead of scalar values
- SQLite insertion failed with `type 'dict' is not supported`

Fix:

- normalized dict/list values to JSON strings in the ingestion layer before writing to SQLite

### 7. Query validation

The following grounded queries were tested successfully:

- `Which products are associated with the highest number of billing documents?`
- `Trace the full flow of billing document 90504298`
- `Identify sales orders that have incomplete flows`
- off-topic prompt rejection with `Write me a poem about dragons`

Observed example outputs during validation:

- top billed product: `SUNSCREEN GEL SPF50-PA+++ 50ML (S8907367039280)` with 22 billing documents
- traced billing flow: `90504298 -> sales order 740598 -> delivery 80738109 -> journal entry 9400000299 -> payment 9400635920`
- incomplete flows detected for 3 sales orders, with `740506` identified as the most severe

### 8. Performance issue and optimization

Problem:

- the first implementation built the SQLite database during FastAPI import, causing slow app startup

Fix:

- moved data preparation out of import-time execution
- added `scripts/prepare_data.py` for explicit one-time preprocessing
- changed deployment to prebuild the database during the build step
- kept a lazy fallback only if the processed database is missing

Result:

- app import time dropped to roughly 1.8 seconds when prepared data exists

### 9. Submission-oriented artifacts

Added:

- `README.md`
- `render.yaml`
- `scripts/download_dataset.py`
- `scripts/prepare_data.py`
- this AI session log

## Prompting and Iteration Pattern

The AI workflow in this session followed a concrete engineering loop:

1. inspect the workspace before making assumptions
2. inspect the real dataset before finalizing the graph model
3. implement the thinnest end-to-end slice first
4. run direct verification against the real data
5. fix ingestion/runtime issues found during verification
6. optimize startup time after functionality was stable
7. add submission artifacts after the core system worked

## Verification Commands Used

Representative checks run during the session:

```powershell
python -c "from backend.app.database import DataRepository; repo = DataRepository(); repo.ensure_initialized(force=True); meta = repo.load_metadata(); print(len(meta['tables']), len(meta['entities']))"
```

```powershell
python -c "from backend.app.main import app; print(app.title)"
```

```powershell
@'
from backend.app.database import DataRepository
from backend.app.graph import GraphService
from backend.app.query_engine import QueryEngine

repo = DataRepository()
repo.ensure_initialized()
engine = QueryEngine(repo, GraphService(repo))
for q in [
    'Which products are associated with the highest number of billing documents?',
    'Trace the full flow of billing document 90504298',
    'Identify sales orders that have incomplete flows',
    'Write me a poem about dragons',
]:
    result = engine.answer(q)
    print(q, result.answer, result.guardrail_blocked)
'@ | python -
```

```powershell
@'
from fastapi.testclient import TestClient
from backend.app.main import app
client = TestClient(app)
print(client.get('/api/health').json())
print(client.post('/api/chat', json={'message':'Trace the full flow of billing document 90504298'}).json()['answer'])
'@ | python -
```

## Remaining Manual Submission Steps

At the point this log was written, the remaining tasks were operational rather than coding:

- create and push the public GitHub repository
- deploy the app and obtain a public demo URL
- submit the repo URL and demo URL through the provided form
