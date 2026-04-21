const GENDER = { Q6581097: 'male', Q6581072: 'female' };
const GENDER_OPTS = [['', '—'], ['Q6581097', 'male'], ['Q6581072', 'female']];
const PER_PAGE = 100;

const COLS = {
  characters: [
    { key: 'name',            label: 'Name',         editable: true, type: 'text' },
    { key: 'wikidata_id',     label: 'Wikidata ID' },
    { key: 'gender',          label: 'Gender',       editable: true, type: 'select',
      fmt: v => GENDER[v] ?? v ?? '—' },
    { key: 'citizenship_ids', label: 'Citizenships', editable: true, type: 'tags',
      fmt: v => (Array.isArray(v) && v.length) ? v.join(', ') : '—' },
    { key: 'occupation_ids',  label: 'Occupations',  editable: true, type: 'tags',
      fmt: v => (Array.isArray(v) && v.length) ? v.join(', ') : '—' },
    { key: 'series_ids',           label: 'Series',       editable: true, type: 'tags',
      fmt: v => (Array.isArray(v) && v.length) ? v.join(', ') : '—' },
    { key: 'genre_ids',            label: 'Genres',       editable: true, type: 'tags',
      fmt: v => (Array.isArray(v) && v.length) ? v.join(', ') : '—' },
    { key: 'member_of_ids',        label: 'Member of',    editable: true, type: 'tags',
      fmt: v => (Array.isArray(v) && v.length) ? v.join(', ') : '—' },
    { key: 'award_ids',            label: 'Awards',       editable: true, type: 'tags',
      fmt: v => (Array.isArray(v) && v.length) ? v.join(', ') : '—' },
    { key: 'country_of_origin_ids',label: 'Origin',       editable: true, type: 'tags',
      fmt: v => (Array.isArray(v) && v.length) ? v.join(', ') : '—' },
    { key: 'hair_color',           label: 'Hair',         editable: true, type: 'text',
      fmt: v => v ?? '—' },
    { key: 'birth_year',      label: 'Born',         editable: true, type: 'number',
      fmt: v => v ?? '—' },
    { key: 'death_year',      label: 'Died',         editable: true, type: 'number',
      fmt: v => v ?? '—' },
    { key: 'is_fictional',    label: 'Fictional',    editable: true, type: 'bool' },
    { key: 'is_animated',     label: 'Animated',     editable: true, type: 'bool' },
  ],
  questions: [
    { key: 'id',            label: 'ID' },
    { key: 'text',          label: 'Question' },
    { key: 'question_type', label: 'Type' },
    { key: 'qid',           label: 'QID', fmt: v => v ?? '—' },
  ],
  games: [
    { key: 'id',          label: 'ID' },
    { key: 'ended_at',    label: 'Date',       fmt: v => v ?? '—' },
    { key: 'guessed',     label: 'Guessed',    fmt: v => v ?? '—' },
    { key: 'correct',     label: 'Correct',    fmt: v => v ?? '—' },
    { key: 'was_correct', label: 'Result' },
    { key: 'confidence',  label: 'Confidence', fmt: v => v != null ? `${v}%` : '—' },
    { key: 'questions',   label: 'Questions' },
  ],
};

const CAN_CREATE = { characters: true,  questions: false, games: false };
const CAN_EDIT   = { characters: true,  questions: false, games: false };
const CAN_DELETE = { characters: true,  questions: true,  games: true  };

let rawData  = { characters: [], questions: [], games: [] };
let tab      = 'characters';
let sortSt   = { characters: { col: null, asc: true }, questions: { col: null, asc: true }, games: { col: null, asc: true } };
let filterTx = '';
let curPage  = { characters: 0, questions: 0, games: 0 };
let editKey  = null;
let creating = false;

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

async function init() {
  const [chars, qs, games] = await Promise.all([
    api('GET', '/data/characters'),
    api('GET', '/data/questions'),
    api('GET', '/data/games'),
  ]);
  rawData.characters = chars;
  rawData.questions  = qs;
  rawData.games      = games;
  updateCounts();
  render();
}

function updateCounts() {
  document.getElementById('counts').textContent =
    `${rawData.characters.length} characters · ${rawData.questions.length} questions · ${rawData.games.length} games`;
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

function setTab(t) {
  tab = t; editKey = null; creating = false; curPage[t] = 0;
  document.getElementById('new-btn').style.display = CAN_CREATE[t] ? '' : 'none';
  render();
}

function onFilter(v) {
  filterTx = v.toLowerCase(); editKey = null; creating = false;
  curPage[tab] = 0; render();
}

function sortBy(col) {
  const s = sortSt[tab];
  if (s.col === col) s.asc = !s.asc; else { s.col = col; s.asc = true; }
  editKey = null; creating = false; render();
}

function goPage(dir) {
  const total = Math.ceil(filtered().length / PER_PAGE);
  curPage[tab] = Math.max(0, Math.min(curPage[tab] + dir, total - 1));
  render();
}

// ---------------------------------------------------------------------------
// CRUD actions
// ---------------------------------------------------------------------------

function startNew() { creating = true; editKey = null; render(); focusFirst('#new-row'); }
function cancelNew() { creating = false; render(); }
function startEdit(key) { editKey = key; creating = false; render(); focusFirst('#edit-row'); }
function cancelEdit() { editKey = null; render(); }

function focusFirst(sel) {
  const el = document.querySelector(sel + ' input, ' + sel + ' select');
  if (el) el.focus();
}

async function saveNew() {
  const wikid = val('new-wikid'); const name = val('new-name');
  if (!wikid || !name) { await modalAlert('Wikidata ID and Name are required', true); return; }
  const body = {
    wikidata_id: wikid, name,
    gender:          val('new-gender') || null,
    citizenship_ids: tagsVal('new-citizenships'),
    occupation_ids:  tagsVal('new-occupations'),
    series_ids:      tagsVal('new-series'),
    genre_ids:       tagsVal('new-genres'),
    member_of_ids:   tagsVal('new-memberof'),
    award_ids:       tagsVal('new-awards'),
    country_of_origin_ids: tagsVal('new-origin'),
    hair_color:      val('new-haircolor') || null,
    birth_year:      numVal('new-birth'),
    death_year:      numVal('new-death'),
    is_fictional:    document.getElementById('new-fictional')?.checked ?? false,
    is_animated:     document.getElementById('new-animated')?.checked ?? false,
  };
  try {
    await api('POST', '/data/characters', body);
  } catch (e) { await modalAlert(e.message, true); return; }
  rawData.characters.push(body);
  updateCounts(); creating = false; render();
}

async function saveEdit(key) {
  const name = val('edit-name');
  if (!name) { await modalAlert('Name is required', true); return; }
  const body = {
    name,
    gender:          val('edit-gender') || null,
    citizenship_ids: tagsVal('edit-citizenships'),
    occupation_ids:  tagsVal('edit-occupations'),
    series_ids:      tagsVal('edit-series'),
    genre_ids:       tagsVal('edit-genres'),
    member_of_ids:   tagsVal('edit-memberof'),
    award_ids:       tagsVal('edit-awards'),
    country_of_origin_ids: tagsVal('edit-origin'),
    hair_color:      val('edit-haircolor') || null,
    birth_year:      numVal('edit-birth'),
    death_year:      numVal('edit-death'),
    is_fictional:    document.getElementById('edit-fictional')?.checked ?? false,
    is_animated:     document.getElementById('edit-animated')?.checked ?? false,
  };
  try {
    await api('PUT', `/data/characters/${encodeURIComponent(key)}`, body);
  } catch (e) { await modalAlert(e.message, true); return; }
  const idx = rawData.characters.findIndex(r => r.wikidata_id === key);
  if (idx >= 0) rawData.characters[idx] = { ...rawData.characters[idx], ...body };
  editKey = null; render();
}

async function del(key) {
  if (!await modalConfirm('Delete this record?')) return;
  let url;
  if (tab === 'characters') url = `/data/characters/${encodeURIComponent(key)}`;
  else if (tab === 'questions') url = `/data/questions/${key}`;
  else url = `/data/games/${key}`;
  try { await api('DELETE', url); } catch (e) { await modalAlert(e.message, true); return; }
  rawData[tab] = rawData[tab].filter(r => rowKey(r) !== key);
  updateCounts(); render();
}

async function reloadEngine() {
  try {
    await api('POST', '/engine/reload', {});
    await modalAlert('Engine reloaded — changes will take effect on the next game.');
  } catch (e) {
    await modalAlert(e.message, true);
  }
}

// ---------------------------------------------------------------------------
// Render
// ---------------------------------------------------------------------------

function render() {
  ['characters', 'questions', 'games'].forEach(t => {
    document.getElementById('tab-' + t).className = t === tab ? 'active' : '';
  });
  document.getElementById('new-btn').style.display = CAN_CREATE[tab] ? '' : 'none';

  const cols = COLS[tab];
  const rows = sorted(filtered());
  const p = curPage[tab];
  const pageRows = rows.slice(p * PER_PAGE, (p + 1) * PER_PAGE);
  const { col: sc, asc } = sortSt[tab];

  let h = '<table><thead><tr>';
  for (const c of cols) {
    const active = sc === c.key;
    h += `<th class="${active ? 'sorted' : ''}" onclick="sortBy('${c.key}')">`;
    h += c.label + (active ? (asc ? ' ▲' : ' ▼') : '') + '</th>';
  }
  h += '<th style="width:90px"></th></tr></thead><tbody>';

  if (creating && tab === 'characters') {
    h += '<tr id="new-row">';
    h += `<td><input id="new-name"         type="text"   placeholder="Name" /></td>`;
    h += `<td><input id="new-wikid"         type="text"   placeholder="Q12345" /></td>`;
    h += `<td>${gselect('new-gender', '')}</td>`;
    h += `<td><input id="new-citizenships"  type="text"   placeholder="Q30, Q145" /></td>`;
    h += `<td><input id="new-occupations"   type="text"   placeholder="Q639669" /></td>`;
    h += `<td><input id="new-series"        type="text"   placeholder="Q462" /></td>`;
    h += `<td><input id="new-genres"        type="text"   placeholder="Q11401" /></td>`;
    h += `<td><input id="new-memberof"      type="text"   placeholder="Q2735" /></td>`;
    h += `<td><input id="new-awards"        type="text"   placeholder="Q38104" /></td>`;
    h += `<td><input id="new-origin"        type="text"   placeholder="Q30" /></td>`;
    h += `<td><input id="new-haircolor"     type="text"   placeholder="Q1068878" /></td>`;
    h += `<td><input id="new-birth"         type="number" placeholder="1970" /></td>`;
    h += `<td><input id="new-death"         type="number" placeholder="" /></td>`;
    h += `<td><input id="new-fictional"     type="checkbox" /></td>`;
    h += `<td><input id="new-animated"      type="checkbox" /></td>`;
    h += `<td class="acts"><button onclick="saveNew()">Save</button><button onclick="cancelNew()">✕</button></td>`;
    h += '</tr>';
  }

  if (pageRows.length === 0) {
    h += `<tr class="empty-row"><td colspan="${cols.length + 1}">No records</td></tr>`;
  }

  for (const row of pageRows) {
    const key = rowKey(row);
    const isEdit = CAN_EDIT[tab] && editKey === key;
    h += '<tr' + (isEdit ? ' id="edit-row"' : '') + '>';

    if (isEdit && tab === 'characters') {
      h += `<td><input id="edit-name"         type="text"   value="${esc(row.name)}" /></td>`;
      h += `<td>${esc(String(row.wikidata_id))}</td>`;
      h += `<td>${gselect('edit-gender', row.gender || '')}</td>`;
      h += `<td><input id="edit-citizenships" type="text"   value="${esc(arrToTags(row.citizenship_ids))}" /></td>`;
      h += `<td><input id="edit-occupations"  type="text"   value="${esc(arrToTags(row.occupation_ids))}" /></td>`;
      h += `<td><input id="edit-series"       type="text"   value="${esc(arrToTags(row.series_ids))}" /></td>`;
      h += `<td><input id="edit-genres"       type="text"   value="${esc(arrToTags(row.genre_ids))}" /></td>`;
      h += `<td><input id="edit-memberof"     type="text"   value="${esc(arrToTags(row.member_of_ids))}" /></td>`;
      h += `<td><input id="edit-awards"       type="text"   value="${esc(arrToTags(row.award_ids))}" /></td>`;
      h += `<td><input id="edit-origin"       type="text"   value="${esc(arrToTags(row.country_of_origin_ids))}" /></td>`;
      h += `<td><input id="edit-haircolor"    type="text"   value="${esc(row.hair_color ?? '')}" /></td>`;
      h += `<td><input id="edit-birth"        type="number" value="${row.birth_year ?? ''}" /></td>`;
      h += `<td><input id="edit-death"        type="number" value="${row.death_year ?? ''}" /></td>`;
      h += `<td><input id="edit-fictional"    type="checkbox" ${row.is_fictional ? 'checked' : ''} /></td>`;
      h += `<td><input id="edit-animated"     type="checkbox" ${row.is_animated  ? 'checked' : ''} /></td>`;
    } else {
      for (const c of cols) {
        const raw = row[c.key];
        let cell;
        if (c.key === 'was_correct' || c.type === 'bool') {
          cell = raw === null || raw === undefined ? '—'
               : `<span class="${raw ? 'badge-yes' : 'badge-no'}">${raw ? 'yes' : 'no'}</span>`;
        } else {
          const display = c.fmt ? c.fmt(raw) : (raw ?? '—');
          cell = esc(String(display));
        }
        h += `<td>${cell}</td>`;
      }
    }

    h += '<td class="acts">';
    if (isEdit) {
      h += `<button onclick="saveEdit('${esc(String(key))}')">Save</button>`;
      h += `<button onclick="cancelEdit()">✕</button>`;
    } else {
      if (tab === 'games') h += `<button onclick="viewGame(${key})">View</button>`;
      if (CAN_EDIT[tab])   h += `<button onclick="startEdit('${esc(String(key))}')">Edit</button>`;
      if (CAN_DELETE[tab]) h += `<button class="btn-del" onclick="del('${esc(String(key))}')">Del</button>`;
    }
    h += '</td></tr>';
  }

  h += '</tbody></table>';

  const totalPages = Math.ceil(rows.length / PER_PAGE);
  h += '<div class="pg">';
  if (totalPages > 1) {
    h += `<button onclick="goPage(-1)" ${p === 0 ? 'disabled' : ''}>←</button>`;
    h += `<span>${p + 1} / ${totalPages}</span>`;
    h += `<button onclick="goPage(1)"  ${p >= totalPages - 1 ? 'disabled' : ''}>→</button>`;
    h += `<span style="margin-left:.25rem">(${rows.length} records)</span>`;
  } else {
    h += `<span>${rows.length} records</span>`;
  }
  h += '</div>';

  document.getElementById('table-wrap').innerHTML = h;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function rowKey(row) {
  return tab === 'characters' ? row.wikidata_id : row.id;
}

function filtered() {
  if (!filterTx) return rawData[tab];
  return rawData[tab].filter(r =>
    Object.values(r).some(v => v !== null && v !== undefined && String(v).toLowerCase().includes(filterTx))
  );
}

function sorted(rows) {
  const { col, asc } = sortSt[tab];
  if (!col) return rows;
  return [...rows].sort((a, b) => {
    const av = a[col], bv = b[col];
    if (av == null) return 1;
    if (bv == null) return -1;
    const cmp = typeof av === 'number' ? av - bv : String(av).localeCompare(String(bv));
    return asc ? cmp : -cmp;
  });
}

function gselect(id, current) {
  const opts = GENDER_OPTS.map(([v, l]) =>
    `<option value="${v}"${current === v ? ' selected' : ''}>${l}</option>`
  ).join('');
  return `<select id="${id}">${opts}</select>`;
}

function val(id) {
  const el = document.getElementById(id);
  return el ? el.value.trim() : '';
}

function numVal(id) {
  const v = val(id);
  return v ? parseInt(v, 10) : null;
}

function tagsVal(id) {
  return val(id).split(',').map(s => s.trim()).filter(Boolean);
}

function arrToTags(arr) {
  return Array.isArray(arr) ? arr.join(', ') : '';
}

function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

async function api(method, url, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const r = await fetch(url, opts);
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail ?? `HTTP ${r.status}`);
  return data;
}

// ---------------------------------------------------------------------------
// Modal
// ---------------------------------------------------------------------------

function _openModal(msg, isError, actions) {
  const msgEl = document.getElementById('modal-msg');
  const actEl = document.getElementById('modal-actions');
  msgEl.textContent = msg;
  msgEl.className = 'modal-msg' + (isError ? ' error' : '');
  actEl.innerHTML = '';
  for (const { label, primary, fn } of actions) {
    const btn = document.createElement('button');
    btn.textContent = label;
    if (!primary) { btn.className = 'btn-muted'; }
    btn.onclick = () => { _closeModal(); fn(); };
    actEl.appendChild(btn);
  }
  document.getElementById('modal-backdrop').classList.add('open');
}

function _closeModal() {
  document.getElementById('modal-backdrop').classList.remove('open');
}

function modalBackdropClick(e) {
  if (e.target === document.getElementById('modal-backdrop')) _closeModal();
}

function modalAlert(msg, isError = false) {
  return new Promise(resolve => {
    _openModal(msg, isError, [{ label: 'OK', primary: true, fn: resolve }]);
  });
}

function modalConfirm(msg) {
  return new Promise(resolve => {
    _openModal(msg, false, [
      { label: 'Cancel', primary: false, fn: () => resolve(false) },
      { label: 'Delete',  primary: true,  fn: () => resolve(true)  },
    ]);
  });
}

async function viewGame(gameId) {
  let rows;
  try {
    rows = await api('GET', `/data/games/${gameId}/detail`);
  } catch (e) {
    await modalAlert(e.message, true);
    return;
  }
  if (!rows.length) {
    await modalAlert('No questions recorded for this game.');
    return;
  }
  const ANSWER_COLOR = { yes: '#4d4', probably: '#8d8', maybe: '#888', 'probably not': '#d84', no: '#f55' };
  const lines = rows.map((r, i) =>
    `<div style="margin-bottom:.4rem">
       <span style="color:#555">${i + 1}.</span> ${esc(r.question)}
       <span style="margin-left:.5rem;color:${ANSWER_COLOR[r.answer_label] ?? '#888'}">${r.answer_label}</span>
     </div>`
  ).join('');
  const msgEl = document.getElementById('modal-msg');
  const actEl = document.getElementById('modal-actions');
  msgEl.innerHTML = `<div style="max-height:60vh;overflow-y:auto;font-size:.85rem">${lines}</div>`;
  msgEl.className = 'modal-msg';
  actEl.innerHTML = '';
  const btn = document.createElement('button');
  btn.textContent = 'Close';
  btn.onclick = _closeModal;
  actEl.appendChild(btn);
  document.getElementById('modal-backdrop').classList.add('open');
}

// ---------------------------------------------------------------------------
// Refresh
// ---------------------------------------------------------------------------

async function refreshData() {
  const btn = document.getElementById('refresh-btn');
  btn.disabled = true;
  btn.textContent = '↻ Refreshing…';
  try {
    const [chars, qs, games] = await Promise.all([
      api('GET', '/data/characters'),
      api('GET', '/data/questions'),
      api('GET', '/data/games'),
    ]);
    rawData.characters = chars;
    rawData.questions  = qs;
    rawData.games      = games;
    editKey  = null;
    creating = false;
    updateCounts();
    render();
  } catch (e) {
    await modalAlert(e.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = '↻ Refresh';
  }
}

init();
