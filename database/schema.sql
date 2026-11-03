-- SQL Schema Definitions for College Database Project
-- Database: Oracle SQL

-- Drop tables if they already exist
BEGIN
   EXECUTE IMMEDIATE 'DROP TABLE employees CASCADE CONSTRAINTS';
EXCEPTION
   WHEN OTHERS THEN
      IF SQLCODE != -942 THEN
         RAISE;
      END IF;
END;
/

BEGIN
   EXECUTE IMMEDIATE 'DROP TABLE dept CASCADE CONSTRAINTS';
EXCEPTION
   WHEN OTHERS THEN
      IF SQLCODE != -942 THEN
         RAISE;
      END IF;
END;
/

-- Create DEPT (Departments) Table
CREATE TABLE dept (
    dept_id     NUMBER PRIMARY KEY,
    dept_name   VARCHAR2(50) NOT NULL,
    location    VARCHAR2(50)
);

-- Create EMPLOYEES Table
CREATE TABLE employees (
    emp_id      NUMBER PRIMARY KEY,
    emp_name    VARCHAR2(50) NOT NULL,
    job_title   VARCHAR2(30),
    salary      NUMBER(10, 2),
    dept_id     NUMBER REFERENCES dept(dept_id)
);

-- Insert Sample Data into DEPT
INSERT INTO dept (dept_id, dept_name, location) VALUES (10, 'ENGINEERING', 'NEW YORK');
INSERT INTO dept (dept_id, dept_name, location) VALUES (20, 'MARKETING', 'SAN FRANCISCO');
INSERT INTO dept (dept_id, dept_name, location) VALUES (30, 'SALES', 'CHICAGO');

-- Insert Sample Data into EMPLOYEES
INSERT INTO employees (emp_id, emp_name, job_title, salary, dept_id) VALUES (101, 'ALICE SMITH', 'SOFTWARE ENGINEER', 95000.00, 10);
INSERT INTO employees (emp_id, emp_name, job_title, salary, dept_id) VALUES (102, 'BOB JOHNSON', 'DEVOPS ENGINEER', 88000.00, 10);
INSERT INTO employees (emp_id, emp_name, job_title, salary, dept_id) VALUES (103, 'CHARLIE DAVIS', 'MARKETING MANAGER', 75000.00, 20);
INSERT INTO employees (emp_id, emp_name, job_title, salary, dept_id) VALUES (104, 'DIANA PRINCE', 'SALES EXECUTIVE', 68000.00, 30);

COMMIT;
