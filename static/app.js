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
  loadAisStatus();
  loadAisVessels();
  loadDarkPeriods();
  loadStsEvents();
  // Defer map init so the rest of the page loads first
  setTimeout(initMap, 1500);

  // Allow Enter key to trigger screening
  document.getElementById('screen-query').addEventListener('keydown', e => {
    if (e.key === 'Enter') runScreening();
  });

  // Auto-refresh AIS status every 15 s
  setInterval(loadAisStatus,  15_000);
  // Auto-refresh vessel roster every 30 s
  setInterval(loadAisVessels, 30_000);
});

// ── Stats ─────────────────────────────────────────────

async function loadStats() {
  try {
    const data = await apiFetch('/api/stats');
    const by = data.by_list || {};

    setText('stat-ofac',          fmt(by['OFAC_SDN']           || 0));
    setText('stat-opensanctions', fmt(by['OpenSanctions']       || 0));
    setText('stat-ais-vessels',   fmt(data.total_ais_vessels    || 0));
    setText('stat-dark-periods',  fmt(data.total_dark_periods   || 0));
    setText('stat-sts-events',    fmt(data.total_sts_events     || 0));

    setText('hdr-total',
      `${fmt(data.total_sanctions)} sanctions · ${fmt(data.total_ais_vessels || 0)} AIS vessels`);

    // Auto-boot: silently populate empty data sources on first load
    autoBootSequence(by['OFAC_SDN'] || 0, by['OpenSanctions'] || 0);
  } catch (e) {
    console.error('Stats load failed', e);
  }
}

// Run once on page load — silently ingests empty sources and tries AIS connect
let _bootDone = false;
async function autoBootSequence(ofacCount, osCount) {
  if (_bootDone) return;
  _bootDone = true;

  const statusEl = document.getElementById('ingest-status');
  let ranIngest = false;

  // ── Sanctions ingests (only if empty) ──────────────────────────────────
  if (ofacCount === 0) {
    statusEl.innerHTML = '<span class="text-muted">⟳ Auto-fetching OFAC SDN (first load)…</span>';
    try {
      const r = await apiFetch('/api/ingest/ofac', { method: 'POST' });
      if (r.status === 'success') {
        statusEl.innerHTML =
          `<span class="text-success">✓ OFAC SDN: ${fmt(r.inserted)} records loaded</span>`;
        ranIngest = true;
      }
    } catch (e) { console.warn('Auto OFAC ingest failed', e); }
  }

  if (osCount === 0) {
    statusEl.innerHTML =
      '<span class="text-muted">⟳ Auto-fetching OpenSanctions (~30–90 s)…</span>';
    try {
      const r = await apiFetch('/api/ingest/opensanctions', { method: 'POST' });
      if (r.status === 'success') {
        statusEl.innerHTML =
          `<span class="text-success">✓ OpenSanctions: ${fmt(r.inserted)} records loaded</span>`;
        ranIngest = true;
      }
    } catch (e) { console.warn('Auto OpenSanctions ingest failed', e); }
  }

  if (ranIngest) {
    // Reconcile after fresh ingest, then refresh all panels
    try { await apiFetch('/api/reconcile', { method: 'POST' }); } catch (_) {}
    await Promise.all([loadStats(), loadSanctions(), loadIngestLog()]);
    statusEl.innerHTML = '<span class="text-success">✓ Data loaded and reconciled.</span>';
  }

  // ── AIS auto-connect (backend uses AISSTREAM_API_KEY env var if no key sent) ─
  try {
    const aisStatus = await apiFetch('/api/ais/status');
    if (!aisStatus.running) {
      // Send empty key — app.py falls back to AISSTREAM_API_KEY env var
      const r = await apiFetch('/api/ais/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: '' }),
      });
      if (r.status === 'started') loadAisStatus();
    }
  } catch (_) { /* No key configured — silently skip */ }
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

const _ROLE_COLOUR = {
  owner:         '#c0392b',
  operator:      '#e67e22',
  manager:       '#2980b9',
  past_owner:    '#888',
  past_operator: '#888',
  past_manager:  '#888',
};
const _ROLE_ORDER = ['owner','operator','manager','past_owner','past_operator','past_manager'];

function ownershipDetailsHtml(hit) {
  const hasOwnership = Array.isArray(hit.ownership)    && hit.ownership.length    > 0;
  const hasFlagHist  = Array.isArray(hit.flag_history) && hit.flag_history.length > 0;
  const hasMeta      = hit.build_year || hit.call_sign || hit.gross_tonnage;
  if (!hasOwnership && !hasFlagHist && !hasMeta) return '';

  let body = '';

  // Meta row — build year / call sign / tonnage
  if (hasMeta) {
    const parts = [];
    if (hit.build_year)    parts.push(`Built: ${hit.build_year}`);
    if (hit.call_sign)     parts.push(`Call sign: ${escHtml(hit.call_sign)}`);
    if (hit.gross_tonnage) parts.push(`${hit.gross_tonnage.toLocaleString()} GT`);
    body += `<div class="ownership-meta">${parts.join(' · ')}</div>`;
  }

  // Ownership rows grouped by role
  if (hasOwnership) {
    const grouped = {};
    for (const e of hit.ownership) {
      (grouped[e.role] = grouped[e.role] || []).push(e.entity_name);
    }
    const roles = [..._ROLE_ORDER, ...Object.keys(grouped).filter(r => !_ROLE_ORDER.includes(r))];
    for (const role of roles) {
      if (!grouped[role]) continue;
      const colour = _ROLE_COLOUR[role] || '#888';
      const label  = role.replace(/_/g, ' ');
      body += `<div class="ownership-row">
        <span class="ownership-role" style="color:${colour}">${escHtml(label)}</span>
        ${grouped[role].map(n => `<span class="ownership-name">${escHtml(n)}</span>`).join('')}
      </div>`;
    }
  }

  // Past flags row
  if (hasFlagHist) {
    const flags = [...new Set(hit.flag_history.map(f => f.flag_state).filter(Boolean))];
    if (flags.length) {
      body += `<div class="ownership-row">
        <span class="ownership-role" style="color:#888">past flags</span>
        ${flags.map(f => `<span class="ownership-flag">${escHtml(f)}</span>`).join('')}
      </div>`;
    }
  }

  return `<details class="ownership-details">
    <summary>Ownership &amp; History</summary>
    <div class="ownership-body">${body}</div>
  </details>`;
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
    const aliases = Array.isArray(hit.aliases) && hit.aliases.length
      ? `<div class="hit-meta">AKA: ${hit.aliases.slice(0, 5).map(escHtml).join(' · ')}</div>`
      : '';
    const imoStr  = hit.imo_number
      ? `<span class="text-info">IMO ${hit.imo_number}</span> · ` : '';
    const mmsiStr = hit.mmsi ? `MMSI ${hit.mmsi} · ` : '';
    const flagStr = hit.flag_state ? `Flag: ${escHtml(hit.flag_state)} · ` : '';
    const typeStr = hit.vessel_type || hit.entity_type || '';

    // Show how many individual list entries this canonical record has
    const memberCount = Array.isArray(hit.memberships) ? hit.memberships.length : 0;
    const memberNote  = memberCount > 1
      ? `<span class="text-muted" style="font-size:.68rem;font-weight:400;">
           (${memberCount} list entries)
         </span>`
      : '';

    html += `
      <div class="hit-card">
        <div style="display:flex;align-items:baseline;gap:.4rem;flex-wrap:wrap;">
          ${sourceTagBadges(hit.source_tags)}
          <span class="hit-name">${escHtml(hit.entity_name)}</span>
          ${memberNote}
        </div>
        <div class="hit-meta">
          ${imoStr}${mmsiStr}${flagStr}${escHtml(typeStr)}
        </div>
        ${hit.program ? `<div class="hit-meta text-accent">Program: ${escHtml(hit.program)}</div>` : ''}
        ${aliases}
        ${ownershipDetailsHtml(hit)}
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

  tbody.innerHTML = rows.map(r => `
    <tr onclick="screenFromTable('${escAttr(r.imo_number || r.entity_name)}')" style="cursor:pointer;">
      <td style="white-space:nowrap;">${sourceTagBadges(r.source_tags)}</td>
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

// ── AIS Feed ──────────────────────────────────────────

async function loadAisStatus() {
  try {
    const s = await apiFetch('/api/ais/status');
    const badge = document.getElementById('ais-status-badge');
    const startBtn = document.getElementById('btn-ais-start');
    const stopBtn  = document.getElementById('btn-ais-stop');

    if (s.running) {
      badge.textContent = 'LIVE';
      badge.className = 'badge badge-green';
      startBtn.disabled = true;
      stopBtn.disabled  = false;
    } else {
      badge.textContent = 'OFFLINE';
      badge.className = 'badge badge-muted';
      startBtn.disabled = false;
      stopBtn.disabled  = true;
    }
    setText('ais-msg-rate',   s.msgs_per_min != null ? fmt(Math.round(s.msgs_per_min)) : '—');
    setText('ais-total-msgs', `${fmt(s.total_messages || 0)} total`);
  } catch (e) {
    console.error('AIS status failed', e);
  }
}

async function aisStart() {
  const key = document.getElementById('ais-api-key').value.trim();
  const btn = document.getElementById('btn-ais-start');
  btn.disabled = true;
  btn.innerHTML = 'Connecting… <span class="spinner"></span>';
  try {
    const body = key ? { api_key: key } : {};
    await apiFetch('/api/ais/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    await loadAisStatus();
  } catch (e) {
    alert(`AIS start failed: ${e.message}`);
    btn.disabled = false;
    btn.textContent = 'Connect';
  }
}

async function aisStop() {
  document.getElementById('btn-ais-stop').disabled = true;
  try {
    await apiFetch('/api/ais/stop', { method: 'POST' });
    await loadAisStatus();
  } catch (e) {
    console.error('AIS stop failed', e);
    document.getElementById('btn-ais-stop').disabled = false;
  }
}

async function loadAisVessels() {
  const sanctionedOnly = document.getElementById('ais-sanctioned-only')?.checked;
  const params = new URLSearchParams({ limit: 200 });
  if (sanctionedOnly) params.set('sanctioned_only', '1');

  const tbody = document.getElementById('ais-vessels-tbody');
  try {
    const rows = await apiFetch(`/api/ais/vessels?${params}`);
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="8" class="empty-state">No AIS vessels yet.</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(r => {
      const sanctBadge = r.sanctions_hit
        ? '<span class="badge badge-red" title="Sanctions hit">⚑</span>' : '';
      const sog = r.last_sog != null ? `${r.last_sog.toFixed(1)} kn` : '—';
      const lat = r.last_lat != null ? r.last_lat.toFixed(3) : '—';
      const lon = r.last_lon != null ? r.last_lon.toFixed(3) : '—';
      const seen = r.last_seen ? new Date(r.last_seen).toLocaleString() : '—';
      return `<tr onclick="document.getElementById('screen-query').value='${escAttr(r.imo_number||r.mmsi)}';runScreening()" style="cursor:pointer;">
        <td class="imo">${escHtml(r.mmsi)}</td>
        <td class="name" title="${escAttr(r.vessel_name||'')}">${escHtml(r.vessel_name||'—')}</td>
        <td class="imo">${r.imo_number ? escHtml(r.imo_number) : '<span class="text-muted">—</span>'}</td>
        <td>${lat}</td>
        <td>${lon}</td>
        <td>${sog}</td>
        <td class="log-time">${escHtml(seen)}</td>
        <td>${sanctBadge}</td>
      </tr>`;
    }).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-danger" style="padding:.5rem;">Error: ${escHtml(e.message)}</td></tr>`;
  }
}

// ── Dark Periods ──────────────────────────────────────

async function loadDarkPeriods() {
  const riskFilter = document.getElementById('dark-risk-filter')?.value || '';
  const params = new URLSearchParams({ limit: 200 });
  if (riskFilter) params.set('risk_level', riskFilter);

  const tbody = document.getElementById('dark-periods-tbody');
  try {
    const rows = await apiFetch(`/api/dark-periods?${params}`);
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="8" class="empty-state">No dark periods detected yet.</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(r => {
      const riskCls = {
        CRITICAL: 'badge-red',
        HIGH:     'badge-red',
        MEDIUM:   'badge-orange',
        LOW:      'badge-muted',
      }[r.risk_level] || 'badge-muted';
      const sanc = r.sanctions_hit ? '⚑' : '';
      const dist = r.distance_km != null ? r.distance_km.toFixed(0) : '—';
      const hrs  = r.gap_hours   != null ? r.gap_hours.toFixed(1)   : '—';
      const ts   = r.gap_start   ? new Date(r.gap_start).toLocaleString() : '—';
      return `<tr>
        <td><span class="badge ${riskCls}">${escHtml(r.risk_level||'')}</span></td>
        <td class="imo">${escHtml(r.mmsi)}</td>
        <td class="name" title="${escAttr(r.vessel_name||'')}">${escHtml(r.vessel_name||'—')}</td>
        <td class="log-time">${escHtml(ts)}</td>
        <td>${hrs}</td>
        <td>${dist}</td>
        <td>${r.risk_zone ? escHtml(r.risk_zone) : '<span class="text-muted">—</span>'}</td>
        <td style="color:var(--danger)">${sanc}</td>
      </tr>`;
    }).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-danger" style="padding:.5rem;">Error: ${escHtml(e.message)}</td></tr>`;
  }
}

async function runDarkDetect() {
  const minHours = parseFloat(document.getElementById('dark-min-hours').value || '2');
  const btn = document.getElementById('btn-detect-dark');
  const statusEl = document.getElementById('dark-detect-status');

  btn.disabled = true;
  btn.innerHTML = 'Detecting… <span class="spinner"></span>';
  statusEl.innerHTML = '<span class="text-muted">Scanning all active MMSIs…</span>';

  try {
    const result = await apiFetch('/api/dark-periods/detect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ min_hours: minHours }),
    });
    statusEl.innerHTML =
      `<span class="text-success">✓ Scanned ${fmt(result.mmsis_scanned||0)} MMSIs — ` +
      `${fmt(result.total_periods_found||0)} dark periods found</span>`;
    await Promise.all([loadDarkPeriods(), loadStats()]);
  } catch (e) {
    statusEl.innerHTML = `<span class="text-danger">Error: ${escHtml(e.message)}</span>`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Run Detection';
  }
}

// ── STS Events ────────────────────────────────────────

async function loadStsEvents() {
  const riskFilter    = document.getElementById('sts-risk-filter')?.value    || '';
  const sanctionsOnly = document.getElementById('sts-sanctions-only')?.checked;
  const params = new URLSearchParams({ limit: 200 });
  if (riskFilter)    params.set('risk_level', riskFilter);
  if (sanctionsOnly) params.set('sanctions_only', '1');

  const tbody = document.getElementById('sts-events-tbody');
  try {
    const rows = await apiFetch(`/api/sts/events?${params}`);
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="11" class="empty-state">No STS events detected yet — run detection above.</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(r => {
      const riskCls = {
        CRITICAL: 'badge-red',
        HIGH:     'badge-red',
        MEDIUM:   'badge-orange',
        LOW:      'badge-muted',
      }[r.risk_level] || 'badge-muted';
      const sanc  = r.sanctions_hit ? '<span class="badge badge-red" title="Sanctions hit">⚑</span>' : '';
      const dist  = r.distance_m != null ? Math.round(r.distance_m) + ' m' : '—';
      const sog1  = r.sog1 != null ? r.sog1.toFixed(1) + ' kn' : '—';
      const sog2  = r.sog2 != null ? r.sog2.toFixed(1) + ' kn' : '—';
      const ts    = r.event_ts ? new Date(r.event_ts).toLocaleString() : '—';
      const v1    = r.vessel_name1 || r.mmsi1;
      const v2    = r.vessel_name2 || r.mmsi2;
      return `<tr>
        <td><span class="badge ${riskCls}">${escHtml(r.risk_level||'')}</span></td>
        <td class="name" title="${escAttr(r.vessel_name1||'')}">${escHtml(v1)}</td>
        <td class="imo">${escHtml(r.mmsi1)}</td>
        <td class="name" title="${escAttr(r.vessel_name2||'')}">${escHtml(v2)}</td>
        <td class="imo">${escHtml(r.mmsi2)}</td>
        <td class="log-time">${escHtml(ts)}</td>
        <td>${dist}</td>
        <td>${sog1}</td>
        <td>${sog2}</td>
        <td>${r.risk_zone ? escHtml(r.risk_zone) : '<span class="text-muted">—</span>'}</td>
        <td>${sanc}</td>
      </tr>`;
    }).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="11" class="text-danger" style="padding:.5rem;">Error: ${escHtml(e.message)}</td></tr>`;
  }
}

async function runStsDetect() {
  const hoursBack = parseInt(document.getElementById('sts-hours-back').value || '48', 10);
  const btn       = document.getElementById('btn-sts-detect');
  const statusEl  = document.getElementById('sts-detect-status');

  btn.disabled = true;
  btn.innerHTML = 'Detecting… <span class="spinner"></span>';
  statusEl.innerHTML = `<span class="text-muted">Scanning last ${hoursBack} h of AIS positions…</span>`;

  try {
    const result = await apiFetch('/api/sts/detect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hours_back: hoursBack }),
    });
    const s = result.summary || {};
    const critHigh = (s.CRITICAL || 0) + (s.HIGH || 0);
    statusEl.innerHTML =
      `<span class="${critHigh > 0 ? 'text-danger' : 'text-success'}">` +
      `✓ ${fmt(result.events_found)} events — ` +
      `${s.CRITICAL||0} CRITICAL · ${s.HIGH||0} HIGH · ${s.MEDIUM||0} MEDIUM · ${s.LOW||0} LOW` +
      `</span>`;
    await Promise.all([loadStsEvents(), loadStats()]);
  } catch (e) {
    statusEl.innerHTML = `<span class="text-danger">Error: ${escHtml(e.message)}</span>`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Run Detection';
  }
}

// ── NOAA Ingest ───────────────────────────────────────

async function runNoaaIngest() {
  const year  = parseInt(document.getElementById('noaa-year').value,  10);
  const month = parseInt(document.getElementById('noaa-month').value, 10);
  const zone  = parseInt(document.getElementById('noaa-zone').value,  10);
  const btn   = document.getElementById('btn-noaa-ingest');
  const statusEl = document.getElementById('noaa-status');

  btn.disabled = true;
  btn.innerHTML = 'Downloading… <span class="spinner"></span>';
  statusEl.innerHTML = '<span class="text-muted">Fetching NOAA CSV (may take 1–3 min for large zones)…</span>';

  try {
    const result = await apiFetch('/api/ingest/noaa', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ year, month, zone }),
    });
    if (result.status === 'success') {
      statusEl.innerHTML =
        `<span class="text-success">✓ ${fmt(result.rows_inserted||0)} positions inserted ` +
        `(${fmt(result.rows_processed||0)} rows scanned)</span>`;
    } else {
      statusEl.innerHTML = `<span class="text-danger">✗ ${escHtml(result.error||'Unknown error')}</span>`;
    }
    await Promise.all([loadAisVessels(), loadStats(), loadIngestLog()]);
  } catch (e) {
    statusEl.innerHTML = `<span class="text-danger">Request failed: ${escHtml(e.message)}</span>`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Load NOAA CSV';
  }
}

// ── Source-tag badge helpers ───────────────────────────

/**
 * Map a source-tag display label to a CSS badge class.
 * Labels come from normalize.py _DATASET_LABELS.
 */
function tagBadgeClass(tag) {
  if (tag === 'OFAC SDN' || tag === 'OFAC CONS') return 'badge-red';
  if (tag === 'UN SC'    || tag === 'Interpol')   return 'badge-orange';
  if (tag.startsWith('EU') || tag.startsWith('UK')) return 'badge-blue';
  return 'badge-muted';
}

/**
 * Render an array of source-tag strings as HTML badge pills.
 * Falls back to a neutral dash if the array is empty / missing.
 */
function sourceTagBadges(tags) {
  if (!Array.isArray(tags) || !tags.length) {
    return '<span class="badge badge-muted">—</span>';
  }
  return tags
    .map(t => `<span class="badge ${tagBadgeClass(t)}" title="${escAttr(t)}">${escHtml(t)}</span>`)
    .join(' ');
}

// ── Reconciliation ─────────────────────────────────────

async function runReconcile() {
  const btn      = document.getElementById('btn-reconcile');
  const statusEl = document.getElementById('reconcile-status');

  btn.disabled = true;
  btn.innerHTML = 'Running… <span class="spinner"></span>';
  statusEl.innerHTML = '<span class="text-muted">Merging duplicate canonical records…</span>';

  try {
    const result = await apiFetch('/api/reconcile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    if (result.status === 'success') {
      const t1    = result.tier1_imo_merges  || 0;
      const t2    = result.tier2_mmsi_merges || 0;
      const total = t1 + t2;
      statusEl.innerHTML = total > 0
        ? `<span class="text-success">✓ ${total} duplicate(s) merged — ` +
          `${t1} IMO collision${t1 !== 1 ? 's' : ''} · ${t2} MMSI→IMO</span>`
        : `<span class="text-success">✓ No duplicates found — canonical data is clean</span>`;
      await Promise.all([loadStats(), loadSanctions()]);
    } else {
      statusEl.innerHTML =
        `<span class="text-danger">✗ ${escHtml(result.error || 'Unknown error')}</span>`;
    }
  } catch (e) {
    statusEl.innerHTML = `<span class="text-danger">Error: ${escHtml(e.message)}</span>`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Reconcile';
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
