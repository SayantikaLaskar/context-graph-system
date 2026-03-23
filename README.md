# Context Graph System

This project turns the supplied SAP O2C dataset into a graph-backed analytics workspace with:

- a SQLite-backed ingestion layer over the raw JSONL tables
- a graph visualization for document and master-data relationships
- a conversational query API that maps natural language to safe dataset queries
- dataset guardrails that reject off-topic prompts

## Folder Structure

- `backend/`: FastAPI API, ingestion, graph logic, and query planner
- `frontend/`: static single-page UI served by the backend
- `data/raw/`: downloaded and extracted source dataset
- `data/processed/`: generated SQLite database and metadata cache
- `scripts/`: utility scripts, including dataset download
- `docs/ai-logs/`: place exported AI session transcripts here for submission

## Architecture Decisions

### Database choice

SQLite was chosen because the dataset is small enough to fit comfortably in a local analytical store, requires no extra service to run, and lets the system expose the exact SQL executed for each grounded answer.

### Graph model

The graph is modeled around business entities and document flow:

- `customer -> sales_order -> sales_order_item`
- `sales_order_item -> delivery_item -> delivery`
- `delivery_item -> billing_item -> billing_document`
- `billing_document -> journal_entry -> payment`
- `sales_order_item -> product`
- `delivery_item -> plant`
- `customer -> address`

The UI starts with an entity-type overview graph and switches to query-specific flow graphs when the user asks about a document or analytic.

### Query strategy

The backend uses a layered approach:

1. Guardrail check to reject prompts outside the dataset domain.
2. Intent templates for the highest-value business questions:
   - top billed products
   - billing document trace
   - sales order trace
   - incomplete O2C flows
3. Optional LLM SQL planning for additional in-domain questions when `LLM_API_KEY`, `LLM_MODEL`, and `LLM_API_URL` are configured.

Only read-only SQL is allowed. Generated SQL must be a single `SELECT` or `WITH` statement. Destructive SQL keywords are blocked before execution.

### Guardrails

The system rejects prompts unrelated to the supplied SAP O2C dataset and responds with:

> This system is designed to answer questions related to the provided SAP O2C dataset only.

This keeps the assistant constrained to sales orders, deliveries, billing documents, journal entries, payments, customers, products, plants, and addresses.

## Setup

### 1. Download the dataset

```bash
python scripts/download_dataset.py
```

This fetches the Google Drive ZIP and extracts it to `data/raw/extracted/sap-o2c-data/`.

### 2. Prepare the local database

```bash
python scripts/prepare_data.py
```

This creates `data/processed/o2c_graph.sqlite` and `data/processed/dataset_metadata.json`. Running this once keeps normal app startup fast.

### 3. Run the backend

```bash
uvicorn backend.app.main:app --reload
```

Then open `http://127.0.0.1:8000`.

## Deployment

The repo includes `render.yaml` for a simple free-tier Render deployment:

1. Create a new Blueprint deployment on Render.
2. Point it at the GitHub repo.
3. Let Render run the build command, which installs dependencies, downloads the dataset, and prebuilds the SQLite database.
4. Use the generated Render URL as the submission demo link.

## Optional LLM Configuration

The app works in template mode without an API key. For broader natural-language coverage, configure:

```env
LLM_API_URL=
LLM_API_KEY=
LLM_MODEL=
```

The SQL planner expects an OpenAI-compatible chat endpoint that returns JSON mode responses.

## Example Questions

- `Which products are associated with the highest number of billing documents?`
- `Trace the full flow of billing document 90504298`
- `Trace sales order 740506`
- `Identify sales orders that have incomplete flows`

## Submission Notes

Before submitting:

1. Push this repo to a public GitHub repository.
2. Deploy the app so the FastAPI service and static UI are reachable from a public URL.
3. Export AI coding transcripts into `docs/ai-logs/` and include them in your submission ZIP if required.
