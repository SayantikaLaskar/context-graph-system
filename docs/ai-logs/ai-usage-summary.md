# AI Usage Summary

## Tools used

- Codex terminal agent

## How AI was used

AI was used as an implementation and debugging partner throughout the assignment. The workflow was not "generate everything at once"; it was iterative:

1. inspect the provided workspace and isolate the assignment into its own repository
2. download and inspect the real dataset before deciding the graph schema
3. design the graph model and backend structure around actual document keys
4. implement the first end-to-end version quickly
5. validate with real queries against the dataset
6. debug ingestion, query-join, startup-time, deployment, and UI issues
7. refine the product quality with better prompts, README, deployment setup, and visual polish

## Key prompts / workflows

The AI workflow focused on these repeated prompt patterns:

- understand the assignment requirements and turn them into a concrete architecture
- inspect the actual dataset structure before finalizing joins or graph edges
- build a minimal vertical slice first instead of overengineering
- verify the implementation against the sample business questions
- fix concrete failures found during testing
- improve startup performance after functionality was stable
- push to GitHub, deploy publicly, and prepare submission artifacts

## Examples of implementation tasks done with AI assistance

- mapping SAP O2C entities into nodes and edges
- creating ingestion logic from JSONL to SQLite
- generating query templates for:
  - top billed products
  - billing document trace
  - incomplete flows
  - top billed customers
  - open billing documents
  - plant-wise delivery volume
- designing guardrails to reject out-of-domain prompts
- improving the frontend information hierarchy and graph workspace styling
- writing submission-facing documentation and the deployment manifest

## Debugging / iteration examples

### Dataset ingestion failure

Issue:

- some SAP time fields were nested JSON objects, which broke SQLite insertion

Iteration:

- inspected sample raw rows
- identified dict-valued fields
- normalized dict/list values to JSON strings before writing to SQLite

### Slow startup

Issue:

- the first version rebuilt the SQLite database at app import time

Iteration:

- moved preprocessing into an explicit preparation step
- kept runtime lazy initialization only as fallback
- bundled the processed database for deployment

### Deployment workflow

Issue:

- needed a public demo URL and a repo linked to the user account

Iteration:

- created and pushed the GitHub repository
- configured deployment for Vercel
- adjusted the repo so the processed database could ship with the app
- redeployed after functional and design improvements

## Outcome

AI was used to accelerate:

- architecture selection
- dataset understanding
- implementation speed
- debugging
- refinement for submission quality

The final system was still validated through direct command-line checks, API tests, deployment verification, and live query checks against the actual dataset.
