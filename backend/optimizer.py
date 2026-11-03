"""
optimizer.py — SQL Query Optimization Workflow.

Workflow:
  1. Validate that the query is a safe, read-only SELECT statement.
  2. Retrieve Oracle schema metadata.
  3. Obtain the Oracle EXPLAIN PLAN (if a live DB is available).
  4. Send query, schema, and plan to the LLM for optimization suggestions.
  5. Validate the LLM-proposed query (SELECT-only, single statement).
  6. Optionally execute both queries and compare result sets.
  7. Return evidence-based recommendations — never fabricate performance claims.
"""

import logging
import re
import time
from typing import Dict, Any, List, Optional

from database import get_schema_metadata, get_execution_plan, execute_readonly_query
from llm import generate_sql_optimization

logger = logging.getLogger(__name__)

# Statement types that are permitted for optimization analysis.
_ALLOWED_PREFIXES = ("SELECT", "WITH")

# Statement types that are definitely dangerous.
_BLOCKED_PREFIXES = (
    "DROP", "TRUNCATE", "DELETE", "UPDATE", "INSERT",
    "ALTER", "CREATE", "GRANT", "REVOKE", "MERGE",
    "EXECUTE", "EXEC", "CALL",
)


def _normalise(sql: str) -> str:
    """Strip comments and excess whitespace, return uppercase first keyword."""
    # Remove single-line comments
    sql = re.sub(r"--[^\n]*", " ", sql)
    # Remove block comments
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return sql.strip()


def _classify_query(sql: str) -> str:
    """
    Return the first SQL keyword of the statement (uppercased).
    Raises ValueError if the query contains multiple statements (semicolons
    in the middle) or is empty.
    """
    normalised = _normalise(sql)
    if not normalised:
        raise ValueError("The SQL query is empty.")

    # Check for multiple statements (semicolons that are not at the very end)
    body = normalised.rstrip(";").strip()
    if ";" in body:
        raise ValueError(
            "Multiple SQL statements are not allowed. "
            "Submit a single SELECT statement for optimization."
        )

    return normalised.lstrip().split()[0].upper()


def _validate_for_optimization(sql: str) -> None:
    """
    Ensure the query is safe to submit for optimization.
    Raises ValueError with a human-readable message if not.
    """
    keyword = _classify_query(sql)

    if keyword in _BLOCKED_PREFIXES:
        raise ValueError(
            f"The statement type '{keyword}' is not eligible for optimization. "
            "Only SELECT (or WITH ... SELECT) queries can be analyzed."
        )

    if keyword not in _ALLOWED_PREFIXES:
        raise ValueError(
            f"Unsupported statement type '{keyword}'. "
            "Only SELECT queries are supported for optimization."
        )


def _validate_llm_sql(proposed_sql: str) -> None:
    """
    Ensure the LLM-proposed SQL is also safe before we execute it.
    Raises ValueError if the proposed SQL is dangerous.
    """
    try:
        keyword = _classify_query(proposed_sql)
    except ValueError as e:
        raise ValueError(f"LLM proposed SQL is invalid: {e}")

    if keyword in _BLOCKED_PREFIXES or keyword not in _ALLOWED_PREFIXES:
        raise ValueError(
            f"LLM proposed a non-SELECT statement ('{keyword}'). "
            "This will not be executed."
        )


def _measure_query(sql: str, label: str) -> Dict[str, Any]:
    """
    Execute a read-only query and record wall-clock time in milliseconds.
    Returns a dict with timing, row count, and error information.
    """
    start = time.perf_counter()
    result = execute_readonly_query(sql)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

    return {
        "label": label,
        "success": result["success"],
        "row_count": len(result.get("rows", [])),
        "columns": result.get("columns", []),
        "rows": result.get("rows", []),
        "elapsed_ms": elapsed_ms,
        "error": result.get("error"),
    }


def optimize_sql_workflow(sql_query: str) -> Dict[str, Any]:
    """
    Run the full SQL optimization analysis workflow.

    Returns:
        {
            status:             "SUCCESS" | "VALIDATION_ERROR" | "LLM_KEY_MISSING"
                                | "LLM_NOT_CONNECTED" | "DB_NOT_CONFIGURED" | "FAILED"
            original_sql:       str
            optimized_sql:      str | None
            explanation:        str
            recommendations:    list[str]
            semantic_preserved: bool | None
            plan_changes:       str
            original_plan:      str   (empty if DB unavailable)
            original_execution: dict | None  (timing + rows from original query)
            optimized_execution: dict | None (timing + rows from optimized query)
            db_available:       bool
        }
    """
    # ── Step 1: Validate the input query ──────────────────────────────────────
    try:
        _validate_for_optimization(sql_query)
    except ValueError as e:
        return {
            "status": "VALIDATION_ERROR",
            "original_sql": sql_query,
            "optimized_sql": None,
            "explanation": str(e),
            "recommendations": [],
            "semantic_preserved": None,
            "plan_changes": "",
            "original_plan": "",
            "original_execution": None,
            "optimized_execution": None,
            "db_available": False,
        }

    # ── Step 2: Retrieve schema metadata ──────────────────────────────────────
    schema_metadata = get_schema_metadata()
    db_available = "fallback" not in schema_metadata.lower()

    # ── Step 3: Get EXPLAIN PLAN (if DB is available) ─────────────────────────
    original_plan = ""
    if db_available:
        original_plan = get_execution_plan(sql_query)

    # ── Step 4: Ask LLM for optimization suggestions ──────────────────────────
    try:
        llm_result = generate_sql_optimization(sql_query, schema_metadata, original_plan)
    except RuntimeError as e:
        return {
            "status": "LLM_KEY_MISSING",
            "original_sql": sql_query,
            "optimized_sql": None,
            "explanation": str(e),
            "recommendations": [],
            "semantic_preserved": None,
            "plan_changes": "",
            "original_plan": original_plan,
            "original_execution": None,
            "optimized_execution": None,
            "db_available": db_available,
        }
    except NotImplementedError as e:
        return {
            "status": "LLM_NOT_CONNECTED",
            "original_sql": sql_query,
            "optimized_sql": None,
            "explanation": str(e),
            "recommendations": [],
            "semantic_preserved": None,
            "plan_changes": "",
            "original_plan": original_plan,
            "original_execution": None,
            "optimized_execution": None,
            "db_available": db_available,
        }
    except Exception as e:
        logger.exception("LLM call failed during optimization")
        return {
            "status": "FAILED",
            "original_sql": sql_query,
            "optimized_sql": None,
            "explanation": f"LLM error: {str(e)}",
            "recommendations": [],
            "semantic_preserved": None,
            "plan_changes": "",
            "original_plan": original_plan,
            "original_execution": None,
            "optimized_execution": None,
            "db_available": db_available,
        }

    optimized_sql = llm_result.get("optimized_sql", "").strip() or sql_query
    explanation = llm_result.get("explanation", "")
    recommendations: List[str] = llm_result.get("recommendations", [])
    semantic_preserved: Optional[bool] = llm_result.get("semantic_preserved", True)
    plan_changes: str = llm_result.get("plan_changes", "")

    # ── Step 5: Validate the LLM-proposed SQL ────────────────────────────────
    try:
        _validate_llm_sql(optimized_sql)
    except ValueError as e:
        return {
            "status": "VALIDATION_ERROR",
            "original_sql": sql_query,
            "optimized_sql": None,
            "explanation": f"LLM proposed an unsafe query: {e}",
            "recommendations": recommendations,
            "semantic_preserved": None,
            "plan_changes": plan_changes,
            "original_plan": original_plan,
            "original_execution": None,
            "optimized_execution": None,
            "db_available": db_available,
        }

    # ── Step 6: Execute and compare (only if DB is available) ─────────────────
    original_execution: Optional[Dict] = None
    optimized_execution: Optional[Dict] = None

    if db_available:
        original_execution = _measure_query(sql_query, "Original")
        if optimized_sql.strip().upper() != sql_query.strip().upper():
            optimized_execution = _measure_query(optimized_sql, "Optimized")
        else:
            optimized_execution = {**original_execution, "label": "Optimized (unchanged)"}

    # ── Step 7: Return results ────────────────────────────────────────────────
    return {
        "status": "SUCCESS",
        "original_sql": sql_query,
        "optimized_sql": optimized_sql,
        "explanation": explanation,
        "recommendations": recommendations,
        "semantic_preserved": semantic_preserved,
        "plan_changes": plan_changes,
        "original_plan": original_plan,
        "original_execution": original_execution,
        "optimized_execution": optimized_execution,
        "db_available": db_available,
    }
