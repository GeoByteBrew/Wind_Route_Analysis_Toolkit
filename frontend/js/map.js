/* global L */

const MapView = (() => {
  const state = {
    map: null,
    layers: {
      roads: null,
      bridges: null,
      slopes: null,
      places: null,
      route: null,
      analysisBridges: null,
      analysisSlopes: null,
      markers: null,
    },
    startMarker: null,
    endMarker: null,
  };

  function init(center = [43.55, 3.55], zoom = 9) {
    state.map = L.map("map", {
      zoomControl: true,
      attributionControl: true,
    }).setView(center, zoom);

    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
      maxZoom: 18,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
    }).addTo(state.map);

    state.layers.roads = L.layerGroup().addTo(state.map);
    state.layers.bridges = L.layerGroup().addTo(state.map);
    state.layers.slopes = L.layerGroup().addTo(state.map);
    state.layers.places = L.layerGroup().addTo(state.map);
    state.layers.route = L.layerGroup().addTo(state.map);
    state.layers.analysisBridges = L.layerGroup().addTo(state.map);
    state.layers.analysisSlopes = L.layerGroup().addTo(state.map);
    state.layers.markers = L.layerGroup().addTo(state.map);

    return state.map;
  }

  function onClick(handler) {
    state.map.on("click", (e) => handler(e.latlng));
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
    state.layers.analysisBridges.clearLayers();
    state.layers.analysisSlopes.clearLayers();
  }

  function clearAllPoints() {
    state.layers.markers.clearLayers();
    state.startMarker = null;
    state.endMarker = null;
    clearAnalysis();
  }

  function drawBaseLayers({ roads, bridges, slopes, places }) {
    state.layers.roads.clearLayers();
    state.layers.bridges.clearLayers();
    state.layers.slopes.clearLayers();
    state.layers.places.clearLayers();

    if (slopes) {
      L.geoJSON(slopes, {
        style: {
          color: "#c45c26",
          weight: 1,
          fillColor: "#c45c26",
          fillOpacity: 0.12,
        },
        onEachFeature: (f, layer) => {
          layer.bindPopup(
            `<strong>${f.properties.name}</strong><br/>Max slope: ${f.properties.max_slope_pct}%`
          );
        },
      }).addTo(state.layers.slopes);
    }

    if (roads) {
      L.geoJSON(roads, {
        style: (f) => ({
          color: f.properties.highway === "motorway" || f.properties.highway === "trunk"
            ? "#3d5c4c"
            : "#6f8a7c",
          weight: f.properties.highway === "motorway" ? 3.5 : 2,
          opacity: 0.75,
        }),
        onEachFeature: (f, layer) => {
          layer.bindPopup(
            `<strong>${f.properties.name}</strong><br/>
             ${f.properties.from} → ${f.properties.to}<br/>
             Width: ${f.properties.width_m} m · Slope: ${f.properties.max_slope_pct}%`
          );
        },
      }).addTo(state.layers.roads);
    }

    if (bridges) {
      L.geoJSON(bridges, {
        pointToLayer: (_f, latlng) =>
          L.circleMarker(latlng, {
            radius: 5,
            color: "#334155",
            weight: 1,
            fillColor: "#94a3b8",
            fillOpacity: 0.85,
          }),
        onEachFeature: (f, layer) => {
          layer.bindPopup(
            `<strong>${f.properties.name}</strong><br/>Clearance: ${f.properties.clearance_m} m`
          );
        },
      }).addTo(state.layers.bridges);
    }

    if (places) {
      L.geoJSON(places, {
        pointToLayer: (_f, latlng) =>
          L.circleMarker(latlng, {
            radius: 3,
            color: "#14201a",
            fillColor: "#14201a",
            fillOpacity: 0.7,
            weight: 0,
          }),
        onEachFeature: (f, layer) => {
          layer.bindTooltip(f.properties.name, {
            permanent: true,
            direction: "right",
            offset: [8, 0],
            className: "place-label",
          });
        },
      }).addTo(state.layers.places);
    }
  }

  function drawAnalysis(result) {
    clearAnalysis();

    if (result.route) {
      const routeLayer = L.geoJSON(result.route, {
        style: {
          color: "#0b3d2e",
          weight: 5,
          opacity: 0.95,
        },
      }).addTo(state.layers.route);

      try {
        state.map.fitBounds(routeLayer.getBounds(), { padding: [40, 40] });
      } catch (_) {
        /* empty */
      }
    }

    if (result.bridges) {
      L.geoJSON(result.bridges, {
        pointToLayer: (f, latlng) => {
          const conflict = f.properties.status === "conflict";
          return L.circleMarker(latlng, {
            radius: conflict ? 8 : 5,
            color: conflict ? "#9f1239" : "#157a4b",
            weight: 2,
            fillColor: conflict ? "#e11d48" : "#34d399",
            fillOpacity: 0.9,
          });
        },
        onEachFeature: (f, layer) => {
          const p = f.properties;
          layer.bindPopup(
            `<strong>${p.name}</strong><br/>
             Clearance: ${p.clearance_m} m<br/>
             Vehicle height: ${p.vehicle_height_m} m<br/>
             Status: <b>${p.status}</b>`
          );
          if (p.status === "conflict") layer.openPopup();
        },
      }).addTo(state.layers.analysisBridges);
    }

    if (result.slopes) {
      L.geoJSON(result.slopes, {
        style: (f) => ({
          color: f.properties.status === "steep" ? "#c45c26" : "#a16207",
          weight: 2,
          fillColor: f.properties.status === "steep" ? "#c45c26" : "#ca8a04",
          fillOpacity: 0.28,
        }),
        onEachFeature: (f, layer) => {
          layer.bindPopup(
            `<strong>${f.properties.name}</strong><br/>
             Max slope: ${f.properties.max_slope_pct}%<br/>
             Limit: ${f.properties.vehicle_max_slope_pct}%`
          );
        },
      }).addTo(state.layers.analysisSlopes);
    }
  }

  return {
    init,
    onClick,
    setMarker,
    clearAllPoints,
    clearAnalysis,
    drawBaseLayers,
    drawAnalysis,
  };
})();
