import React, { useEffect, useMemo, useState } from 'react';
import { AlertCircle, ArrowRight, ArrowUpRight, Bot, CheckCircle2, Circle, Clock, ClipboardList, Copy, ExternalLink, GitBranch, Play, Search, ShieldAlert, ShieldCheck, Users } from 'lucide-react';
import { api } from './api';

const scenarios = [
  { id: 'success', title: 'Successful Payment Investigation', request: 'Investigate payment TXN1001', detail: 'Verify TXN1001 · expected demo record ₹500 SUCCESS', icon: Search, tone: 'teal' },
  { id: 'pending', title: 'Pending Payment Resolution', request: 'Resolve pending payment TXN1002', detail: 'Verify TXN1002 · expected demo record ₹250 PENDING · opens a ticket', icon: Clock, tone: 'blue' },
  { id: 'refund', title: 'Refund Request', request: 'I want a refund for transaction TXN1002', detail: 'Creates a human-review case · no refund is performed', icon: ShieldAlert, tone: 'amber' },
  { id: 'general', title: 'General AI Support', request: 'How can I understand the different payment statuses?', detail: 'Runs a normal support question through the configured AI workflow', icon: Bot, tone: 'purple' },
];
const agentNames = ['Payment Investigation Agent', 'Customer Support Agent', 'Resolution Coordinator Agent'];
const labelStatus = value => ({ pending: 'Pending', running: 'Running', completed: 'Completed', failed: 'Failed', requires_human_review: 'Requires Human Review' }[value] || 'Pending');
function Card({ children, className = '' }) { return <section className={`card ${className}`}>{children}</section>; }
function Tag({ children, type = '' }) { return <span className={`tag ${type}`}><i/>{children}</span>; }
function PageHead({ eyebrow, title, sub, action }) { return <div className="page-head"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{sub}</p></div>{action}</div>; }
function Empty({ label, sub }) { return <div className="empty"><div className="empty-icon"><GitBranch size={18}/></div><b>{label}</b><span>{sub}</span></div>; }

export default function AgentCommandCenter() {
  const [request, setRequest] = useState('');
  const [result, setResult] = useState(null);
  const [queue, setQueue] = useState([]);
  const [busy, setBusy] = useState(false);
  const [activeScenario, setActiveScenario] = useState(null);
  const [scenarioStates, setScenarioStates] = useState({});
  const [error, setError] = useState('');
  const [copyState, setCopyState] = useState('Copy Summary');
  const [copyError, setCopyError] = useState('');
  useEffect(() => { api('/agents/executions').then(setQueue).catch(() => {}); }, [result]);

  async function execute(customerRequest, scenarioId = null) {
    if (!customerRequest.trim() || busy) return;
    setBusy(true); setError(''); setCopyError(''); setCopyState('Copy Summary'); setActiveScenario(scenarioId);
    if (scenarioId) setScenarioStates(previous => ({ ...previous, [scenarioId]: 'running' }));
    try {
      const key = globalThis.crypto?.randomUUID?.() || `agent-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      const response = await api('/agents/execute', { method: 'POST', body: JSON.stringify({ request: customerRequest.trim(), client_request_id: key }) });
      setRequest(customerRequest);
      setResult(response);
      if (response.status === 'failed') setError(response.reply || 'The backend workflow failed.');
      if (scenarioId) setScenarioStates(previous => ({ ...previous, [scenarioId]: response.status }));
    } catch (e) {
      setError(e.message);
      if (scenarioId) setScenarioStates(previous => ({ ...previous, [scenarioId]: 'failed' }));
    } finally { setBusy(false); setActiveScenario(null); }
  }
  async function run(event) { event.preventDefault(); await execute(request); }
  const pending = queue.filter(item => item.resolution?.requires_human_review);
  const transaction = result?.investigation?.transaction;
  const ticket = result?.resolution?.ticket;
  const stepByAgent = useMemo(() => Object.fromEntries((result?.steps || []).map(step => [step.agent_name, step])), [result]);
  const agentsInvolved = (result?.steps || []).filter(step => agentNames.includes(step.agent_name)).map(step => step.agent_name);
  const outcome = result?.resolution?.summary || result?.reply || 'No outcome was returned.';
  const recommended = result ? (result.resolution?.requires_human_review
    ? 'A support operator should review the prepared case. No employee has been contacted.'
    : ticket ? 'Review the open support ticket and provide any required follow-up.'
      : transaction?.status === 'SUCCESS' ? 'No follow-up ticket was needed for this verified successful payment.'
        : transaction ? 'Ask the customer to confirm the reference or provide any additional context in support.'
          : 'Review the support response; request a transaction reference if payment-specific help is needed.') : '';
  const summaryText = result ? [
    `Customer request: ${result.request}`,
    `Transaction: ${transaction ? `${transaction.id} · ₹${Number(transaction.amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })} · ${transaction.status}` : 'No verified transaction reference'}`,
    `Agents involved: ${agentsInvolved.length ? agentsInvolved.join(', ') : 'None recorded'}`,
    `Ticket: ${ticket?.id || 'None created'}`,
    `Final outcome: ${outcome}`,
    `Recommended next step: ${recommended}`,
  ].join('\n') : '';
  async function copySummary() {
    try { await navigator.clipboard.writeText(summaryText); setCopyState('Copied'); setCopyError(''); }
    catch { setCopyError('Clipboard access is unavailable in this browser.'); }
  }

  return <div className="page agent-page">
    <PageHead eyebrow="AUTONOMOUS SUPPORT / LIVE EXECUTION" title="Agent Command Center" sub="Coordinate payment verification, customer explanations, and safe case routing." action={<div className="live-pill"><span/> Backend workflows</div>}/>
    <div className="agent-intro"><div><div className="eyebrow">START A WORKFLOW</div><h2>What should the agents resolve?</h2><p>Execution steps and outcomes below come directly from the backend.</p></div><form onSubmit={run}><textarea value={request} onChange={e => setRequest(e.target.value)} placeholder="Example: Check payment TXN1002" maxLength={2000}/><button className="button primary" disabled={!request.trim() || busy}><Play size={15}/>{busy && !activeScenario ? 'Running…' : 'Run agents'}</button></form>{error && <div className="agent-error"><AlertCircle size={15}/>{error}</div>}</div>

    <section className="scenario-section"><div className="scenario-heading"><div><div className="eyebrow">GUIDED DEMO</div><h2>Try Live Scenarios</h2><p>Each scenario submits a real request to the existing backend workflow.</p></div><span className="scenario-note"><ShieldCheck size={14}/> Synthetic records · no financial actions</span></div><div className="scenario-grid">{scenarios.map(scenario => { const Icon = scenario.icon; const state = scenarioStates[scenario.id]; return <article className={`scenario-card ${scenario.tone}`} key={scenario.id}><div className="scenario-icon"><Icon size={17}/></div><div className="scenario-title">{scenario.title}</div><p>{scenario.detail}</p><button type="button" className="scenario-run" disabled={busy} onClick={() => execute(scenario.request, scenario.id)}>{state === 'running' ? <><span className="scenario-spinner"/> Running…</> : state === 'requires_human_review' ? <><ShieldAlert size={14}/> Review prepared · run again</> : state === 'completed' ? <><CheckCircle2 size={14}/> Run again</> : state === 'failed' ? <><AlertCircle size={14}/> Retry scenario</> : <>Run scenario <ArrowRight size={14}/></>}</button>{state === 'failed' && activeScenario !== scenario.id && <small className="scenario-state error">Request failed. Check the error above and retry.</small>}{state === 'completed' && <small className="scenario-state success">Backend workflow completed.</small>}{state === 'requires_human_review' && <small className="scenario-state review">Human review case prepared. No refund was performed.</small>}</article>; })}</div></section>

    <div className="agent-cards"><Card><div className="agent-card-icon teal"><Search size={18}/></div><span className={`agent-live-status ${stepByAgent[agentNames[0]]?.status || 'pending'}`}><StatusIcon status={stepByAgent[agentNames[0]]?.status || 'pending'}/>{labelStatus(stepByAgent[agentNames[0]]?.status || 'pending')}</span><h3>Payment Investigation Agent</h3><p>{stepByAgent[agentNames[0]]?.output_summary || 'Verifies a supplied transaction reference against the database.'}</p></Card><Card><div className="agent-card-icon blue"><Bot size={18}/></div><span className={`agent-live-status ${stepByAgent[agentNames[1]]?.status || 'pending'}`}><StatusIcon status={stepByAgent[agentNames[1]]?.status || 'pending'}/>{labelStatus(stepByAgent[agentNames[1]]?.status || 'pending')}</span><h3>Customer Support Agent</h3><p>{stepByAgent[agentNames[1]]?.output_summary || 'Prepares a clear response using verified results where available.'}</p></Card><Card><div className="agent-card-icon amber"><ShieldAlert size={18}/></div><span className={`agent-live-status ${stepByAgent[agentNames[2]]?.status || 'pending'}`}><StatusIcon status={stepByAgent[agentNames[2]]?.status || 'pending'}/>{labelStatus(stepByAgent[agentNames[2]]?.status || 'pending')}</span><h3>Resolution Coordinator Agent</h3><p>{stepByAgent[agentNames[2]]?.output_summary || 'Chooses a safe follow-up, ticket, or human-review route.'}</p></Card></div>

    <div className="agent-columns"><Card><div className="card-head"><div><h3><GitBranch size={15}/> Execution timeline</h3><p>Recorded backend agent steps</p></div>{result && <Tag type={result.status === 'completed' ? 'success' : result.status === 'failed' ? 'failed' : 'pending'}>{labelStatus(result.status)}</Tag>}</div>{result ? <><div className="execution-id">Execution {result.execution_id}</div><div className="agent-flow-visual" aria-label="Agent collaboration flow">{agentNames.map((name, index) => { const step = stepByAgent[name]; const state = step?.status || 'pending'; return <React.Fragment key={name}><div className={`agent-flow-node ${state}`}><div className="agent-flow-node-status"><StatusIcon status={state}/><span>{labelStatus(state)}</span></div><b>{name}</b><small>{step?.action || 'Not routed for this request'}</small>{step?.output_summary && <p>{step.output_summary}</p>}</div>{index < agentNames.length - 1 && <div className={`agent-flow-link ${state === 'completed' || state === 'requires_human_review' ? 'complete' : ''}`}><ArrowRight size={15}/></div>}</React.Fragment>; })}</div><div className="timeline">{result.steps.map(step => <div className="timeline-step" key={step.step_id}><div className={`timeline-marker ${step.status}`}><StatusIcon status={step.status}/></div><div><b>{step.agent_name}</b><span>{step.action}</span><p>{step.output_summary}</p><small><Clock size={11}/>{new Date(step.timestamp).toLocaleTimeString()} · {labelStatus(step.status)}</small></div></div>)}</div></> : <Empty label="No execution yet" sub="Run a scenario or submit a request to see backend agent activity."/>}</Card>
      <div className="agent-side"><Card><div className="card-head"><div><h3>Collaboration flow</h3><p>Conditional routing based on the request</p></div></div>{['Customer request', 'Payment investigation', 'Customer support', 'Resolution coordinator', 'Final response'].map((step, i) => <div className="flow-row" key={step}><span>{i + 1}</span><b>{step}</b>{i < 4 && <i/>}</div>)}</Card><Card><div className="card-head"><div><h3>Human review queue</h3><p>{pending.length} prepared case{pending.length === 1 ? '' : 's'} · no employee contacted</p></div><Users size={16}/></div>{pending.length ? pending.map(item => <a className="queue-row" href="/tickets" key={item.execution_id}><ShieldAlert size={15}/><span><b>{item.resolution.ticket?.id || item.execution_id}</b><small>{item.request}</small></span><ArrowUpRight size={14}/></a>) : <Empty label="Queue is clear" sub="Sensitive requests appear here after an agent run."/>}</Card></div>
    </div>

    {result && <Card className="resolution-summary"><div className="resolution-summary-head"><div><div className="eyebrow">WORKFLOW RESULT</div><h2>Resolution Summary</h2></div><Tag type={result.status === 'completed' ? 'success' : result.status === 'failed' ? 'failed' : 'pending'}>{labelStatus(result.status)}</Tag></div><div className="resolution-summary-grid"><div className="summary-detail request-detail"><small>CUSTOMER REQUEST</small><p>{result.request}</p></div><div className="summary-detail"><small>TRANSACTION REFERENCE</small><b>{transaction?.id || result.investigation?.reference || 'Not provided'}</b></div><div className="summary-detail"><small>VERIFIED PAYMENT</small><b>{transaction ? `₹${Number(transaction.amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })} · ${transaction.status}` : 'No verified transaction'}</b></div><div className="summary-detail"><small>AGENTS INVOLVED</small><b>{agentsInvolved.length ? agentsInvolved.map(name => name.replace(' Agent', '')).join(' · ') : 'None recorded'}</b></div><div className="summary-detail"><small>TICKET</small><b>{ticket?.id || 'No ticket created'}</b></div><div className="summary-detail full"><small>FINAL OUTCOME</small><p>{outcome}</p></div><div className="summary-detail full next-step"><small>RECOMMENDED NEXT STEP</small><p>{recommended}</p></div></div><div className="resolution-actions"><button className="button secondary" onClick={copySummary}><Copy size={14}/>{copyState}</button>{ticket && <a className="button secondary" href={`/tickets?ticket_id=${encodeURIComponent(ticket.id)}`}><ClipboardList size={14}/>View Ticket<ExternalLink size={13}/></a>}<a className="button secondary" href="/logs"><ArrowUpRight size={14}/>View Agent Activity</a>{copyError && <small className="copy-error">{copyError}</small>}</div></Card>}

    <div className="data-disclaimer"><ShieldCheck size={15}/> Refunds, transfers, and payments are never executed by these agents.</div><footer className="footer"><span>© 2026 ResolveMate AI <i/> ByteForce</span><span><span className="footer-status"/> Systems operational <i/> Prototype v1.0.0</span></footer>
  </div>;
}

function StatusIcon({ status }) {
  if (status === 'completed') return <CheckCircle2 size={14}/>;
  if (status === 'failed') return <AlertCircle size={14}/>;
  if (status === 'requires_human_review') return <ShieldAlert size={14}/>;
  if (status === 'running') return <span className="status-running-dot"/>;
  return <Circle size={14}/>;
}
