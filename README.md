# LLM-Based SQL Debugging Assistant

A college database systems project that automates SQL error detection, correction, and query optimization using **Oracle Database**, **Google Gemini AI**, and a React frontend.

---

## Project Architecture

```
User SQL Query
      │
      ▼
Oracle Database Execution ──(Success)──► Return Results
      │
  (Failure: Capture ORA-XXXXX Error)
      │
      ▼
Retrieve Oracle Schema Metadata (user_tab_columns)
      │
      ▼
Gemini AI: Diagnose error, propose corrected SQL
      │
      ▼
Re-execute corrected SQL (up to 3 attempts)
      │
      ▼
Return verified SQL, explanation, results, and history
```

---

## Project Structure

```
SQL-Debugging-Assistant/
├── backend/
│   ├── main.py         # FastAPI app — GET /, GET /health/db, POST /debug, POST /optimize
│   ├── database.py     # Oracle connection, query execution, schema metadata, EXPLAIN PLAN
│   ├── llm.py          # Google Gemini integration for debugging and optimization
│   ├── debugger.py     # 3-attempt SQL debugging loop
│   ├── optimizer.py    # SQL optimization workflow with safety checks
│   ├── requirements.txt
│   └── .env.example    # Copy to .env and fill in credentials
├── frontend/
│   ├── src/
│   │   ├── App.jsx     # React UI — Debug tab + Optimize tab
│   │   ├── index.css   # Dark glassmorphism design system
│   │   └── main.jsx    # React entry point
│   ├── package.json
│   └── vite.config.js
├── database/
│   ├── schema.sql      # Oracle DDL for EMPLOYEES and DEPT tables
│   └── test_queries.sql # Test queries: valid, invalid column, invalid table, syntax error
├── .gitignore
└── README.md
```

---

## Setup Instructions

### Prerequisites

- Python 3.10+
- Node.js 18+ and npm
- Docker Desktop (for Oracle Database)
- A Google AI Studio API key (free at https://aistudio.google.com/app/apikey)

---

### Step 1 — Oracle Database via Docker

> [!IMPORTANT]
> Docker Desktop must be installed and running before this step.

```bash
# Pull the Oracle Free image (≈ 2 GB download)
docker pull gvenzl/oracle-free

# Start the Oracle container
# Replace MySecurePass123 with a password of your choice
docker run -d \
  --name oracle-db \
  -p 1521:1521 \
  -e ORACLE_PASSWORD=MySecurePass123 \
  gvenzl/oracle-free

# Wait ~60–90 seconds for Oracle to initialise, then check status
docker logs oracle-db | tail -20

# When you see "DATABASE IS READY TO USE!", initialise the schema
docker exec -i oracle-db sqlplus system/MySecurePass123@localhost:1521/FREEPDB1 < database/schema.sql
```

The schema creates the `EMPLOYEES` and `DEPT` tables with sample data.

---

### Step 2 — Backend Setup

```bash
cd backend

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate          # macOS / Linux
# venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt

# Create your .env file
cp .env.example .env
```

Edit `backend/.env` and fill in:

```env
DB_USER=system
DB_PASSWORD=MySecurePass123          # same password used in Step 1
DB_HOST=localhost
DB_PORT=1521
DB_SERVICE_NAME=FREEPDB1

LLM_API_KEY=your_gemini_api_key      # from https://aistudio.google.com/app/apikey
LLM_MODEL=gemini-1.5-flash
LLM_PROVIDER=gemini
```

Start the server:

```bash
uvicorn main:app --reload --port 8000
```

Verify:
- Health check: http://127.0.0.1:8000/
- DB status: http://127.0.0.1:8000/health/db
- API docs: http://127.0.0.1:8000/docs

---

### Step 3 — Frontend Setup

Open a **new terminal**:

```bash
cd frontend
npm install
npm run dev
```

Open the app: http://localhost:5173

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Health check |
| `GET` | `/health/db` | Oracle connectivity check |
| `POST` | `/debug` | SQL debugging (up to 3 LLM attempts) |
| `POST` | `/optimize` | SQL optimization analysis |

### POST /debug

```json
Request:  { "sql_query": "SELECT emp_nmae FROM employees" }

Response: {
  "status": "SUCCESS | FAILED | DB_NOT_CONFIGURED | LLM_KEY_MISSING | ...",
  "verified_sql": "SELECT emp_name FROM employees",
  "explanation": "The column 'emp_nmae' was a typo ...",
  "attempts": 1,
  "oracle_error": "ORA-00904: ...",
  "execution_result": { "columns": [...], "rows": [...] },
  "history": [{ "attempt": 1, "sql": "...", "error": "...", "corrected_sql": "..." }]
}
```

### POST /optimize

```json
Request:  { "sql_query": "SELECT * FROM employees WHERE dept_id = 10" }

Response: {
  "status": "SUCCESS",
  "original_sql": "...",
  "optimized_sql": "SELECT emp_id, emp_name, salary FROM employees WHERE dept_id = 10",
  "explanation": "...",
  "recommendations": ["Avoid SELECT *", "Consider an index on dept_id"],
  "semantic_preserved": true,
  "plan_changes": "...",
  "original_plan": "...",
  "original_execution": { "elapsed_ms": 12.4, "row_count": 2 },
  "optimized_execution": { "elapsed_ms": 8.1, "row_count": 2 },
  "db_available": true
}
```

---

## Test Queries

See `database/test_queries.sql` for ready-to-use test cases:

| Test | Query | Expected Oracle Error |
|------|-------|-----------------------|
| Valid | `SELECT emp_name FROM employees` | None |
| Bad column | `SELECT emp_nmae FROM employees` | ORA-00904 |
| Bad table | `SELECT emp_name FROM emp_list` | ORA-00942 |
| Syntax error | `SELECT FROM employees` | ORA-00936 |
| Bad column name | `SELECT * FROM employees WHERE department_id = 20` | ORA-00904 |

---

## Status Codes Reference

| Status | Meaning |
|--------|---------|
| `SUCCESS` | Query executed successfully |
| `FAILED` | All 3 debug attempts exhausted |
| `DB_NOT_CONFIGURED` | `DB_USER` / `DB_PASSWORD` not set in `.env` |
| `DB_CONNECTION_ERROR` | Credentials set but Oracle not reachable |
| `LLM_KEY_MISSING` | `LLM_API_KEY` not set in `.env` |
| `VALIDATION_ERROR` | Non-SELECT query submitted to optimizer |

---

## Known Limitations

- **Oracle on macOS**: Oracle Database does not have a native macOS installer. Docker is required.
- **Execution plan timing**: Wall-clock measurements are approximate for a college demo environment. Do not treat them as production benchmarks.
- **LLM correctness**: Gemini AI may occasionally produce incorrect SQL. The 3-attempt loop mitigates this but does not guarantee correctness on all inputs.
- **Schema scope**: Only tables owned by the connected user are visible in metadata queries (`user_tab_columns`). Tables in other schemas require `all_tab_columns` with appropriate privileges.
- **Thin mode**: python-oracledb is used in thin mode — no Oracle Client library is required.
