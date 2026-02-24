/* map.js — Live Maritime Risk Map (Leaflet 1.9.4)
 *
 * Depends on:
 *   - Leaflet loaded before this script
 *   - escHtml() / escAttr() defined in app.js
 *
 * Exported globals used by dashboard.html onclick attributes:
 *   initMap(), refreshMap(), setMapFilter(btn), toggleOpenSeaMap(on)
 */

(function () {
  "use strict";

  // ── State ────────────────────────────────────────────────────────────────
  let _map          = null;
  let _markers      = null;   // L.LayerGroup for vessel markers
  let _trackLayer   = null;   // L.Polyline for active vessel track
  let _trackMmsi    = null;   // MMSI of the currently loaded track
  let _openSeaLayer = null;
  let _currentFilter = "medium_plus";
  let _refreshTimer  = null;
  let _vessels       = [];    // last fetched vessel list

  const REFRESH_MS = 60_000;

  // ── Tile layers ──────────────────────────────────────────────────────────
  const CARTO_DARK = L.tileLayer(
    "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors ' +
        '&copy; <a href="https://carto.com/attributions">CARTO</a>',
      subdomains: "abcd",
      maxZoom: 19,
    }
  );

  const OPEN_SEA_MAP = L.tileLayer(
    "https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png",
    {
      attribution:
        'Sea marks &copy; <a href="http://www.openseamap.org">OpenSeaMap</a> contributors',
      opacity: 0.8,
    }
  );

  // ── Colour / size helpers ────────────────────────────────────────────────
  function riskColour(vessel) {
    return vessel.risk_colour || "#475569";
  }

  function riskRadius(vessel) {
    return vessel.risk_radius || 4;
  }

  function markerOptions(vessel) {
    const col = riskColour(vessel);
    const r   = riskRadius(vessel);
    // No per-marker renderer — share the map's single canvas (preferCanvas: true).
    // Creating L.canvas() per-marker generates independent canvas elements and
    // breaks Leaflet's hit-detection, causing tooltips/popups to fail randomly.
    return {
      radius:      r,
      color:       col,
      fillColor:   col,
      fillOpacity: 0.85,
      weight:      vessel.sanctioned ? 2 : 1,
      opacity:     1,
    };
  }

  // ── Tooltip content ──────────────────────────────────────────────────────
  function tooltipHtml(v) {
    const name  = escHtml(v.vessel_name || "Unknown");
    const flag  = v.flag_state ? ` · ${escHtml(v.flag_state)}` : "";
    const sog   = v.sog != null ? `${v.sog} kn` : "—";
    const badge = `<span class="badge badge-${riskBadgeClass(v.risk_level)}" ` +
                  `style="font-size:.65rem;padding:.1rem .35rem;">${escHtml(v.risk_level)}</span>`;
    return `<div class="map-tooltip">
      <strong>${name}</strong>${flag}<br>
      MMSI: <code>${escHtml(v.mmsi || "—")}</code>&nbsp;
      IMO: <code>${escHtml(v.imo_number || "—")}</code><br>
      SOG: ${sog}&nbsp;&nbsp;${badge}
    </div>`;
  }

  function riskBadgeClass(level) {
    switch (level) {
      case "CRITICAL": return "red";
      case "HIGH":     return "orange";
      case "MEDIUM":   return "warn";
      default:         return "muted";
    }
  }

  // ── Popup content ────────────────────────────────────────────────────────
  function popupHtml(v) {
    const name   = escHtml(v.vessel_name || "Unknown");
    const imo    = escHtml(v.imo_number  || "—");
    const mmsi   = escHtml(v.mmsi        || "—");
    const flag   = escHtml(v.flag_state  || "—");
    const type   = escHtml(v.vessel_type || "—");
    const sog    = v.sog  != null ? `${v.sog} kn`  : "—";
    const cog    = v.cog  != null ? `${v.cog}°`     : "—";
    const dest   = escHtml(v.destination || "—");
    const seen   = v.last_seen ? v.last_seen.replace("T", " ").slice(0, 16) + " UTC" : "—";
    const reasons = (v.risk_reasons || [])
      .map(r => `<li>${escHtml(r)}</li>`).join("") || "<li>No flags</li>";
    const tags = (v.source_tags || [])
      .map(t => `<span class="badge badge-${tagBadgeClass(t)}" style="font-size:.65rem;">${escHtml(t)}</span>`)
      .join(" ") || "";
    
    const trackBtn = v.mmsi 
      ? `<button class="btn btn-secondary btn-sm" style="margin-top:.5rem;width:100%;"
           onclick="toggleVesselTrack('${escAttr(v.mmsi)}', '${escAttr(v.vessel_name||"Unknown")}');">
           ${v.mmsi === _trackMmsi ? "Hide Track" : "Show 72h Track"}
         </button>`
      : "";

    const screenBtn = v.imo_number
      ? `<button class="btn btn-primary btn-sm" style="margin-top:.25rem;width:100%;"
           onclick="document.getElementById('screen-query').value='${escAttr(v.imo_number)}';runScreening();">
           Screen this vessel
         </button>`
      : `<button class="btn btn-secondary btn-sm" style="margin-top:.25rem;width:100%;"
           onclick="document.getElementById('screen-query').value='${escAttr(v.mmsi||"")}';runScreening();">
           Screen this vessel (MMSI)
         </button>`;

    return `<div class="map-popup">
      <div class="map-popup-title">${name}</div>
      <table class="map-popup-table">
        <tr><td>IMO</td><td><code>${imo}</code></td></tr>
        <tr><td>MMSI</td><td><code>${mmsi}</code></td></tr>
        <tr><td>Flag</td><td>${flag}</td></tr>
        <tr><td>Type</td><td>${type}</td></tr>
        <tr><td>SOG / COG</td><td>${sog} / ${cog}</td></tr>
        <tr><td>Destination</td><td>${dest}</td></tr>
        <tr><td>Last seen</td><td>${seen}</td></tr>
      </table>
      <div style="margin:.4rem 0 .2rem;font-size:.72rem;color:var(--muted);">Risk factors</div>
      <ul class="map-popup-risks">${reasons}</ul>
      ${tags ? `<div style="margin-top:.35rem;">${tags}</div>` : ""}
      ${trackBtn}
      ${screenBtn}
    </div>`;
  }

  // ── Fetch & render ───────────────────────────────────────────────────────
  async function fetchVessels() {
    const url = `/api/map/vessels?hours=720&dp_days=30&sts_days=30&risk_filter=${_currentFilter}`;
    try {
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      _vessels = data.vessels || [];
      renderMarkers(_vessels);
      const el = document.getElementById("map-vessel-count");
      if (el) el.textContent = `${_vessels.length} vessel${_vessels.length !== 1 ? "s" : ""} tracked`;
    } catch (err) {
      console.warn("map: fetch error", err);
    }
  }

  function renderMarkers(vessels) {
    _markers.clearLayers();
    vessels.forEach(v => {
      if (v.lat == null || v.lon == null) return;
      const marker = L.circleMarker([v.lat, v.lon], markerOptions(v));
      marker.bindTooltip(tooltipHtml(v), {
        className:   "map-tooltip-wrapper",
        sticky:      true,
        direction:   "top",
        offset:      [0, -6],
      });
      marker.bindPopup(popupHtml(v), {
        className:   "map-popup-wrapper",
        maxWidth:    280,
        minWidth:    220,
      });
      _markers.addLayer(marker);
    });
  }

  // ── Track Visualization ──────────────────────────────────────────────────
  async function toggleVesselTrack(mmsi, name) {
    // If clicking the same vessel that's already showing, just clear it (toggle off)
    if (_trackMmsi === mmsi) {
      clearTrack();
      return;
    }

    // Otherwise, clear any existing track and load the new one
    clearTrack();

    try {
      const resp = await fetch(`/api/ais/vessels/${mmsi}/track?hours=72`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      
      if (!data.track || data.track.length < 2) {
        alert(`No track data found for ${name} in the last 72 hours.`);
        return;
      }

      const latlngs = data.track.map(p => [p.lat, p.lon]);
      _trackLayer = L.polyline(latlngs, {
        color:       "#3b82f6", // Blue-500
        weight:      3,
        opacity:     0.8,
        dashArray:   "5, 10",
        lineJoin:    "round"
      }).addTo(_map);

      _trackMmsi = mmsi;
      updateTrackButton(true);

      _map.fitBounds(_trackLayer.getBounds(), { padding: [50, 50] });
      _map.closePopup();

    } catch (err) {
      console.warn("map: track fetch error", err);
      alert("Failed to load vessel track.");
    }
  }

  function clearTrack() {
    if (_trackLayer) {
      _map.removeLayer(_trackLayer);
      _trackLayer = null;
    }
    _trackMmsi = null;
    updateTrackButton(false);
  }

  function updateTrackButton(active) {
    const btn = document.getElementById("btn-clear-track");
    if (!btn) return;
    if (active) {
      btn.textContent = "Hide Track";
      btn.classList.add("active");
      btn.disabled = false;
    } else {
      btn.textContent = "No Active Track";
      btn.classList.remove("active");
      btn.disabled = true;
    }
  }

  // ── Public API ───────────────────────────────────────────────────────────
  window.initMap = function () {
    if (_map) return;   // already initialised

    _map = L.map("risk-map", {
      center:            [20, 0],
      zoom:              3,
      preferCanvas:      true,
      zoomControl:       true,
      attributionControl: true,
    });

    CARTO_DARK.addTo(_map);
    _openSeaLayer = OPEN_SEA_MAP;   // not added until toggled on

    _markers = L.layerGroup().addTo(_map);

    // Initial data load
    fetchVessels();

    // Auto-refresh every 30 s
    _refreshTimer = setInterval(fetchVessels, REFRESH_MS);
  };

  window.refreshMap = function () {
    fetchVessels();
  };

  window.toggleVesselTrack = function (mmsi, name) {
    toggleVesselTrack(mmsi, name);
  };

  window.clearTrack = function () {
    clearTrack();
  };

  window.setMapFilter = function (btn) {
    document.querySelectorAll(".map-filter-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    _currentFilter = btn.dataset.filter || "all";
    fetchVessels();
  };

  window.toggleOpenSeaMap = function (on) {
    if (!_map) return;
    if (on) {
      _openSeaLayer.addTo(_map);
    } else {
      _map.removeLayer(_openSeaLayer);
    }
  };

})();
