/* static/alerts.js — Alert badge polling and panel rendering (Phase 7)
 * CSP: no inline onclick in JS-generated HTML; use addEventListener.
 * Badge polls /api/alerts/unread-count every 30s.
 * Panel fetches /api/alerts on open.
 */

(function () {
  "use strict";

  var POLL_INTERVAL_MS = 30000;
  var _pollTimer = null;

  /* ── Badge ────────────────────────────────────────────────────────────── */

  function updateBadge(count) {
    var btn = document.getElementById("alert-badge-btn");
    var span = document.getElementById("alert-badge-count");
    if (!btn || !span) return;
    span.textContent = count;
    if (count > 0) {
      btn.classList.remove("hidden");
    } else {
      btn.classList.add("hidden");
    }
  }

  function pollUnreadCount() {
    fetch("/api/alerts/unread-count")
      .then(function (resp) {
        if (!resp.ok) throw new Error("unread-count failed: " + resp.status);
        return resp.json();
      })
      .then(function (data) {
        updateBadge(data.count || 0);
      })
      .catch(function (err) {
        console.warn("[alerts] poll error:", err);
      });
  }

  /* ── Panel ────────────────────────────────────────────────────────────── */

  function toggleAlertPanel() {
    var panel = document.getElementById("alert-panel");
    var overlay = document.getElementById("alert-overlay");
    if (!panel) return;
    var isHidden = panel.classList.contains("hidden");
    if (isHidden) {
      panel.classList.remove("hidden");
      if (overlay) overlay.classList.remove("hidden");
      fetchAndRenderPanel();
    } else {
      panel.classList.add("hidden");
      if (overlay) overlay.classList.add("hidden");
    }
  }

  function fetchAndRenderPanel() {
    var body = document.getElementById("alert-panel-body");
    if (!body) return;
    body.innerHTML = "<div class=\"empty-state\">Loading\u2026</div>";
    fetch("/api/alerts")
      .then(function (resp) {
        if (!resp.ok) throw new Error("alerts fetch failed: " + resp.status);
        return resp.json();
      })
      .then(function (data) {
        renderAlertPanel(data, body);
      })
      .catch(function (err) {
        body.innerHTML = "<div class=\"empty-state\">Error loading alerts.</div>";
        console.error("[alerts] fetch error:", err);
      });
  }

  function renderAlertPanel(data, bodyEl) {
    bodyEl.innerHTML = "";

    /* Unread section */
    var unread = data.unread || [];
    var unreadSection = document.createElement("div");
    unreadSection.className = "alert-section";
    var unreadHeader = document.createElement("h3");
    unreadHeader.className = "alert-section-title";
    unreadHeader.textContent = "Unread (" + unread.length + ")";
    unreadSection.appendChild(unreadHeader);
    if (unread.length === 0) {
      var emptyMsg = document.createElement("div");
      emptyMsg.className = "empty-state";
      emptyMsg.textContent = "No unread alerts.";
      unreadSection.appendChild(emptyMsg);
    } else {
      unread.forEach(function (alert) {
        unreadSection.appendChild(buildAlertItem(alert, false));
      });
    }
    bodyEl.appendChild(unreadSection);

    /* Read section */
    var read = data.read || [];
    if (read.length > 0) {
      var readSection = document.createElement("div");
      readSection.className = "alert-section alert-section--read";
      var readHeader = document.createElement("h3");
      readHeader.className = "alert-section-title";
      readHeader.textContent = "Read (" + read.length + ")";
      readSection.appendChild(readHeader);
      read.forEach(function (alert) {
        readSection.appendChild(buildAlertItem(alert, true));
      });
      bodyEl.appendChild(readSection);
    }
  }

  function buildAlertItem(alert, isRead) {
    var item = document.createElement("div");
    item.className = "alert-item" + (isRead ? " alert-item--read" : "");
    item.dataset.alertId = alert.id;

    /* Summary row */
    var summary = document.createElement("div");
    summary.className = "alert-item-summary";

    var typeLabel = document.createElement("span");
    typeLabel.className = "alert-type-label";
    typeLabel.textContent = formatAlertType(alert.alert_type);

    var vessel = document.createElement("span");
    vessel.className = "alert-vessel-name";
    vessel.textContent = alert.vessel_name || alert.imo_number || "Unknown";

    var scoreSpan = document.createElement("span");
    scoreSpan.className = "alert-score";
    scoreSpan.textContent = "Score: " + (alert.score_at_trigger != null ? alert.score_at_trigger : "\u2014");

    var ageSpan = document.createElement("span");
    ageSpan.className = "alert-age";
    ageSpan.textContent = formatAge(alert.triggered_at);

    summary.appendChild(typeLabel);
    summary.appendChild(vessel);
    summary.appendChild(scoreSpan);
    summary.appendChild(ageSpan);
    item.appendChild(summary);

    /* Detail row (ALRT-03) */
    var detail = document.createElement("div");
    detail.className = "alert-item-detail hidden";

    var deltaText = document.createElement("p");
    deltaText.textContent =
      "Score: " + (alert.before_score != null ? alert.before_score : "\u2014") +
      " \u2192 " + (alert.after_score != null ? alert.after_score : "\u2014") +
      "  |  Risk: " + (alert.before_risk_level || "\u2014") +
      " \u2192 " + (alert.after_risk_level || "\u2014");
    detail.appendChild(deltaText);

    var indicators = Array.isArray(alert.new_indicators_json)
      ? alert.new_indicators_json
      : [];
    if (indicators.length > 0) {
      var indPara = document.createElement("p");
      indPara.textContent = "New indicators: " + indicators.join(", ");
      detail.appendChild(indPara);
    }

    var viewLink = document.createElement("a");
    viewLink.href = "/vessel/" + encodeURIComponent(alert.imo_number || "");
    viewLink.className = "alert-view-vessel";
    viewLink.textContent = "View Vessel \u2192";
    detail.appendChild(viewLink);

    item.appendChild(detail);

    /* Expand/collapse on summary click */
    summary.addEventListener("click", function () {
      detail.classList.toggle("hidden");
    });

    /* Mark as read button (unread only) */
    if (!isRead) {
      var markBtn = document.createElement("button");
      markBtn.className = "alert-mark-read-btn";
      markBtn.textContent = "Mark as read";
      markBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        markRead(alert.id);
      });
      item.appendChild(markBtn);
    }

    return item;
  }

  function markRead(alertId) {
    fetch("/api/alerts/" + alertId + "/read", { method: "POST" })
      .then(function (resp) {
        if (!resp.ok) throw new Error("mark-read failed: " + resp.status);
        return resp.json();
      })
      .then(function (data) {
        updateBadge(data.count || 0);
        fetchAndRenderPanel();
      })
      .catch(function (err) {
        console.error("[alerts] mark-read error:", err);
      });
  }

  /* ── Formatters ───────────────────────────────────────────────────────── */

  function formatAlertType(type) {
    var labels = {
      risk_level_crossing: "Risk Level Change",
      top_50_entry:        "Entered Top 50",
      sanctions_match:     "Sanctions Match",
      score_spike:         "Score Spike",
    };
    return labels[type] || type;
  }

  function formatAge(isoString) {
    if (!isoString) return "";
    var then = new Date(isoString);
    var diffMs = Date.now() - then.getTime();
    var diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return "just now";
    if (diffMin < 60) return diffMin + "m ago";
    var diffH = Math.floor(diffMin / 60);
    if (diffH < 24) return diffH + "h ago";
    return Math.floor(diffH / 24) + "d ago";
  }

  /* ── Initialisation ───────────────────────────────────────────────────── */

  function initAlerts() {
    /* Wire badge button */
    var btn = document.getElementById("alert-badge-btn");
    if (btn) {
      btn.addEventListener("click", toggleAlertPanel);
    }

    /* Wire close button */
    var closeBtn = document.querySelector(".alert-panel-close");
    if (closeBtn) {
      closeBtn.addEventListener("click", toggleAlertPanel);
    }

    /* Wire overlay */
    var overlay = document.getElementById("alert-overlay");
    if (overlay) {
      overlay.addEventListener("click", toggleAlertPanel);
    }

    /* Initial badge fetch then poll */
    pollUnreadCount();
    _pollTimer = setInterval(pollUnreadCount, POLL_INTERVAL_MS);
  }

  document.addEventListener("DOMContentLoaded", initAlerts);
})();
