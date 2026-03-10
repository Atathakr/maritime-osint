// static/ranking.js — Vessel risk ranking table (Phase 5 FE-1, FE-2, FE-3)
// No inline scripts — all DOM logic here (CSP enforcement active).

(function () {
  'use strict';

  // ── State ────────────────────────────────────────────────────────────────
  var _rankingData     = [];
  var _rankingFiltered = [];
  var _rankingSortKey  = 'composite_score';
  var _rankingSortAsc  = false;    // default: score descending
  var _rankingPage     = 0;
  var _rankingPageSize = 50;

  var RISK_NUM = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1, UNKNOWN: 0 };

  // ── Helpers ──────────────────────────────────────────────────────────────

  function escHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function relativeTime(isoStr) {
    if (!isoStr) return '—';
    var diffMs  = Date.now() - new Date(isoStr).getTime();
    var diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 2)  return 'just now';
    if (diffMin < 60) return diffMin + 'm ago';
    var h = Math.floor(diffMin / 60);
    if (h < 24) return h + 'h ago';
    return Math.floor(h / 24) + 'd ago';
  }

  function scoreToRiskLevel(score) {
    if (score === null || score === undefined) return 'UNKNOWN';
    if (score >= 100) return 'CRITICAL';
    if (score >= 70)  return 'HIGH';
    if (score >= 40)  return 'MEDIUM';
    return 'LOW';
  }

  function riskBadgeHtml(level) {
    var cls = { CRITICAL: 'risk-badge-critical', HIGH: 'risk-badge-high',
                MEDIUM: 'risk-badge-medium', LOW: 'risk-badge-low' }[level] || 'badge-muted';
    return '<span class="risk-badge ' + cls + '">' + escHtml(level || 'UNKNOWN') + '</span>';
  }

  // ── Data loading ─────────────────────────────────────────────────────────

  function loadRankingTable() {
    fetch('/api/vessels/ranking?limit=500')
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (data) {
        _rankingData = (data.vessels || []).map(function (v) {
          var ev = Object.keys(v.indicator_json || {}).length;
          return Object.assign({}, v, {
            evidence_count: ev,
            risk_level: scoreToRiskLevel(v.composite_score),
            risk_num: RISK_NUM[scoreToRiskLevel(v.composite_score)] || 0,
          });
        });
        applyRankingFilter();
      })
      .catch(function (err) {
        var tbody = document.getElementById('ranking-tbody');
        if (tbody) tbody.innerHTML = '<tr><td colspan="8" class="text-muted" style="text-align:center;">Failed to load ranking data.</td></tr>';
      });
  }

  // ── Filter ───────────────────────────────────────────────────────────────

  function applyRankingFilter() {
    var input = document.getElementById('ranking-filter');
    var q = input ? input.value.trim().toLowerCase() : '';
    _rankingFiltered = q
      ? _rankingData.filter(function (v) {
          return (v.entity_name || '').toLowerCase().includes(q) ||
                 (v.imo_number  || '').toLowerCase().includes(q);
        })
      : _rankingData.slice();
    _rankingPage = 0;  // reset to first page on filter change
    sortAndRenderRanking();
  }
  window.applyRankingFilter = applyRankingFilter;

  // ── Sort ─────────────────────────────────────────────────────────────────

  function sortRanking(thEl) {
    var key = thEl ? thEl.getAttribute('data-key') : _rankingSortKey;
    if (key === _rankingSortKey) {
      _rankingSortAsc = !_rankingSortAsc;
    } else {
      _rankingSortKey = key;
      _rankingSortAsc = false;
    }
    // Update header arrow indicators
    document.querySelectorAll('.ranking-th.sortable').forEach(function (th) {
      th.classList.remove('sort-asc', 'sort-desc');
    });
    if (thEl) thEl.classList.add(_rankingSortAsc ? 'sort-asc' : 'sort-desc');
    sortAndRenderRanking();
  }
  window.sortRanking = sortRanking;

  function sortAndRenderRanking() {
    var key = _rankingSortKey;
    var asc = _rankingSortAsc;
    _rankingFiltered.sort(function (a, b) {
      var av = a[key], bv = b[key];
      if (av === null || av === undefined) av = asc ? Infinity : -Infinity;
      if (bv === null || bv === undefined) bv = asc ? Infinity : -Infinity;
      if (typeof av === 'string') av = av.toLowerCase();
      if (typeof bv === 'string') bv = bv.toLowerCase();
      if (av < bv) return asc ? -1 : 1;
      if (av > bv) return asc ? 1 : -1;
      return 0;
    });
    renderRankingPage();
  }

  // ── Render ───────────────────────────────────────────────────────────────

  function renderRankingPage() {
    var tbody = document.getElementById('ranking-tbody');
    var paginEl = document.getElementById('ranking-pagination');
    if (!tbody) return;

    var start = _rankingPage * _rankingPageSize;
    var page  = _rankingFiltered.slice(start, start + _rankingPageSize);
    var total = _rankingFiltered.length;

    if (total === 0) {
      tbody.innerHTML = '<tr><td colspan="8" class="text-muted" style="text-align:center;padding:2rem;">No vessels match.</td></tr>';
      if (paginEl) paginEl.innerHTML = '';
      return;
    }

    var rows = page.map(function (v, i) {
      var rank     = start + i + 1;
      var stale    = v.is_stale ? ' <span class="text-warn" title="Score stale">&bull;</span>' : '';
      var lastSeen = relativeTime(v.computed_at) + stale;
      var evStr    = v.evidence_count + '/31';
      return '<tr class="ranking-row ranking-row-' + (v.risk_level || 'unknown').toLowerCase() + '" '
        + 'onclick="window.location.href=\'/vessel/' + escHtml(v.imo_number) + '\'" '
        + 'style="cursor:pointer;">'
        + '<td class="text-muted" style="font-size:0.85em;">' + rank + '</td>'
        + '<td><strong>' + (v.composite_score !== null && v.composite_score !== undefined ? v.composite_score : '—') + '</strong></td>'
        + '<td>' + escHtml(v.entity_name || '—') + '</td>'
        + '<td class="text-muted" style="font-size:0.85em;">' + escHtml(v.imo_number || '—') + '</td>'
        + '<td>' + escHtml(v.flag_normalized || '—') + '</td>'
        + '<td>' + escHtml(evStr) + '</td>'
        + '<td>' + lastSeen + '</td>'
        + '<td>' + riskBadgeHtml(v.risk_level) + '</td>'
        + '</tr>';
    }).join('');

    tbody.innerHTML = rows;

    // Pagination controls
    if (paginEl) {
      var totalPages = Math.ceil(total / _rankingPageSize);
      var html = '<span class="text-muted" style="font-size:0.85em;">'
        + (start + 1) + '&ndash;' + Math.min(start + _rankingPageSize, total)
        + ' of ' + total + '</span>';
      if (_rankingPage > 0) {
        html += ' <button class="btn btn-secondary" onclick="goRankingPage(' + (_rankingPage - 1) + ')">Prev</button>';
      }
      if (start + _rankingPageSize < total) {
        html += ' <button class="btn btn-secondary" onclick="goRankingPage(' + (_rankingPage + 1) + ')">Next</button>';
      }
      paginEl.innerHTML = html;
    }
  }

  function goRankingPage(n) {
    _rankingPage = n;
    renderRankingPage();
  }
  window.goRankingPage = goRankingPage;

  function setRankingPageSize() {
    var sel = document.getElementById('ranking-page-size');
    _rankingPageSize = parseInt(sel ? sel.value : '50', 10) || 50;
    _rankingPage = 0;
    renderRankingPage();
  }
  window.setRankingPageSize = setRankingPageSize;

  // ── Boot ─────────────────────────────────────────────────────────────────

  document.addEventListener('DOMContentLoaded', function () {
    // Load ranking table when the ranking tab is first shown
    // Hook into existing switchTab function in app.js
    var origSwitchTab = window.switchTab;
    window.switchTab = function (tabName) {
      if (origSwitchTab) origSwitchTab(tabName);
      if (tabName === 'ranking' && _rankingData.length === 0) {
        loadRankingTable();
      }
    };
    // Also load immediately if ranking tab is the active tab on page load
    var activeTab = document.querySelector('.tab-btn.active');
    if (activeTab && activeTab.id === 'tab-btn-ranking') {
      loadRankingTable();
    }
  });

}());
