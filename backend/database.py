"""
database.py — Database Connection and Query Execution.

Supports two backends:
  - sqlite  (default for local dev — no Oracle installation needed)
  - oracle  (python-oracledb — requires credentials in .env)

Set DB_TYPE=oracle in backend/.env to switch to Oracle.
When DB_TYPE is 'oracle' but credentials are missing,
the code returns a 'credentials_error' response rather than crashing.

All connections are opened and closed within each function call.
"""

import os
import sqlite3
import logging
from pathlib import Path
from typing import Dict, Any, List

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Statement types safe to read
_READONLY_PREFIXES = ("SELECT", "WITH", "EXPLAIN")

# Statement types that must never run automatically
_DANGEROUS_PREFIXES = (
    "DROP", "TRUNCATE", "DELETE", "UPDATE", "INSERT",
    "ALTER", "CREATE", "GRANT", "REVOKE", "MERGE",
    "EXECUTE", "EXEC", "CALL",
)

# Path to the SQLite database file (relative to project root)
_SQLITE_PATH = Path(__file__).parent.parent / "database" / "dev.db"


# ── Configuration helpers ─────────────────────────────────────────────────────

def _db_type() -> str:
    return os.getenv("DB_TYPE", "sqlite").lower()


def _get_oracle_config() -> Dict[str, str]:
    return {
        "user":     os.getenv("DB_USER", ""),
        "password": os.getenv("DB_PASSWORD", ""),
        "host":     os.getenv("DB_HOST", "localhost"),
        "port":     os.getenv("DB_PORT", "1521"),
        "service":  os.getenv("DB_SERVICE_NAME", "FREEPDB1"),
    }


# ── Connection factories ──────────────────────────────────────────────────────

def _get_sqlite_connection() -> sqlite3.Connection:
    """Open (and initialise if needed) the SQLite dev database."""
    _SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_SQLITE_PATH))
    conn.row_factory = sqlite3.Row          # column-name access
    conn.execute("PRAGMA journal_mode=WAL") # safe concurrent reads
    _ensure_sqlite_schema(conn)
    return conn


def _ensure_sqlite_schema(conn: sqlite3.Connection) -> None:
    """Create EMPLOYEES and DEPT tables with sample data if they don't exist."""
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS dept (
            dept_id   INTEGER PRIMARY KEY,
            dept_name TEXT NOT NULL,
            location  TEXT
        );

        CREATE TABLE IF NOT EXISTS employees (
            emp_id    INTEGER PRIMARY KEY,
            emp_name  TEXT NOT NULL,
            job_title TEXT,
            salary    REAL,
            dept_id   INTEGER REFERENCES dept(dept_id)
        );
    """)

    # Seed only when empty
    if cur.execute("SELECT COUNT(*) FROM dept").fetchone()[0] == 0:
        cur.executescript("""
            INSERT INTO dept VALUES (10, 'ENGINEERING',  'NEW YORK');
            INSERT INTO dept VALUES (20, 'MARKETING',    'SAN FRANCISCO');
            INSERT INTO dept VALUES (30, 'SALES',        'CHICAGO');

            INSERT INTO employees VALUES (101, 'ALICE SMITH',    'SOFTWARE ENGINEER', 95000, 10);
            INSERT INTO employees VALUES (102, 'BOB JOHNSON',    'DEVOPS ENGINEER',   88000, 10);
            INSERT INTO employees VALUES (103, 'CHARLIE DAVIS',  'MARKETING MANAGER', 75000, 20);
            INSERT INTO employees VALUES (104, 'DIANA PRINCE',   'SALES EXECUTIVE',   68000, 30);
        """)
        conn.commit()

    cur.close()


def _get_oracle_connection():
    """Open an Oracle connection. Raises ValueError if credentials are absent."""
    import oracledb
    cfg = _get_oracle_config()
    if not cfg["user"] or not cfg["password"]:
        raise ValueError(
            "Oracle DB credentials (DB_USER, DB_PASSWORD) are not configured in backend/.env."
        )
    dsn = f"{cfg['host']}:{cfg['port']}/{cfg['service']}"
    return oracledb.connect(user=cfg["user"], password=cfg["password"], dsn=dsn)


def get_connection():
    """Return a database connection for the configured backend."""
    if _db_type() == "oracle":
        return _get_oracle_connection()
    return _get_sqlite_connection()


# ── Error categorisation ──────────────────────────────────────────────────────

def _classify_error(err: Exception) -> str:
    s = str(err).lower()
    if "credentials" in s or "not configured" in s or "db_user" in s:
        return "credentials_error"
    if any(t in s for t in ("ora-12541", "ora-12154", "connection refused", "tns:", "timeout")):
        return "connection_error"
    return "oracle_error"  # covers sqlite errors too — label doesn't matter much for sqlite


# ── Public query functions ────────────────────────────────────────────────────

def execute_oracle_query(query: str) -> Dict[str, Any]:
    """
    Execute a SQL query and return a standard result dict.

    Works with both SQLite (local dev) and Oracle (production).
    Returns:
        {success, columns, rows, error, error_type}
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()

        if isinstance(conn, sqlite3.Connection):
            # ── SQLite path ──────────────────────────────────────────────────
            cursor = conn.cursor()
            cursor.execute(query)
            if cursor.description:
                columns = [d[0].upper() for d in cursor.description]
                rows    = [list(row) for row in cursor.fetchall()]
                return {"success": True, "columns": columns, "rows": rows,
                        "error": None, "error_type": None}
            else:
                conn.commit()
                return {"success": True, "columns": [], "rows": [],
                        "message": "Query executed with no result set.",
                        "error": None, "error_type": None}
        else:
            # ── Oracle path ──────────────────────────────────────────────────
            cursor = conn.cursor()
            cursor.execute(query)
            if cursor.description:
                columns = [col[0] for col in cursor.description]
                rows    = [list(row) for row in cursor.fetchall()]
                return {"success": True, "columns": columns, "rows": rows,
                        "error": None, "error_type": None}
            else:
                conn.commit()
                return {"success": True, "columns": [], "rows": [],
                        "message": "Query executed with no result set.",
                        "error": None, "error_type": None}

    except ValueError as e:
        return {"success": False, "columns": [], "rows": [],
                "error": str(e), "error_type": "credentials_error"}
    except Exception as e:
        return {"success": False, "columns": [], "rows": [],
                "error": str(e), "error_type": _classify_error(e)}
    finally:
        for obj in (cursor, conn):
            if obj:
                try: obj.close()
                except Exception: pass


def execute_readonly_query(query: str) -> Dict[str, Any]:
    """
    Execute a query only if it is a SELECT/WITH/EXPLAIN statement.
    Raises ValueError for non-read-only statements.
    """
    stripped = query.strip().upper()
    if not any(stripped.startswith(p) for p in _READONLY_PREFIXES):
        raise ValueError(
            f"Refusing to execute non-read-only query during optimization. "
            f"Statement starts with: {stripped[:25]!r}"
        )
    if any(stripped.startswith(p) for p in _DANGEROUS_PREFIXES):
        raise ValueError(f"Dangerous statement blocked: {stripped[:25]!r}")
    return execute_oracle_query(query)


def get_schema_metadata() -> str:
    """
    Return a formatted description of all user tables and columns.
    Falls back to a hardcoded description when the database is unavailable.
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()

        if isinstance(conn, sqlite3.Connection):
            # ── SQLite: read from sqlite_master ─────────────────────────────
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [r[0] for r in cursor.fetchall()]
            if not tables:
                return "(No tables found in SQLite database.)"

            lines = []
            for table in tables:
                cursor.execute(f"PRAGMA table_info({table})")
                cols = cursor.fetchall()
                col_defs = [f"{c[1].upper()} {c[2].upper() or 'TEXT'}" for c in cols]
                lines.append(f"Table {table.upper()}: {', '.join(col_defs)}")
            return "\n".join(lines)

        else:
            # ── Oracle: read from user_tab_columns ──────────────────────────
            cursor = conn.cursor()
            cursor.execute("""
                SELECT table_name, column_name, data_type, data_length, nullable
                FROM user_tab_columns
                ORDER BY table_name, column_id
            """)
            rows = cursor.fetchall()
            if not rows:
                return "(No user tables found in Oracle schema.)"

            schema: Dict[str, List[str]] = {}
            for table, col, dtype, length, nullable in rows:
                schema.setdefault(table, [])
                null_s = "" if nullable == "Y" else " NOT NULL"
                if dtype in ("NUMBER", "FLOAT"):
                    schema[table].append(f"{col} {dtype}{null_s}")
                else:
                    schema[table].append(f"{col} {dtype}({length}){null_s}")

            return "\n".join(
                f"Table {t}: {', '.join(cols)}" for t, cols in schema.items()
            )

    except Exception as e:
        logger.warning("Could not retrieve schema: %s", e)
        return (
            "Schema Metadata (fallback — database not connected):\n"
            "Table EMPLOYEES: EMP_ID INTEGER NOT NULL, EMP_NAME TEXT NOT NULL, "
            "JOB_TITLE TEXT, SALARY REAL, DEPT_ID INTEGER\n"
            "Table DEPT: DEPT_ID INTEGER NOT NULL, DEPT_NAME TEXT NOT NULL, LOCATION TEXT"
        )
    finally:
        for obj in (cursor, conn):
            if obj:
                try: obj.close()
                except Exception: pass


def get_execution_plan(query: str) -> str:
    """
    Return a query execution plan if available.
    SQLite uses EXPLAIN QUERY PLAN; Oracle uses EXPLAIN PLAN.
    Returns an empty string if unavailable.
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()

        if isinstance(conn, sqlite3.Connection):
            cursor = conn.cursor()
            cursor.execute(f"EXPLAIN QUERY PLAN {query}")
            rows = cursor.fetchall()
            if not rows:
                return ""
            lines = ["id  parent  notused  detail"]
            lines.append("-" * 50)
            for row in rows:
                lines.append(f"{row[0]:<4} {row[1]:<7} {row[2]:<8} {row[3]}")
            return "\n".join(lines)

        else:
            # Oracle EXPLAIN PLAN
            cursor = conn.cursor()
            cursor.execute(f"EXPLAIN PLAN FOR {query}")
            cursor.execute("""
                SELECT LPAD(' ', 2*(LEVEL-1)) || OPERATION || ' ' || OPTIONS
                       || ' ' || NVL(OBJECT_NAME, '') AS step,
                       COST, CARDINALITY
                FROM PLAN_TABLE
                CONNECT BY PRIOR ID = PARENT_ID
                START WITH ID = 0
                ORDER SIBLINGS BY ID
            """)
            rows = cursor.fetchall()
            conn.rollback()
            if not rows:
                return ""
            lines = [f"{'Step':<55} {'Cost':<6} Rows"]
            lines.append("-" * 70)
            for step, cost, card in rows:
                lines.append(f"{str(step):<55} {str(cost or ''):<6} {str(card or '')}")
            return "\n".join(lines)

    except Exception as e:
        logger.info("Could not get execution plan: %s", e)
        return ""
    finally:
        for obj in (cursor, conn):
            if obj:
                try: obj.close()
                except Exception: pass


def test_connection() -> Dict[str, Any]:
    """Check whether the database is reachable. Used by GET /health/db."""
    conn = None
    try:
        conn = get_connection()
        if isinstance(conn, sqlite3.Connection):
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM employees")
            count = cur.fetchone()[0]
            cur.close()
            return {
                "connected": True,
                "message": f"SQLite connected. EMPLOYEES has {count} row(s).",
                "db_version": f"SQLite {sqlite3.sqlite_version}",
                "db_type": "sqlite",
            }
        else:
            cur = conn.cursor()
            cur.execute("SELECT banner FROM v$version WHERE ROWNUM = 1")
            version = cur.fetchone()[0]
            cur.close()
            return {
                "connected": True,
                "message": "Oracle connection successful.",
                "db_version": version,
                "db_type": "oracle",
            }
    except ValueError as e:
        return {"connected": False, "message": str(e), "db_version": None, "db_type": _db_type()}
    except Exception as e:
        return {"connected": False, "message": f"Connection failed: {e}", "db_version": None, "db_type": _db_type()}
    finally:
        if conn:
            try: conn.close()
            except Exception: pass
