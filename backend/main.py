"""
main.py — FastAPI Application Entry Point.

Endpoints:
  GET  /           — Health check
  GET  /health/db  — Oracle database connectivity check
  POST /debug      — SQL debugging workflow (up to 3 LLM-assisted attempts)
  POST /optimize   — SQL query optimization analysis

CORS is restricted to the local Vite development server (http://localhost:5173).
"""

import logging
import os
from typing import Any, Dict, List, Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from database import test_connection
from debugger import debug_sql_workflow
from optimizer import optimize_sql_workflow

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="LLM-Based SQL Debugging Assistant API",
    description=(
        "Automated SQL debugging and optimization using Oracle DB and LLM AI reasoning. "
        "College database system project."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ─────────────────────────────────────────────────────────────────────
# Restricted to the local Vite dev server. Extend for production deployments.
# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://localhost:3000",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Accept"],
)


# ── Request / Response Models ─────────────────────────────────────────────────

class SQLDebugRequest(BaseModel):
    sql_query: str = Field(
        ...,
        min_length=1,
        description="The Oracle SQL query to execute and debug.",
        examples=["SELECT emp_nmae, dept_id FROM employees WHERE dept_id = 10;"],
    )


class SQLDebugResponse(BaseModel):
    status: str = Field(
        ...,
        description=(
            "Workflow status: SUCCESS | FAILED | DB_NOT_CONFIGURED | "
            "DB_CONNECTION_ERROR | LLM_KEY_MISSING | LLM_NOT_CONNECTED"
        ),
    )
    verified_sql: Optional[str] = Field(None, description="The final SQL query (original or corrected).")
    explanation: Optional[str] = Field(None, description="AI diagnosis and explanation of the fix.")
    attempts: int = Field(0, description="Number of debug attempts made (max 3).")
    oracle_error: Optional[str] = Field(None, description="Raw Oracle error message from the last failure.")
    execution_result: Optional[Dict[str, Any]] = Field(None, description="Query result set (columns + rows).")
    history: Optional[List[Dict[str, Any]]] = Field(None, description="Step-by-step attempt log.")


class SQLOptimizeRequest(BaseModel):
    sql_query: str = Field(
        ...,
        min_length=1,
        description="A valid Oracle SELECT query to analyze and optimize.",
        examples=["SELECT * FROM employees WHERE dept_id = 10;"],
    )


class SQLOptimizeResponse(BaseModel):
    status: str = Field(
        ...,
        description=(
            "Workflow status: SUCCESS | VALIDATION_ERROR | FAILED | "
            "LLM_KEY_MISSING | LLM_NOT_CONNECTED | DB_NOT_CONFIGURED"
        ),
    )
    original_sql: Optional[str] = None
    optimized_sql: Optional[str] = None
    explanation: Optional[str] = None
    recommendations: Optional[List[str]] = None
    semantic_preserved: Optional[bool] = Field(
        None, description="True if optimized query returns identical results to original."
    )
    plan_changes: Optional[str] = Field(None, description="Expected execution plan changes.")
    original_plan: Optional[str] = Field(None, description="Oracle EXPLAIN PLAN for original query.")
    original_execution: Optional[Dict[str, Any]] = Field(None, description="Timing and rows for original query.")
    optimized_execution: Optional[Dict[str, Any]] = Field(None, description="Timing and rows for optimized query.")
    db_available: bool = Field(False, description="True if a live Oracle connection was used.")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def health_check():
    """Basic health check — confirms the FastAPI server is running."""
    return {
        "status": "healthy",
        "service": "LLM-Based SQL Debugging Assistant API",
        "version": "2.0.0",
    }


@app.get("/health/db", tags=["Health"])
def database_health():
    """Check whether Oracle Database is reachable with the current .env credentials."""
    result = test_connection()
    return {
        "connected": result["connected"],
        "message": result["message"],
        "db_version": result.get("db_version"),
    }


@app.post("/debug", response_model=SQLDebugResponse, tags=["SQL Debugger"])
def debug_sql(payload: SQLDebugRequest):
    """
    Execute a SQL query, capture Oracle errors, and use the LLM to
    iteratively correct and re-execute the query (up to 3 attempts).
    """
    sql = payload.sql_query.strip()
    if not sql:
        raise HTTPException(status_code=400, detail="sql_query must not be empty.")

    logger.info("POST /debug — query length %d chars", len(sql))
    result = debug_sql_workflow(sql)
    return result


@app.post("/optimize", response_model=SQLOptimizeResponse, tags=["SQL Optimizer"])
def optimize_sql(payload: SQLOptimizeRequest):
    """
    Analyze a valid Oracle SELECT query for performance inefficiencies.
    Returns an optimized version, an explanation, and actionable recommendations.
    Execution plan and runtime comparison are included when a live DB is available.
    """
    sql = payload.sql_query.strip()
    if not sql:
        raise HTTPException(status_code=400, detail="sql_query must not be empty.")

    logger.info("POST /optimize — query length %d chars", len(sql))
    result = optimize_sql_workflow(sql)
    return result


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host=host, port=port, reload=True)
