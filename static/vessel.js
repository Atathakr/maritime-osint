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

  // ── Boot ─────────────────────────────────────────────────────────────────

  document.addEventListener('DOMContentLoaded', function () {
    var scoreEl = document.getElementById('vessel-score-data');
    var score = null;
    if (scoreEl) {
      try { score = JSON.parse(scoreEl.textContent); } catch (e) {}
    }
    renderScoreHero(score);
  });

}());
