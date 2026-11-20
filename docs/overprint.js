window.Overprint = (function () {
  // dot values are one digit 0..9 per cell (map/ink_grid.py q()); tip(v) turns that digit back into words for the tooltip
  const about = (v) => `about ${Math.round(v / 9 * 10) * 10}%`;
  const level = (v) => `level ${v} of 9 (9 = highest tract on the map)`;
  const INKS = [
    { k: "f21", label: "High tide at +21 in (2050s)", color: "#2b9ed8", tip: (v) => `${about(v)} of this spot under water` },
    { k: "f36", label: "High tide at +36 in (2070s)", color: "#a9ddf3", tip: (v) => `${about(v)} of this spot under water` },   // lighter: the wider extent, underneath +21 in
    { k: "assets", label: "Critical assets", color: "#e8443a", tip: () => "Critical asset here" },
    { k: "unpave", label: "Public paved land", color: "#ff6c2f", tip: (v) => `${about(v)} of parcel area` },
    { k: "stores", label: "Food stores, larger = supermarket", color: "#ffe14d", tip: (v) => v >= 9 ? "Supermarket here" : v >= 6 ? "Grocer here" : "Convenience store here" },
    { k: "blueline", label: "Subway and Silver Line, larger = station", color: "#00838a", tip: (v) => v >= 9 ? "Station here" : "Line passes here" },
    { k: "power", label: "Electrical substations", color: "#4b4038", tip: () => "Substation here" },
    { k: "expo", byTide: true, label: "Flood exposure, share of parcels under water", color: "#1f4fa3", tip: (v) => `${about(v)} of parcel area under water` },
    { k: "imperv", label: "Impervious surface, over 50%", color: "#8d9096", tip: (v) => `about ${Math.round((50 + 50 * v / 9) / 5) * 5}% of parcel area paved` },
    { k: "owner", label: "Public land", color: "#00a95c", tip: (v) => `${about(v)} of parcel area` },
    { k: "owner_ex", follows: "owner", label: "Tax exempt land", color: "#9a6fd1", tip: (v) => `${about(v)} of parcel area` },
    { k: "vuln", label: "Social vulnerability", color: "#2e2a6b", tip: level },
    { k: "transit", label: "Workers who commute by transit", color: "#914e72", tip: level },
    { k: "noveh", label: "Households with no car", color: "#ff62bd", tip: level },
  ];
  const LEVEL_ZOOMS = [11.7, 13.3];                     // below the first: 200 m grid; between: 100 m; above: 50 m
  // each ink prints slightly out of register, as on a real press
  const OFFSET = INKS.reduce((o, ink, i) => { const a = i * 2.4; o[ink.k] = [Math.cos(a), Math.sin(a)]; return o; }, {});

  function create(map, canvas, data) {
    const ctx = canvas.getContext("2d");
    const levels = data.levels.map((L) => ({ spacing: L.spacing, lon: L.lon, lat: L.lat, v: L.v, n: L.lon.length, x: new Float32Array(L.lon.length), y: new Float32Array(L.lon.length) }));
    let last = null;  

    function draw(active, tide) {
      const dpr = window.devicePixelRatio || 1, w = canvas.clientWidth, h = canvas.clientHeight;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) { canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr); }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
      const z = map.getZoom(), L = levels[z < LEVEL_ZOOMS[0] ? 0 : z < LEVEL_ZOOMS[1] ? 1 : 2];
      const mpp = 40075016.686 * Math.cos(map.getCenter().lat * Math.PI / 180) / (512 * Math.pow(2, z));
      const sp = L.spacing / mpp, rmax = sp * 0.56, pad = sp;
      const vis = [];
      for (let i = 0; i < L.n; i++) {
        const p = map.project([L.lon[i], L.lat[i]]); L.x[i] = p.x; L.y[i] = p.y;
        if (p.x > -pad && p.x < w + pad && p.y > -pad && p.y < h + pad) vis.push(i);
      }
      ctx.globalCompositeOperation = "multiply"; ctx.globalAlpha = 0.8;
      const keys = [];
      active.forEach((ink) => {
        const key = ink.byTide ? ink.k + tide : ink.k, s = L.v[key]; if (!s) return;
        keys.push([ink, key]);
        const ox = OFFSET[ink.k][0] * sp * 0.07, oy = OFFSET[ink.k][1] * sp * 0.07;
        ctx.fillStyle = ink.color; ctx.beginPath();
        for (const i of vis) {
          const v = s.charCodeAt(i) - 48; if (v <= 0) continue;
          const r = rmax * Math.sqrt(v / 9), x = L.x[i] + ox, y = L.y[i] + oy;
          ctx.moveTo(x + r, y); ctx.arc(x, y, r, 0, 6.2832);
        }
        ctx.fill();
      });
      ctx.globalCompositeOperation = "source-over"; ctx.globalAlpha = 1;
      last = { L, vis, keys, sp };
    }

  
    function at(x, y) {
      if (!last) return null;
      let best = -1, bd = last.sp * last.sp;
      for (const i of last.vis) { const dx = last.L.x[i] - x, dy = last.L.y[i] - y, d = dx * dx + dy * dy; if (d < bd) { bd = d; best = i; } }
      if (best < 0) return null;
      const rows = last.keys.map(([ink, key]) => ({ ink, v: last.L.v[key].charCodeAt(best) - 48 })).filter((r) => r.v > 0);
      return rows.length ?{ x: last.L.x[best], y: last.L.y[best], lngLat: [last.L.lon[best], last.L.lat[best]], rows } : null;
    }
    return { draw, at };
  }
  return { INKS, create };
})();
