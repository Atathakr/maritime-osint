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

  // ── History section (Phase 8 PROF-01 + PROF-02) ──────────────────────────

  var RISK_COLOR = {
    CRITICAL: '#dc2626',
    HIGH:     '#ea580c',
    MEDIUM:   '#d97706',
    LOW:      '#16a34a',
  };

  function renderScoreHistoryCard(history) {
    var placeholder = document.getElementById('score-history-placeholder');
    var canvas      = document.getElementById('score-history-chart');
    if (!canvas) return;

    if (!history || history.length === 0) {
      if (placeholder) placeholder.style.display = 'block';
      return;
    }

    // history[0] is most recent; chart shows oldest→newest (reverse)
    var reversed    = history.slice().reverse();
    var labels      = reversed.map(function(row) { return relativeTime(row.recorded_at); });
    var scores      = reversed.map(function(row) { return row.composite_score; });
    var pointColors = reversed.map(function(row) {
      return RISK_COLOR[row.risk_level] || '#9ca3af';
    });
    var riskLevels  = reversed.map(function(row) { return row.risk_level || 'UNKNOWN'; });

    if (placeholder) placeholder.style.display = 'none';
    canvas.style.display = 'block';

    // Destroy previous instance if re-initialised (e.g. dev hot reload)
    if (window._scoreChart) {
      window._scoreChart.destroy();
      window._scoreChart = null;
    }

    window._scoreChart = new Chart(canvas, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          data: scores,
          borderColor: '#374151',
          borderWidth: 2,
          pointBackgroundColor: pointColors,
          pointBorderColor: pointColors,
          pointRadius: 5,
          pointHoverRadius: 7,
          tension: 0.2,
          fill: false,
        }],
      },
      options: {
        responsive: true,
        animation: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: function(ctx) {
                var i = ctx.dataIndex;
                return 'Score: ' + ctx.parsed.y + ' \u00b7 ' + riskLevels[i] + ' \u00b7 ' + labels[i];
              },
            },
          },
        },
        scales: {
          y: {
            min: 0,
            max: 100,
            ticks: { stepSize: 20 },
          },
          x: {
            ticks: { maxTicksLimit: 8 },
          },
        },
      },
    });
  }

  function renderRecentChangesCard(history, indicatorNameMap) {
    var container = document.getElementById('recent-changes-content');
    if (!container) return;

    // Zero snapshots
    if (!history || history.length === 0) {
      container.innerHTML = '<p class="text-muted">No changes recorded yet.</p>';
      return;
    }

    // Exactly 1 snapshot — no prior to compare
    if (history.length === 1) {
      container.innerHTML = '<p class="text-muted">No prior snapshot to compare \u2014 this is the first recorded score.</p>';
      return;
    }

    var snap0 = history[0];  // most recent
    var snap1 = history[1];  // prior

    var ind0 = snap0.indicator_json || {};
    var ind1 = snap1.indicator_json || {};

    var delta = snap0.composite_score - snap1.composite_score;

    // Identical case
    if (delta === 0 && snap0.risk_level === snap1.risk_level && Object.keys(ind0).join(',') === Object.keys(ind1).join(',')) {
      container.innerHTML = '<p class="text-muted">No changes since last run.</p>';
      return;
    }

    var parts = [];

    // Score delta row
    var arrow = delta > 0 ? '\u25b2' : (delta < 0 ? '\u25bc' : '');
    var sign  = delta > 0 ? '+' : '';
    parts.push('<div class="history-row"><span class="history-label">Score delta</span>'
      + '<span class="history-value history-delta">' + escHtml(arrow + ' ' + sign + delta + ' pts') + '</span></div>');

    // Risk level change row — only if changed
    if (snap0.risk_level !== snap1.risk_level) {
      parts.push('<div class="history-row"><span class="history-label">Risk level</span>'
        + '<span class="history-value">' + escHtml(snap1.risk_level + ' \u2192 ' + snap0.risk_level) + '</span></div>');
    }

    // Newly fired indicators (in snap0 but not snap1)
    var fired = Object.keys(ind0).filter(function(k) { return !ind1.hasOwnProperty(k); });
    if (fired.length > 0) {
      var firedNames = fired.map(function(k) {
        return escHtml(indicatorNameMap[k] || k);
      }).join(', ');
      parts.push('<div class="history-row"><span class="history-label">Newly fired</span>'
        + '<span class="history-value history-fired">' + firedNames + '</span></div>');
    }

    // Newly cleared indicators (in snap1 but not snap0)
    var cleared = Object.keys(ind1).filter(function(k) { return !ind0.hasOwnProperty(k); });
    if (cleared.length > 0) {
      var clearedNames = cleared.map(function(k) {
        return escHtml(indicatorNameMap[k] || k);
      }).join(', ');
      parts.push('<div class="history-row"><span class="history-label">Newly cleared</span>'
        + '<span class="history-value history-cleared">' + clearedNames + '</span></div>');
    }

    container.innerHTML = '<div class="history-log">' + parts.join('') + '</div>';
  }

  function initHistorySection() {
    // Build indicator name map from server-injected meta
    var indicatorNameMap = {};
    var metaEl = document.getElementById('indicator-meta');
    if (metaEl) {
      try {
        var meta = JSON.parse(metaEl.textContent);
        meta.forEach(function(m) { indicatorNameMap[m.id] = m.name; });
      } catch (e) {}
    }

    // Read IMO from data attribute
    var imoEl = document.getElementById('vessel-data');
    var imo = imoEl ? imoEl.getAttribute('data-imo') : null;
    if (!imo) return;

    fetch('/api/vessels/' + encodeURIComponent(imo) + '/history')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        var history = data.history || [];
        renderScoreHistoryCard(history);
        renderRecentChangesCard(history, indicatorNameMap);
      })
      .catch(function() {
        // Silently degrade — cards show whatever placeholder text is in HTML
        var container = document.getElementById('recent-changes-content');
        if (container) container.innerHTML = '<p class="text-muted">Unable to load history.</p>';
      });
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
    initHistorySection();
  });

}());
