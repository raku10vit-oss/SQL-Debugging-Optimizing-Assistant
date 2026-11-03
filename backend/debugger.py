"""
debugger.py — 3-Attempt Automated SQL Debugging Workflow.

Architecture:
  Attempt 1..3:
    1. Execute the SQL query against Oracle.
    2. If success → return results.
    3. If failure → capture Oracle error string.
    4. Fetch schema metadata.
    5. Ask the LLM to propose a corrected query + explanation.
    6. Replace the current SQL with the corrected SQL.
    7. Continue to next attempt.
  After 3 failures → return FAILED status with full history.

Status codes returned:
  SUCCESS          — Query executed without errors.
  DB_NOT_CONFIGURED — Oracle credentials missing or incomplete in .env.
  DB_CONNECTION_ERROR — Oracle credentials present but server unreachable.
  LLM_KEY_MISSING  — LLM API key not set in .env.
  LLM_NOT_CONNECTED — LLM module not yet wired (should not happen in production).
  FAILED           — All 3 attempts exhausted without success.
"""

import logging
from typing import Dict, Any, List

from database import execute_oracle_query, get_schema_metadata
from llm import generate_sql_fix

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3


def debug_sql_workflow(initial_sql: str) -> Dict[str, Any]:
    """
    Run the 3-attempt SQL debugging loop.

    Args:
        initial_sql: The SQL query string submitted by the user.

    Returns:
        A dict with keys:
          status, verified_sql, explanation, attempts,
          oracle_error, execution_result, history.
    """
    current_sql = initial_sql
    attempts_history: List[Dict[str, Any]] = []
    final_explanation = ""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        logger.info("Debug attempt %d/%d", attempt, MAX_ATTEMPTS)

        # ── Step 1: Execute current SQL ───────────────────────────────────────
        exec_result = execute_oracle_query(current_sql)

        if exec_result["success"]:
            if attempts_history:
                attempts_history.append({
                    "attempt": attempt,
                    "sql": current_sql,
                    "status": "SUCCESS",
                    "error": None,
                    "corrected_sql": current_sql,
                    "explanation": final_explanation or "Corrected SQL executed successfully.",
                })

            return {
                "status": "SUCCESS",
                "verified_sql": current_sql,
                "explanation": final_explanation or "SQL executed successfully.",
                "attempts": attempt,
                "execution_result": exec_result,
                "oracle_error": None,
                "history": attempts_history,
            }

        oracle_error = exec_result.get("error", "Unknown error")
        error_type = exec_result.get("error_type", "oracle_error")

        # Record this attempt
        attempt_record = {
            "attempt": attempt,
            "sql": current_sql,
            "error": oracle_error,
            "error_type": error_type,
        }
        attempts_history.append(attempt_record)

        # ── Step 2: Check error type ──────────────────────────────────────────
        if error_type == "credentials_error":
            return {
                "status": "DB_NOT_CONFIGURED",
                "verified_sql": current_sql,
                "explanation": (
                    "Oracle Database credentials are not configured. "
                    "Copy backend/.env.example to backend/.env and fill in "
                    "DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, and DB_SERVICE_NAME."
                ),
                "attempts": attempt,
                "execution_result": exec_result,
                "oracle_error": oracle_error,
                "history": attempts_history,
            }

        if error_type == "connection_error":
            return {
                "status": "DB_CONNECTION_ERROR",
                "verified_sql": current_sql,
                "explanation": (
                    "Oracle Database credentials are set but the server could not be reached. "
                    "Ensure Oracle is running and the host/port/service name are correct."
                ),
                "attempts": attempt,
                "execution_result": exec_result,
                "oracle_error": oracle_error,
                "history": attempts_history,
            }

        # ── Step 3: Fetch schema metadata ─────────────────────────────────────
        schema_metadata = get_schema_metadata()

        # ── Step 4: Ask LLM for a fix ─────────────────────────────────────────
        try:
            llm_result = generate_sql_fix(current_sql, oracle_error, schema_metadata)
        except RuntimeError as e:
            # API key missing
            return {
                "status": "LLM_KEY_MISSING",
                "verified_sql": current_sql,
                "explanation": str(e),
                "attempts": attempt,
                "execution_result": exec_result,
                "oracle_error": oracle_error,
                "history": attempts_history,
            }
        except NotImplementedError as e:
            return {
                "status": "LLM_NOT_CONNECTED",
                "verified_sql": current_sql,
                "explanation": str(e),
                "attempts": attempt,
                "execution_result": exec_result,
                "oracle_error": oracle_error,
                "history": attempts_history,
            }
        except Exception as e:
            logger.exception("LLM error on attempt %d", attempt)
            attempt_record["llm_error"] = str(e)
            break  # Give up — LLM is broken, no point retrying

        corrected_sql = llm_result.get("corrected_sql", "").strip()
        final_explanation = llm_result.get("explanation", "")
        attempt_record["corrected_sql"] = corrected_sql
        attempt_record["explanation"] = final_explanation

        if not corrected_sql:
            logger.warning("LLM returned empty corrected_sql on attempt %d", attempt)
            break

        current_sql = corrected_sql

    # ── All attempts exhausted ────────────────────────────────────────────────
    last_error = attempts_history[-1]["error"] if attempts_history else None
    return {
        "status": "FAILED",
        "verified_sql": current_sql,
        "explanation": (
            f"Could not resolve the SQL error after {len(attempts_history)} attempt(s). "
            "Review the attempt history for details."
        ),
        "attempts": len(attempts_history),
        "execution_result": None,
        "oracle_error": last_error,
        "history": attempts_history,
    }
