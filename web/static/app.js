// 医晓 Hospital Agent · 临床指挥台前端（原生 JS，EventSource 实时事件流）
'use strict';

const $ = (id) => document.getElementById(id);
let currentCase = null;
let es = null;
let seenSeq = -1;

// ---------- 启动 ----------
(async function boot() {
  try {
    const me = await get('/api/me');
    showApp(me);
  } catch (e) {
    $('login-view').classList.remove('hidden');
  }
})();

async function get(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error((await r.json()).error || r.status);
  return r.json();
}
async function post(url, body) {
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                               body: JSON.stringify(body || {}) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.status);
  return data;
}

// ---------- 登录 ----------
$('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  $('login-error').textContent = '';
  try {
    await post('/login', { username: $('login-user').value.trim(), password: $('login-pass').value });
    const me = await get('/api/me');
    showApp(me);
  } catch (err) {
    $('login-error').textContent = '登录失败：' + err.message;
  }
});
$('btn-logout').addEventListener('click', async () => { await post('/logout'); location.href = '/'; });

function showApp(me) {
  $('login-view').classList.add('hidden');
  $('app-view').classList.remove('hidden');
  $('st-model').textContent = me.model || '—';
  $('kb-stats').textContent = `${me.knowledge.departments} 科室 · ${me.knowledge.skills} Skill · ${me.knowledge.exams} 检查`;
  refreshCases();
  setInterval(refreshCases, 5000);
}

// ---------- 病例 ----------
$('btn-create').addEventListener('click', async () => {
  const complaint = $('in-complaint').value.trim();
  if (!complaint) { $('in-complaint').focus(); return; }
  try {
    const { case_id } = await post('/api/cases', {
      chief_complaint: complaint,
      age: Number($('in-age').value) || null,
      sex: $('in-sex').value,
      duration: $('in-duration').value.trim(),
      symptoms: $('in-symptoms').value.split(/[,，]/).map(s => s.trim()).filter(Boolean),
      past_history: $('in-history').value.trim(),
      allergies: $('in-allergies').value.trim(),
      medications: $('in-meds').value.trim(),
    });
    $('in-complaint').value = '';
    openCase(case_id);
    refreshCases();
  } catch (err) { alert('创建失败：' + err.message); }
});

async function refreshCases() {
  try {
    const { cases } = await get('/api/cases');
    const ul = $('case-list');
    ul.innerHTML = '';
    if (!cases.length) { ul.innerHTML = '<li class="empty">暂无病例</li>'; return; }
    for (const c of cases) {
      const li = document.createElement('li');
      if (c.id === currentCase) li.className = 'active';
      const d = new Date(c.created_at * 1000);
      li.innerHTML = `<b>${esc(c.chief_complaint).slice(0, 24)}</b>` +
        `<span>${d.toLocaleTimeString('zh-CN')} · ${c.status === 'final' ? '已完成' : '进行中'}</span>`;
      li.onclick = () => openCase(c.id);
      ul.appendChild(li);
    }
  } catch (e) { /* 未登录时忽略 */ }
}

async function openCase(caseId) {
  currentCase = caseId;
  seenSeq = -1;
  $('timeline').innerHTML = '';
  $('audit-count').textContent = '0 条事件 · 每一次交接与工具调用都可回放';
  if (es) es.close();
  es = new EventSource(`/api/cases/${caseId}/events`);
  es.addEventListener('agent', (e) => {
    const ev = JSON.parse(e.data);
    if (ev.seq > seenSeq) { seenSeq = ev.seq; onEvent(ev); }
  });
  await renderView();
  refreshCases();
}

// ---------- 渲染 ----------
async function renderView() {
  if (!currentCase) return;
  let v;
  try { v = await get(`/api/cases/${currentCase}`); } catch (e) { return; }
  if (!v || !v.stage) return;
  $('case-headline').textContent = `${v.chief_complaint}（${v.sex || ''} ${v.age ?? ''} 岁）`;
  $('intake-brief').innerHTML =
    `主诉：<b>${esc(v.chief_complaint)}</b> · 持续 ${esc(v.duration || '—')}<br>` +
    `症状：${esc((v.symptoms || []).join('、') || '—')} · 既往史：${esc(v.past_history || '—')} · ` +
    `过敏史：${esc(v.allergies || '无')} · 用药：${esc(v.medications || '无')}`;
  if (v.stats) {
    $('st-events').textContent = $('timeline').children.length || (v.stats.events || 0);
    $('st-calls').textContent = v.stats.model_calls || 0;
    $('st-tokens').textContent = (v.stats.prompt_tokens || 0) + (v.stats.completion_tokens || 0);
  }
  renderRail(v);
  renderQA(v);
  renderExams(v);
  renderSafety(v);
  renderConclusion(v);
  renderReport(v);
  renderError(v);
}

const STAGE_ORDER = ['triage', 'interview', 'differential', 'examination', 'specialist', 'attending', 'safety', 'audit'];
function renderRail(v) {
  const stage = (v.stage || '').replace(/_r\d+$/, '');
  let currentIdx = STAGE_ORDER.indexOf(stage === 'await_exams' ? 'examination' : stage);
  if (v.stage === 'final') currentIdx = STAGE_ORDER.length;
  const reviews = (v.safety && v.safety.reviews) || [];
  const lastRejected = reviews.length && !reviews[reviews.length - 1].approved;
  document.querySelectorAll('#stage-rail .node').forEach((node, i) => {
    node.classList.remove('active', 'done', 'reject');
    if (i < currentIdx) node.classList.add('done');
    else if (i === currentIdx) node.classList.add('active');
  });
  if (lastRejected && currentIdx >= 6) {
    const safetyNode = document.querySelector('[data-s="safety"]');
    safetyNode.classList.remove('done', 'active');
    safetyNode.classList.add('reject');
  }
  $('stage-label').textContent = v.stage === 'final' ? '已完成：报告可验收、可复盘'
    : v.stage.startsWith('interview_r') ? `问诊第 ${v.stage.split('_r')[1]} 轮 · 每轮 2-3 问`
    : v.stage === 'await_exams' ? '等待检查结果录入 · 系统不伪造数据'
    : v.stage === 'specialist' ? '双专科并行会诊中' : '八智能体接力 · 双专科并行';
}

function renderQA(v) {
  const area = $('qa-area');
  area.innerHTML = '';
  const rounds = v.interview_rounds || [];
  rounds.forEach((r, idx) => {
    const div = document.createElement('div');
    div.className = 'qa-round';
    const pending = v.phase === 'await_answers' && v.pending_round === r.round;
    div.innerHTML = `<h4>第 ${r.round} 轮追问（信息差驱动 · 每轮 2-3 问）</h4>`;
    r.questions.forEach((q) => {
      const item = document.createElement('div');
      item.className = 'qa-item';
      const answered = r.answers && r.answers[q.id];
      if (answered) {
        item.innerHTML = `<div class="q">问：${esc(q.question)}<i>${esc(q.why || '')}</i></div>` +
                         `<div class="answered">答：${esc(answered)}</div>`;
      } else if (pending) {
        item.innerHTML = `<div class="q">问：${esc(q.question)}<i>${esc(q.why || '')}</i></div>` +
                         `<textarea rows="1" data-qid="${q.id}" placeholder="输入患者回答…"></textarea>`;
      } else {
        item.innerHTML = `<div class="q">问：${esc(q.question)}<i>等待回答…</i></div>`;
      }
      div.appendChild(item);
    });
    if (pending) {
      const btn = document.createElement('button');
      btn.className = 'btn-sm';
      btn.textContent = '提交本轮回答';
      btn.onclick = () => submitAnswers(r.round);
      div.appendChild(btn);
    }
    area.appendChild(div);
  });
}

async function submitAnswers() {
  const answers = {};
  document.querySelectorAll('#qa-area textarea[data-qid]').forEach((ta) => {
    answers[ta.dataset.qid] = ta.value.trim() || '（未答）';
  });
  try { await post(`/api/cases/${currentCase}/answers`, { answers }); } catch (e) { alert(e.message); }
}

function renderExams(v) {
  const area = $('exam-area');
  area.innerHTML = '';
  const plan = v.exam_plan || [];
  if (!plan.length) return;
  const pending = v.phase === 'await_exams';
  const h = document.createElement('h4');
  h.style.cssText = 'color:#26e5ff;font-size:13px;margin:10px 0 6px';
  h.textContent = `检查规划（${plan.length} 项 · 必要/鉴别/避免三清单约束）`;
  area.appendChild(h);
  plan.forEach((p) => {
    const row = document.createElement('div');
    row.className = 'exam-item';
    const result = v.exam_inputs && v.exam_inputs[p.exam];
    row.innerHTML = `<div class="name">${esc(p.exam)}<i>${p.priority === 'essential' ? '必要检查' : '条件触发'}</i></div>`;
    if (result) {
      row.innerHTML += `<div class="answered" style="color:#5aeed1;font-size:13px;padding-top:8px">结果：${esc(result)}</div>`;
    } else if (pending) {
      row.innerHTML += `<textarea rows="1" data-exam="${esc(p.exam)}" placeholder="录入检查结果（系统不伪造数据）…"></textarea>`;
    } else {
      row.innerHTML += `<div class="empty" style="padding-top:8px">等待录入…</div>`;
    }
    area.appendChild(row);
  });
  if (pending) {
    const btn = document.createElement('button');
    btn.className = 'btn-sm';
    btn.textContent = '提交检查结果 · 进入双专科会诊';
    btn.onclick = async () => {
      const results = {};
      document.querySelectorAll('#exam-area textarea[data-exam]').forEach((ta) => {
        results[ta.dataset.exam] = ta.value.trim() || '未提供';
      });
      try { await post(`/api/cases/${currentCase}/exams`, { results }); } catch (e) { alert(e.message); }
    };
    area.appendChild(btn);
  }
}

function renderSafety(v) {
  const badge = $('safety-badge');
  const list = $('safety-list');
  const reviews = (v.safety && v.safety.reviews) || [];
  if (!reviews.length) { badge.className = 'badge idle'; badge.textContent = 'STANDBY'; return; }
  const last = reviews[reviews.length - 1];
  badge.className = 'badge ' + (last.approved ? 'approved' : 'rejected');
  badge.textContent = last.approved ? `SAFETY APPROVED · 第 ${reviews.length} 轮` : `SAFETY REJECTED · 第 ${reviews.length} 轮`;
  list.innerHTML = '';
  reviews.forEach((r) => {
    const div = document.createElement('div');
    div.className = 'safety-review ' + (r.approved ? 'approved' : 'rejected');
    div.innerHTML = `<b>第 ${r.round} 轮 · ${r.approved ? '通过' : '驳回'}</b>` +
      (r.rejection_reasons && r.rejection_reasons.length
        ? `<ul>${r.rejection_reasons.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : '') +
      (r.required_revision ? `<div style="color:#ffc452;margin-top:4px">修订要求：${esc(r.required_revision)}</div>` : '');
    list.appendChild(div);
  });
}

function renderConclusion(v) {
  const el = $('conclusion');
  const att = v.attending || {};
  if (!att.final_assessment && !(att.diagnosis_candidates || []).length) {
    el.innerHTML = '<div class="empty">—</div>';
    return;
  }
  el.innerHTML = `拟诊：<b>${(att.diagnosis_candidates || []).map(esc).join(' / ') || '—'}</b><br>` +
    `评估：${esc(att.final_assessment || '')}<br>` +
    `会诊：${Object.values(v.specialists || {}).map((o) => `${esc(o.department)}（${esc(o.primary_opinion || '').slice(0, 18)}…）`).join(' · ')}` +
    ((v.safety_preconditions || []).length
      ? `<div class="precond">⚠ 前置条件：${v.safety_preconditions.map(esc).join('<br>')}</div>` : '');
}

function renderReport(v) {
  const area = $('report-area');
  if (v.stage !== 'final' || !v.final) { area.innerHTML = ''; return; }
  const f = v.final;
  const warns = (f.safety.warning || []).map((w) => `<div class="warn">⚠ ${esc(w)}</div>`).join('');
  area.innerHTML = `<div class="report">
    <h4>结构化诊疗报告（可验收 · 可复盘）</h4>
    <div class="diagnosis">最终拟诊：${(f.attending.diagnosis_candidates || []).map(esc).join(' / ')}</div>
    <h4>诊断依据</h4><ul>${(f.attending.consensus || []).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
    <h4>治疗方案</h4><ul>${(f.attending.treatment_plan || []).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
    <h4>检查与结果</h4><ul>${f.exams.map((e) => `<li>${esc(e.exam)}（${e.priority === 'essential' ? '必要' : '条件'}）：${esc(e.result || '未提供')}</li>`).join('')}</ul>
    <h4>安全审查</h4>
    <ul><li>共 ${f.safety.rounds} 轮 · 结论：${f.safety.approved ? '通过' : '未完全通过（保守回退）'}</li>
    ${(f.safety.preconditions || []).map((x) => `<li>前置条件：${esc(x)}</li>`).join('')}</ul>
    ${warns}
    <h4>统计</h4>
    <ul><li>${f.stats.events} 条事件 · ${f.stats.model_calls} 次模型调用 · ${f.stats.prompt_tokens + f.stats.completion_tokens} tokens · 问诊 ${f.interview_rounds} 轮 · Safety ${f.safety.rounds} 轮</li></ul>
    <div class="disc">${esc(f.disclaimer)}</div>
  </div>`;
}

function renderError(v) {
  const el = $('error-area');
  if (v.error) { el.classList.remove('hidden'); el.textContent = '流程错误（如实显示，不伪造成功）：' + v.error; }
  else el.classList.add('hidden');
}

// ---------- 事件流 ----------
const TYPE_LABEL = { case_created: '病例创建', agent_start: '智能体启动', agent_done: '智能体完成',
  handoff: '结构化交接', validate_retry: '输出校验重试', await_user: '等待用户输入',
  answers_received: '回答已提交', exam_results_received: '检查结果录入', avoid_filtered: 'avoid 过滤',
  revision: '主治修订', case_final: '报告交付', error: '错误', agent_retry: '失败重试' };

function onEvent(ev) {
  const tl = $('timeline');
  if (tl.querySelector('.empty')) tl.innerHTML = '';
  const row = document.createElement('div');
  const cls = 'tl-row ev-' + ev.type;
  row.className = cls;
  const t = new Date(ev.ts * 1000).toLocaleTimeString('zh-CN', { hour12: false });
  row.innerHTML = `<span class="t">${t}</span><span class="a">${esc(ev.agent)}</span>` +
    `<span class="ty">${TYPE_LABEL[ev.type] || ev.type}</span><span class="s">${esc(ev.summary)}</span>`;
  row.title = JSON.stringify(ev.payload, null, 1);
  tl.appendChild(row);
  tl.scrollTop = tl.scrollHeight;
  $('audit-count').textContent = `${tl.children.length} 条事件 · 每一次交接与工具调用都可回放`;
  $('st-events').textContent = tl.children.length;
  if (['agent_done', 'await_user', 'answers_received', 'exam_results_received', 'revision', 'case_final', 'error'].includes(ev.type)) {
    renderView();
  }
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
