/* global MapView */

(() => {
  const els = {
    routeFile: document.getElementById("route-file"),
    sampleRoute: document.getElementById("btn-sample-route"),
    routeMeta: document.getElementById("route-meta"),
    vehicleTemplate: document.getElementById("vehicle-template"),
    templateDesc: document.getElementById("template-desc"),
    obsType: document.getElementById("obs-type"),
    obsName: document.getElementById("obs-name"),
    obsValue: document.getElementById("obs-value"),
    obsSeverity: document.getElementById("obs-severity"),
    obsBypass: document.getElementById("obs-bypass"),
    obsNote: document.getElementById("obs-note"),
    obsPhoto: document.getElementById("obs-photo"),
    placeObs: document.getElementById("btn-place-obs"),
    obsList: document.getElementById("obs-list"),
    analyze: document.getElementById("btn-analyze"),
    saveProject: document.getElementById("btn-save-project"),
    projectFile: document.getElementById("project-file"),
    reset: document.getElementById("btn-reset"),
    status: document.getElementById("status"),
    summarySection: document.getElementById("summary-section"),
    summary: document.getElementById("summary"),
    checklist: document.getElementById("checklist"),
    downloads: document.getElementById("downloads"),
    length: document.getElementById("length"),
    width: document.getElementById("width"),
    height: document.getElementById("height"),
    weight: document.getElementById("weight"),
    slope: document.getElementById("slope"),
  };

  const state = {
    routeFeature: null,
    routeMeta: null,
    placingObstacle: false,
    obstacles: [],
    pendingPhoto: "",
    templates: [],
    lastResult: null,
  };

  const DEFAULT_VALUES = {
    low_bridge: 3.8,
    narrow_road: 4.0,
    weight_limit: 60,
    steep_slope: 12,
    note: "",
  };

  const LOCAL_KEY = "route_analysis_toolkit_project_v1";

  function setStatus(msg, isError = false) {
    els.status.textContent = msg || "";
    els.status.style.color = isError ? "#9f1239" : "";
  }

  function selectedTemplate() {
    return state.templates.find((t) => t.id === els.vehicleTemplate.value) || {
      id: "custom",
      label: "Custom",
    };
  }

  function vehiclePayload() {
    const t = selectedTemplate();
    return {
      length_m: Number(els.length.value),
      width_m: Number(els.width.value),
      height_m: Number(els.height.value),
      weight_t: Number(els.weight.value),
      max_slope_pct: Number(els.slope.value),
      template_id: t.id,
      template_label: t.label,
    };
  }

  function applyTemplate(id) {
    const t = state.templates.find((x) => x.id === id);
    if (!t) return;
    els.vehicleTemplate.value = t.id;
    els.templateDesc.textContent = t.description || "";
    els.length.value = t.length_m;
    els.width.value = t.width_m;
    els.height.value = t.height_m;
    els.weight.value = t.weight_t;
    els.slope.value = t.max_slope_pct;
  }

  function renderTemplates() {
    els.vehicleTemplate.innerHTML = state.templates
      .map((t) => `<option value="${t.id}">${t.label}</option>`)
      .join("");
    applyTemplate("blade");
  }

  function featureToObstacle(f) {
    return {
      id: f.properties.id,
      name: f.properties.name,
      type: f.properties.type,
      value: f.properties.value,
      lon: f.geometry.coordinates[0],
      lat: f.geometry.coordinates[1],
      note: f.properties.note || "",
      severity: f.properties.severity || "medium",
      bypass_possible: !!f.properties.bypass_possible,
      photo_data_url: f.properties.photo_data_url || "",
      status: f.properties.status,
      detail: f.properties.detail,
      km: f.properties.km,
      km_label: f.properties.km_label,
    };
  }

  function renderObsList() {
    if (!state.obstacles.length) {
      els.obsList.innerHTML = "<li class='hint'>No obstacles yet — place them on the route.</li>";
      return;
    }
    const sorted = [...state.obstacles].sort((a, b) => (a.km ?? 1e9) - (b.km ?? 1e9));
    els.obsList.innerHTML = sorted
      .map((o) => {
        const idx = state.obstacles.indexOf(o);
        return `
      <li>
        <div>
          <strong>${o.km_label ? o.km_label + " · " : ""}${o.name}</strong>
          <span class="hint">${o.type.replace("_", " ")} · ${o.value ?? "—"} · ${o.severity || "medium"}${
            o.bypass_possible ? " · bypass" : ""
          }${o.photo_data_url ? " · photo" : ""}</span>
        </div>
        <button type="button" data-idx="${idx}" class="linkish">Remove</button>
      </li>`;
      })
      .join("");

    els.obsList.querySelectorAll("button[data-idx]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = Number(btn.getAttribute("data-idx"));
        state.obstacles.splice(idx, 1);
        MapView.drawObstacles(state.obstacles);
        renderObsList();
        persistLocal();
      });
    });
  }

  function projectPayload(name = "route-project") {
    return {
      name,
      route: state.routeFeature,
      obstacles: state.obstacles,
      vehicle: vehiclePayload(),
      meta: {
        source_format: state.routeMeta?.source_format,
        distance_km: state.routeMeta?.distance_km,
      },
    };
  }

  function persistLocal() {
    if (!state.routeFeature) return;
    try {
      localStorage.setItem(LOCAL_KEY, JSON.stringify(projectPayload("autosave")));
    } catch (_) {
      /* quota */
    }
  }

  function applyRoutePayload(data, { replaceObstacles = false } = {}) {
    state.routeFeature = data.route;
    state.routeMeta = data;
    els.routeMeta.textContent = `${data.distance_km} km · ${data.source_format || "file"} · ${
      data.route.properties.vertex_count || "?"
    } vertices`;
    MapView.drawUploadedRoute(data.route);
    if (data.start) MapView.setMarker("start", { lat: data.start.lat, lng: data.start.lon });
    if (data.end) MapView.setMarker("end", { lat: data.end.lat, lng: data.end.lon });
    if (replaceObstacles && Array.isArray(data.obstacles)) {
      state.obstacles = data.obstacles.map((o) => ({ ...o }));
      MapView.drawObstacles(state.obstacles);
      renderObsList();
    }
    persistLocal();
    setStatus("Route loaded. Place obstacles (they snap to km), then run analysis.");
  }

  async function uploadFile(file) {
    const form = new FormData();
    form.append("file", file);
    setStatus(`Uploading ${file.name}…`);
    const res = await fetch("/api/upload/route", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload failed");
    state.obstacles = [];
    renderObsList();
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
      <div><strong>${s.distance_km} km</strong> · ${s.issues_count} issue(s) · ${s.vehicle_template || ""}</div>
      <div>Conflicts: ${s.conflict_count || 0} · Cautions: ${s.caution_count || 0} · Obstacles: ${s.obstacle_count || 0}</div>
    `;

    const checklist = result.checklist || [];
    els.checklist.innerHTML = checklist.length
      ? `<ul>${checklist
          .map(
            (c) =>
              `<li class="${c.state}"><span>${c.state === "done" ? "✓" : "☐"}</span> <div><strong>${c.item}</strong><br/><span class="hint">${c.detail}</span></div></li>`
          )
          .join("")}</ul>`
      : "";

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
    setStatus("Analyzing (snap + km order)…");
    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          route: state.routeFeature,
          obstacles: state.obstacles,
          vehicle: vehiclePayload(),
          snap: true,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Analysis failed");

      state.lastResult = data;
      MapView.drawAnalysis(data);
      if (data.obstacles && data.obstacles.features) {
        state.obstacles = data.obstacles.features.map(featureToObstacle);
        renderObsList();
      }
      renderSummary(data);
      persistLocal();
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

  async function saveProject() {
    if (!state.routeFeature) {
      setStatus("Load a route before saving.", true);
      return;
    }
    const name = `project-${new Date().toISOString().slice(0, 10)}`;
    const payload = projectPayload(name);

    // Local download always
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${name}.json`;
    a.click();
    URL.revokeObjectURL(url);

    try {
      const res = await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (res.ok) {
        setStatus(`Project saved (${data.id}). JSON downloaded.`);
      } else {
        setStatus("JSON downloaded (server save skipped).");
      }
    } catch (_) {
      setStatus("JSON downloaded locally.");
    }
    persistLocal();
  }

  function loadProjectObject(proj) {
    if (!proj.route) throw new Error("Invalid project file");
    state.routeFeature = proj.route;
    state.routeMeta = {
      distance_km: proj.route.properties?.distance_km || proj.meta?.distance_km,
      source_format: proj.meta?.source_format || "project",
    };
    els.routeMeta.textContent = `${state.routeMeta.distance_km ?? "?"} km · project`;
    MapView.drawUploadedRoute(proj.route);
    state.obstacles = (proj.obstacles || []).map((o) => ({ ...o }));
    MapView.drawObstacles(state.obstacles);
    renderObsList();
    if (proj.vehicle) {
      if (proj.vehicle.template_id) applyTemplate(proj.vehicle.template_id);
      els.length.value = proj.vehicle.length_m ?? els.length.value;
      els.width.value = proj.vehicle.width_m ?? els.width.value;
      els.height.value = proj.vehicle.height_m ?? els.height.value;
      els.weight.value = proj.vehicle.weight_t ?? els.weight.value;
      els.slope.value = proj.vehicle.max_slope_pct ?? els.slope.value;
    }
    persistLocal();
    setStatus("Project loaded.");
  }

  function reset() {
    state.routeFeature = null;
    state.routeMeta = null;
    state.obstacles = [];
    state.placingObstacle = false;
    state.pendingPhoto = "";
    state.lastResult = null;
    els.routeMeta.textContent = "No route loaded yet.";
    els.routeFile.value = "";
    els.obsPhoto.value = "";
    els.obsNote.value = "";
    els.summarySection.hidden = true;
    els.summary.innerHTML = "";
    els.checklist.innerHTML = "";
    els.downloads.innerHTML = "";
    els.placeObs.classList.remove("chip--active");
    MapView.clearAllPoints();
    renderObsList();
    localStorage.removeItem(LOCAL_KEY);
    setStatus("Upload a route, or load the Montpellier → Lyon sample.");
  }

  function readPhotoAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      if (!file) return resolve("");
      if (file.size > 2_500_000) {
        reject(new Error("Photo too large (max ~2.5 MB)."));
        return;
      }
      const reader = new FileReader();
      reader.onload = () => {
        const img = new Image();
        img.onload = () => {
          const maxW = 1280;
          const scale = Math.min(1, maxW / img.width);
          const canvas = document.createElement("canvas");
          canvas.width = Math.round(img.width * scale);
          canvas.height = Math.round(img.height * scale);
          const ctx = canvas.getContext("2d");
          ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
          resolve(canvas.toDataURL("image/jpeg", 0.72));
        };
        img.onerror = () => reject(new Error("Could not read image"));
        img.src = reader.result;
      };
      reader.onerror = () => reject(new Error("Could not read image"));
      reader.readAsDataURL(file);
    });
  }

  async function onMapClick(latlng) {
    if (!state.placingObstacle) return;
    if (!state.routeFeature) {
      setStatus("Load a route first.", true);
      return;
    }

    setStatus("Snapping to route…");
    try {
      const res = await fetch("/api/snap", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          route: state.routeFeature,
          lon: latlng.lng,
          lat: latlng.lat,
        }),
      });
      const snap = await res.json();
      if (!res.ok) throw new Error(snap.detail || "Snap failed");

      const type = els.obsType.value;
      const rawVal = els.obsValue.value;
      state.obstacles.push({
        id: `obs_${Date.now()}`,
        name: els.obsName.value || "Obstacle",
        type,
        value: rawVal === "" ? null : Number(rawVal),
        lon: snap.lon,
        lat: snap.lat,
        km: snap.km,
        km_label: snap.km_label,
        note: els.obsNote.value || "",
        severity: els.obsSeverity.value,
        bypass_possible: !!els.obsBypass.checked,
        photo_data_url: state.pendingPhoto || "",
      });

      state.placingObstacle = false;
      state.pendingPhoto = "";
      els.obsPhoto.value = "";
      els.placeObs.classList.remove("chip--active");
      MapView.drawObstacles(state.obstacles);
      renderObsList();
      persistLocal();
      setStatus(`Obstacle placed at ${snap.km_label} (offset ${snap.offset_m} m).`);
    } catch (err) {
      setStatus(err.message || String(err), true);
    }
  }

  async function boot() {
    const [meta, templates] = await Promise.all([
      fetch("/api/meta").then((r) => r.json()),
      fetch("/api/vehicle-templates").then((r) => r.json()),
    ]);
    state.templates = templates.templates || [];
    renderTemplates();
    MapView.init([meta.center.lat, meta.center.lon], 7);
    MapView.onClick(onMapClick);
    renderObsList();

    const saved = localStorage.getItem(LOCAL_KEY);
    if (saved) {
      try {
        loadProjectObject(JSON.parse(saved));
        setStatus("Restored autosaved project. Load sample to replace.");
        return;
      } catch (_) {
        /* fall through */
      }
    }
    await loadSampleRoute();
  }

  els.analyze.addEventListener("click", runAnalysis);
  els.saveProject.addEventListener("click", () => {
    saveProject().catch((err) => setStatus(err.message, true));
  });
  els.reset.addEventListener("click", reset);
  els.sampleRoute.addEventListener("click", () => {
    loadSampleRoute().catch((err) => setStatus(err.message, true));
  });
  els.routeFile.addEventListener("change", () => {
    const file = els.routeFile.files && els.routeFile.files[0];
    if (!file) return;
    uploadFile(file).catch((err) => setStatus(err.message, true));
  });
  els.projectFile.addEventListener("change", () => {
    const file = els.projectFile.files && els.projectFile.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        loadProjectObject(JSON.parse(reader.result));
      } catch (err) {
        setStatus(err.message || "Invalid project JSON", true);
      }
    };
    reader.readAsText(file);
  });
  els.vehicleTemplate.addEventListener("change", () => applyTemplate(els.vehicleTemplate.value));
  els.placeObs.addEventListener("click", () => {
    if (!state.routeFeature) {
      setStatus("Load a route before placing obstacles.", true);
      return;
    }
    state.placingObstacle = !state.placingObstacle;
    els.placeObs.classList.toggle("chip--active", state.placingObstacle);
    setStatus(
      state.placingObstacle
        ? "Click the map — point will snap to the route and get a km mark."
        : "Placement cancelled."
    );
  });
  els.obsPhoto.addEventListener("change", async () => {
    const file = els.obsPhoto.files && els.obsPhoto.files[0];
    try {
      state.pendingPhoto = await readPhotoAsDataUrl(file);
      setStatus(state.pendingPhoto ? "Photo ready — place obstacle on map." : "");
    } catch (err) {
      state.pendingPhoto = "";
      setStatus(err.message, true);
    }
  });
  els.obsType.addEventListener("change", () => {
    const t = els.obsType.value;
    const def = DEFAULT_VALUES[t];
    els.obsValue.value = def === "" || def === undefined ? "" : def;
    const autoNames = ["Bridge A", "Narrow section", "Weight limit", "Steep segment", "Note", "Obstacle"];
    if (!els.obsName.value || autoNames.some((n) => els.obsName.value.startsWith(n.split(" ")[0]) || autoNames.includes(els.obsName.value))) {
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
