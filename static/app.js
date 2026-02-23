/* Maritime OSINT — dashboard JS */

'use strict';

// ── Sanctions table pagination state ─────────────────

const PAGE_SIZE = 100;
let sanctionsOffset = 0;

// ── Init ──────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  loadStats();
  loadSanctions();
  loadIngestLog();

  // Allow Enter key to trigger screening
  document.getElementById('screen-query').addEventListener('keydown', e => {
    if (e.key === 'Enter') runScreening();
  });
});

// ── Stats ─────────────────────────────────────────────

async function loadStats() {
  try {
    const data = await apiFetch('/api/stats');
    const by = data.by_list || {};

    setText('stat-ofac',           fmt(by['OFAC_SDN']      || 0));
    setText('stat-opensanctions',  fmt(by['OpenSanctions'] || 0));
    setText('stat-vessels',        fmt(data.total_vessels  || 0));
    setText('stat-with-imo',       fmt((data.by_list
      ? Object.values(data.by_list).reduce((a, b) => a + b, 0)
      : data.total_sanctions) || 0));

    setText('hdr-total',
      `${fmt(data.total_sanctions)} entries · ${fmt(data.total_vessels)} vessels`);
  } catch (e) {
    console.error('Stats load failed', e);
  }
}

// ── Screening ─────────────────────────────────────────

async function runScreening() {
  const query = document.getElementById('screen-query').value.trim();
  if (!query) return;

  const btn = document.getElementById('screen-btn');
  btn.disabled = true;
  btn.innerHTML = 'SCREENING <span class="spinner"></span>';

  const el = document.getElementById('screen-result');
  el.innerHTML = '';

  try {
    const result = await apiFetch('/api/screen', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    });
    renderScreenResult(el, result);
  } catch (e) {
    el.innerHTML = `<p class="text-danger" style="margin-top:.5rem;">Error: ${escHtml(e.message)}</p>`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'SCREEN';
  }
}

function renderScreenResult(el, result) {
  if (result.error) {
    el.innerHTML = `<p class="text-danger" style="margin-top:.5rem;">${escHtml(result.error)}</p>`;
    return;
  }

  const qtype = result.query_type || 'name';
  const qtypeLabel = { imo: 'IMO', mmsi: 'MMSI', name: 'name' }[qtype] || qtype;

  if (!result.sanctioned) {
    el.innerHTML = `
      <p class="result-clear" style="margin-top:.75rem;">
        ✓ No sanctions matches found for <strong>${escHtml(result.query)}</strong>
        <span class="text-muted">(searched by ${qtypeLabel})</span>
      </p>
      <p class="text-muted" style="font-size:.72rem;margin-top:.3rem;">
        Not listed on OFAC SDN or OpenSanctions. Absence does not confirm clean status —
        run full due diligence before transacting.
      </p>`;
    return;
  }

  let html = `
    <div class="result-sanctioned" style="margin-top:.75rem;font-weight:700;">
      ⚠ SANCTIONS MATCH — ${result.total_hits} hit${result.total_hits !== 1 ? 's' : ''}
      for <em>${escHtml(result.query)}</em>
      <span class="text-muted" style="font-weight:400;">(by ${qtypeLabel})</span>
    </div>`;

  for (const hit of result.hits) {
    const listClass = hit.list_name === 'OFAC_SDN' ? 'list-ofac' : 'list-opensanctions';
    const aliases = Array.isArray(hit.aliases) && hit.aliases.length
      ? `<div class="hit-meta">AKA: ${hit.aliases.slice(0, 5).map(escHtml).join(' · ')}</div>`
      : '';
    const imoStr = hit.imo_number
      ? `<span class="text-info">IMO ${hit.imo_number}</span> · ` : '';
    const mmsiStr = hit.mmsi ? `MMSI ${hit.mmsi} · ` : '';
    const flagStr = hit.flag_state ? `Flag: ${hit.flag_state} · ` : '';
    const typeStr = hit.vessel_type || hit.entity_type || '';

    html += `
      <div class="hit-card">
        <div>
          <span class="hit-badge ${listClass}">${escHtml(hit.list_name)}</span>
          <span class="hit-name">${escHtml(hit.entity_name)}</span>
        </div>
        <div class="hit-meta">
          ${imoStr}${mmsiStr}${flagStr}${escHtml(typeStr)}
        </div>
        ${hit.program ? `<div class="hit-meta text-accent">Program: ${escHtml(hit.program)}</div>` : ''}
        ${aliases}
        <div class="confidence">${escHtml(hit.match_confidence || '')}</div>
      </div>`;
  }

  el.innerHTML = html;
}

// ── Sanctions table ───────────────────────────────────

let _debounceTimer;
function debounceLoadSanctions() {
  clearTimeout(_debounceTimer);
  _debounceTimer = setTimeout(() => {
    sanctionsOffset = 0;
    loadSanctions();
  }, 300);
}

function changePage(dir) {
  sanctionsOffset = Math.max(0, sanctionsOffset + dir * PAGE_SIZE);
  loadSanctions();
}

async function loadSanctions() {
  const q      = document.getElementById('filter-q').value.trim();
  const list   = document.getElementById('filter-list').value;
  const type   = document.getElementById('filter-type').value;
  const prog   = document.getElementById('filter-prog').value.trim();

  const params = new URLSearchParams({
    limit:  PAGE_SIZE,
    offset: sanctionsOffset,
  });
  if (q)    params.set('q', q);
  if (list) params.set('list_name', list);
  if (type) params.set('entity_type', type);
  if (prog) params.set('program', prog);

  const tbody = document.getElementById('sanctions-tbody');
  tbody.innerHTML = '<tr><td colspan="7" class="empty-state">Loading…</td></tr>';

  try {
    const rows = await apiFetch(`/api/sanctions?${params}`);
    renderSanctionsTable(rows);
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-danger" style="padding:.75rem;">Error: ${escHtml(e.message)}</td></tr>`;
  }
}

function renderSanctionsTable(rows) {
  const tbody = document.getElementById('sanctions-tbody');

  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No entries found. Run an ingest to populate the database.</td></tr>';
    document.getElementById('sanctions-count').textContent = '';
    document.getElementById('sanctions-page-info').textContent = '';
    document.getElementById('sanctions-prev').disabled = true;
    document.getElementById('sanctions-next').disabled = true;
    return;
  }

  const start = sanctionsOffset + 1;
  const end   = sanctionsOffset + rows.length;
  document.getElementById('sanctions-page-info').textContent =
    `Showing ${start}–${end}`;
  document.getElementById('sanctions-count').textContent =
    `${rows.length} rows`;
  document.getElementById('sanctions-prev').disabled = sanctionsOffset === 0;
  document.getElementById('sanctions-next').disabled = rows.length < PAGE_SIZE;

  const listBadge = name => {
    const cls = name === 'OFAC_SDN' ? 'badge-red' : 'badge-blue';
    const label = name === 'OFAC_SDN' ? 'OFAC' : 'OS';
    return `<span class="badge ${cls}">${label}</span>`;
  };

  tbody.innerHTML = rows.map(r => `
    <tr onclick="screenFromTable('${escAttr(r.imo_number || r.entity_name)}')" style="cursor:pointer;">
      <td>${listBadge(r.list_name)}</td>
      <td class="name" title="${escAttr(r.entity_name)}">${escHtml(r.entity_name)}</td>
      <td class="imo">${r.imo_number ? escHtml(r.imo_number) : '<span class="text-muted">—</span>'}</td>
      <td>${r.mmsi ? escHtml(r.mmsi) : '<span class="text-muted">—</span>'}</td>
      <td>${r.entity_type ? `<span class="badge badge-muted">${escHtml(r.entity_type)}</span>` : ''}</td>
      <td class="flag">${r.flag_state ? escHtml(r.flag_state) : '<span class="text-muted">—</span>'}</td>
      <td class="prog">${r.program ? escHtml(r.program.split(',')[0].trim()) : '<span class="text-muted">—</span>'}</td>
    </tr>`).join('');
}

function screenFromTable(query) {
  document.getElementById('screen-query').value = query;
  document.getElementById('screen-query').scrollIntoView({ behavior: 'smooth', block: 'center' });
  runScreening();
}

// ── Ingestion ─────────────────────────────────────────

async function runIngest(source) {
  const btnId = `btn-ingest-${source}`;
  const btn = document.getElementById(btnId);
  const statusEl = document.getElementById('ingest-status');

  btn.disabled = true;
  btn.innerHTML = `Fetching… <span class="spinner"></span>`;
  statusEl.innerHTML = `<span class="text-muted">Downloading and parsing ${source.toUpperCase()}…</span>`;

  // Warn user about expected time for OpenSanctions
  if (source === 'opensanctions') {
    statusEl.innerHTML += ' <span class="text-muted">(streaming large dataset, ~30–90 s)</span>';
  }

  try {
    const result = await apiFetch(`/api/ingest/${source}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });

    if (result.status === 'success') {
      statusEl.innerHTML =
        `<span class="text-success">✓ ${result.source}: ${fmt(result.inserted)} inserted, ` +
        `${fmt(result.updated)} updated (${fmt(result.processed)} processed)</span>`;
    } else {
      statusEl.innerHTML =
        `<span class="text-danger">✗ ${result.source}: ${escHtml(result.error || 'Unknown error')}</span>`;
    }

    // Refresh stats, table and log
    await Promise.all([loadStats(), loadSanctions(), loadIngestLog()]);
  } catch (e) {
    statusEl.innerHTML = `<span class="text-danger">Request failed: ${escHtml(e.message)}</span>`;
  } finally {
    btn.disabled = false;
    btn.textContent = source === 'ofac' ? 'Fetch OFAC SDN' : 'Fetch OpenSanctions';
  }
}

async function loadIngestLog() {
  try {
    const logs = await apiFetch('/api/ingest/log');
    const ul = document.getElementById('ingest-log-list');
    if (!logs.length) {
      ul.innerHTML = '<li><span class="text-muted">No ingests yet — click a Fetch button above.</span></li>';
      return;
    }
    ul.innerHTML = logs.slice(0, 10).map(l => {
      const statusCls = l.status === 'success' ? 'log-ok' : 'log-err';
      const countStr  = l.status === 'success'
        ? `+${fmt(l.records_inserted)} ins, ~${fmt(l.records_updated)} upd`
        : l.error_message || 'error';
      const ts = l.completed_at ? new Date(l.completed_at).toLocaleString() : '—';
      return `<li>
        <span class="log-src">${escHtml(l.source_name)}</span>
        <span class="${statusCls} log-count">${escHtml(countStr)}</span>
        <span class="log-time">${escHtml(ts)}</span>
      </li>`;
    }).join('');
  } catch (e) {
    console.error('Ingest log failed', e);
  }
}

// ── Utilities ─────────────────────────────────────────

async function apiFetch(url, opts = {}) {
  const resp = await fetch(url, opts);
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.error || `HTTP ${resp.status}`);
  }
  return resp.json();
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function fmt(n) {
  return Number(n).toLocaleString();
}

function escHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escAttr(str) {
  return escHtml(str).replace(/'/g, '&#39;');
}
