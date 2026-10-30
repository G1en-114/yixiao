// YiXiao Hospital Agent · clinical console (vanilla JS, live EventSource stream)
'use strict';

const $ = (id) => document.getElementById(id);
const AGENTS = [
  { k: 'triage', n: 'Triage', sub: 'urgency · department', ab: 'TR' },
  { k: 'interview', n: 'Interview', sub: '2–3 questions a round', ab: 'IN' },
  { k: 'differential', n: 'Differential', sub: 'ranked diagnoses', ab: 'DX' },
  { k: 'examination', n: 'Exams', sub: 'required · avoid', ab: 'EX' },
  { k: 'specialist', n: 'Specialists', sub: 'A ∥ B in parallel', ab: 'SP' },
  { k: 'attending', n: 'Attending', sub: 'management plan', ab: 'AT' },
  { k: 'safety', n: 'Safety', sub: 'veto power', ab: 'SG' },
  { k: 'audit', n: 'Audit', sub: 'full replay', ab: 'AU' },
];
const AGENT_IDX = Object.fromEntries(AGENTS.map((a, i) => [a.k, i]));
const NAME = Object.fromEntries(AGENTS.map((a) => [a.k, a.n]));
NAME.system = 'System'; NAME.specialist_A = 'Specialist A'; NAME.specialist_B = 'Specialist B';

let currentCase = null, es = null, seenSeq = -1;
let relay = { idx: -1, working: new Set(), rejected: false, final: false, events: 0 };
const seenBlocks = new Set();

// ---------- boot ----------
buildRing();
buildRail();
(async function boot() {
  try { showApp(await get('/api/me')); } catch (e) { $('login-view').classList.remove('hidden'); }
})();

async function get(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.status);
  return r.json();
}
async function post(url, body) {
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.status);
  return data;
}

// ---------- sign-in ----------
$('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  $('login-error').textContent = '';
  try {
    await post('/login', { username: $('login-user').value.trim(), password: $('login-pass').value });
    showApp(await get('/api/me'));
  } catch (err) { $('login-error').textContent = 'Sign-in failed: ' + err.message; }
});
$('btn-logout').addEventListener('click', async () => { await post('/logout'); location.href = '/'; });

function showApp(me) {
  $('login-view').classList.add('hidden');
  $('app-view').classList.remove('hidden');
  $('st-model').textContent = me.model || '—';
  $('kb-stats').textContent = `${me.knowledge.departments} departments · ${me.knowledge.skills} Skills · ${me.knowledge.exams} exams`;
  refreshCases();
  setInterval(refreshCases, 5000);
}

// animated relay ring on the sign-in page
function buildRing() {
  const svg = $('ring'); if (!svg) return;
  const cx = 210, cy = 210, R = 160;
  let html = `<circle class="ring-track" cx="${cx}" cy="${cy}" r="${R}"/>`;
  AGENTS.forEach((a, i) => {
    const ang = -Math.PI / 2 + i * Math.PI / 4, x = cx + R * Math.cos(ang), y = cy + R * Math.sin(ang);
    html += `<g class="ring-node${a.k === 'safety' ? ' veto' : ''}" id="rn${i}"><circle cx="${x}" cy="${y}" r="22"/>` +
            `<text x="${x}" y="${y + 4}">${a.ab}</text><text x="${x}" y="${y + (y > cy ? 42 : -32)}">${a.n}</text></g>`;
  });
  html += `<circle class="ring-pulse" id="ring-pulse" r="6"/>`;
  svg.innerHTML = html;
  const t0 = performance.now();
  (function tick(now) {
    const p = ((now - t0) / 1000 / 8) % 1, ang = -Math.PI / 2 + p * Math.PI * 2;
    const dot = $('ring-pulse'); if (!dot) return;
    dot.setAttribute('cx', cx + R * Math.cos(ang)); dot.setAttribute('cy', cy + R * Math.sin(ang));
    const lit = Math.floor(p * 8 + 0.08) % 8;
    AGENTS.forEach((_, i) => $('rn' + i).classList.toggle('on', i === lit));
    if (!$('login-view').classList.contains('hidden')) requestAnimationFrame(tick);
  })(t0);
}

function buildRail() {
  $('stage-rail').innerHTML = AGENTS.map((a, i) =>
    `<div class="relay-node" data-s="${a.k}"><span class="relay-dot">${i + 1}</span><div class="nm">${a.n}</div><div class="sub">${a.sub}</div></div>`).join('');
}

// ---------- cases ----------
$('btn-create').addEventListener('click', async () => {
  const complaint = $('in-complaint').value.trim();
  if (!complaint) { $('in-complaint').focus(); return; }
  const btn = $('btn-create'); btn.disabled = true;
  try {
    const { case_id } = await post('/api/cases', {
      chief_complaint: complaint,
      age: Number($('in-age').value) || null,
      sex: $('in-sex').value,
      duration: $('in-duration').value.trim(),
      symptoms: $('in-symptoms').value.split(',').map((s) => s.trim()).filter(Boolean),
      past_history: $('in-history').value.trim(),
      allergies: $('in-allergies').value.trim(),
      medications: $('in-meds').value.trim(),
    });
    $('in-complaint').value = '';
    openCase(case_id);
    refreshCases();
  } catch (err) { alert('Could not create the case: ' + err.message); }
  btn.disabled = false;
});

async function refreshCases() {
  try {
    const { cases } = await get('/api/cases');
    const ul = $('case-list');
    if (!cases.length) { ul.innerHTML = '<li class="empty">No cases yet</li>'; return; }
    ul.innerHTML = '';
    for (const c of cases) {
      const li = document.createElement('li');
      if (c.id === currentCase) li.className = 'active';
      const d = new Date(c.created_at * 1000);
      li.innerHTML = `<b>${esc(c.chief_complaint)}</b><span>${d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })} · ` +
        (c.status === 'final' ? '<span class="ok">report ready</span>' : 'in progress') + '</span>';
      li.onclick = () => openCase(c.id);
      ul.appendChild(li);
    }
  } catch (e) { /* signed out */ }
}

async function openCase(caseId) {
  currentCase = caseId; seenSeq = -1;
  relay = { idx: -1, working: new Set(), rejected: false, final: false, events: 0 };
  seenBlocks.clear();
  $('timeline').innerHTML = '';
  $('canvas').innerHTML = '';
  $('audit-count').textContent = '0 events';
  if (es) es.close();
  es = new EventSource(`/api/cases/${caseId}/events`);
  es.addEventListener('agent', (e) => {
    const ev = JSON.parse(e.data);
    if (ev.seq > seenSeq) { seenSeq = ev.seq; onEvent(ev); }
  });
  await renderView();
  refreshCases();
}

// ---------- event stream ----------
const TYPE = { case_created: 'case created', agent_start: 'started', agent_done: 'done', handoff: 'handoff',
  validate_retry: 'output re-validated', await_user: 'waiting for input', answers_received: 'answers submitted',
  exam_results_received: 'exam results entered', avoid_filtered: 'avoid filter', exam_filtered: 'catalog filter', essential_added: 'essential exams added',
  revision: 'attending revision', case_final: 'report delivered', error: 'error', agent_retry: 'retry' };
let renderTimer = null;

function onEvent(ev) {
  const base = ev.agent.startsWith('specialist') ? 'specialist' : ev.agent;
  if (ev.type === 'agent_start' && base in AGENT_IDX) {
    relay.working.add(base);
    relay.idx = AGENT_IDX[base];
    if (base === 'attending') relay.rejected = relay.rejected && true;
  }
  if (ev.type === 'agent_done' && base in AGENT_IDX) {
    relay.working.delete(base);
    if (base === 'safety') relay.rejected = (ev.payload.result || {}).status === 'rejected';
  }
  if (ev.type === 'agent_start' && base === 'safety') relay.rejected = false;
  if (ev.type === 'case_final') { relay.final = true; relay.working.clear(); }
  if (ev.type === 'error') relay.working.clear();
  relay.events += 1;
  addTimeline(ev);
  paintRail();
  clearTimeout(renderTimer);
  renderTimer = setTimeout(renderView, 120);
}

function addTimeline(ev) {
  const tl = $('timeline');
  if (tl.querySelector('.empty')) tl.innerHTML = '';
  const base = ev.agent.startsWith('specialist') ? 'specialist' : ev.agent;
  const row = document.createElement('div');
  const rejected = ev.type === 'handoff' && ev.agent === 'safety';
  row.className = `ev ev-${ev.type} new` + (rejected ? ' reject' : '') + (ev.type === 'case_final' ? ' final' : '');
  row.style.setProperty('--c', `var(--c-${base in AGENT_IDX ? base : 'system'})`);
  const t = new Date(ev.ts * 1000).toLocaleTimeString('en-GB', { hour12: false });
  row.innerHTML = `<span class="t">${t}</span><span class="d"></span>` +
    `<span class="txt"><b>${esc(NAME[ev.agent] || ev.agent)}</b> <span>${esc(eventText(ev))}</span></span>`;
  row.title = JSON.stringify(ev.payload, null, 1).slice(0, 2000);
  tl.appendChild(row);
  tl.scrollTop = tl.scrollHeight;
  $('audit-count').textContent = `${relay.events} events`;
  $('st-events').textContent = relay.events;
}

function eventText(ev) {
  if (ev.type === 'agent_start') return 'started';
  if (ev.type === 'agent_done') return `done · ${(ev.payload.result || {}).status || 'ok'}`;
  if (ev.type === 'handoff') { const h = ev.payload.handoff || {}; return `→ ${NAME[h.to_agent] || h.to_agent}: ${h.task}`; }
  return ev.summary || TYPE[ev.type] || ev.type;
}

function paintRail() {
  document.querySelectorAll('#stage-rail .relay-node').forEach((node, i) => {
    const k = AGENTS[i].k;
    node.classList.remove('active', 'done', 'reject', 'working');
    if (relay.final || i < relay.idx) node.classList.add('done');
    else if (i === relay.idx) { node.classList.add('active'); if (relay.working.has(k)) node.classList.add('working'); }
    if (k === 'safety' && relay.rejected && !relay.final) { node.classList.remove('done', 'active'); node.classList.add('reject'); }
  });
}

// ---------- render ----------
async function renderView() {
  if (!currentCase) return;
  let v;
  try { v = await get(`/api/cases/${currentCase}`); } catch (e) { return; }
  if (!v || !v.stage) return;
  if (v.stats) {
    $('st-calls').textContent = v.stats.model_calls || 0;
    $('st-tokens').textContent = ((v.stats.prompt_tokens || 0) + (v.stats.completion_tokens || 0)).toLocaleString('en-US');
  }
  renderStatus(v);
  renderCanvas(v);
  renderGate(v);
}

function renderStatus(v) {
  const el = document.querySelector('.relay-status');
  el.classList.remove('live', 'wait', 'done');
  const working = [...relay.working];
  let html;
  if (v.error) html = '<b>Pipeline error</b> — shown as-is, never faked';
  else if (v.stage === 'final') { el.classList.add('done'); html = '<b>Report delivered</b> · verifiable and replayable'; }
  else if (v.phase === 'await_answers') { el.classList.add('wait'); html = `<b>Waiting for the patient</b> · interview round ${v.pending_round}`; }
  else if (v.phase === 'await_exams') { el.classList.add('wait'); html = '<b>Waiting for exam results</b> · entered by a person, never invented'; }
  else if (working.length) {
    el.classList.add('live');
    html = working.includes('specialist') ? '<b>Two specialists</b> consulting in parallel'
      : `<b>${NAME[working[working.length - 1]]} agent</b> is working`;
  } else { el.classList.add('live'); html = '<b>Relay running</b>'; }
  $('stage-label').innerHTML = html;
}

function block(key, agent, title, who, body, right = '') {
  const isNew = !seenBlocks.has(key);
  seenBlocks.add(key);
  const a = AGENTS.find((x) => x.k === agent);
  return `<section class="block${isNew ? ' enter' : ''}" data-key="${key}" style="--c: var(--c-${agent})">
    <span class="avatar">${a ? a.ab : 'PT'}</span>
    <div class="block-head"><h4>${title}</h4><span class="who">${who}</span><span class="right">${right}</span></div>
    <div class="block-body">${body}</div></section>`;
}

function renderCanvas(v) {
  const canvas = $('canvas');
  const keep = {};
  canvas.querySelectorAll('textarea[data-key]').forEach((ta) => { keep[ta.dataset.key] = ta.value; });
  const focused = document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.key : null;
  const before = seenBlocks.size;
  const out = [];

  // intake
  out.push(block('intake', 'system', 'Case opened', 'chief complaint', `<div class="panel">
    <div style="font:600 16px var(--display)">“${esc(v.chief_complaint)}”</div>
    <div class="chips" style="margin-top:10px">
      <span class="chip">${esc(v.sex || '—')}, ${esc(v.age ?? '—')} y</span><span class="chip">${esc(v.duration || '—')}</span>
      ${(v.symptoms || []).map((s) => `<span class="chip">${esc(s)}</span>`).join('')}
      <span class="chip">History: ${esc(v.past_history || 'none')}</span>
      <span class="chip">Allergies: ${esc(v.allergies || 'none')}</span>
      <span class="chip">Meds: ${esc(v.medications || 'none')}</span>
    </div></div>`));

  // triage
  const tr = v.triage || {};
  if (tr.urgency) {
    const uc = { emergency: 'red', high: 'red', medium: 'amber', low: 'green' }[tr.urgency] || 'amber';
    out.push(block('triage', 'triage', 'Triage', 'TriageAgent', `<div class="panel">
      <dl class="kv"><dt>Urgency</dt><dd><span class="chip ${uc}">${esc(tr.urgency)}</span></dd>
      <dt>Departments</dt><dd class="chips">${(tr.candidate_departments || []).map((d) => `<span class="chip accent">${esc(d)}</span>`).join('')}</dd>
      <dt>Red flags</dt><dd class="chips">${(tr.red_flags || []).map((d) => `<span class="chip red">${esc(d)}</span>`).join('') || '<span class="muted">none</span>'}</dd>
      <dt>Next step</dt><dd>${esc(tr.next_step || '')}</dd></dl>
      <p class="reason">${esc(tr.triage_reasoning || '')}</p></div>`));
  }

  // interview
  const rounds = v.interview_rounds || [];
  if (rounds.length) {
    let body = '';
    rounds.forEach((r) => {
      const pending = v.phase === 'await_answers' && v.pending_round === r.round;
      const asked = pending || r.questions.some((q) => r.answers && r.answers[q.id]);
      if (!r.questions.length || !asked) {
        body += `<div class="round-label">ROUND ${r.round}</div><div class="stop-note">✓ The picture is complete — no further questions needed.</div>`;
        return;
      }
      body += `<div class="round-label">ROUND ${r.round} · INFORMATION-GAP QUESTIONS</div>`;
      r.questions.forEach((q) => {
        const ans = r.answers && r.answers[q.id];
        body += `<div class="msg q"><div class="bubble">${esc(q.question)}</div>${q.why ? `<div class="why">${esc(q.why)}</div>` : ''}</div>`;
        if (ans) body += `<div class="msg a"><span class="who">Patient</span><div class="bubble">${esc(ans)}</div></div>`;
        else if (pending) {
          const key = 'ans-' + q.id;
          body += `<div class="msg a"><span class="who">Patient</span><textarea rows="2" data-qid="${esc(q.id)}" data-key="${key}" placeholder="Type the patient's answer…">${esc(keep[key] || '')}</textarea></div>`;
        }
      });
      if (pending) body += `<div style="text-align:right"><button class="btn primary sm" id="btn-answers">Send answers</button></div>`;
    });
    const last = rounds[rounds.length - 1];
    const doneInterview = (v.differential || {}).differential_diagnoses;
    if (doneInterview && last.questions.length) body += `<div class="stop-note" style="margin-top:6px">✓ Enough information — the interview stopped after ${rounds.length} rounds.</div>`;
    out.push(block('interview', 'interview', 'History taking', 'InterviewAgent', body, `<span class="chip">${rounds.length} round${rounds.length > 1 ? 's' : ''}</span>`));
  }

  // differential
  const dd = (v.differential || {}).differential_diagnoses || [];
  if (dd.length) {
    const cc = { high: 'red', medium: 'amber', low: '' };
    out.push(block('differential', 'differential', 'Differential diagnosis', 'DifferentialAgent', `<div class="panel">` +
      dd.map((d) => `<div style="padding:6px 0;border-top:1px solid var(--line)">
        <div style="display:flex;gap:8px;align-items:center"><b>${esc(d.disease)}</b><span class="chip ${cc[d.confidence] || ''}">${esc(d.confidence || '')}</span>
        <span class="muted small" style="margin-left:auto">${esc(d.department || '')}</span></div>
        <div class="small muted" style="margin-top:2px">${(d.supporting_evidence || []).slice(0, 3).map(esc).join(' · ')}</div></div>`).join('')
        .replace('border-top:1px solid var(--line)', 'border-top:0') + `</div>`));
  }

  // exams
  const plan = v.exam_plan || [];
  if (plan.length) {
    const pending = v.phase === 'await_exams';
    let rows = plan.map((p) => {
      const res = v.exam_inputs && v.exam_inputs[p.exam];
      const key = 'exam-' + p.exam;
      const right = res ? `<div class="res">${esc(res)}</div>`
        : pending ? `<textarea rows="1" data-exam="${esc(p.exam)}" data-key="${esc(key)}" placeholder="Enter the result…">${esc(keep[key] || '')}</textarea>`
        : '<div class="res none">waiting…</div>';
      return `<div class="exam-row"><div><div class="nm">${esc(p.exam)}</div>
        <div class="why"><span class="chip ${p.priority === 'essential' ? 'accent' : ''}" style="padding:1px 8px">${p.priority === 'essential' ? 'essential' : 'conditional'}</span> ${esc(p.reason || '')}</div></div>${right}</div>`;
    }).join('');
    rows += `<div class="note">ⓘ Results are entered by a person. The system never invents exam data.</div>`;
    if (pending) rows += `<div style="text-align:right;margin-top:8px"><button class="btn primary sm" id="btn-exams">Submit results · start the specialist consult</button></div>`;
    out.push(block('exams', 'examination', 'Exam plan', 'ExaminationAgent', `<div class="panel">${rows}</div>`,
      `<span class="chip">${plan.length} exams · avoid list enforced</span>`));
  }

  // specialists
  const sp = v.specialists || {};
  const consulting = relay.working.has('specialist') || Object.keys(sp).length;
  if (consulting) {
    const lane = (L) => {
      const o = sp[L];
      if (!o) return `<div class="lane-card"><div class="lane-head"><span class="chip">Lane ${L}</span></div><div class="waiting"><span class="spinner"></span>consulting…</div></div>`;
      return `<div class="lane-card"><div class="lane-head"><span class="chip accent">Lane ${L}</span><b>${esc(o.department)}</b></div>
        <div class="op">${esc(o.primary_opinion || '')}</div>
        <div class="chips">${(o.likely_diseases || []).slice(0, 3).map((d) => `<span class="chip">${esc(d)}</span>`).join('')}</div></div>`;
    };
    out.push(block('specialists', 'specialist', 'Specialist consult', 'two lanes in parallel', `<div class="lanes">${lane('A')}${lane('B')}</div>`));
  }

  // attending plans and safety reviews, interleaved: plan 1 -> review 1 -> revised plan -> review 2
  const att = v.attending || {};
  const plans = (v.attending_history || []).length ? v.attending_history
    : (att.final_assessment || (att.diagnosis_candidates || []).length) ? [att] : [];
  const reviews = (v.safety && v.safety.reviews) || [];
  plans.forEach((p, i) => {
    const rev = p.revision_no ? `<span class="chip amber">revision ${p.revision_no}</span>` : '';
    const isLast = i === plans.length - 1;
    out.push(block('attending-' + i, 'attending', p.revision_no ? 'Revised plan' : 'Attending plan', 'AttendingAgent', `<div class="panel">
      <div class="sec-title">Working diagnosis</div><div class="dx">${(p.diagnosis_candidates || []).map((d) => `<span>${esc(d)}</span>`).join('')}</div>
      <div class="sec-title">Assessment</div><div style="font-size:13.5px">${esc(p.final_assessment || '')}</div>
      <div class="sec-title">Management plan</div><ul class="list accent">${(p.treatment_plan || []).map((x) => `<li>${hiNitrate(esc(x))}</li>`).join('')}</ul>
      ${(p.conflicts || []).length && !p.revision_no ? `<div class="sec-title">Conflicts resolved</div><ul class="list amber">${p.conflicts.slice(0, 3).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
      ${isLast && p.revision_no && (v.safety_preconditions || []).length ? `<div class="precondition"><b>Precondition from the safety review:</b> ${v.safety_preconditions.map(reason).join('<br>')}</div>` : ''}
    </div>`, rev));
    if (reviews[i]) out.push(reviewBlock(reviews[i]));
  });

  // report
  if (v.stage === 'final' && v.final) out.push(block('report', 'audit', 'Clinical report', 'AuditAgent', reportHtml(v.final)));

  if (v.error) out.push(`<section class="block"><span class="avatar" style="--c:var(--red)">!</span><div class="block-head"><h4>Pipeline error</h4></div>
    <div class="block-body"><div class="error-box">${esc(v.error)}<div class="small" style="margin-top:6px">Shown as-is. The system never fakes a result.</div></div></div></section>`);

  // live "thinking" line
  const working = [...relay.working].filter((k) => k !== 'specialist' || !Object.keys(sp).length);
  if (working.length && v.stage !== 'final' && !v.error) {
    const k = working[working.length - 1];
    out.push(`<div class="thinking"><span class="spinner"></span><span><b>${NAME[k]} agent</b> is working…</span></div>`);
  }

  canvas.innerHTML = out.join('');
  if (focused) { const el = canvas.querySelector(`[data-key="${CSS.escape(focused)}"]`); if (el) el.focus(); }
  const ba = $('btn-answers'); if (ba) ba.onclick = submitAnswers;
  const be = $('btn-exams'); if (be) be.onclick = submitExams;
  if (seenBlocks.size > before || working.length) canvas.scrollTop = canvas.scrollHeight;
}

function reviewBlock(r) {
  const ok = r.approved;
  return block('review-' + r.round, 'safety', ok ? `Safety review · round ${r.round} · approved` : `Safety review · round ${r.round} · REJECTED`,
    'SafetyAgent', `<div class="panel" style="border-color:${ok ? 'rgba(52,211,153,.4)' : 'rgba(255,90,110,.5)'}">
    ${ok ? `<div style="color:var(--green);font-weight:600">✓ No violations. The plan may be delivered.</div>${r.patient_facing_warning ? `<p class="reason">${esc(r.patient_facing_warning)}</p>` : ''}`
      : `<ul class="list">${(r.rejection_reasons || []).map((x) => `<li style="color:#ffb3bd">${reason(x)}</li>`).join('')}</ul>
         ${r.required_revision ? `<div class="sec-title" style="color:var(--amber)">Required revision</div><div style="font-size:13px;color:#ffd48a">${esc(r.required_revision)}</div>` : ''}`}
  </div>`, `<span class="chip ${ok ? 'green' : 'red'}">${ok ? 'approved' : 'veto'}</span>`);
}

function reportHtml(f) {
  const s = f.stats || {};
  return `<div class="panel report">
    <div class="report-head"><span class="chip green">final</span><h5>${esc(f.title)}</h5></div>
    <div class="sec-title">Working diagnosis</div><div class="dx">${(f.attending.diagnosis_candidates || []).map((d) => `<span>${esc(d)}</span>`).join('')}</div>
    <div class="sec-title">Basis</div><ul class="list">${(f.attending.consensus || []).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
    <div class="sec-title">Management plan</div><ul class="list accent">${(f.attending.treatment_plan || []).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
    <div class="sec-title">Exams and results</div><ul class="list">${f.exams.map((e) => `<li>${esc(e.exam)}: <span class="muted">${esc(e.result || 'not provided')}</span></li>`).join('')}</ul>
    <div class="sec-title">Safety review</div><ul class="list"><li>${f.safety.rounds} round(s) · ${f.safety.approved ? 'approved' : 'not fully approved (conservative fallback)'}</li>
      ${(f.safety.preconditions || []).map((x) => `<li>Precondition: ${reason(x)}</li>`).join('')}</ul>
    ${(f.safety.warning || []).map((w) => `<div class="warn">⚠ ${esc(w)}</div>`).join('')}
    <div class="stat-row"><div><b>${s.events}</b><span>events</span></div><div><b>${s.model_calls}</b><span>model calls</span></div>
      <div><b>${((s.prompt_tokens || 0) + (s.completion_tokens || 0)).toLocaleString('en-US')}</b><span>tokens</span></div>
      <div><b>${f.interview_rounds}</b><span>interview rounds</span></div><div><b>${f.safety.rounds}</b><span>safety reviews</span></div></div>
    <div class="disc">${esc(f.disclaimer)}</div></div>`;
}

function renderGate(v) {
  const badge = $('safety-badge'), list = $('safety-list');
  const reviews = (v.safety && v.safety.reviews) || [];
  const reviewing = relay.working.has('safety');
  if (reviewing) { badge.className = 'gate-badge reviewing'; badge.innerHTML = '<span class="dot"></span><b>Reviewing</b><i>rule engine + model check</i>'; }
  else if (!reviews.length) { badge.className = 'gate-badge idle'; badge.innerHTML = '<span class="dot"></span><b>Standby</b><i>waiting for a plan</i>'; }
  else {
    const last = reviews[reviews.length - 1];
    badge.className = 'gate-badge ' + (last.approved ? 'approved' : 'rejected');
    badge.innerHTML = `<span class="dot"></span><b>${last.approved ? 'Approved' : 'Rejected'}</b><i>round ${reviews.length} · ${last.approved ? 'plan released' : 'sent back to the attending'}</i>`;
  }
  list.innerHTML = reviews.map((r) => `<div class="review ${r.approved ? 'approved' : 'rejected'}">
    <div class="r-head">Round ${r.round} · ${r.approved ? 'approved' : 'rejected'}</div>
    ${(r.rejection_reasons || []).length ? `<ul>${r.rejection_reasons.map((x) => `<li>${reason(x)}</li>`).join('')}</ul>` : ''}
    ${r.required_revision ? (r.approved ? `<div class="note">Notes: ${esc(r.required_revision)}</div>`
      : `<div class="rev">Revision: ${esc(r.required_revision)}</div>`) : ''}</div>`).join('');
}

async function submitAnswers() {
  const answers = {};
  document.querySelectorAll('#canvas textarea[data-qid]').forEach((ta) => { answers[ta.dataset.qid] = ta.value.trim() || '(no answer)'; });
  try { await post(`/api/cases/${currentCase}/answers`, { answers }); } catch (e) { alert(e.message); }
}
async function submitExams() {
  const results = {};
  document.querySelectorAll('#canvas textarea[data-exam]').forEach((ta) => { results[ta.dataset.exam] = ta.value.trim() || 'not provided'; });
  try { await post(`/api/cases/${currentCase}/exams`, { results }); } catch (e) { alert(e.message); }
}

// "[precondition_0] text" / "[llm] text" -> source tag + text, so the rule-engine vs model double check is visible
function reason(x) {
  const m = /^\[([\w-]+)\]\s*(.*)$/s.exec(String(x ?? ''));
  if (!m) return esc(x);
  return `<span class="src">${m[1] === 'llm' ? 'model review' : 'rule engine'}</span>${esc(m[2])}`;
}

// make the drug class that triggered the safety rule easy to spot in a plan
function hiNitrate(html) {
  return html.replace(/\b(nitroglycerin|glyceryl trinitrate|isosorbide \w+|nitrates?)\b/gi, '<mark class="drug">$1</mark>');
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
