/* global L */

const MapView = (() => {
  const state = {
    map: null,
    layers: {
      route: null,
      markers: null,
      obstacles: null,
      profile: null,
    },
    startMarker: null,
    endMarker: null,
    clickHandler: null,
  };

  function init(center = [44.7, 4.35], zoom = 7) {
    if (state.map) return state.map;

    state.map = L.map("map", {
      zoomControl: true,
      attributionControl: true,
    }).setView(center, zoom);

    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
      maxZoom: 18,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
    }).addTo(state.map);

    Object.keys(state.layers).forEach((key) => {
      state.layers[key] = L.layerGroup().addTo(state.map);
    });

    return state.map;
  }

  function onClick(handler) {
    if (state.clickHandler) state.map.off("click", state.clickHandler);
    state.clickHandler = (e) => handler(e.latlng);
    state.map.on("click", state.clickHandler);
  }

  function setMarker(kind, latlng) {
    const isStart = kind === "start";
    const icon = L.divIcon({
      className: "",
      html: `<div style="
        width:16px;height:16px;border-radius:50%;
        background:${isStart ? "#1f6b4a" : "#c45c26"};
        border:2px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.35);
      "></div>`,
      iconSize: [16, 16],
      iconAnchor: [8, 8],
    });

    if (isStart) {
      if (state.startMarker) state.layers.markers.removeLayer(state.startMarker);
      state.startMarker = L.marker(latlng, { icon }).addTo(state.layers.markers);
    } else {
      if (state.endMarker) state.layers.markers.removeLayer(state.endMarker);
      state.endMarker = L.marker(latlng, { icon }).addTo(state.layers.markers);
    }
  }

  function clearAnalysis() {
    state.layers.route.clearLayers();
    state.layers.profile.clearLayers();
  }

  function clearObstacles() {
    state.layers.obstacles.clearLayers();
  }

  function clearAllPoints() {
    state.layers.markers.clearLayers();
    state.startMarker = null;
    state.endMarker = null;
    clearAnalysis();
    clearObstacles();
  }

  function drawUploadedRoute(routeFeature) {
    clearAnalysis();
    const layer = L.geoJSON(routeFeature, {
      style: { color: "#0b3d2e", weight: 5, opacity: 0.95 },
    }).addTo(state.layers.route);
    try {
      state.map.fitBounds(layer.getBounds(), { padding: [40, 40] });
    } catch (_) {
      /* empty */
    }
  }

  function drawProfile(profile) {
    state.layers.profile.clearLayers();
    if (!profile || !profile.length) return;
    profile.forEach((p) => {
      const m = L.circleMarker([p.lat, p.lon], {
        radius: 4,
        color: "#245c42",
        fillColor: "#fff",
        fillOpacity: 1,
        weight: 2,
      }).addTo(state.layers.profile);
      m.bindTooltip(p.km_label, { permanent: false, direction: "top" });
    });
  }

  function drawObstacles(obstacles) {
    clearObstacles();
    obstacles.forEach((obs) => {
      const status = obs.status || "pending";
      const color =
        status === "conflict"
          ? "#9f1239"
          : status === "caution"
            ? "#b45309"
            : status === "ok"
              ? "#157a4b"
              : status === "off_route"
                ? "#64748b"
                : "#1f6b4a";
      const marker = L.circleMarker([obs.lat, obs.lon], {
        radius: 8,
        color,
        weight: 2,
        fillColor: color,
        fillOpacity: 0.85,
      }).addTo(state.layers.obstacles);

      const km = obs.km_label || (obs.km != null ? `km ${obs.km}` : "");
      if (km) {
        marker.bindTooltip(km, { permanent: true, direction: "right", offset: [8, 0], className: "km-label" });
      }
      marker.bindPopup(
        `<strong>${obs.name}</strong><br/>
         ${km ? km + "<br/>" : ""}
         ${obs.type} · ${obs.value ?? "—"}<br/>
         severity: ${obs.severity || "—"} · bypass: ${obs.bypass_possible ? "yes" : "no"}<br/>
         ${obs.detail || status}`
      );
    });
  }

  function drawAnalysis(result) {
    if (result.route) drawUploadedRoute(result.route);
    if (result.distance_profile) drawProfile(result.distance_profile);
    if (result.obstacles && result.obstacles.features) {
      const list = result.obstacles.features.map((f) => ({
        name: f.properties.name,
        type: f.properties.type,
        value: f.properties.value,
        lon: f.geometry.coordinates[0],
        lat: f.geometry.coordinates[1],
        status: f.properties.status,
        detail: f.properties.detail,
        km: f.properties.km,
        km_label: f.properties.km_label,
        severity: f.properties.severity,
        bypass_possible: f.properties.bypass_possible,
        note: f.properties.note,
      }));
      drawObstacles(list);
    }
  }

  return {
    init,
    onClick,
    setMarker,
    clearAllPoints,
    clearAnalysis,
    clearObstacles,
    drawAnalysis,
    drawUploadedRoute,
    drawObstacles,
    drawProfile,
  };
})();
