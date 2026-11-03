-- =============================================================
-- Test Queries for LLM-Based SQL Debugging Assistant
-- =============================================================
-- Run these queries through the Debug SQL panel to test the
-- full debugging workflow.
-- =============================================================

-- ─────────────────────────────────────────────────────────────
-- Test 1: VALID query (should succeed immediately)
-- ─────────────────────────────────────────────────────────────
SELECT emp_name, dept_id
FROM employees
WHERE dept_id = 10
ORDER BY emp_name;

-- ─────────────────────────────────────────────────────────────
-- Test 2: INVALID COLUMN NAME — ORA-00904
-- Expected: ORA-00904: "EMP_NMAE": invalid identifier
-- Expected fix: change emp_nmae to emp_name
-- ─────────────────────────────────────────────────────────────
SELECT emp_nmae, dept_id
FROM employees
WHERE dept_id = 10;

-- ─────────────────────────────────────────────────────────────
-- Test 3: INVALID TABLE NAME — ORA-00942
-- Expected: ORA-00942: table or view does not exist
-- Expected fix: change emp_list to employees
-- ─────────────────────────────────────────────────────────────
SELECT emp_name, salary
FROM emp_list
WHERE salary > 80000;

-- ─────────────────────────────────────────────────────────────
-- Test 4: SYNTAX ERROR — ORA-00936 (missing expression)
-- Expected: ORA-00936: missing expression
-- ─────────────────────────────────────────────────────────────
SELECT FROM employees WHERE dept_id = 10;

-- ─────────────────────────────────────────────────────────────
-- Test 5: INVALID CONDITION — ORA-00904
-- Expected: ORA-00904: "DEPARTMENT_ID": invalid identifier
-- Expected fix: change department_id to dept_id
-- ─────────────────────────────────────────────────────────────
SELECT emp_name, salary
FROM employees
WHERE department_id = 20;

-- =============================================================
-- Optimization Test Queries (use the Optimize SQL panel)
-- =============================================================

-- Opt Test 1: SELECT * (potential optimization to list columns)
SELECT *
FROM employees
WHERE dept_id = 10
ORDER BY salary DESC;

-- Opt Test 2: Inefficient pattern — subquery that could be a JOIN
SELECT emp_name
FROM employees
WHERE dept_id IN (
    SELECT dept_id FROM dept WHERE dept_name = 'ENGINEERING'
);

-- Opt Test 3: Missing WHERE clause on large join
SELECT e.emp_name, d.dept_name
FROM employees e, dept d
WHERE e.dept_id = d.dept_id;
