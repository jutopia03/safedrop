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

// ---------------- 초기화 ----------------
async function init() {
  people = await (await fetch('/api/people')).json();
  pubKey = await crypto.subtle.importKey('jwk', await (await fetch('/api/pubkey')).json(),
    { name: 'ECDSA', namedCurve: 'P-256' }, false, ['verify']);
  $('me').innerHTML = people.map((p) => `<option value="${p.id}">${esc(p.name)} (${esc(p.dept)})</option>`).join('');
  const saved = new URLSearchParams(location.search).get('me');
  if (saved) $('me').value = saved;
  $('me').onchange = () => switchUser($('me').value);
  $('btnJudge').onclick = doJudge;
  $('btnSend').onclick = doSend;
  $('btnAudit').onclick = loadAudit;
  $('file').onchange = () => { $('btnSend').disabled = true; $('results').innerHTML = ''; };
  switchUser($('me').value);
  loadAudit();
}

function switchUser(id) {
  me = id;
  const p = person(me);
  $('send').style.display = p.external ? 'none' : '';   // 외부 담당자는 받기만
  $('recipients').innerHTML = people.filter((x) => x.id !== me).map((x) =>
    `<label><input type="checkbox" value="${x.id}"> ${esc(x.name)} <span class="dept">${esc(x.dept)}${x.privileged ? ' · 취급자' : ''}</span></label>`).join('');
  $('results').innerHTML = ''; $('btnSend').disabled = true;
  $('inboxList').innerHTML = '<p class="empty">아직 받은 파일이 없습니다.</p>';
  connectWS();
}

// ---------------- 보내기 ----------------
function formData() {
  const f = $('file').files[0];
  const rids = [...document.querySelectorAll('#recipients input:checked')].map((x) => x.value);
  if (!f || !rids.length) { $('sendMsg').textContent = '파일과 수신자를 선택하세요.'; return null; }
  const fd = new FormData();
  fd.append('file', f); fd.append('sender_id', me); fd.append('recipient_ids', rids.join(','));
  return fd;
}

async function doJudge() {
  const fd = formData(); if (!fd) return;
  $('sendMsg').textContent = '검사 중...';
  const r = await fetch('/api/judge', { method: 'POST', body: fd });
  const d = await r.json();
  if (!r.ok) { $('sendMsg').textContent = d.detail || '오류'; return; }
  const show = (e) => e.category === 'SENSITIVE'
    ? `민감정보(${e.type}) <code>${esc(e.text.trim().slice(0, 40))}${e.text.trim().length > 40 ? '…' : ''}</code>`
    : `${e.type} <code>${esc(e.text)}</code>`;
  const found = d.readable
    ? (d.entities.length ? d.entities.map(show).join(', ') : '탐지된 개인정보 없음')
    : `⚠ ${esc(d.reason)}`;
  const llmLine = d.llm?.llm === 'off' ? 'AI 문맥 판단 꺼짐 (규칙 탐지만)'
    : `AI 문맥 판단: ${esc(d.llm.llm)} · 후보 문장 ${d.llm.candidates}개${d.llm.error ? ' · ⚠ AI 판단 실패 → 후보 문장을 민감정보로 간주 (' + esc(d.llm.error) + ')' : ''}`;
  $('sendMsg').innerHTML = `<span class="found">탐지 결과: ${found}<br>${llmLine}</span>`;
  $('results').innerHTML = d.decisions.map(renderDecision).join('');
  $('btnSend').disabled = !d.decisions.some((x) => x.action !== 'BLOCK');
}

function renderDecision(x) {
  const reasons = x.reasons.map((r) =>
    `<li>${LABEL.category[r.category]} ${r.category === 'UNREADABLE' ? '' : r.count + '건'} → <b>${LABEL.action[r.action]}</b>
      <span class="clause">[${r.clause}] ${esc(r.clause_text)}</span></li>`).join('') || '<li>탐지된 개인정보 없음</li>';
  const preview = x.masked_preview ? `<details><summary>마스킹본 미리보기</summary><pre>${esc(x.masked_preview)}</pre></details>` : '';
  return `<div class="res ${x.action}" id="res-${x.recipient.id}">
    <div class="head"><div><b>${esc(x.recipient.name)}</b> · ${esc(x.recipient.dept)} <span class="dept">(${LABEL.rclass[x.recipient_class]})</span></div>
      <span class="badge ${x.action}">${LABEL.action[x.action]}</span></div>
    <ul class="reasons">${reasons}</ul>${preview}<div class="status"></div></div>`;
}

async function doSend() {
  const fd = formData(); if (!fd) return;
  $('btnSend').disabled = true;
  $('sendMsg').textContent = '서버가 다시 판정하고 전송 허가 토큰을 발급하는 중...';
  const r = await fetch('/api/transfer', { method: 'POST', body: fd });
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
  loadAudit();
}

async function sendRelay(tid, item, bytes) {
  const q = new URLSearchParams({ sender: me, file: item.file, token: item.token });
  await fetch(`/api/relay/${tid}/${item.recipient.id}?${q}`, { method: 'PUT', body: bytes });
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
      const online = await (await fetch('/api/online')).json();
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
function connectWS() {
  ws?.close();
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws/${me}`);
  ws.onopen = () => $('conn').className = 'dot on';
  ws.onclose = () => $('conn').className = 'dot off';
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
      const r = await fetch(`/api/relay/${msg.data.tid}/${me}`);
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
  fetch('/api/receipt', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tid: claims.tid || header?.tid, recipient: me, verified: ok, via, detail }) });

  const box = $('inboxList');
  if (box.querySelector('.empty')) box.innerHTML = '';
  const link = ok ? `<a download="${esc(claims.file)}" href="${URL.createObjectURL(new Blob([bytes]))}">⬇ 다운로드</a>` : '수신 거부됨';
  box.insertAdjacentHTML('afterbegin', `<div class="res ${ok ? 'ALLOW' : 'BLOCK'}">
    <div class="head"><div><b>${esc(claims.file || header?.file || '?')}</b> · 보낸 사람 ${esc(person(from).name)} · ${via}</div>
      <span class="badge ${ok ? 'ok' : 'bad'}">${ok ? '검증 통과' : '검증 실패'}</span></div>
    <div class="status">${checks.map(([k, v]) => `${v ? '✔' : '✘'} ${k}`).join(' · ')} ${claims.action ? '· 조치: ' + LABEL.action[claims.action] : ''}</div>
    <div class="status">${link}</div></div>`);
  loadAudit();
}

// ---------------- 감사 로그 ----------------
async function loadAudit() {
  const rows = await (await fetch('/api/audit?limit=30')).json();
  const name = (id) => (id ? person(id).name : '');
  $('audit').innerHTML = rows.length ? `<table><tr><th>시각</th><th>이벤트</th><th>발신</th><th>수신</th><th>파일</th><th>내용</th></tr>` +
    rows.map((r) => `<tr><td>${r.time.slice(5)}</td><td>${r.event}</td><td>${esc(name(r.sender))}</td><td>${esc(name(r.recipient))}</td>
      <td>${esc(r.file || '')}</td><td>${r.clauses ? '근거 ' + r.clauses.join(', ') : ''}${r.verified != null ? (r.verified ? '검증 통과' : '검증 실패: ' + esc(r.detail)) + ' (' + r.via + ')' : ''}</td></tr>`).join('') + '</table>'
    : '<p class="empty">기록 없음</p>';
}

init();
