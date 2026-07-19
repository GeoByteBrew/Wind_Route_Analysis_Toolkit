/* global MapView */

(() => {
  const els = {
    routeFile: document.getElementById("route-file"),
    sampleRoute: document.getElementById("btn-sample-route"),
    routeMeta: document.getElementById("route-meta"),
    obsType: document.getElementById("obs-type"),
    obsName: document.getElementById("obs-name"),
    obsValue: document.getElementById("obs-value"),
    placeObs: document.getElementById("btn-place-obs"),
    obsList: document.getElementById("obs-list"),
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
    routeFeature: null,
    placingObstacle: false,
    obstacles: [],
  };

  const DEFAULT_VALUES = {
    low_bridge: 3.8,
    narrow_road: 4.0,
    weight_limit: 60,
    steep_slope: 12,
    note: "",
  };

  function setStatus(msg, isError = false) {
    els.status.textContent = msg || "";
    els.status.style.color = isError ? "#9f1239" : "";
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

  function renderObsList() {
    if (!state.obstacles.length) {
      els.obsList.innerHTML = "<li class='hint'>No obstacles yet — place them on the route.</li>";
      return;
    }
    els.obsList.innerHTML = state.obstacles
      .map(
        (o, idx) => `
      <li>
        <div>
          <strong>${o.name}</strong>
          <span class="hint">${o.type.replace("_", " ")} · ${o.value ?? "—"}</span>
        </div>
        <button type="button" data-idx="${idx}" class="linkish">Remove</button>
      </li>`
      )
      .join("");

    els.obsList.querySelectorAll("button[data-idx]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = Number(btn.getAttribute("data-idx"));
        state.obstacles.splice(idx, 1);
        MapView.drawObstacles(state.obstacles);
        renderObsList();
      });
    });
  }

  function applyRoutePayload(data, { replaceObstacles = false } = {}) {
    state.routeFeature = data.route;
    els.routeMeta.textContent = `${data.distance_km} km · ${data.source_format || "file"} · ${
      data.route.properties.vertex_count || "?"
    } vertices`;
    MapView.drawUploadedRoute(data.route);
    if (data.start) {
      MapView.setMarker("start", { lat: data.start.lat, lng: data.start.lon });
    }
    if (data.end) {
      MapView.setMarker("end", { lat: data.end.lat, lng: data.end.lon });
    }
    if (replaceObstacles && Array.isArray(data.obstacles)) {
      state.obstacles = data.obstacles.map((o) => ({ ...o }));
      MapView.drawObstacles(state.obstacles);
      renderObsList();
    }
    setStatus("Route loaded. Place obstacles on the corridor, then run analysis.");
  }

  async function uploadFile(file) {
    const form = new FormData();
    form.append("file", file);
    setStatus(`Uploading ${file.name}…`);
    const res = await fetch("/api/upload/route", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload failed");
    applyRoutePayload(data);
  }

  async function loadSampleRoute() {
    setStatus("Loading Montpellier → Lyon sample KMZ…");
    const res = await fetch("/api/sample/route");
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Sample route failed");
    applyRoutePayload(data, { replaceObstacles: true });
  }

  function renderSummary(result) {
    const s = result.summary;
    els.summarySection.hidden = false;
    els.summary.innerHTML = `
      <span class="summary__badge ${s.feasibility}">${s.feasibility}</span>
      <div><strong>${s.distance_km} km</strong> · ${s.issues_count} issue(s)</div>
      <div>Conflicts: ${s.conflict_count || 0} · Cautions: ${s.caution_count || 0} · Obstacles: ${s.obstacle_count || 0}</div>
    `;

    const d = result.downloads || {};
    els.downloads.innerHTML = [
      d.geojson ? `<a href="${d.geojson}" download>GeoJSON</a>` : "",
      d.csv ? `<a href="${d.csv}" download>CSV</a>` : "",
      d.pdf ? `<a href="${d.pdf}" download>PDF Report</a>` : "",
    ].join("");
  }

  async function runAnalysis() {
    if (!state.routeFeature) {
      setStatus("Upload or load a route first.", true);
      return;
    }

    els.analyze.disabled = true;
    setStatus("Analyzing…");

    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          route: state.routeFeature,
          obstacles: state.obstacles,
          vehicle: vehiclePayload(),
        }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Analysis failed");

      MapView.drawAnalysis(data);
      if (data.obstacles && data.obstacles.features) {
        state.obstacles = data.obstacles.features.map((f) => ({
          id: f.properties.id,
          name: f.properties.name,
          type: f.properties.type,
          value: f.properties.value,
          lon: f.geometry.coordinates[0],
          lat: f.geometry.coordinates[1],
          note: f.properties.note,
          status: f.properties.status,
          detail: f.properties.detail,
        }));
        renderObsList();
      }
      renderSummary(data);
      setStatus(`Done — ${data.summary.feasibility} (${data.summary.distance_km} km).`);
    } catch (err) {
      setStatus(err.message || String(err), true);
      els.summarySection.hidden = true;
    } finally {
      els.analyze.disabled = false;
      state.placingObstacle = false;
      els.placeObs.classList.remove("chip--active");
    }
  }

  function reset() {
    state.routeFeature = null;
    state.obstacles = [];
    state.placingObstacle = false;
    els.routeMeta.textContent = "No route loaded yet.";
    els.routeFile.value = "";
    els.summarySection.hidden = true;
    els.summary.innerHTML = "";
    els.downloads.innerHTML = "";
    els.placeObs.classList.remove("chip--active");
    MapView.clearAllPoints();
    renderObsList();
    setStatus("Upload a route, or load the Montpellier → Lyon sample.");
  }

  function onMapClick(latlng) {
    if (!state.placingObstacle) return;
    const type = els.obsType.value;
    const rawVal = els.obsValue.value;
    state.obstacles.push({
      id: `obs_${Date.now()}`,
      name: els.obsName.value || "Obstacle",
      type,
      value: rawVal === "" ? null : Number(rawVal),
      lon: latlng.lng,
      lat: latlng.lat,
    });
    state.placingObstacle = false;
    els.placeObs.classList.remove("chip--active");
    MapView.drawObstacles(state.obstacles);
    renderObsList();
    setStatus("Obstacle added. Place more or run analysis.");
  }

  async function boot() {
    const meta = await fetch("/api/meta").then((r) => r.json());
    MapView.init([meta.center.lat, meta.center.lon], 7);
    MapView.onClick(onMapClick);
    renderObsList();
    await loadSampleRoute();
  }

  els.analyze.addEventListener("click", runAnalysis);
  els.reset.addEventListener("click", reset);
  els.sampleRoute.addEventListener("click", () => {
    loadSampleRoute().catch((err) => setStatus(err.message, true));
  });
  els.routeFile.addEventListener("change", () => {
    const file = els.routeFile.files && els.routeFile.files[0];
    if (!file) return;
    uploadFile(file).catch((err) => setStatus(err.message, true));
  });
  els.placeObs.addEventListener("click", () => {
    if (!state.routeFeature) {
      setStatus("Load a route before placing obstacles.", true);
      return;
    }
    state.placingObstacle = !state.placingObstacle;
    els.placeObs.classList.toggle("chip--active", state.placingObstacle);
    setStatus(
      state.placingObstacle
        ? "Click the map on the corridor to place the obstacle."
        : "Placement cancelled."
    );
  });
  els.obsType.addEventListener("change", () => {
    const t = els.obsType.value;
    const def = DEFAULT_VALUES[t];
    els.obsValue.value = def === "" || def === undefined ? "" : def;
    if (
      !els.obsName.value ||
      els.obsName.value.startsWith("Bridge") ||
      els.obsName.value.startsWith("Narrow") ||
      els.obsName.value.startsWith("Weight") ||
      els.obsName.value.startsWith("Steep") ||
      els.obsName.value === "Note" ||
      els.obsName.value.startsWith("Obstacle")
    ) {
      els.obsName.value =
        t === "low_bridge"
          ? "Bridge A"
          : t === "narrow_road"
            ? "Narrow section"
            : t === "weight_limit"
              ? "Weight limit"
              : t === "steep_slope"
                ? "Steep segment"
                : "Note";
    }
  });

  boot().catch((err) => setStatus(`Failed to start: ${err.message}`, true));
})();
