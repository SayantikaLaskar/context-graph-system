from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import FRONTEND_ROOT, settings
from .database import DataRepository
from .graph import GraphService
from .models import ChatRequest, ChatResponse
from .query_engine import QueryEngine


@lru_cache(maxsize=1)
def get_repository() -> DataRepository:
    return DataRepository()


@lru_cache(maxsize=1)
def get_graph_service() -> GraphService:
    return GraphService(get_repository())


@lru_cache(maxsize=1)
def get_query_engine() -> QueryEngine:
    repository = get_repository()
    if not repository.is_initialized():
        repository.ensure_initialized()
    return QueryEngine(repository, get_graph_service())


app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, object]:
    repository = get_repository()
    return {"status": "ok", "dataPrepared": repository.is_initialized()}


@app.get("/api/bootstrap")
def bootstrap() -> dict[str, object]:
    repository = get_repository()
    if not repository.is_initialized():
        repository.ensure_initialized()
    metadata = repository.load_metadata()
    return {
        "metadata": metadata,
        "overviewGraph": get_graph_service().overview_graph().model_dump(),
        "llmEnabled": settings.llm_enabled,
    }


@app.get("/api/graph/overview")
def graph_overview() -> dict[str, object]:
    repository = get_repository()
    if not repository.is_initialized():
        repository.ensure_initialized()
    return get_graph_service().overview_graph().model_dump()


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    return get_query_engine().answer(payload.message)


@app.get("/api/entity/{entity_type}/{entity_key}")
def entity_lookup(entity_type: str, entity_key: str) -> dict[str, object]:
    repository = get_repository()
    if not repository.is_initialized():
        repository.ensure_initialized()

    sql_map = {
        "sales_order": ("SELECT * FROM sales_order_headers WHERE sales_order = ?", (entity_key,)),
        "billing_document": ("SELECT * FROM billing_document_headers WHERE billing_document = ?", (entity_key,)),
        "delivery": ("SELECT * FROM outbound_delivery_headers WHERE delivery_document = ?", (entity_key,)),
        "product": ("SELECT * FROM products WHERE product = ?", (entity_key,)),
        "customer": (
            "SELECT * FROM business_partners WHERE business_partner = ? OR customer = ?",
            (entity_key, entity_key),
        ),
        "plant": ("SELECT * FROM plants WHERE plant = ?", (entity_key,)),
    }
    if entity_type not in sql_map:
        raise HTTPException(status_code=404, detail=f"Unsupported entity type: {entity_type}")

    sql, params = sql_map[entity_type]
    result = repository.query_one(sql, params)
    if not result:
        raise HTTPException(status_code=404, detail="Entity not found")
    return result


def _frontend_file(name: str) -> FileResponse:
    path = FRONTEND_ROOT / name
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Missing frontend file: {name}")
    return FileResponse(path)


@app.get("/")
def index() -> FileResponse:
    return _frontend_file("index.html")


@app.get("/app.js")
def app_js() -> FileResponse:
    return _frontend_file("app.js")


@app.get("/styles.css")
def styles() -> FileResponse:
    return _frontend_file("styles.css")
