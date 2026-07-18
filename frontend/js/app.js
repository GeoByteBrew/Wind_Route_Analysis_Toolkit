/* global MapView */

(() => {
  const els = {
    modeStart: document.getElementById("btn-mode-start"),
    modeEnd: document.getElementById("btn-mode-end"),
    startLabel: document.getElementById("start-label"),
    endLabel: document.getElementById("end-label"),
    analyze: document.getElementById("btn-analyze"),
    reset: document.getElementById("btn-reset"),
    status: document.getElementById("status"),
    summarySection: document.getElementById("summary-section"),
    summary: document.getElementById("summary"),
    downloads: document.getElementById("downloads"),
    length: document.getElementById("length"),
    width: document.getElementById("width"),
    height: document.getElementById("height"),
    weight: document.getElementById("weight"),
    slope: document.getElementById("slope"),
  };

  const state = {
    mode: "start",
    start: null,
    end: null,
  };

  function fmt(pt) {
    if (!pt) return "—";
    return `${pt.lat.toFixed(4)}, ${pt.lon.toFixed(4)}`;
  }

  function setMode(mode) {
    state.mode = mode;
    els.modeStart.classList.toggle("chip--active", mode === "start");
    els.modeEnd.classList.toggle("chip--active", mode === "end");
  }

  function setStatus(msg, isError = false) {
    els.status.textContent = msg || "";
    els.status.style.color = isError ? "#9f1239" : "";
  }

  async function loadLayers() {
    const [meta, roads, bridges, slopes, places] = await Promise.all([
      fetch("/api/meta").then((r) => r.json()),
      fetch("/api/layers/roads").then((r) => r.json()),
      fetch("/api/layers/bridges").then((r) => r.json()),
      fetch("/api/layers/slopes").then((r) => r.json()),
      fetch("/api/layers/places").then((r) => r.json()),
    ]);

    MapView.init([meta.center.lat, meta.center.lon], 9);
    MapView.drawBaseLayers({ roads, bridges, slopes, places });

    MapView.onClick((latlng) => {
      const point = { lat: latlng.lat, lon: latlng.lng };
      if (state.mode === "start") {
        state.start = point;
        els.startLabel.textContent = fmt(point);
        MapView.setMarker("start", latlng);
        setMode("end");
        setStatus("Start set. Click the map to choose destination.");
      } else {
        state.end = point;
        els.endLabel.textContent = fmt(point);
        MapView.setMarker("end", latlng);
        setStatus("Destination set. Adjust vehicle limits and run analysis.");
      }
    });

    // Demo defaults near Montpellier → Béziers corridor
    state.start = { lat: 43.6108, lon: 3.8767 };
    state.end = { lat: 43.3442, lon: 3.2158 };
    els.startLabel.textContent = fmt(state.start);
    els.endLabel.textContent = fmt(state.end);
    MapView.setMarker("start", { lat: state.start.lat, lng: state.start.lon });
    MapView.setMarker("end", { lat: state.end.lat, lng: state.end.lon });
    setStatus("Demo points loaded (Montpellier → Béziers). Run analysis or pick new points.");
  }

  function vehiclePayload() {
    return {
      length_m: Number(els.length.value),
      width_m: Number(els.width.value),
      height_m: Number(els.height.value),
      weight_t: Number(els.weight.value),
      max_slope_pct: Number(els.slope.value),
    };
  }

  function renderSummary(result) {
    const s = result.summary;
    els.summarySection.hidden = false;
    els.summary.innerHTML = `
      <span class="summary__badge ${s.feasibility}">${s.feasibility}</span>
      <div><strong>${s.distance_km} km</strong> · ${s.issues_count} issue(s)</div>
      <div>Low bridges: ${s.bridge_conflicts} · Steep zones: ${s.steep_zones} · Narrow segments: ${s.narrow_segments}</div>
    `;

    const d = result.downloads || {};
    els.downloads.innerHTML = [
      d.geojson ? `<a href="${d.geojson}" download>GeoJSON</a>` : "",
      d.csv ? `<a href="${d.csv}" download>CSV</a>` : "",
      d.pdf ? `<a href="${d.pdf}" download>PDF Report</a>` : "",
    ].join("");
  }

  async function runAnalysis() {
    if (!state.start || !state.end) {
      setStatus("Select start and destination on the map first.", true);
      return;
    }

    els.analyze.disabled = true;
    setStatus("Analyzing route…");

    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          start: state.start,
          end: state.end,
          vehicle: vehiclePayload(),
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Analysis failed");
      }

      MapView.drawAnalysis(data);
      renderSummary(data);
      setStatus(`Done — ${data.summary.feasibility} (${data.summary.distance_km} km).`);
    } catch (err) {
      setStatus(err.message || String(err), true);
      els.summarySection.hidden = true;
    } finally {
      els.analyze.disabled = false;
    }
  }

  function reset() {
    state.start = null;
    state.end = null;
    els.startLabel.textContent = "—";
    els.endLabel.textContent = "—";
    els.summarySection.hidden = true;
    els.summary.innerHTML = "";
    els.downloads.innerHTML = "";
    MapView.clearAllPoints();
    setMode("start");
    setStatus("Click the map to select start.");
  }

  els.modeStart.addEventListener("click", () => setMode("start"));
  els.modeEnd.addEventListener("click", () => setMode("end"));
  els.analyze.addEventListener("click", runAnalysis);
  els.reset.addEventListener("click", reset);

  loadLayers().catch((err) => {
    setStatus(`Failed to load map layers: ${err.message}`, true);
  });
})();
