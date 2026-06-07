#!/usr/bin/env python3
"""
Phase 3 — FastAPI backend for the Mutual Fund FAQ Assistant.

Exposes POST /query for the Phase 4 UI and GET /health for readiness checks.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from phase3.api.schemas import HealthResponse, QueryRequest, QueryResponse
from phase3.generation.config import API_HOST, API_PORT, GROQ_MODEL, PHASE2_DIR
from phase3.generation.query_service import QueryService

UI_DIR = Path(__file__).resolve().parents[2] / "phase4" / "ui"


def create_app(
    phase2_dir=None,
    use_llm=None,
    groq_model: str = GROQ_MODEL,
) -> FastAPI:
    """Build the FastAPI application with a shared QueryService instance."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        service = QueryService(
            phase2_dir=phase2_dir,
            use_llm=use_llm,
            groq_model=groq_model,
        )
        service.initialize()
        app.state.query_service = service
        yield

    app = FastAPI(
        title="Mutual Fund FAQ Assistant",
        description="Facts-only Q&A with citations from five AMC corpus pages.",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        service: QueryService = app.state.query_service
        return HealthResponse(**service.health_status())

    @app.post("/query", response_model=QueryResponse)
    def query_endpoint(body: QueryRequest) -> QueryResponse:
        service: QueryService = app.state.query_service
        try:
            result = service.handle_query(body.query)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Internal server error") from exc

        return QueryResponse(
            response=result["response"],
            citation=result.get("citation", ""),
            footer=result.get("footer", ""),
            educational_link=result.get("educational_link", ""),
            response_type=result["response_type"],
            intent=result["intent"],
            confidence=result["confidence"],
            has_citation=result.get("has_citation", False),
            has_grounded_answer=result.get("has_grounded_answer", False),
        )

    if UI_DIR.is_dir() and os.environ.get("SERVE_UI", "true").strip().lower() not in (
        "0",
        "false",
        "no",
    ):
        app.mount("/", StaticFiles(directory=UI_DIR, html=True), name="ui")

    return app


app = create_app(phase2_dir=PHASE2_DIR)


def main() -> None:
    import uvicorn

    uvicorn.run(
        "phase3.api.server:app",
        host=API_HOST,
        port=API_PORT,
        reload=False,
    )


if __name__ == "__main__":
    main()
