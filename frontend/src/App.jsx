import React, { useState, useCallback } from 'react';
import {
  Database, Terminal, Sparkles, CheckCircle2, AlertTriangle,
  Play, RotateCcw, Copy, Check, Cpu, FileCode2, Info,
  Zap, ChevronDown, ChevronRight, BarChart2, XCircle,
  ArrowRight, Lightbulb, Clock, Table2, RefreshCw,
} from 'lucide-react';

// ── Constants ──────────────────────────────────────────────────────────────
const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const SAMPLE_DEBUG_SQL =
  'SELECT emp_nmae, dept_id\nFROM employees\nWHERE dept_id = 10;';

const SAMPLE_OPTIMIZE_SQL =
  'SELECT *\nFROM employees\nWHERE dept_id = 10\nORDER BY salary DESC;';

// Status → badge class + label
const STATUS_MAP = {
  SUCCESS:            { cls: 'badge-success', label: '✓ Success' },
  FAILED:             { cls: 'badge-error',   label: '✗ Failed' },
  DB_NOT_CONFIGURED:  { cls: 'badge-warning', label: '⚠ DB Not Configured' },
  DB_CONNECTION_ERROR:{ cls: 'badge-warning', label: '⚠ DB Unreachable' },
  LLM_KEY_MISSING:    { cls: 'badge-warning', label: '⚠ LLM Key Missing' },
  LLM_NOT_CONNECTED:  { cls: 'badge-info',    label: 'ℹ LLM Not Wired' },
  VALIDATION_ERROR:   { cls: 'badge-error',   label: '✗ Validation Error' },
};

// ── Helpers ────────────────────────────────────────────────────────────────

function CopyButton({ text, small = true }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(text).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      className={`btn btn-secondary${small ? ' btn-sm' : ''}`}
      onClick={handleCopy}
      title="Copy to clipboard"
    >
      {copied ? <Check size={13} /> : <Copy size={13} />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

function StatusBadge({ status }) {
  const info = STATUS_MAP[status] ?? { cls: 'badge-info', label: status };
  return <span className={`badge ${info.cls}`}>{info.label}</span>;
}

function ResultsTable({ columns, rows }) {
  if (!columns || columns.length === 0) {
    return <p className="table-empty">Query executed successfully with no result set.</p>;
  }
  return (
    <div className="table-wrapper">
      <table className="results-table">
        <thead>
          <tr>{columns.map(c => <th key={c}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.length === 0
            ? <tr><td colSpan={columns.length} className="table-empty">No rows returned.</td></tr>
            : rows.map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td key={j}>{cell === null ? <em className="text-dim">NULL</em> : String(cell)}</td>
                ))}
              </tr>
            ))
          }
        </tbody>
      </table>
    </div>
  );
}

function AttemptHistory({ history }) {
  const [openIdx, setOpenIdx] = useState(null);
  if (!history || history.length === 0) return null;
  return (
    <div>
      {history.map((item) => (
        <details key={item.attempt} className="history-item">
          <summary
            className="history-summary"
            onClick={(e) => { e.preventDefault(); setOpenIdx(openIdx === item.attempt ? null : item.attempt); }}
          >
            <span className="step-number">{item.attempt}</span>
            <span className="text-sm" style={{ flex: 1 }}>
              Attempt {item.attempt} — {item.error ? 'Failed' : 'Success'}
            </span>
            {item.error && <span className="badge badge-error" style={{ fontSize: '0.68rem' }}>Error</span>}
            {openIdx === item.attempt ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </summary>
          {openIdx === item.attempt && (
            <div className="history-body fade-in">
              <div>
                <div className="history-label">SQL Executed</div>
                <div className="code-block" style={{ maxHeight: 140, overflow: 'auto' }}>{item.sql}</div>
              </div>
              {item.error && (
                <div>
                 <div className="history-label">Database Error</div>
                  <div className="code-block error">{item.error}</div>
                </div>
              )}
              {item.corrected_sql && (
                <div>
                  <div className="history-label">LLM Proposed Correction</div>
                  <div className="code-block success">{item.corrected_sql}</div>
                </div>
              )}
              {item.explanation && (
                <div>
                  <div className="history-label">Explanation</div>
                  <p className="text-sm text-muted">{item.explanation}</p>
                </div>
              )}
            </div>
          )}
        </details>
      ))}
    </div>
  );
}

// ── Main App ───────────────────────────────────────────────────────────────

export default function App() {
  const [activeTab, setActiveTab] = useState('debug');
  const [sqlQuery, setSqlQuery] = useState(SAMPLE_DEBUG_SQL);
  const [loading, setLoading] = useState(false);
  const [debugResult, setDebugResult] = useState(null);
  const [optimizeResult, setOptimizeResult] = useState(null);
  const [networkError, setNetworkError] = useState(null);

  // Keep SQL in sync when switching tabs (load appropriate sample)
  const switchTab = (tab) => {
    setActiveTab(tab);
    setSqlQuery(tab === 'debug' ? SAMPLE_DEBUG_SQL : SAMPLE_OPTIMIZE_SQL);
    setDebugResult(null);
    setOptimizeResult(null);
    setNetworkError(null);
  };

  const handleReset = () => {
    setSqlQuery(activeTab === 'debug' ? SAMPLE_DEBUG_SQL : SAMPLE_OPTIMIZE_SQL);
    setDebugResult(null);
    setOptimizeResult(null);
    setNetworkError(null);
  };

  const callApi = useCallback(async (endpoint) => {
    if (!sqlQuery.trim()) return;
    setLoading(true);
    setNetworkError(null);
    setDebugResult(null);
    setOptimizeResult(null);

    try {
      const res = await fetch(`${API_BASE}/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sql_query: sqlQuery }),
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`HTTP ${res.status}: ${detail}`);
      }
      const data = await res.json();
      if (endpoint === 'debug') setDebugResult(data);
      else setOptimizeResult(data);
    } catch (err) {
      setNetworkError(err.message || 'Could not connect to backend.');
    } finally {
      setLoading(false);
    }
  }, [sqlQuery]);

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <header className="app-header">
        <div className="header-brand">
          <div className="header-icon"><Database size={22} /></div>
          <div>
            <h1 className="header-title">LLM-Based SQL Debugging Assistant</h1>
            <p className="header-subtitle">College Database Systems Project · SQLite + Gemini AI</p>
          </div>
        </div>
        <div className="header-badges">
          <span className="badge badge-primary"><Cpu size={12} /> FastAPI</span>
          <span className="badge badge-primary"><Database size={12} /> SQLite DB</span>
          <span className="badge badge-purple"><Sparkles size={12} /> Gemini AI</span>
        </div>
      </header>

      {/* ── Page Content ────────────────────────────────────────────────── */}
      <main className="main-container" style={{ flex: 1 }}>

        {/* Tabs */}
        <div style={{ marginBottom: '1.25rem' }}>
          <div className="tabs-container">
            <button
              className={`tab-btn${activeTab === 'debug' ? ' active' : ''}`}
              onClick={() => switchTab('debug')}
            >
              <Terminal size={16} /> Debug SQL
            </button>
            <button
              className={`tab-btn${activeTab === 'optimize' ? ' active' : ''}`}
              onClick={() => switchTab('optimize')}
            >
              <Zap size={16} /> Optimize SQL
            </button>
          </div>
        </div>

        {/* ── Layout grid ─────────────────────────────────────────────── */}
        <div className="layout-grid">

          {/* ╔═ Left column: Editor + Controls ══════════════════════════╗ */}
          <div className="panel-col">

            {/* SQL Editor Card */}
            <div className="glass-card">
              <div className="section-header">
                <div className="section-title">
                  <FileCode2 size={17} color="var(--primary)" />
                  {activeTab === 'debug' ? 'SQL Query to Debug' : 'SQL Query to Optimize'}
                </div>
                <button className="btn btn-secondary btn-sm" onClick={handleReset}>
                  <RefreshCw size={13} /> Reset
                </button>
              </div>
              <div className="code-editor-area">
                <textarea
                  className="sql-textarea"
                  value={sqlQuery}
                  onChange={e => setSqlQuery(e.target.value)}
                  placeholder="Type or paste your SQLite SQL query here…"
                  spellCheck={false}
                />
              </div>
              <div className="editor-footer">
                <span className="text-sm text-dim">SQLite Database · sqlite3</span>
                <div style={{ display: 'flex', gap: 8 }}>
                  {activeTab === 'debug' ? (
                    <button
                      className="btn btn-primary"
                      onClick={() => callApi('debug')}
                      disabled={loading || !sqlQuery.trim()}
                    >
                      {loading
                        ? <><div className="spinner" /> Debugging…</>
                        : <><Play size={15} /> Debug SQL</>
                      }
                    </button>
                  ) : (
                    <button
                      className="btn btn-optimize"
                      onClick={() => callApi('optimize')}
                      disabled={loading || !sqlQuery.trim()}
                    >
                      {loading
                        ? <><div className="spinner" /> Analyzing…</>
                        : <><Zap size={15} /> Optimize SQL</>
                      }
                    </button>
                  )}
                </div>
              </div>
            </div>

            {/* Network error alert */}
            {networkError && (
              <div className="alert error fade-in">
                <XCircle size={18} className="alert-icon" />
                <div className="alert-text">
                  <strong>Backend Connection Error</strong>
                  {networkError}<br />
                  <span className="text-xs">Make sure the FastAPI server is running at {API_BASE}</span>
                </div>
              </div>
            )}

            {/* Workflow info card */}
            <div className="glass-card p-4">
              <h4 className="section-title" style={{ marginBottom: '1rem' }}>
                <Info size={15} color="var(--primary)" />
                {activeTab === 'debug' ? 'Debug Workflow' : 'Optimization Workflow'}
              </h4>
              {activeTab === 'debug' ? (
                <div className="workflow-steps">
                  {[
                    'Execute SQL query against SQLite Database',
                    'Capture the SQLite error message',
                    'Retrieve schema metadata from SQLite',
                    'Send error + schema to Gemini AI for diagnosis',
                    'Execute corrected SQL and verify result',
                    'Repeat up to 3 attempts if needed',
                  ].map((step, i) => (
                    <div className="workflow-step" key={i}>
                      <div className="step-number">{i + 1}</div>
                      <span>{step}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="workflow-steps">
                  {[
                    'Validate query is a safe SELECT statement',
                    'Retrieve SQLite schema metadata',
                    'Obtain SQLite EXPLAIN QUERY PLAN (if DB available)',,
                    'Send query + schema + plan to Gemini AI',
                    'Validate proposed optimized query',
                    'Execute and compare both queries (if DB available)',
                  ].map((step, i) => (
                    <div className="workflow-step" key={i}>
                      <div className="step-number">{i + 1}</div>
                      <span>{step}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* ╔═ Right column: Results ════════════════════════════════════╗ */}
          <div className="panel-col">

            {/* ══ DEBUG RESULTS ══════════════════════════════════════════ */}
            {activeTab === 'debug' && (
              <>
                {/* Status banner */}
                <div className="glass-card">
                  <div className="status-banner">
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <Terminal size={18} color="var(--primary)" />
                      <span style={{ fontWeight: 600, fontSize: '0.95rem' }}>Validation Status</span>
                    </div>
                    {debugResult
                      ? <StatusBadge status={debugResult.status} />
                      : <span className="badge badge-info">Awaiting Input</span>
                    }
                  </div>
                  {debugResult && (
                    <div className="status-note p-4" style={{ paddingTop: 0 }}>
                      {debugResult.status === 'SUCCESS' && (
                        <div className="alert success" style={{ marginTop: 0 }}>
                          <CheckCircle2 size={16} className="alert-icon" />
                          <div className="alert-text">
                            Query executed successfully in {debugResult.attempts} attempt(s).
                          </div>
                        </div>
                      )}
                      {['DB_NOT_CONFIGURED', 'DB_CONNECTION_ERROR'].includes(debugResult.status) && (
                        <div className="alert warning" style={{ marginTop: 0 }}>
                          <AlertTriangle size={16} className="alert-icon" />
                          <div className="alert-text">{debugResult.explanation}</div>
                        </div>
                      )}
                      {['LLM_KEY_MISSING', 'LLM_NOT_CONNECTED'].includes(debugResult.status) && (
                        <div className="alert info" style={{ marginTop: 0 }}>
                          <Info size={16} className="alert-icon" />
                          <div className="alert-text">{debugResult.explanation}</div>
                        </div>
                      )}
                      {debugResult.status === 'FAILED' && (
                        <div className="alert error" style={{ marginTop: 0 }}>
                          <XCircle size={16} className="alert-icon" />
                          <div className="alert-text">{debugResult.explanation}</div>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Oracle Error */}
                <div className="glass-card">
                  <div className="section-header">
                    <div className="section-title">
                      <AlertTriangle size={16} color="var(--error)" /> Database Error
                    </div>
                  </div>
                  <div className="p-4">
                    {debugResult?.oracle_error
                      ? <div className="code-block error">{debugResult.oracle_error}</div>
                      : debugResult && !debugResult.oracle_error
                        ? <p className="text-sm" style={{ color: 'var(--success)' }}>No database errors captured.</p>
                        : <div className="code-block dim">-- SQLite error (e.g. no such column: emp_nmae) --</div>  
                    }
                  </div>
                </div>

                {/* AI Diagnosis */}
                <div className="glass-card">
                  <div className="section-header">
                    <div className="section-title">
                      <Sparkles size={16} color="var(--accent-purple)" /> AI Diagnosis
                    </div>
                  </div>
                  <div className="p-4">
                    {debugResult?.explanation && !['DB_NOT_CONFIGURED','DB_CONNECTION_ERROR','LLM_KEY_MISSING','LLM_NOT_CONNECTED','FAILED'].includes(debugResult.status)
                      ? <p className="text-sm" style={{ lineHeight: 1.7 }}>{debugResult.explanation}</p>
                      : <p className="text-sm text-dim">-- LLM explanation of the root cause and fix will appear here --</p>
                    }
                  </div>
                </div>

                {/* Corrected SQL */}
                <div className="glass-card">
                  <div className="section-header">
                    <div className="section-title">
                      <CheckCircle2 size={16} color="var(--success)" /> Corrected SQL
                    </div>
                    {debugResult?.verified_sql && debugResult.status === 'SUCCESS' && (
                      <CopyButton text={debugResult.verified_sql} />
                    )}
                  </div>
                  <div className="p-4">
                    {debugResult?.verified_sql && debugResult.status === 'SUCCESS'
                      ? <div className="code-block success">{debugResult.verified_sql}</div>
                      : <div className="code-block dim">-- Verified corrected SQL will appear here --</div>
                    }
                  </div>
                </div>

                {/* Query Results Table */}
                {debugResult?.execution_result?.success && (
                  <div className="glass-card fade-in">
                    <div className="section-header">
                      <div className="section-title">
                        <Table2 size={16} color="var(--primary)" /> Query Results
                      </div>
                      <span className="text-xs text-muted">
                        {debugResult.execution_result.rows?.length ?? 0} row(s)
                      </span>
                    </div>
                    <div className="p-4">
                      <ResultsTable
                        columns={debugResult.execution_result.columns}
                        rows={debugResult.execution_result.rows}
                      />
                    </div>
                  </div>
                )}

                {/* Attempt History */}
                {debugResult?.history && debugResult.history.length > 0 && (
                  <div className="glass-card fade-in">
                    <div className="section-header">
                      <div className="section-title">
                        <BarChart2 size={16} color="var(--primary)" /> Attempt History
                      </div>
                      <span className="badge badge-primary">{debugResult.history.length} attempt(s)</span>
                    </div>
                    <div className="p-4">
                      <AttemptHistory history={debugResult.history} />
                    </div>
                  </div>
                )}
              </>
            )}

            {/* ══ OPTIMIZE RESULTS ═══════════════════════════════════════ */}
            {activeTab === 'optimize' && (
              <>
                {/* Status banner */}
                <div className="glass-card">
                  <div className="status-banner">
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <Zap size={18} color="var(--accent)" />
                      <span style={{ fontWeight: 600, fontSize: '0.95rem' }}>Optimization Status</span>
                    </div>
                    {optimizeResult
                      ? <StatusBadge status={optimizeResult.status} />
                      : <span className="badge badge-info">Awaiting Input</span>
                    }
                  </div>
                  {optimizeResult && (
                    <div style={{ padding: '0 1.25rem 1rem' }}>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        {optimizeResult.db_available
                          ? <span className="badge badge-success"><Database size={12} /> Live DB Used</span>
                          : <span className="badge badge-warning"><Database size={12} /> No Live DB</span>
                        }
                        {optimizeResult.semantic_preserved === true && (
                          <span className="badge badge-success"><CheckCircle2 size={12} /> Semantics Preserved</span>
                        )}
                        {optimizeResult.semantic_preserved === false && (
                          <span className="badge badge-error"><AlertTriangle size={12} /> Semantics Changed</span>
                        )}
                      </div>
                    </div>
                  )}
                </div>

                {/* Error / info alerts */}
                {optimizeResult?.status === 'VALIDATION_ERROR' && (
                  <div className="alert error fade-in">
                    <XCircle size={18} className="alert-icon" />
                    <div className="alert-text">
                      <strong>Validation Error</strong>{optimizeResult.explanation}
                    </div>
                  </div>
                )}
                {optimizeResult?.status === 'LLM_KEY_MISSING' && (
                  <div className="alert warning fade-in">
                    <AlertTriangle size={18} className="alert-icon" />
                    <div className="alert-text">
                      <strong>LLM API Key Missing</strong>{optimizeResult.explanation}
                    </div>
                  </div>
                )}

                {/* AI Explanation */}
                {optimizeResult?.explanation && optimizeResult.status === 'SUCCESS' && (
                  <div className="glass-card fade-in">
                    <div className="section-header">
                      <div className="section-title">
                        <Sparkles size={16} color="var(--accent-purple)" /> AI Analysis
                      </div>
                    </div>
                    <div className="p-4">
                      <p className="text-sm" style={{ lineHeight: 1.75 }}>{optimizeResult.explanation}</p>
                    </div>
                  </div>
                )}

                {/* Query Comparison */}
                {optimizeResult?.status === 'SUCCESS' && (
                  <div className="glass-card fade-in">
                    <div className="section-header">
                      <div className="section-title">
                        <FileCode2 size={16} color="var(--primary)" /> Query Comparison
                      </div>
                    </div>
                    <div className="p-4">
                      <div className="compare-grid">
                        <div className="compare-panel">
                          <span className="compare-label original">Original</span>
                          <div className="code-block">{optimizeResult.original_sql}</div>
                          {optimizeResult.original_execution && (
                            <span className="timing-chip original">
                              <Clock size={11} style={{ marginRight: 4, verticalAlign: 'middle' }} />
                              {optimizeResult.original_execution.elapsed_ms} ms
                              · {optimizeResult.original_execution.row_count} rows
                            </span>
                          )}
                        </div>
                        <div className="compare-panel">
                          <span className="compare-label optimized">Optimized</span>
                          <div className="code-block" style={{ color: 'var(--accent)' }}>
                            {optimizeResult.optimized_sql}
                          </div>
                          {optimizeResult.optimized_execution && (
                            <span className="timing-chip optimized">
                              <Clock size={11} style={{ marginRight: 4, verticalAlign: 'middle' }} />
                              {optimizeResult.optimized_execution.elapsed_ms} ms
                              · {optimizeResult.optimized_execution.row_count} rows
                            </span>
                          )}
                          <CopyButton text={optimizeResult.optimized_sql} />
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Recommendations */}
                {optimizeResult?.recommendations && optimizeResult.recommendations.length > 0 && (
                  <div className="glass-card fade-in">
                    <div className="section-header">
                      <div className="section-title">
                        <Lightbulb size={16} color="var(--warning)" /> Recommendations
                      </div>
                      <span className="badge badge-warning">{optimizeResult.recommendations.length}</span>
                    </div>
                    <div className="p-4">
                      <div className="rec-list">
                        {optimizeResult.recommendations.map((rec, i) => (
                          <div className="rec-item" key={i}>
                            <ArrowRight size={15} className="rec-icon" />
                            <span>{rec}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {/* Execution Plan */}
                {optimizeResult?.original_plan && (
                  <div className="glass-card fade-in">
                    <div className="section-header">
                      <div className="section-title">
                        <BarChart2 size={16} color="var(--primary)" /> SQLite Query Plan
                      </div>
                    </div>
                    <div className="p-4">
                      <div className="code-block" style={{ fontSize: '0.78rem' }}>
                        {optimizeResult.original_plan}
                      </div>
                      {optimizeResult.plan_changes && (
                        <p className="text-sm text-muted" style={{ marginTop: '0.75rem' }}>
                          <strong style={{ color: 'var(--text-main)' }}>Expected plan changes: </strong>
                          {optimizeResult.plan_changes}
                        </p>
                      )}
                    </div>
                  </div>
                )}

                {/* Placeholder when no result yet */}
                {!optimizeResult && (
                  <div className="glass-card p-4" style={{ textAlign: 'center', color: 'var(--text-dim)' }}>
                    <Zap size={32} style={{ marginBottom: 10, color: 'var(--accent)' }} />
                    <p className="text-sm">Enter a SELECT query and click <strong>Optimize SQL</strong> to get AI-powered recommendations.</p>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
