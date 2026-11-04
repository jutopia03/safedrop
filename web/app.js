// SafeDrop 화면 로직
// 1) 보내기: 검사(/api/judge) → 전송(/api/transfer: 서버가 다시 판정 + 토큰 발급) → P2P(WebRTC) 또는 서버 중계
// 2) 받기: 수신한 파일을 브라우저에서 직접 검증(서명·해시·수신자·만료) 후에만 다운로드 허용

const $ = (id) => document.getElementById(id);
const LABEL = {
  action: { ALLOW: '원본 허용', MASK: '마스킹본 전송', BLOCK: '차단' },
  rclass: { PRIVILEGED: '개인정보취급자', SAME_DEPT: '같은 부서', INTERNAL: '다른 부서', EXTERNAL: '외부' },
  category: { UNIQUE_ID: '고유식별정보', FINANCIAL: '금융정보', CONTACT: '연락처정보', SENSITIVE: '민감정보', UNREADABLE: '내용 확인 불가' },
};
const RTC_CONFIG = { iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] };
const P2P_TIMEOUT_MS = 8000;
const CHUNK = 16 * 1024;

let me = null, people = [], ws = null, pubKey = null;
const peers = {};      // 상대 id → RTCPeerConnection
const pendingIce = {}; // 연결 정보가 offer/answer보다 먼저 도착한 경우 잠시 보관
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const person = (id) => people.find((p) => p.id === id) || { name: id, dept: '' };

// ---------------- 로그인·초기화 ----------------
// 세션 토큰은 탭마다 따로 보관(sessionStorage) → 한 브라우저에서 탭별로 다른 직원으로 시연 가능
let session = null;
try { session = sessionStorage.getItem('sd_session'); } catch (e) { /* 저장소를 못 쓰면 매번 로그인 */ }
let meUser = null;

// 모든 API 호출에 세션 토큰을 붙인다. 401이면 로그인 화면으로.
async function api(url, opts = {}) {
  const headers = { ...(opts.headers || {}), ...(session ? { Authorization: `Bearer ${session}` } : {}) };
  const r = await fetch(url, { ...opts, headers });
  if (r.status === 401 && url !== '/api/login') showLogin('로그인이 만료되었습니다. 다시 로그인하세요.');
  return r;
}

async function init() {
  people = await (await fetch('/api/people')).json();
  pubKey = await crypto.subtle.importKey('jwk', await (await fetch('/api/pubkey')).json(),
    { name: 'ECDSA', namedCurve: 'P-256' }, false, ['verify']);
  $('loginUser').innerHTML = people.map((p) => `<option value="${p.id}">${esc(p.name)} · ${esc(p.dept)} ${esc(p.title)}${p.privileged ? ' (취급자)' : ''}${p.admin ? ' (관리자)' : ''}</option>`).join('');
  $('btnLogin').onclick = doLogin;
  $('loginPw').onkeydown = (e) => { if (e.key === 'Enter') doLogin(); };
  $('btnLogout').onclick = () => { try { sessionStorage.removeItem('sd_session'); } catch (e) {} session = null; clearTimeout(wsTimer); ws?.close(); showLogin(''); };
  $('btnJudge').onclick = doJudge;
  $('btnSend').onclick = doSend;
  $('btnAudit').onclick = loadAudit;
  document.querySelectorAll('#evalBtns button').forEach((b) => b.onclick = () => runEval(b.dataset.eval));
  $('file').onchange = () => { $('btnSend').disabled = true; $('results').innerHTML = ''; };
  if (session) {
    const r = await api('/api/me');
    if (r.ok) return startApp(await r.json());
  }
  showLogin('');
}

function showLogin(msg) {
  $('app').hidden = true; $('meBox').hidden = true; $('login').hidden = false;
  $('loginMsg').textContent = msg;
}

async function doLogin() {
  $('loginMsg').textContent = '';
  const r = await fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ uid: $('loginUser').value, password: $('loginPw').value }) });
  const d = await r.json();
  if (!r.ok) { $('loginMsg').textContent = d.detail || '로그인 실패'; return; }
  session = d.token;
  try { sessionStorage.setItem('sd_session', session); } catch (e) {}
  $('loginPw').value = '';
  startApp(d.user);
}

function startApp(user) {
  meUser = user; me = user.id;
  $('login').hidden = true; $('app').hidden = false; $('meBox').hidden = false;
  $('meName').textContent = `${user.name} · ${user.dept}`;
  $('send').hidden = !!user.external;      // 외부 담당자는 받기만
  $('auditCard').hidden = !user.admin;      // 감사 로그는 정보보호 관리자만
  $('recipients').innerHTML = people.filter((x) => x.id !== me).map((x) =>
    `<label><input type="checkbox" value="${x.id}"> ${esc(x.name)} <span class="dept">${esc(x.dept)}${x.privileged ? ' · 취급자' : ''}</span></label>`).join('');
  $('results').innerHTML = ''; $('btnSend').disabled = true;
  $('inboxList').innerHTML = '<p class="empty">아직 받은 파일이 없습니다.</p>';
  connectWS();
  if (user.admin) loadAudit();
}

// ---------------- 보내기 ----------------
function formData() {
  const f = $('file').files[0];
  const rids = [...document.querySelectorAll('#recipients input:checked')].map((x) => x.value);
  if (!f || !rids.length) { $('sendMsg').textContent = '파일과 수신자를 선택하세요.'; return null; }
  const fd = new FormData();
  fd.append('file', f); fd.append('recipient_ids', rids.join(','));   // 발신자는 서버가 세션에서 정한다
  return fd;
}

async function doJudge() {
  const fd = formData(); if (!fd) return;
  $('sendMsg').textContent = '검사 중... (AI 문맥 판단이 켜져 있으면 10초 안팎 걸립니다)';
  const r = await api('/api/judge', { method: 'POST', body: fd });
  const d = await r.json();
  if (!r.ok) { $('sendMsg').textContent = d.detail || '오류'; return; }
  const show = (e) => e.category === 'SENSITIVE'
    ? `민감정보(${e.type}) <code>${esc(e.text.trim().slice(0, 40))}${e.text.trim().length > 40 ? '…' : ''}</code>`
    : `${e.type} <code>${esc(e.text)}</code>`;
  const found = d.readable
    ? (d.entities.length ? d.entities.map(show).join(', ') : '탐지된 개인정보 없음')
    : `⚠ ${esc(d.reason)}`;
  const llmLine = d.llm?.llm === 'off' ? 'AI 문맥 판단 꺼짐 (규칙 탐지만)'
    : `AI 문맥 판단: ${esc(d.llm.llm)} · 후보 문장 ${d.llm.candidates}개${d.llm.cached ? ' (이전 판단 재사용)' : ''}${d.llm.error ? ' · ⚠ AI 판단 실패 → 후보 문장을 민감정보로 간주 (' + esc(d.llm.error) + ')' : ''}${d.llm.injection ? ' · ⚠ AI에게 내리는 지시문 의심(' + d.llm.injection_hits.map(esc).join(' / ') + ') → AI 판단을 쓰지 않고 후보 문장을 민감정보로 간주' : ''}`;
  const ocrLine = d.ocr_confidence != null
    ? `<br>📷 스캔 문서·이미지를 OCR로 읽음 (인식 신뢰도 ${d.ocr_confidence}%${d.readable ? '' : ' → 기준 미달이라 확인 불가로 차단'})` : '';
  $('sendMsg').innerHTML = `<span class="found">탐지 결과: ${found}${ocrLine}<br>${llmLine}</span>`;
  $('results').innerHTML = d.decisions.map(renderDecision).join('');
  if (d.ai_explain && d.decisions.some((x) => x.reasons.length)) loadExplanations(d.judge_id);
  $('btnSend').disabled = !d.decisions.some((x) => x.action !== 'BLOCK');
}

// 판정은 먼저 보여주고, AI 설명(검색 근거 + 인용 검증)은 도착하는 대로 채운다.
// 경과 시간을 보여주고, 90초가 넘으면 기다리기를 멈추고 기본 설명을 유지한다.
const EXPLAIN_TIMEOUT_MS = 90000;
async function loadExplanations(jid) {
  const tags = () => document.querySelectorAll('.explain .tag');
  const t0 = Date.now();
  const tick = setInterval(() => tags().forEach((t) => {
    t.textContent = `기본 설명 · AI 설명 생성 중… (${Math.round((Date.now() - t0) / 1000)}초)`; }), 1000);
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), EXPLAIN_TIMEOUT_MS);
  try {
    const r = await api(`/api/explain/${jid}`, { signal: ctrl.signal });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const ex = await r.json();
    clearInterval(tick);
    for (const [rid, e] of Object.entries(ex)) {
      const box = document.querySelector(`#res-${rid} .explain`);
      if (box) box.outerHTML = renderExplain(e);
    }
  } catch (e) {
    clearInterval(tick);
    const why = e.name === 'AbortError' ? 'AI 응답 지연(90초 초과)' : `AI 설명 오류(${e.message})`;
    tags().forEach((t) => { t.textContent = `기본 설명 · ${why}`; });
  } finally { clearTimeout(timer); }
}

function renderExplain(ex) {
  const took = ex.seconds != null ? ` (${ex.seconds}초${ex.model ? ', ' + esc(ex.model) : ''})` : '';
  return `<div class="explain ${ex.source}"><span class="tag">${ex.source === 'ai' ? 'AI 설명 · 인용 검증 통과' : '기본 설명'}${took}</span>
      ${esc(ex.text)}${ex.citations?.length ? ` <span class="cites">근거 ${ex.citations.map((c) => `[${esc(c)}]`).join(' ')}</span>` : ''}${ex.problems?.length ? `<div class="why">AI 설명 미사용 사유: ${esc(ex.problems.join(', '))}</div>` : ''}</div>`;
}

function renderDecision(x) {
  const reasons = x.reasons.map((r) =>
    `<li>${LABEL.category[r.category]} ${r.category === 'UNREADABLE' ? '' : r.count + '건'} → <b>${LABEL.action[r.action]}</b>
      <span class="clause">[${r.clause}] ${esc(r.clause_text)}</span></li>`).join('') || '<li>탐지된 개인정보 없음</li>';
  const exBox = x.explanation ? renderExplain(x.explanation) : '';
  const preview = x.masked_preview ? `<details><summary>마스킹본 미리보기</summary><pre>${esc(x.masked_preview)}</pre></details>` : '';
  return `<div class="res ${x.action}" id="res-${x.recipient.id}">
    <div class="head"><div><b>${esc(x.recipient.name)}</b> · ${esc(x.recipient.dept)} <span class="dept">(${LABEL.rclass[x.recipient_class]})</span></div>
      <span class="badge ${x.action}">${LABEL.action[x.action]}</span></div>
    ${exBox}<ul class="reasons">${reasons}</ul>${preview}<div class="status"></div></div>`;
}

async function doSend() {
  const fd = formData(); if (!fd) return;
  $('btnSend').disabled = true;
  $('sendMsg').textContent = '서버가 다시 판정하고 전송 허가 토큰을 발급하는 중...';
  const r = await api('/api/transfer', { method: 'POST', body: fd });
  const d = await r.json();
  if (!r.ok) { $('sendMsg').textContent = d.detail || '오류'; return; }
  const original = new Uint8Array(await $('file').files[0].arrayBuffer());
  $('sendMsg').textContent = `전송 ID ${d.tid}`;
  for (const item of d.items) {
    const st = document.querySelector(`#res-${item.recipient.id} .status`);
    if (item.action === 'BLOCK') { if (st) st.textContent = '⛔ 전송하지 않음'; continue; }
    const bytes = item.payload_text != null ? new TextEncoder().encode(item.payload_text) : original;
    if (st) st.textContent = 'P2P 연결 시도 중...';
    try {
      await sendP2P(item.recipient.id, { tid: d.tid, token: item.token, file: item.file }, bytes);
      if (st) st.textContent = '✅ P2P로 직접 전송 완료 (파일 전달은 서버를 거치지 않음)';
    } catch (e) {
      await sendRelay(d.tid, item, bytes);
      if (st) st.textContent = `↪ P2P 실패(${e.message}) → 서버 중계로 전송 (수신 즉시 삭제, 최대 10분 보관)`;
    }
  }
  if (meUser?.admin) loadAudit();
}

async function sendRelay(tid, item, bytes) {
  const q = new URLSearchParams({ token: item.token });   // 서버가 토큰 서명·발신자=본인 여부를 확인
  const r = await api(`/api/relay/${tid}/${item.recipient.id}?${q}`, { method: 'PUT', body: bytes });
  if (!r.ok) throw new Error((await r.json()).detail || '중계 실패');
}

// ---------------- P2P (WebRTC DataChannel) ----------------
function newPeer(other) {
  peers[other]?.close();
  const pc = new RTCPeerConnection(RTC_CONFIG);
  pc.onicecandidate = (e) => e.candidate && ws.send(JSON.stringify({ to: other, type: 'ice', data: e.candidate }));
  peers[other] = pc;
  return pc;
}

function sendP2P(to, header, bytes) {
  return new Promise(async (resolve, reject) => {
    const timer = setTimeout(() => { peers[to]?.close(); reject(new Error('시간 초과')); }, P2P_TIMEOUT_MS);
    try {
      const online = await (await api('/api/online')).json();
      if (!online.includes(to)) { clearTimeout(timer); return reject(new Error('수신자 미접속')); }
      const pc = newPeer(to);
      const dc = pc.createDataChannel('file');
      dc.binaryType = 'arraybuffer';
      dc.onopen = async () => {
        dc.send(JSON.stringify({ ...header, size: bytes.length }));
        for (let i = 0; i < bytes.length; i += CHUNK) {
          while (dc.bufferedAmount > 1 << 20) await new Promise((r) => setTimeout(r, 20));
          dc.send(bytes.slice(i, i + CHUNK));
        }
        dc.send('EOF');
      };
      dc.onmessage = (e) => { if (e.data === 'ACK') { clearTimeout(timer); resolve(); setTimeout(() => pc.close(), 500); } };
      await pc.setLocalDescription(await pc.createOffer());
      ws.send(JSON.stringify({ to, type: 'offer', data: pc.localDescription }));
    } catch (e) { clearTimeout(timer); reject(e); }
  });
}

async function onOffer(from, sdp) {
  const pc = newPeer(from);
  pc.ondatachannel = (e) => {
    const dc = e.channel; dc.binaryType = 'arraybuffer';
    let header = null; const parts = [];
    dc.onmessage = async (m) => {
      if (typeof m.data === 'string') {
        if (m.data === 'EOF') {
          dc.send('ACK');
          await verifyAndShow(header, new Uint8Array(await new Blob(parts).arrayBuffer()), 'P2P', from);
        } else header = JSON.parse(m.data);
      } else parts.push(m.data);
    };
  };
  await pc.setRemoteDescription(sdp);
  await flushIce(from);
  await pc.setLocalDescription(await pc.createAnswer());
  ws.send(JSON.stringify({ to: from, type: 'answer', data: pc.localDescription }));
}

async function flushIce(from) {
  for (const c of pendingIce[from] || []) await peers[from]?.addIceCandidate(c).catch(() => {});
  delete pendingIce[from];
}

// ---------------- 신호 채널 (WebSocket) ----------------
// 서버가 재시작·절전 후 깨어나면 연결이 끊기므로 자동으로 다시 연결한다 (1초 → 최대 30초 간격)
let wsRetry = 0, wsTimer = null;
function connectWS() {
  clearTimeout(wsTimer);
  if (ws) { ws.onclose = null; ws.close(); }
  if (!session) return;                                   // 로그아웃 상태면 연결하지 않음
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const sock = new WebSocket(`${proto}://${location.host}/ws`);
  ws = sock;
  sock.onopen = () => { sock.send(JSON.stringify({ type: 'auth', token: session })); wsRetry = 0; $('conn').className = 'dot on'; };
  sock.onclose = (ev) => {
    $('conn').className = 'dot off';
    if (ws !== sock || !session) return;                 // 새 연결로 바뀌었거나 로그아웃
    if (ev.code === 4401) { showLogin('로그인이 만료되었습니다. 다시 로그인하세요.'); return; }
    wsTimer = setTimeout(connectWS, Math.min(30000, 1000 * 2 ** wsRetry++));
  };
  ws.onmessage = async (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === 'offer') await onOffer(msg.from, msg.data);
    else if (msg.type === 'answer') { await peers[msg.from]?.setRemoteDescription(msg.data); await flushIce(msg.from); }
    else if (msg.type === 'ice') {
      const pc = peers[msg.from];
      if (pc?.remoteDescription) await pc.addIceCandidate(msg.data).catch(() => {});
      else (pendingIce[msg.from] ||= []).push(msg.data);
    }
    else if (msg.type === 'relay') {
      const r = await api(`/api/relay/${msg.data.tid}/${me}`);
      if (r.ok) await verifyAndShow(msg.data, new Uint8Array(await r.arrayBuffer()), '서버 중계', msg.from);
    }
  };
}

// ---------------- 수신 검증 ----------------
const b64u = (s) => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((s.length + 3) % 4)), (c) => c.charCodeAt(0));
const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');

async function verifyAndShow(header, bytes, via, from) {
  const [payload, sig] = (header?.token || '.').split('.');
  let claims = {}, checks = [];
  try {
    claims = JSON.parse(new TextDecoder().decode(b64u(payload)));
    const sigOk = await crypto.subtle.verify({ name: 'ECDSA', hash: 'SHA-256' }, pubKey, b64u(sig), new TextEncoder().encode(payload));
    const sha = hex(await crypto.subtle.digest('SHA-256', bytes));
    checks = [
      ['서버 서명', sigOk],
      ['파일 해시 일치', sha === claims.sha256],
      ['수신자 = 나', claims.recipient === me],
      ['만료 전', claims.exp * 1000 > Date.now()],
    ];
  } catch (e) { checks = [['토큰 형식', false]]; }
  const ok = checks.every(([, v]) => v);
  const detail = checks.filter(([, v]) => !v).map(([k]) => k).join(', ');
  api('/api/receipt', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tid: claims.tid || header?.tid, verified: ok, via, detail }) });

  const box = $('inboxList');
  if (box.querySelector('.empty')) box.innerHTML = '';
  const link = ok ? `<a download="${esc(claims.file)}" href="${URL.createObjectURL(new Blob([bytes]))}">⬇ 다운로드</a>` : '수신 거부됨';
  box.insertAdjacentHTML('afterbegin', `<div class="res ${ok ? 'ALLOW' : 'BLOCK'}">
    <div class="head"><div><b>${esc(claims.file || header?.file || '?')}</b> · 보낸 사람 ${esc(person(from).name)} · ${via}</div>
      <span class="badge ${ok ? 'ok' : 'bad'}">${ok ? '검증 통과' : '검증 실패'}</span></div>
    <div class="status">${checks.map(([k, v]) => `${v ? '✔' : '✘'} ${k}`).join(' · ')} ${claims.action ? '· 조치: ' + LABEL.action[claims.action] : ''}</div>
    <div class="status">${link}</div></div>`);
  if (meUser?.admin) loadAudit();
}

// ---------------- 감사 로그 ----------------
async function loadAudit() {
  const r = await api('/api/audit?limit=30');
  if (!r.ok) return;
  const rows = await r.json();
  const name = (id) => (id ? person(id).name : '');
  $('audit').innerHTML = rows.length ? `<table><tr><th>시각</th><th>이벤트</th><th>발신</th><th>수신</th><th>파일</th><th>내용</th></tr>` +
    rows.map((r) => `<tr><td>${r.time.slice(5)}</td><td>${r.event}</td><td>${esc(name(r.sender))}</td><td>${esc(name(r.recipient))}</td>
      <td>${esc(r.file || '')}</td><td>${r.clauses ? '근거 ' + r.clauses.join(', ') : ''}${r.verified != null ? (r.verified ? '검증 통과' : '검증 실패: ' + esc(r.detail)) + ' (' + r.via + ')' : ''}</td></tr>`).join('') + '</table>'
    : '<p class="empty">기록 없음</p>';
}

init();

// 관리자 전용 성능 측정: 처음 누르면 시작, 다시 누르면 진행 상황·결과를 보여준다
async function runEval(name) {
  const rerun = $('evalRerun').checked ? 1 : 0;
  $('evalRerun').checked = false;
  $('evalOut').textContent = `${name} 요청 중...`;
  const r = await api(`/api/eval/${name}?rerun=${rerun}`);
  $('evalOut').textContent = await r.text();
}
