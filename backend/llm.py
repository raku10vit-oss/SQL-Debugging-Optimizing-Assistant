"""
llm.py — LLM Integration Module for SQL Debugging and Optimization.

Supports Google Gemini (default) as the LLM backend.
The LLM_PROVIDER env var can be set to 'openai' to switch to OpenAI.
API keys are read from the environment at call time (not at import time).
"""

import os
import json
import re
import logging
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _get_config() -> Dict[str, str]:
    """Read LLM configuration from environment at call time."""
    return {
        "api_key": os.getenv("LLM_API_KEY", ""),
        "model": os.getenv("LLM_MODEL", "gemini-3.6-flash"),
        "provider": os.getenv("LLM_PROVIDER", "gemini"),
    }


def _validate_api_key(cfg: Dict[str, str]) -> None:
    """Raise a clear error if the API key is missing or is the placeholder."""
    key = cfg["api_key"]
    if not key or key in ("your_llm_api_key_here", "your_api_key"):
        raise RuntimeError(
            "LLM_API_KEY is missing or not configured in backend/.env. "
            "Set LLM_API_KEY to your Google AI Studio API key to enable AI features."
        )


def _extract_json(text: str) -> Dict[str, Any]:
    """
    Extract the first JSON object from a model response string.
    Handles code fences like ```json ... ``` as well as bare JSON.
    """
    # Strip markdown code fences
    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    text = text.rstrip("`").strip()

    # Find outermost {...}
    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON object found in LLM response: {text[:200]}")
    depth, end = 0, -1
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        raise ValueError("Malformed JSON in LLM response (unmatched braces).")
    return json.loads(text[start : end + 1])


def _call_gemini(system_prompt: str, user_prompt: str, cfg: Dict[str, str]) -> str:
    """Call the Google GenAI SDK and return the raw text response."""
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError(
            "Google GenAI SDK is not installed. "
            "Run: python -m pip install google-genai"
        ) from exc

    logger.info("Connecting to Gemini model: %s", cfg["model"])

    try:
        client = genai.Client(api_key=cfg["api_key"])

        response = client.models.generate_content(
            model=cfg["model"],
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.1,
            ),
        )

        if not response.text:
            raise RuntimeError("Gemini returned an empty response.")

        logger.info("Gemini response received successfully.")
        return response.text

    except Exception:
        logger.exception("Gemini API request failed.")
        raise


def _call_openai(system_prompt: str, user_prompt: str, cfg: Dict[str, str]) -> str:
    """Call the OpenAI API and return the raw text response."""
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError(
            "openai package is not installed. Run: pip install openai"
        )

    client = OpenAI(api_key=cfg["api_key"])
    response = client.chat.completions.create(
        model=cfg["model"],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content


def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """Route to the configured LLM provider and return the raw text response."""
    cfg = _get_config()
    _validate_api_key(cfg)

    provider = cfg["provider"].lower()
    if provider == "openai":
        return _call_openai(system_prompt, user_prompt, cfg)
    else:
        return _call_gemini(system_prompt, user_prompt, cfg)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_sql_fix(sql_query: str, oracle_error: str, schema_metadata: str) -> Dict[str, str]:
    """Ask the LLM to diagnose an SQL error and return a corrected query."""

    system_prompt = (
        "You are an expert SQL database debugger.\n"
        "Analyze the failing SQL query, database error message, and schema.\n"
        "The database may be SQLite, Oracle, PostgreSQL, or another SQL database. "
        "Use the supplied error message and schema to identify the actual database dialect.\n"
        "Return ONLY a JSON object with exactly two keys:\n"
        "  corrected_sql: the corrected, executable SQL query (string)\n"
        "  explanation: a concise explanation of the root cause and fix (string)\n"
        "Do not include DDL, DML, TRUNCATE, DROP, or multiple statements.\n"
        "The corrected query must preserve the original query's intended meaning.\n"
        "Do not invent table names, columns, or schema details."
    )

    user_prompt = (
        f"FAULTY SQL:\n{sql_query}\n\n"
        f"DATABASE ERROR:\n{oracle_error}\n\n"
        f"DATABASE SCHEMA:\n{schema_metadata}"
    )

    raw = _call_llm(system_prompt, user_prompt)
    logger.debug("LLM raw debug response: %s", raw[:500])

    parsed = _extract_json(raw)

    corrected = parsed.get("corrected_sql", "").strip()
    explanation = parsed.get("explanation", "").strip()

    if not corrected:
        raise ValueError("LLM returned an empty corrected_sql field.")

    return {"corrected_sql": corrected, "explanation": explanation}



def generate_sql_optimization(sql_query: str, schema_metadata: str, execution_plan: str = "") -> Dict[str, Any]:
    """
    Ask the LLM to analyze a SQL query and suggest optimizations.

    Args:
        sql_query:       The valid SQL query to optimize.
        schema_metadata: Formatted schema string from get_schema_metadata().
        execution_plan:  Oracle EXPLAIN PLAN output (optional, empty string if unavailable).

    Returns:
        {
            "optimized_sql":       "<proposed optimized Oracle SQL query>",
            "explanation":         "<explanation of inefficiencies found>",
            "recommendations":     ["<rec 1>", "<rec 2>", ...],
            "semantic_preserved":  true/false,
            "plan_changes":        "<description of expected execution plan changes>"
        }

    Raises:
        RuntimeError: If the API key is missing.
        ValueError:   If the LLM response cannot be parsed.
    """
    
    plan_section = (
        f"DATABASE EXECUTION PLAN:\n{execution_plan}\n\n"
        if execution_plan.strip()
        else "DATABASE EXECUTION PLAN: Not available.\n\n"
    )

    system_prompt = (
        "You are an expert SQL performance tuning specialist.\n"
        "Analyze the SQL query, database schema, and execution plan if provided.\n"
        "Use the database dialect indicated by the query, error messages, schema, "
        "and execution plan. Do not assume the database is Oracle.\n"
        "Return ONLY a JSON object with exactly these keys:\n"
        "  optimized_sql: the proposed optimized SQL query (string). "
        "If no improvement is justified, return the original query unchanged.\n"
        "  explanation: explanation of inefficiencies and potential improvements (string)\n"
        "  recommendations: array of actionable recommendations (array of strings)\n"
        "  semantic_preserved: true if the query's meaning is preserved, false otherwise (boolean)\n"
        "  plan_changes: expected execution-plan or performance changes (string)\n"
        "CRITICAL RULES:\n"
        "- Do not claim measured performance improvements without reliable measurements.\n"
        "- Do not change the query's meaning, filtering, joins, NULL behavior, or ordering.\n"
        "- Do not put CREATE INDEX or ALTER TABLE in optimized_sql; recommendations only.\n"
        "- Return a single SELECT statement in optimized_sql.\n"
        "- If the query is already suitable, return it unchanged and explain why.\n"
        "- Do not recommend database-specific commands unless the database supports them.\n"
    )


    user_prompt = (
        f"SQL QUERY TO OPTIMIZE:\n{sql_query}\n\n"
        f"DATABASE SCHEMA:\n{schema_metadata}\n\n"
        f"{plan_section}"
    )

    raw = _call_llm(system_prompt, user_prompt)
    logger.debug("LLM raw optimize response: %s", raw[:500])

    parsed = _extract_json(raw)

    return {
        "optimized_sql": parsed.get("optimized_sql", sql_query).strip(),
        "explanation": parsed.get("explanation", "").strip(),
        "recommendations": parsed.get("recommendations", []),
        "semantic_preserved": parsed.get("semantic_preserved", True),
        "plan_changes": parsed.get("plan_changes", "").strip(),
    }
