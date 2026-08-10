import React, { useState } from 'react';
import './DatabaseTester.css';

const BASE = 'http://localhost:8000';

const api = {
  post: (path, body) => fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  }).then(r => r.json()),
  get: (path) => fetch(BASE + path).then(r => r.json()),
};

// ─── tiny helpers ────────────────────────────────────────────────────────────

function Badge({ type, label }) {
  return <span className={`db-badge db-badge-${type}`}>{label}</span>;
}

function Spinner() {
  return <span className="db-spinner" />;
}

function ResultPanel({ data }) {
  if (!data) return null;
  const good    = data.success === true;
  const blocked = !good && (data.blocked || (data.error || '').toLowerCase().includes('frozen') || data.is_safe === false);

  return (
    <div className={`db-result ${good ? 'good' : blocked ? 'blocked' : 'err'}`}>
      <div className="db-result-head">
        {good    && <Badge type="green"  label="SUCCESS" />}
        {blocked && <Badge type="red"    label="BLOCKED" />}
        {!good && !blocked && <Badge type="yellow" label="ERROR" />}
        {data.count !== undefined && <span className="db-result-count">{data.count} record{data.count !== 1 ? 's' : ''}</span>}
      </div>

      {/* pretty table for arrays */}
      {good && data.data && data.data.length > 0
        ? <DataTable rows={data.data} />
        : <pre className="db-json">{JSON.stringify(data, null, 2)}</pre>
      }
    </div>
  );
}

function DataTable({ rows }) {
  if (!rows || rows.length === 0) return null;
  const cols = Object.keys(rows[0]);
  return (
    <div className="db-table-wrap">
      <table className="db-table">
        <thead>
          <tr>{cols.map(c => <th key={c}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>{cols.map(c => <td key={c}>{String(r[c] ?? '')}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Action button with inline result ────────────────────────────────────────

function Action({ icon, label, desc, color, onClick, loading, disabled, result }) {
  return (
    <div className={`db-action db-action-${color}`}>
      <div className="db-action-row">
        <span className="db-action-icon">{icon}</span>
        <div className="db-action-info">
          <strong>{label}</strong>
          <span>{desc}</span>
        </div>
        <button
          className={`db-btn db-btn-${color}`}
          onClick={onClick}
          disabled={loading || disabled}
        >
          {loading ? <Spinner /> : 'Run'}
        </button>
      </div>
      <ResultPanel data={result} />
    </div>
  );
}

// ─── PostgreSQL panel ─────────────────────────────────────────────────────────

function PostgreSQLPanel({ frozen, onFreeze }) {
  const [busy, setBusy]   = useState({});
  const [res,  setRes]    = useState({});
  const [sql,  setSql]    = useState('SELECT * FROM employees');
  const [empId, setEmpId] = useState('');

  const run = async (key, fn) => {
    setBusy(b => ({ ...b, [key]: true }));
    try   { const data = await fn(); setRes(r => ({ ...r, [key]: data })); }
    catch (e) { setRes(r => ({ ...r, [key]: { success: false, error: e.message } })); }
    setBusy(b => ({ ...b, [key]: false }));
  };

  return (
    <div className="db-panel">
      <div className="db-panel-info">
        <div className="db-schema-pills">
          <span className="db-pill">employees</span>
          <span className="db-pill">payrolls</span>
          <span className="db-pill">departments</span>
        </div>
        <span className="db-panel-note">Relational · SQL · Tables</span>
      </div>

      {/* Read queries */}
      <div className="db-section-label">READ QUERIES</div>

      <Action icon="👥" label="Query Employees" color="blue"
        desc="SELECT * FROM employees"
        loading={busy.emp} result={res.emp}
        disabled={frozen}
        onClick={() => run('emp', () => api.post('/database/query/employees?db_type=postgresql'))} />

      <div className="db-inline-field">
        <label>Employee ID filter (optional)</label>
        <input placeholder="e.g. 1" value={empId} onChange={e => setEmpId(e.target.value)} />
      </div>
      <Action icon="💰" label="Query Payrolls" color="blue"
        desc={`SELECT * FROM payrolls${empId ? ` WHERE emp_id=${empId}` : ''}`}
        loading={busy.pay} result={res.pay}
        disabled={frozen}
        onClick={() => run('pay', () => api.post(`/database/query/payrolls?db_type=postgresql${empId ? `&emp_id=${empId}` : ''}`))} />

      <Action icon="🏢" label="Query Departments" color="blue"
        desc="SELECT * FROM departments"
        loading={busy.dept} result={res.dept}
        disabled={frozen}
        onClick={() => run('dept', () => api.post('/database/query/departments?db_type=postgresql'))} />

      {/* Custom SQL */}
      <div className="db-section-label">CUSTOM SQL QUERY</div>
      <div className="db-custom-box">
        <textarea
          className="db-sql-input"
          value={sql}
          onChange={e => setSql(e.target.value)}
          rows={3}
          placeholder="SELECT * FROM employees"
          spellCheck={false}
        />
        <button
          className="db-btn db-btn-blue"
          disabled={busy.sql || frozen}
          onClick={() => run('sql', () => api.post('/database/pg/execute', { query: sql }))}
        >
          {busy.sql ? <Spinner /> : 'Execute SQL'}
        </button>
        <ResultPanel data={res.sql} />
      </div>

      {/* Destructive tests */}
      <div className="db-section-label">SAFETY TESTS — DESTRUCTIVE QUERIES</div>

      <Action icon="🚫" label="Test DELETE" color="red"
        desc="DELETE FROM employees WHERE id = 1  →  must be blocked"
        loading={busy.del} result={res.del}
        onClick={() => run('del', () => api.post('/database/test-destructive/delete'))} />

      <Action icon="🚫" label="Test DROP" color="red"
        desc="DROP TABLE employees  →  must be blocked"
        loading={busy.drop} result={res.drop}
        onClick={() => run('drop', () => api.post('/database/test-destructive/drop'))} />

      <Action icon="🚫" label="Test UPDATE" color="red"
        desc="UPDATE employees SET salary=0  →  must be blocked"
        loading={busy.upd} result={res.upd}
        onClick={() => run('upd', () => api.post('/database/test-destructive/update'))} />

      {/* Report + Freeze */}
      <div className="db-section-label">AUDIT</div>

      <Action icon="📊" label="Safety Report" color="purple"
        desc="Full audit trail — all queries logged"
        loading={busy.rep} result={res.rep}
        onClick={() => run('rep', () => api.get('/database/safety-report'))} />

      <Action icon="🔒" label={frozen ? 'Database Frozen' : 'Freeze Database'} color="orange"
        desc={frozen ? 'Locked — reset agent to unlock' : 'Lock all operations permanently'}
        loading={busy.frz} result={res.frz}
        disabled={frozen}
        onClick={() => run('frz', async () => {
          const d = await api.post('/database/freeze');
          if (d.success) onFreeze();
          return d;
        })} />
    </div>
  );
}

// ─── MongoDB panel ────────────────────────────────────────────────────────────

function MongoDBPanel({ frozen, onFreeze }) {
  const [busy,   setBusy]   = useState({});
  const [res,    setRes]    = useState({});
  const [col,    setCol]    = useState('employees');
  const [filter, setFilter] = useState('{}');
  const [filterErr, setFilterErr] = useState('');

  const run = async (key, fn) => {
    setBusy(b => ({ ...b, [key]: true }));
    try   { const data = await fn(); setRes(r => ({ ...r, [key]: data })); }
    catch (e) { setRes(r => ({ ...r, [key]: { success: false, error: e.message } })); }
    setBusy(b => ({ ...b, [key]: false }));
  };

  const runMongoFind = () => {
    let parsed;
    try { parsed = JSON.parse(filter); setFilterErr(''); }
    catch { setFilterErr('Invalid JSON filter'); return; }
    run('find', () => api.post('/database/mongo/find', { collection: col, filter: parsed }));
  };

  return (
    <div className="db-panel">
      <div className="db-panel-info">
        <div className="db-schema-pills">
          <span className="db-pill db-pill-mongo">employees</span>
          <span className="db-pill db-pill-mongo">payrolls</span>
          <span className="db-pill db-pill-mongo">departments</span>
        </div>
        <span className="db-panel-note">Document store · BSON · Collections</span>
      </div>

      {/* Read queries */}
      <div className="db-section-label">READ QUERIES</div>

      <Action icon="👥" label="Find Employees" color="green"
        desc='db.employees.find({})'
        loading={busy.emp} result={res.emp}
        disabled={frozen}
        onClick={() => run('emp', () => api.post('/database/query/employees?db_type=mongodb'))} />

      <Action icon="💰" label="Find Payrolls" color="green"
        desc='db.payrolls.find({})'
        loading={busy.pay} result={res.pay}
        disabled={frozen}
        onClick={() => run('pay', () => api.post('/database/query/payrolls?db_type=mongodb'))} />

      <Action icon="🏢" label="Find Departments" color="green"
        desc='db.departments.find({})'
        loading={busy.dept} result={res.dept}
        disabled={frozen}
        onClick={() => run('dept', () => api.post('/database/query/departments?db_type=mongodb'))} />

      {/* Custom find */}
      <div className="db-section-label">CUSTOM FIND</div>
      <div className="db-custom-box">
        <div className="db-mongo-row">
          <select value={col} onChange={e => setCol(e.target.value)} className="db-mongo-select">
            <option value="employees">employees</option>
            <option value="payrolls">payrolls</option>
            <option value="departments">departments</option>
          </select>
          <span className="db-mongo-dot">.find(</span>
        </div>
        <textarea
          className="db-sql-input db-mongo-filter"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          rows={3}
          spellCheck={false}
          placeholder='{"status": "active"}'
        />
        <span className="db-mongo-dot">)</span>
        {filterErr && <div className="db-filter-err">{filterErr}</div>}
        <button
          className="db-btn db-btn-green"
          disabled={busy.find || frozen}
          onClick={runMongoFind}
        >
          {busy.find ? <Spinner /> : 'Execute Find'}
        </button>
        <ResultPanel data={res.find} />
      </div>

      {/* Destructive tests */}
      <div className="db-section-label">SAFETY TESTS — DESTRUCTIVE OPERATIONS</div>

      <Action icon="🚫" label="Test deleteOne" color="red"
        desc='db.employees.deleteOne(...)  →  must be blocked'
        loading={busy.del} result={res.del}
        onClick={() => run('del', () => api.post('/database/test-destructive/delete'))} />

      <Action icon="🚫" label="Test dropCollection" color="red"
        desc='db.employees.drop()  →  must be blocked'
        loading={busy.drop} result={res.drop}
        onClick={() => run('drop', () => api.post('/database/test-destructive/drop'))} />

      <Action icon="🚫" label="Test updateMany" color="red"
        desc='db.employees.updateMany(...)  →  must be blocked'
        loading={busy.upd} result={res.upd}
        onClick={() => run('upd', () => api.post('/database/test-destructive/update'))} />

      {/* Report + Freeze */}
      <div className="db-section-label">AUDIT</div>

      <Action icon="📊" label="Safety Report" color="purple"
        desc="Full audit trail — all queries logged"
        loading={busy.rep} result={res.rep}
        onClick={() => run('rep', () => api.get('/database/safety-report'))} />

      <Action icon="🔒" label={frozen ? 'Database Frozen' : 'Freeze Database'} color="orange"
        desc={frozen ? 'Locked — reset agent to unlock' : 'Lock all operations permanently'}
        loading={busy.frz} result={res.frz}
        disabled={frozen}
        onClick={() => run('frz', async () => {
          const d = await api.post('/database/freeze');
          if (d.success) onFreeze();
          return d;
        })} />
    </div>
  );
}

// ─── AI Agent panel ───────────────────────────────────────────────────────────

const SAMPLE_QUESTIONS = [
  'Show all employees with their salaries',
  'Who is in the Engineering department?',
  'What is Ahmed Khan\'s payroll history?',
  'List all departments with their budgets',
  'Which employees have active status?',
  'Show payroll details for emp_id 1',
];

function StepCard({ step, index }) {
  const blocked = step.blocked;
  const count   = step.result?.count;
  const phase   = step.tool === 'explore_schema' ? 1 : 2;

  return (
    <div className={`ag-step ${blocked ? 'ag-step-blocked' : 'ag-step-ok'}`}>
      <span className="ag-step-num">Step {index + 1}</span>
      <span className="ag-step-tool">{step.tool}</span>
      {step.args?.query && (
        <code className="ag-step-arg">{step.args.query}</code>
      )}
      {step.args?.collection && (
        <code className="ag-step-arg">{step.args.collection}.find({step.args.filter_json || '{}'})</code>
      )}
      <span className={`ag-step-badge ${blocked ? 'ag-badge-red' : 'ag-badge-green'}`}>
        {blocked ? 'BLOCKED' : count !== undefined ? `${count} records` : 'OK'}
      </span>
      {blocked && step.result?.reason && (
        <span className="ag-step-reason">{step.result.reason}</span>
      )}
    </div>
  );
}

function AgentPanel() {
  const [question, setQuestion] = useState('');
  const [loading,  setLoading]  = useState(false);
  const [result,   setResult]   = useState(null);
  const [error,    setError]    = useState('');

  const ask = async (q) => {
    const text = (q || question).trim();
    if (!text) return;
    setLoading(true);
    setResult(null);
    setError('');
    try {
      const data = await api.post('/database/agent/query', { question: text });
      setResult(data);
      if (!data.success && !data.answer) setError(data.error || 'Agent failed.');
    } catch (e) {
      setError(e.message);
    }
    setLoading(false);
  };

  // Find the step with the most rows for table display
  const bestData = result?.steps
    ?.filter(s => !s.blocked && s.result?.data?.length > 0)
    ?.sort((a, b) => (b.result?.count ?? 0) - (a.result?.count ?? 0))[0]
    ?.result?.data;

  return (
    <div className="ag-panel">
      {/* Sample questions */}
      <div className="ag-samples-label">SAMPLE QUESTIONS</div>
      <div className="ag-samples">
        {SAMPLE_QUESTIONS.map(q => (
          <button key={q} className="ag-chip" onClick={() => { setQuestion(q); ask(q); }}>
            {q}
          </button>
        ))}
      </div>

      {/* Input */}
      <div className="ag-input-row">
        <textarea
          className="ag-textarea"
          rows={3}
          placeholder="Ask anything about the database... e.g. 'Show me all Engineering employees with salaries'"
          value={question}
          onChange={e => setQuestion(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) ask(); }}
          disabled={loading}
          spellCheck={false}
        />
        <div className="ag-input-actions">
          <button className="ag-btn-ask" onClick={() => ask()} disabled={loading || !question.trim()}>
            {loading ? <Spinner /> : 'Ask Agent'}
          </button>
          {result && (
            <button className="ag-btn-clear" onClick={() => { setResult(null); setQuestion(''); setError(''); }}>
              New Question
            </button>
          )}
        </div>
      </div>
      <div className="ag-hint">Ctrl+Enter to send</div>

      {/* Loading state */}
      {loading && (
        <div className="ag-thinking">
          <Spinner /> Agent is thinking — exploring schema, writing queries...
        </div>
      )}

      {/* Error */}
      {error && <div className="ag-error">{error}</div>}

      {/* Result */}
      {result && (
        <>
          {/* Phase log */}
          <div className="ag-phase-log">
            <span className={`ag-phase-pill ${result.phase_log?.explored ? 'ok' : 'warn'}`}>
              Phase 1 {result.phase_log?.explored ? 'Complete' : 'Skipped'}
            </span>
            <span className="ag-phase-pill ok">
              {result.phase_log?.queries_run ?? 0} Queries Run
            </span>
            {result.phase_log?.blocked_attempts > 0 && (
              <span className="ag-phase-pill blocked">
                {result.phase_log.blocked_attempts} Blocked
              </span>
            )}
          </div>

          {/* Answer */}
          <div className={`ag-answer ${result.success ? 'ag-answer-ok' : 'ag-answer-err'}`}>
            <div className="ag-answer-label">{result.success ? 'Agent Answer' : 'Agent Response'}</div>
            <div className="ag-answer-text">{result.answer}</div>
          </div>

          {/* Data table if available */}
          {bestData && bestData.length > 0 && (
            <div className="ag-data-section">
              <div className="ag-answer-label">Data Retrieved</div>
              <DataTable rows={bestData} />
            </div>
          )}

          {/* Steps */}
          {result.steps?.length > 0 && (
            <div className="ag-steps-section">
              <div className="ag-answer-label">Agent Steps ({result.steps.length})</div>
              {result.steps.map((step, i) => (
                <StepCard key={i} step={step} index={i} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ─── Root ─────────────────────────────────────────────────────────────────────

export default function DatabaseTester() {
  const [db,     setDb]     = useState('postgresql'); // 'postgresql' | 'mongodb' | 'agent'
  const [frozen, setFrozen] = useState(false);
  const [resetting, setResetting] = useState(false);

  const reset = async () => {
    setResetting(true);
    await api.post('/database/reset');
    setFrozen(false);
    setResetting(false);
  };

  return (
    <div className="dt-root">
      {/* Header */}
      <div className="dt-header">
        <div className="dt-header-left">
          <h2>Database Agent — MCP Safety Testing</h2>
          <p>Read-only enforcement · Destructive query blocking · Audit trail</p>
        </div>
        <button className="dt-reset-top" onClick={reset} disabled={resetting}>
          {resetting ? <Spinner /> : '↺'} Reset Agent
        </button>
      </div>

      {/* DB selector */}
      <div className="dt-db-selector">
        <button
          className={`dt-db-btn ${db === 'postgresql' ? 'active-pg' : ''}`}
          onClick={() => setDb('postgresql')}
        >
          <span className="dt-db-icon">🐘</span>
          <span className="dt-db-label">PostgreSQL</span>
          <span className="dt-db-sub">Relational · SQL</span>
        </button>
        <button
          className={`dt-db-btn ${db === 'mongodb' ? 'active-mg' : ''}`}
          onClick={() => setDb('mongodb')}
        >
          <span className="dt-db-icon">🍃</span>
          <span className="dt-db-label">MongoDB</span>
          <span className="dt-db-sub">Document · NoSQL</span>
        </button>
        <button
          className={`dt-db-btn ${db === 'agent' ? 'active-ai' : ''}`}
          onClick={() => setDb('agent')}
        >
          <span className="dt-db-icon">🤖</span>
          <span className="dt-db-label">AI Agent</span>
          <span className="dt-db-sub">Natural Language</span>
        </button>
      </div>

      {frozen && db !== 'agent' && (
        <div className="dt-frozen-bar">
          🔒 Database is FROZEN — click Reset Agent to start fresh
        </div>
      )}

      {/* Panels */}
      {db === 'postgresql' && <PostgreSQLPanel frozen={frozen} onFreeze={() => setFrozen(true)} />}
      {db === 'mongodb'    && <MongoDBPanel    frozen={frozen} onFreeze={() => setFrozen(true)} />}
      {db === 'agent'      && <AgentPanel />}
    </div>
  );
}
