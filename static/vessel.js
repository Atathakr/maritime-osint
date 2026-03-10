// static/vessel.js — Vessel profile page logic (Phase 5 FE-5, FE-3)
// All DOM manipulation lives here (CSP enforcement: no inline scripts in vessel.html).

(function () {
  'use strict';

  // ── Helpers ──────────────────────────────────────────────────────────────

  function escHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function relativeTime(isoStr) {
    if (!isoStr) return '—';
    var diffMs  = Date.now() - new Date(isoStr).getTime();
    var diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 2)  return 'just now';
    if (diffMin < 60) return diffMin + 'm ago';
    var h = Math.floor(diffMin / 60);
    if (h < 24)       return h + 'h ago';
    var d = Math.floor(h / 24);
    return d + 'd ago';
  }

  // Thresholds match screening.py and app.js renderVesselProfileHtml()
  function scoreToRiskLevel(score) {
    if (score === null || score === undefined) return 'UNKNOWN';
    if (score >= 100) return 'CRITICAL';
    if (score >= 70)  return 'HIGH';
    if (score >= 40)  return 'MEDIUM';
    return 'LOW';
  }

  function riskBadgeHtml(level) {
    var cls = {
      CRITICAL: 'risk-badge-critical',
      HIGH:     'risk-badge-high',
      MEDIUM:   'risk-badge-medium',
      LOW:      'risk-badge-low',
    }[level] || 'badge-muted';
    return '<span class="risk-badge ' + cls + '">' + escHtml(level || 'UNKNOWN') + '</span>';
  }

  // ── Score hero rendering ─────────────────────────────────────────────────

  function renderScoreHero(score) {
    var loading    = document.getElementById('score-loading');
    var content    = document.getElementById('score-content');
    var noneEl     = document.getElementById('score-none');
    var scoreVal   = document.getElementById('score-value');
    var scoreBadge = document.getElementById('score-badge');
    var freshEl    = document.getElementById('score-freshness');

    if (!score || score.composite_score === null || score.composite_score === undefined) {
      if (loading)  loading.style.display  = 'none';
      if (noneEl)   noneEl.style.display   = 'block';
      return;
    }

    var level    = scoreToRiskLevel(score.composite_score);
    var freshStr = score.computed_at ? 'Computed ' + relativeTime(score.computed_at) : '';
    var staleStr = '';
    if (score.is_stale) {
      staleStr = ' &nbsp;<span class="text-warn" title="Score has not been refreshed — AIS data may be outdated">&bull; Stale</span>';
    }

    if (scoreVal)   scoreVal.textContent = score.composite_score;
    if (scoreBadge) scoreBadge.innerHTML = riskBadgeHtml(level);
    if (freshEl)    freshEl.innerHTML    = escHtml(freshStr) + staleStr;

    if (loading)  loading.style.display  = 'none';
    if (content)  content.style.display  = 'block';

    // Expose score data for plan 05-03 indicator breakdown
    window._vesselScore = score;
  }

  // ── Indicator breakdown table ─────────────────────────────────────────────

  function renderIndicatorTable(score) {
    var section = document.getElementById('indicator-section');
    var container = document.getElementById('indicator-table-container');
    if (!section || !container) return;

    var metaEl = document.getElementById('indicator-meta');
    var indicators = [];
    if (metaEl) {
      try { indicators = JSON.parse(metaEl.textContent); } catch (e) {}
    }
    if (!indicators || indicators.length === 0) return;

    var indJson = (score && score.indicator_json) ? score.indicator_json : {};

    // Sort: fired indicators float to top (globally, not per-category)
    var sorted = indicators.slice().sort(function (a, b) {
      var af = indJson.hasOwnProperty(a.id) ? 1 : 0;
      var bf = indJson.hasOwnProperty(b.id) ? 1 : 0;
      return bf - af;  // fired (1) before not-fired (0)
    });

    var totalPts = 0;
    var rows = sorted.map(function (meta) {
      var indData = indJson[meta.id];
      var fired   = indData !== undefined;
      var pts     = fired ? (indData.pts || 0) : 0;
      totalPts   += pts;
      var firedAt = fired && indData.fired_at ? relativeTime(indData.fired_at) : '—';
      var rowStyle = fired ? 'background:#fef2f2;' : '';
      var catStyle = fired ? '' : 'color:var(--muted);';
      var nameStyle = fired ? '' : 'color:var(--muted);';
      var statusHtml = fired
        ? '<span class="badge badge-red" style="font-size:0.75em;">Fired</span>'
        : '<span style="color:var(--muted);">—</span>';
      return '<tr style="' + rowStyle + '">'
        + '<td style="font-size:0.8em;' + catStyle + '">' + escHtml(meta.category) + '</td>'
        + '<td style="' + nameStyle + '">' + escHtml(meta.name) + '</td>'
        + '<td style="text-align:right;">' + (pts > 0 ? pts : '—') + '</td>'
        + '<td>' + statusHtml + '</td>'
        + '<td style="font-size:0.85em;color:var(--muted);">' + escHtml(firedAt) + '</td>'
        + '</tr>';
    }).join('');

    var tableHtml = '<table class="data-table" style="width:100%;">'
      + '<thead><tr>'
      + '<th style="font-size:0.8em;color:var(--muted);">Category</th>'
      + '<th style="font-size:0.8em;color:var(--muted);">Indicator</th>'
      + '<th style="font-size:0.8em;color:var(--muted);text-align:right;">Points</th>'
      + '<th style="font-size:0.8em;color:var(--muted);">Status</th>'
      + '<th style="font-size:0.8em;color:var(--muted);">Last Fired</th>'
      + '</tr></thead>'
      + '<tbody>' + rows + '</tbody>'
      + '<tfoot><tr>'
      + '<td colspan="2" style="font-weight:600;padding-top:0.5rem;">Total Score</td>'
      + '<td style="font-weight:700;text-align:right;padding-top:0.5rem;">' + totalPts + '</td>'
      + '<td colspan="2"></td>'
      + '</tr></tfoot>'
      + '</table>';

    container.innerHTML = tableHtml;
    section.style.display = 'block';
  }

  // ── Boot ─────────────────────────────────────────────────────────────────

  document.addEventListener('DOMContentLoaded', function () {
    var scoreEl = document.getElementById('vessel-score-data');
    var score = null;
    if (scoreEl) {
      try { score = JSON.parse(scoreEl.textContent); } catch (e) {}
    }
    renderScoreHero(score);
    renderIndicatorTable(score);
  });

}());
