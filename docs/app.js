/* East Boston sea level rise: three-view map.
   Planner view   = Esri Light Gray Canvas, for decisions.
   Atlas view     = no tiles, the same layers drawn in a print language.
   Ink view       = Overprint: the same layers again, as halftone dots on a grid (docs/overprint.js).
   One list of layer toggles drives all three views.
   Data comes from docs/data/*.js (built by map/export_web.py) as window.EB.<name>. */
(function () {
  const D = window.EB, S = D.stats;
  const $ = (s) => document.querySelector(s);

  // ------------------------------------------------------------------ palette
  const C = {
    ink: "#1d3557", paper: "#f3eee2", land: "#fbf8f0", street: "#b9b1a0", parcelPale: "#ddd5c4",
    flood21: "#08519c", flood36: "#4292c6",      // both can show at once: +21 in is drawn on top, darker, inside the wider +36 in area
    // walk to nearest grocer: blue = close, gray = middle, warm = far / cut off / flooded
    imperv: ["#f1efe9", "#d4cfc4", "#a8a193", "#6f6a60", "#2f2c27"],     // grey ramp: pavement, light to dark
    people: ["#ece9fb", "#c5bdf2", "#9085e9", "#6250d6", "#3a2c93"],
    owner: { public: "#2b8cbe", exempt: "#9e9ac8", private: "#c4c4c0" },
    critical: "#d03b3b", blueLine: "#003da5", power: "#b7791f",
    expo: ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"],
    lines: { red: "#da291c", orange: "#ed8b00", blue: "#003da5", green: "#00843d", silver: "#7c878e", other: "#5b6770" },     // MBTA line colours
  };
  const SLR_LABEL = { 0: "today", 21: "at +21 in, 2050s", 36: "at +36 in, 2070s" };

  // ------------------------------------------------------------------ layer toggles (one list, both views)
  const GROUPS = [
    ["Flooding", [["f21", "High tide at +21 in (2050s)"], ["f36", "High tide at +36 in (2070s)"], ["assets", "Critical assets"], ["unpave", "Public paved land"]]],
    ["Food", [["stores", "Food stores"]]],
    ["Movement", [["blueline", "Subway and Silver Line"]]],
    ["Energy", [["power", "Electrical substations"]]],
  ];
  // layers that colour the same shapes cannot stack, so they are offered as one choice each
  const PICKS = [
    ["Colour parcels by", "pf", [["expo", "Flood exposure"], ["imperv", "Impervious surface"], ["owner", "Owner type"]]],
    ["Colour census tracts by", "tf", [["vuln", "Social vulnerability"], ["transit", "Workers who commute by transit"], ["noveh", "Households with no car"]]],
  ];
  const PICK_KEYS = PICKS.flatMap((g) => g[2].map(([k]) => k));
  const DEFAULT_ON = ["f36", "expo"];          // first glance: the flood and how much of each parcel it covers

  // ------------------------------------------------------------------ state (URL params make any state linkable)
  const q = new URLSearchParams(location.search);
  const onList = q.get("on") ? q.get("on").split(",") : DEFAULT_ON;
  const state = { view: q.get("view") || "planner", lens: q.get("lens") || "off", on: {} };
  // the Overprint view uses the same toggles: each layer is one ink (owner type prints two)
  const OP = window.Overprint;
  const inkOn = (i) => !!state.on[i.follows || i.k] && !(i.byTide && slr() === "0");
  const slr = () => state.on.f36 ? "36" : state.on.f21 ? "21" : "0";   // scenario the data layers follow: the highest tide ticked
  GROUPS.flatMap((g) => g[1]).forEach(([k]) => { state.on[k] = onList.includes(k); });
  PICK_KEYS.forEach((k) => { state.on[k] = onList.includes(k); });

  // ------------------------------------------------------------------ maps
  const GLYPHS = "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf";
  const esri = (svc) => ({ type: "raster", tileSize: 256, maxzoom: 16, attribution: "Esri",
    tiles: [`https://services.arcgisonline.com/ArcGIS/rest/services/${svc}/MapServer/tile/{z}/{y}/{x}`] });
  const B = (S.meta && S.meta.bounds) || [-71.060, 42.343, -70.984, 42.401], BOUNDS = [[B[0], B[1]], [B[2], B[3]]];      // study area extent, written by the export
  const wide = () => window.innerWidth > 820;
  const mk = (id, style, interactive) => new maplibregl.Map({
    container: id, style, bounds: BOUNDS, fitBoundsOptions: { padding: wide() ? { top: 30, bottom: 30, left: 290, right: 370 } : 20 },
    interactive, attributionControl: false, minZoom: 11, maxZoom: 18, dragRotate: false, pitchWithRotate: false,
  });
  const planner = mk("map-planner", { version: 8, glyphs: GLYPHS, sources: { base: esri("Canvas/World_Light_Gray_Base"), ref: esri("Canvas/World_Light_Gray_Reference") },
    layers: [{ id: "base", type: "raster", source: "base" }] }, true);
  const atlas = mk("map-atlas", { version: 8, glyphs: GLYPHS, sources: {}, layers: [{ id: "paper", type: "background", paint: { "background-color": C.paper } }] }, true);
  const sat = mk("map-sat", { version: 8, sources: { img: esri("World_Imagery") }, layers: [{ id: "img", type: "raster", source: "img" }] }, false);
  // overprint view: a near-blank paper map; the inks are drawn on a canvas above it
  const ink = mk("map-ink", { version: 8, glyphs: GLYPHS, sources: {}, layers: [{ id: "paper", type: "background", paint: { "background-color": "#f0eee8" } }] }, true);
  const maps = { planner, atlas, ink, sat };
  let press = null;
  const SOURCES = "Climate Ready Boston · City of Boston Assessing · USDA SNAP · ACS · OpenStreetMap · USGS 3DEP";
  planner.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: "Esri Light Gray Canvas · " + SOURCES }), "bottom-right");
  atlas.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: SOURCES }), "bottom-right");
  ink.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: SOURCES }), "bottom-right");
  [planner, atlas, ink].forEach((m) => {
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-left");
    m.addControl(new maplibregl.ScaleControl({ unit: "imperial" }), "bottom-left");
    m.touchZoomRotate.disableRotation();
  });

  // keep the three cameras locked to whichever view is active
  Object.entries(maps).forEach(([name, m]) => m.on("move", () => {
    if (name !== state.view) return;
    const cam = { center: m.getCenter(), zoom: m.getZoom() };
    Object.entries(maps).forEach(([n, o]) => { if (n !== name) o.jumpTo(cam); });
  }));

  // ------------------------------------------------------------------ helpers
  const zoomW = (expr, k12, k16) => ["interpolate", ["exponential", 2], ["zoom"], 12, ["*", k12, expr], 16, ["*", k16, expr]];
  const stepColor = (prop, stops, colors) => { const e = ["step", ["coalesce", ["get", prop], 0], colors[0]]; stops.forEach((s, i) => e.push(s, colors[i + 1])); return e; };
  function pattern(m, name, draw, size) {
    const c = document.createElement("canvas"); c.width = c.height = size; const g = c.getContext("2d"); draw(g, size);
    m.addImage(name, g.getImageData(0, 0, size, size), { pixelRatio: 2 });
  }

  // ------------------------------------------------------------------ layers: one definition, two themes
  const THEME = {
    planner: { isAtlas: false, halo: "#fff", etch: "#0d366b", stationRing: "#1f2937", hole: "#fff",
      line: ["match", ["get", "line"], "red", C.lines.red, "orange", C.lines.orange, "blue", C.lines.blue, "green", C.lines.green, "silver", C.lines.silver, C.lines.other] },
    atlas: { isAtlas: true, halo: C.land, etch: C.ink, line: "#111", stationRing: "#111", hole: C.land },
  };
  function build(m, T) {
    const src = (id, data) => m.addSource(id, { type: "geojson", data });
    ["parcels", "aoi", "flood21", "flood36", "water", "stores", "streets",
      "blueline", "stations", "tracts", "svi", "assets", "power_subs"].forEach((k) => src(k, D[k]));
    const label = (size) => ({ "text-font": ["Open Sans Semibold"], "text-size": size || 11.5 });
    const halo = { "text-color": "#111", "text-halo-color": T.halo, "text-halo-width": 1.6 };
    const add = (l) => m.addLayer(l);

    if (T.isAtlas) {
      src("land", D.land); src("shore", D.shore);
      add({ id: "shore", type: "line", source: "shore", paint: { "line-color": C.ink, "line-width": 0.7, "line-opacity": ["interpolate", ["linear"], ["get", "i"], 0, 0.55, 4, 0.12] } });
      add({ id: "land", type: "fill", source: "land", paint: { "fill-color": C.land } });
      add({ id: "coast", type: "line", source: "land", paint: { "line-color": C.ink, "line-width": 0.9 } });
      add({ id: "streets", type: "line", source: "streets", paint: { "line-color": C.street, "line-width": zoomW(1, 0.25, 1.1), "line-opacity": ["case", ["==", ["get", "eb"], 1], 0.9, 0.55] } });
    }
    if (!T.isAtlas) add({ id: "water", type: "fill", source: "water", paint: { "fill-color": "#c9dcea", "fill-opacity": 0.85 } });   // open water, always shown
    add({ id: "tract-fill", type: "fill", source: "tracts", paint: { "fill-opacity": 0.6, "fill-outline-color": "#fff" } });
    add({ id: "svi-fill", type: "fill", source: "svi", paint: { "fill-opacity": 0.6, "fill-outline-color": "#fff", "fill-color": stepColor("vuln_pct", [0.2, 0.4, 0.6, 0.8], C.people) } });
    add({ id: "flood36", type: "fill", source: "flood36", paint: { "fill-color": C.flood36, "fill-opacity": T.isAtlas ? 0.25 : 0.45 } });
    add({ id: "flood21", type: "fill", source: "flood21", paint: { "fill-color": C.flood21, "fill-opacity": T.isAtlas ? 0.25 : 0.45 } });
    if (T.isAtlas) {                                               // parcels are always inked on paper; data fills print over them
      add({ id: "parcels-shadow", type: "fill", source: "parcels", paint: { "fill-color": C.ink, "fill-opacity": 0.13, "fill-translate": [1.6, 1.6] } });
      add({ id: "parcels-base", type: "fill", source: "parcels", paint: { "fill-color": C.parcelPale } });
    }
    add({ id: "parcels", type: "fill", source: "parcels", paint: { "fill-color": "#ccc" } });
    if (!T.isAtlas) add({ id: "parcels-line", type: "line", source: "parcels", paint: { "line-color": "#fff", "line-width": ["interpolate", ["linear"], ["zoom"], 13, 0.15, 16, 0.8] } });
    ["21", "36"].forEach((s) => {
      if (!T.isAtlas) return;
      add({ id: "tide" + s, type: "line", source: "flood" + s, paint: { "line-color": T.etch, "line-width": 1.1, "line-dasharray": [3, 2] } });
    });
    add({ id: "unpave", type: "line", source: "parcels", filter: ["==", ["get", "unpave_candidate"], 1], paint: { "line-color": "#b25a00", "line-width": 1.8, "line-dasharray": [2, 1.5] } });
    add({ id: "aoi", type: "line", source: "aoi", paint: T.isAtlas ? { "line-color": "#111", "line-width": 1, "line-dasharray": [0.6, 2.4] } : { "line-color": "#333", "line-width": 1.4, "line-dasharray": [4, 3] } });
    add({ id: "blueline", type: "line", source: "blueline", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": T.line, "line-width": T.isAtlas ? zoomW(1, 2.2, 7) : zoomW(1, 1.6, 5) } });
    add({ id: "assets", type: "circle", source: "assets", paint: { "circle-radius": 4, "circle-color": "#7a1f1f", "circle-stroke-color": "#fff", "circle-stroke-width": 1.5 } });
    add({ id: "stores", type: "circle", source: "stores", paint: { "circle-stroke-width": 1.6, "circle-radius": zoomW(["match", ["get", "size"], 3, 2.6, 2, 1.5, 1], 2.2, 5.5) } });
    add({ id: "stations", type: "circle", source: "stations", paint: { "circle-radius": zoomW(1, 3.4, 10), "circle-stroke-width": 2 } });
    add({ id: "power-subs", type: "circle", source: "power_subs", paint: { "circle-radius": zoomW(1, 4.5, 11), "circle-color": T.hole, "circle-stroke-color": C.power, "circle-stroke-width": 3 } });
    if (!T.isAtlas) add({ id: "ref", type: "raster", source: "ref" });      // official label layer sits above the data
    const caps = T.isAtlas ? (e) => ["upcase", e] : (e) => e;
    add({ id: "stations-label", type: "symbol", source: "stations", layout: Object.assign({ "text-field": caps(["get", "name"]), "text-offset": [0, 1.2], "text-anchor": "top", "text-padding": 4, "text-letter-spacing": T.isAtlas ? 0.12 : 0 }, label(T.isAtlas ? 10.5 : 11.5)), paint: halo });
    add({ id: "power-label", type: "symbol", source: "power_subs", layout: Object.assign({ "text-field": caps(["get", "name"]), "text-offset": [0, 1.3], "text-anchor": "top", "text-padding": 4 }, label(10.5)), paint: Object.assign({}, halo, { "text-color": "#6b4410" }) });
    add({ id: "stores-label", type: "symbol", source: "stores", filter: ["==", ["get", "size"], 3], layout: Object.assign({ "text-field": ["get", "name"], "text-offset": [0, 1.2], "text-anchor": "top" }, label(10.5)), paint: halo });
    wireTips(m);
  }

  // ------------------------------------------------------------------ apply state
  function paint(m, T) {
    const s = slr(), wet = s !== "0", on = state.on;
    const vis = (id, show) => m.getLayer(id) && m.setLayoutProperty(id, "visibility", show ? "visible" : "none");
    ["21", "36"].forEach((k) => { vis("flood" + k, on["f" + k]); vis("tide" + k, T.isAtlas && on["f" + k]); });

    const fill = (on.expo && wet) ? "expo" : on.imperv ? "imperv" : on.owner ? "owner" : null;
    vis("parcels", !!fill); vis("parcels-line", !!fill);
    if (fill === "expo") { m.setPaintProperty("parcels", "fill-color", stepColor("ff" + s, [0.25, 0.5, 0.75, 0.95], C.expo)); m.setPaintProperty("parcels", "fill-opacity", ["case", [">", ["get", "ff" + s], 0.02], 0.9, 0]); }
    if (fill === "imperv") { m.setPaintProperty("parcels", "fill-color", stepColor("impervious_frac", [0.5, 0.7, 0.85, 0.95], C.imperv)); m.setPaintProperty("parcels", "fill-opacity", 0.88); }
    if (fill === "owner") { m.setPaintProperty("parcels", "fill-color", ["match", ["get", "owner_type"], "public", C.owner.public, "exempt", C.owner.exempt, C.owner.private]); m.setPaintProperty("parcels", "fill-opacity", 0.85); }
    if (T.isAtlas) m.setPaintProperty("parcels-base", "fill-opacity", 1);

    vis("svi-fill", on.vuln); vis("tract-fill", on.transit || on.noveh);
    if (on.transit) m.setPaintProperty("tract-fill", "fill-color", stepColor("transit_pct", [30, 40, 50, 60], C.people));
    else if (on.noveh) m.setPaintProperty("tract-fill", "fill-color", stepColor("noveh_pct", [20, 30, 40, 50], C.people));

    vis("unpave", on.unpave); vis("assets", on.assets);
    ["blueline", "stations", "stations-label"].forEach((id) => vis(id, on.blueline));
    ["power-subs", "power-label"].forEach((id) => vis(id, on.power));

    vis("stores", on.stores); vis("stores-label", on.stores);
    const closed = wet ? ["==", ["get", "c" + s], 1] : false;
    m.setPaintProperty("stores", "circle-color", ["case", closed, T.hole, ["case", ["==", ["get", "grocer"], 1], "#14532d", "#7f9b88"]]);
    m.setPaintProperty("stores", "circle-stroke-color", ["case", closed, C.critical, "#fff"]);
    m.setPaintProperty("stations", "circle-color", T.hole);
    m.setPaintProperty("stations", "circle-stroke-color", T.stationRing);

  }

  function apply() {
    paint(planner, THEME.planner); paint(atlas, THEME.atlas);
    // which map is on top, and what the lens shows
    const lensSrc = state.lens === "off" ? null : state.lens === "sat" ? "sat" : (state.view === "planner" ? "atlas" : "planner");
    if (controlsFor !== state.view) renderControls();
    Object.keys(maps).forEach((n) => { const w = $("#wrap-" + n); w.classList.toggle("active", n === state.view);
      w.classList.toggle("lens", n === lensSrc); });
    $("#stage").classList.toggle("lens-on", !!lensSrc);
    $("#lens-other").textContent = state.view === "planner" ? "Etching" : "Basemap";
    const cam = { center: maps[state.view].getCenter(), zoom: maps[state.view].getZoom() };
    Object.entries(maps).forEach(([n, o]) => { if (n !== state.view) o.jumpTo(cam); });
    const mark = (id, key) => document.querySelectorAll(id + " button").forEach((b) => b.classList.toggle("on", b.dataset.v === state[key]));
    mark("#seg-view", "view");
    document.querySelectorAll("#seg-lens input").forEach((i) => { i.checked = state.lens === i.dataset.lens; });
    document.querySelectorAll("#controls input[data-k]").forEach((i) => { i.checked = state.on[i.dataset.k]; });
    drawInk();
    document.querySelectorAll("#controls input[type=radio]").forEach((i) => { i.checked = !!state.on[i.value]; });
    document.querySelectorAll("#controls .clear").forEach((b) => { b.hidden = !b.dataset.keys.split(",").some((k) => state.on[k]); });
    renderLegend();
  }

  // ------------------------------------------------------------------ panel: layer toggles
  let controlsFor = null;
  function drawInk() { if (press && state.view === "ink") press.draw(OP.INKS.filter(inkOn), slr()); }
  function renderControls() {
    controlsFor = state.view;            // the same list in all three views
    const check = ([k, label]) => `<label class="chk"><input type="checkbox" data-k="${k}"> ${label}</label>`;
    const pick = ([name, group, items]) => { const keys = items.map(([k]) => k).join(",");
      return `<div class="grp"><div class="muted small pick-head">${name}<button type="button" class="clear" data-keys="${keys}" title="Clear" aria-label="Clear ${name.toLowerCase()}">&#x2715;</button></div>` + items.map(([k, label]) =>
        `<label class="chk"><input type="radio" name="${group}" value="${k}" data-keys="${keys}"> ${label}</label>`).join("") + `</div>`; };
    $("#controls").innerHTML =
      GROUPS.map(([name, items]) => `<div class="grp"><div class="muted small">${name}</div>${items.map(check).join("")}</div>`).join("") +
      PICKS.map(pick).join("");
  }

  // ------------------------------------------------------------------ panel: legend follows the toggles
  const row = (cls, color, label) => `<div class="lg-row"><span class="sw ${cls}" style="background:${color};border-color:${color}"></span>${label}</div>`;
  const ramp = (colors, lo, hi) => `<div class="ramp">${colors.map((c) => `<i style="background:${c}"></i>`).join("")}</div><div class="ramp-ax"><span>${lo}</span><span>${hi}</span></div>`;
  function renderLegend() {
    if (state.view === "ink") {
      const act = OP.INKS.filter(inkOn), uniq = act.filter((i, n) => act.findIndex((o) => o.color === i.color) === n);
      let x = act.map((i) => `<div class="lg-row"><span class="ink-sw" style="background:${i.color}"></span>${i.label}</div>`).join("");
      $("#legend").innerHTML = act.length ? `<div class="grp">${x}</div><div class="grp muted small">Bigger dot = more of it in that spot.</div>` : `<div class="muted small">Tick a layer to print it.</div>`;
      $("#legend-panel").style.display = ""; return;
    }
    const on = state.on, s = slr(), wet = s !== "0", A = state.view === "atlas", T = THEME[state.view]; let h = "";
    if (on.expo && wet) h += `<div class="grp">Flood exposure, share of parcel under water${ramp(C.expo, "a little", "all of it")}</div>`;
    else if (on.imperv) h += `<div class="grp">Impervious surface, share of parcel${ramp(C.imperv, "under 50%", "over 95%")}</div>`;
    else if (on.owner) h += `<div class="grp">${row("", C.owner.public, "Public")}${row("", C.owner.exempt, "Tax exempt")}${row("", C.owner.private, "Private")}</div>`;
    if (on.vuln) h += `<div class="grp">Social vulnerability, citywide percentile${ramp(C.people, "0", "100")}</div>`;
    if (on.transit) h += `<div class="grp">Workers who commute by transit${ramp(C.people, "under 30%", "over 60%")}</div>`;
    else if (on.noveh) h += `<div class="grp">Households with no car${ramp(C.people, "under 20%", "over 50%")}</div>`;
    let g = "";
    if (on.f21) g += row("", C.flood21, "High tide at +21 in, 2050s");
    if (on.f36) g += row("", C.flood36, "High tide at +36 in, 2070s");
    if (on.stores) g += row("dot", "#14532d", "Grocer, larger = supermarket") + row("dot", "#7f9b88", "Convenience store") + (wet ? row("ring", C.critical, "Store under water") : "");
    if (on.unpave) g += row("line", "#b25a00", "Public paved land");
    if (on.assets) g += row("dot", "#7a1f1f", "Critical asset");
    if (on.power) g += row("ring", C.power, "Electrical substation");
    if (g) h += `<div class="grp">${g}</div>`;
    $("#legend").innerHTML = h;
    $("#legend-panel").style.display = h ? "" : "none";
  }

  // ------------------------------------------------------------------ tooltips on stores and stations
  function wireTips(m) {
    const pop = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10 });
    let raf = 0;
    m.on("mousemove", (e) => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        const f = m.queryRenderedFeatures(e.point, { layers: ["stores", "stations", "power-subs", "assets"] })[0];
        if (f) pop.setLngLat(e.lngLat).setHTML(tip(f)).addTo(m); else pop.remove();
        m.getCanvas().style.cursor = f ? "pointer" : "";
      });
    });
    m.on("mouseout", () => pop.remove());
  }
  const ASSET_LABEL = { school: "School", fire_station: "Fire station", police: "Police station", hospital: "Hospital", community_centre: "Community centre" };
  function tip(f) {
    const p = f.properties, s = slr();
    if (f.layer.id === "power-subs") return `<b>${p.name} substation</b>` +
      (s !== "0" && p["share_" + s] >= 0.25 ? `<br><span style="color:#b3261e">Under water ${SLR_LABEL[s]}</span>` : "");
    if (f.layer.id === "assets") return `<b>${p.name || ASSET_LABEL[p.asset_type]}</b><br>${ASSET_LABEL[p.asset_type]}`;
    if (f.layer.id === "stores") return `<b>${p.name}</b><br>${p.type}${s !== "0" && p["c" + s] ? "<br><span style='color:#b3261e'>Under water " + SLR_LABEL[s] + "</span>" : ""}`;
    const share = s === "0" ? 0 : Math.round(p["share_" + s] * 100);
    const txt = s !== "0" && p["s" + s] ? `Under water ${SLR_LABEL[s]}: ${share}% of the station area floods`
      : share > 0 ? `Water at the edge ${SLR_LABEL[s]}: ${share}% of the station area floods` : "";
    return `<b>${p.name}</b> · ${p.lines} Line` + (txt ? `<br>${txt}` : "");
  }

  // ------------------------------------------------------------------ wiring
  let loaded = 0;
  function ready() {
    if (++loaded < 3) return;
    renderControls(); wire(); apply();
    // credits stay one click away behind the small "i" button instead of a strip across the map
    document.querySelectorAll(".maplibregl-ctrl-attrib").forEach((e) => { e.classList.remove("maplibregl-compact-show"); e.removeAttribute("open"); });
  }
  planner.on("load", () => { build(planner, THEME.planner); ready(); });
  atlas.on("load", () => { build(atlas, THEME.atlas); ready(); });
  ink.on("load", () => {
    const src = (id, data) => ink.addSource(id, { type: "geojson", data });
    src("land", D.land); src("aoi", D.aoi); src("streets", D.streets);
    ink.addLayer({ id: "land", type: "fill", source: "land", paint: { "fill-color": "#fdfcfa" } });
    ink.addLayer({ id: "coast", type: "line", source: "land", paint: { "line-color": "#bdb8ac", "line-width": 0.8 } });
    ink.addLayer({ id: "streets", type: "line", source: "streets", filter: ["==", ["get", "eb"], 1], paint: { "line-color": "#d8d4ca", "line-width": zoomW(1, 0.2, 1) } });
    ink.addLayer({ id: "aoi", type: "line", source: "aoi", paint: { "line-color": "#8c877b", "line-width": 0.9, "line-dasharray": [1, 2.5] } });
    ink.addLayer({ id: "hoods", type: "symbol", source: "aoi", layout: { "text-field": ["upcase", ["get", "name"]], "text-font": ["Open Sans Semibold"], "text-size": 10, "text-letter-spacing": 0.14 },
      paint: { "text-color": "#6f6b62", "text-halo-color": "#fdfcfa", "text-halo-width": 1.6 } });
    press = OP.create(ink, $("#ink-canvas"), D.ink);
    ink.on("move", drawInk); ink.on("resize", drawInk);
    ready();
  });

  function wire() {
    const seg = (id, key) => $(id).addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; state[key] = b.dataset.v; apply(); });
    seg("#seg-view", "view");
    // two on/off toggles; turning one on turns the other off, both off = no x-ray
    $("#seg-lens").addEventListener("change", (e) => { state.lens = e.target.checked ? e.target.dataset.lens : "off"; apply(); });
    $("#controls").addEventListener("change", (e) => {
      const t = e.target;
      if (t.type === "radio") { t.dataset.keys.split(",").forEach((k) => { state.on[k] = k === t.value; }); apply(); return; }
      const k = t.dataset.k; if (!k) return;
      state.on[k] = t.checked; apply();
    });
    $("#controls").addEventListener("click", (e) => {
      const b = e.target.closest(".clear"); if (!b) return;
      b.dataset.keys.split(",").forEach((k) => { state.on[k] = false; }); apply();
    });
    const root = document.documentElement.style, stage = $("#stage");
    const move = (x, y) => { root.setProperty("--lx", x + "px"); root.setProperty("--ly", y + "px"); };
    stage.addEventListener("pointermove", (e) => move(e.clientX, e.clientY));
    stage.addEventListener("pointerleave", () => move(-500, -500));
    document.addEventListener("keydown", (e) => { if (e.key === "l" || e.key === "L") { state.lens = state.lens === "off" ? "other" : "off"; apply(); } });
    if (q.get("lx")) move(Number(q.get("lx")), Number(q.get("ly")));      // lets a link pin the lens

    // the controls card folds into its corner by hand from the header, and on its own as soon as someone
    // pans or zooms the map; it stays folded until reopened. The legend always stays open.
    const panel = $("#panel"), head = panel.querySelector(".card-head");
    const fold = (shut) => { panel.classList.toggle("collapsed", shut); head.setAttribute("aria-expanded", String(!shut)); };
    head.addEventListener("click", () => fold(!panel.classList.contains("collapsed")));
    [planner, atlas].forEach((m) => m.on("movestart", (e) => { if (e.originalEvent) fold(true); }));     // user moves only, not the camera sync
  }
})();
