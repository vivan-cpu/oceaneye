// oceaneye.js - same detection as detect.py, but in javascript so it runs in the browser.
// (github pages can't run python, so we rewrote it)
// img = { db: Float32Array (NaN = no data), w, h, pxKm (pixel width in km), pxKm2 (pixel area) }

(function (root) {

  const SETTINGS = {
    speckle: 7,          // lee filter window
    backgroundKm: 3.0,
    contrastDb: 3.0,
    maxDb: -18.0,
    minAreaKm2: 0.05,
    twoPass: true,       // 2nd pass so the middle of big slicks gets found too
  };

  // ---------- helpers ----------

  // summed-area table so box averages are fast even on big images
  function integral(a, w, h) {
    const s = new Float64Array((w + 1) * (h + 1));
    for (let y = 0; y < h; y++) {
      let row = 0;
      for (let x = 0; x < w; x++) {
        row += a[y * w + x];
        s[(y + 1) * (w + 1) + x + 1] = s[y * (w + 1) + x + 1] + row;
      }
    }
    return s;
  }

  function boxSum(s, w, h, x, y, r) {
    const x0 = Math.max(0, x - r), y0 = Math.max(0, y - r);
    const x1 = Math.min(w, x + r + 1), y1 = Math.min(h, y + r + 1);
    const W = w + 1;
    return s[y1 * W + x1] - s[y0 * W + x1] - s[y1 * W + x0] + s[y0 * W + x0];
  }

  function boxMean(a, w, h, size) {
    const r = size >> 1, s = integral(a, w, h), out = new Float32Array(w * h);
    for (let y = 0; y < h; y++)
      for (let x = 0; x < w; x++) {
        const x0 = Math.max(0, x - r), y0 = Math.max(0, y - r);
        const x1 = Math.min(w, x + r + 1), y1 = Math.min(h, y + r + 1);
        out[y * w + x] = boxSum(s, w, h, x, y, r) / ((x1 - x0) * (y1 - y0));
      }
    return out;
  }

  const toDb = v => 10 * Math.log10(Math.max(v, 1e-6));

  // lee speckle filter on linear values
  function lee(lin, w, h, size) {
    const sq = new Float32Array(lin.length);
    for (let i = 0; i < lin.length; i++) sq[i] = lin[i] * lin[i];
    const m = boxMean(lin, w, h, size), m2 = boxMean(sq, w, h, size);
    const v = new Float32Array(lin.length);
    let noise = 0;
    for (let i = 0; i < lin.length; i++) { v[i] = Math.max(m2[i] - m[i] * m[i], 0); noise += v[i]; }
    noise /= lin.length;
    const out = new Float32Array(lin.length);
    for (let i = 0; i < lin.length; i++) {
      const k = v[i] / (v[i] + noise + 1e-12);
      out[i] = m[i] + k * (lin[i] - m[i]);
    }
    return out;
  }

  // disk shaped neighbourhood offsets
  function disk(r) {
    const o = [];
    for (let dy = -r; dy <= r; dy++)
      for (let dx = -r; dx <= r; dx++)
        if (dx * dx + dy * dy <= r * r) o.push([dx, dy]);
    return o;
  }

  function erode(m, w, h, se) {
    const out = new Uint8Array(m.length);
    for (let y = 0; y < h; y++)
      for (let x = 0; x < w; x++) {
        let ok = 1;
        for (const [dx, dy] of se) {
          const xx = x + dx, yy = y + dy;
          if (xx < 0 || yy < 0 || xx >= w || yy >= h || !m[yy * w + xx]) { ok = 0; break; }
        }
        out[y * w + x] = ok;
      }
    return out;
  }

  function dilate(m, w, h, se) {
    const out = new Uint8Array(m.length);
    for (let y = 0; y < h; y++)
      for (let x = 0; x < w; x++) {
        if (!m[y * w + x]) continue;
        for (const [dx, dy] of se) {
          const xx = x + dx, yy = y + dy;
          if (xx >= 0 && yy >= 0 && xx < w && yy < h) out[yy * w + xx] = 1;
        }
      }
    return out;
  }

  function fillHoles(m, w, h) {
    // flood the background from the border, anything not reached is a hole
    const seen = new Uint8Array(m.length), stack = [];
    const push = i => { if (!m[i] && !seen[i]) { seen[i] = 1; stack.push(i); } };
    for (let x = 0; x < w; x++) { push(x); push((h - 1) * w + x); }
    for (let y = 0; y < h; y++) { push(y * w); push(y * w + w - 1); }
    while (stack.length) {
      const i = stack.pop(), x = i % w, y = (i / w) | 0;
      if (x > 0) push(i - 1); if (x < w - 1) push(i + 1);
      if (y > 0) push(i - w); if (y < h - 1) push(i + w);
    }
    const out = new Uint8Array(m.length);
    for (let i = 0; i < m.length; i++) out[i] = m[i] || !seen[i] ? 1 : 0;
    return out;
  }

  // 8-connected labelling. returns {lab, n, pixels: [[idx...], ...]}
  function label(m, w, h) {
    const lab = new Int32Array(m.length), groups = [];
    let n = 0;
    for (let i = 0; i < m.length; i++) {
      if (!m[i] || lab[i]) continue;
      n++;
      const px = [], stack = [i];
      lab[i] = n;
      while (stack.length) {
        const j = stack.pop(); px.push(j);
        const x = j % w, y = (j / w) | 0;
        for (let dy = -1; dy <= 1; dy++)
          for (let dx = -1; dx <= 1; dx++) {
            const xx = x + dx, yy = y + dy;
            if (xx < 0 || yy < 0 || xx >= w || yy >= h) continue;
            const k = yy * w + xx;
            if (m[k] && !lab[k]) { lab[k] = n; stack.push(k); }
          }
      }
      groups.push(px);
    }
    return { lab, n, groups };
  }

  // ---------- main steps ----------

  function findDarkSpots(img, s) {
    const { w, h, db } = img;
    const N = w * h;
    const sea = new Uint8Array(N);
    const lin = new Float32Array(N);
    for (let i = 0; i < N; i++) {
      sea[i] = Number.isFinite(db[i]) ? 1 : 0;
      lin[i] = sea[i] ? Math.pow(10, db[i] / 10) : 0;
    }

    const f = lee(lin, w, h, s.speckle);
    const smooth = new Float32Array(N);
    for (let i = 0; i < N; i++) smooth[i] = sea[i] ? toDb(f[i]) : NaN;

    // background = average of sea pixels in a big window (ignoring no-data)
    let win = Math.round(s.backgroundKm / img.pxKm) | 1;
    win = Math.max(win, 15);
    const a = new Float32Array(N);
    for (let i = 0; i < N; i++) a[i] = sea[i] ? smooth[i] : 0;
    const num = boxMean(a, w, h, win), den = boxMean(sea, w, h, win);
    const bg = new Float32Array(N);
    for (let i = 0; i < N; i++) bg[i] = num[i] / Math.max(den[i], 1e-6);

    let dark = new Uint8Array(N);
    for (let i = 0; i < N; i++)
      dark[i] = sea[i] && bg[i] - smooth[i] > s.contrastDb && smooth[i] < s.maxDb ? 1 : 0;

    // second pass (same as 3b in detect.py): work out the background again without the
    // dark pixels, so the middle of a big slick doesn't count as "normal sea"
    if (s.twoPass && dark.some(v => v)) {
      const near = dilate(dark, w, h, disk(2));
      const clean = new Uint8Array(N), a2 = new Float32Array(N), vals = [];
      for (let i = 0; i < N; i++) {
        clean[i] = sea[i] && !near[i] ? 1 : 0;
        a2[i] = clean[i] ? smooth[i] : 0;
        if (clean[i]) vals.push(smooth[i]);
      }
      vals.sort((p, q) => p - q);
      const sceneBg = vals.length ? vals[vals.length >> 1] : NaN;
      const n2 = boxMean(a2, w, h, win), d2 = boxMean(clean, w, h, win);
      const nBig = boxMean(a2, w, h, win * 4 + 1), dBig = boxMean(clean, w, h, win * 4 + 1);
      for (let i = 0; i < N; i++) {
        if (d2[i] > 0) bg[i] = n2[i] / d2[i];
        else if (dBig[i] > 0) bg[i] = nBig[i] / dBig[i];
        else if (Number.isFinite(sceneBg)) bg[i] = sceneBg;
        dark[i] = sea[i] && bg[i] - smooth[i] > s.contrastDb && smooth[i] < s.maxDb ? 1 : 0;
      }
    }

    dark = dilate(erode(dark, w, h, disk(1)), w, h, disk(1));   // opening
    dark = erode(dilate(dark, w, h, disk(2)), w, h, disk(2));   // closing
    dark = fillHoles(dark, w, h);

    const minPx = Math.max(Math.floor(s.minAreaKm2 / img.pxKm2), 10);
    const L = label(dark, w, h);
    const keep = L.groups.filter(g => g.length >= minPx);
    return { smooth, bg, sea, keep };
  }

  function sobelAt(a, w, h, x, y) {
    const g = (xx, yy) => a[Math.min(h - 1, Math.max(0, yy)) * w + Math.min(w - 1, Math.max(0, xx))];
    const gx = (g(x + 1, y - 1) + 2 * g(x + 1, y) + g(x + 1, y + 1)) - (g(x - 1, y - 1) + 2 * g(x - 1, y) + g(x - 1, y + 1));
    const gy = (g(x - 1, y + 1) + 2 * g(x, y + 1) + g(x + 1, y + 1)) - (g(x - 1, y - 1) + 2 * g(x, y - 1) + g(x + 1, y - 1));
    // skimage's sobel is scaled by 1/4 and averaged over the 2 directions
    return Math.sqrt((gx * gx + gy * gy) / 2) / 4;
  }

  function scoreBlob(f, sceneBg, seaKm2) {
    let pts = 0; const why = [];
    if (f.contrastDb >= 6) { pts += 2; why.push("very dark vs sea (+2)"); }
    else if (f.contrastDb >= 4) { pts += 1; why.push("dark vs sea (+1)"); }
    if (f.elongation >= 3) { pts += 2; why.push("long & thin like a ship trail (+2)"); }
    else if (f.elongation >= 1.8) { pts += 1; why.push("stretched shape (+1)"); }
    if (f.edge >= 0.9) { pts += 1; why.push("sharp edges (+1)"); }
    else if (f.edge < 0.45) { pts -= 1; why.push("fuzzy edges, could be calm wind (-1)"); }
    if (f.areaKm2 > 0.25 * seaKm2) { pts -= 3; why.push("covers huge part of scene, probably low wind (-3)"); }
    if (sceneBg < -22) { pts -= 1; why.push("very calm sea overall, hard to tell (-1)"); }
    const verdict = pts >= 4 ? "likely oil" : pts >= 2 ? "possible oil" : "probably look-alike";
    return { pts, verdict, why };
  }

  function analyse(img, opts) {
    const s = Object.assign({}, SETTINGS, opts || {});
    const { w, h } = img;
    const { smooth, sea, keep } = findDarkSpots(img, s);

    const seaVals = [];
    for (let i = 0; i < sea.length; i += 7) if (sea[i]) seaVals.push(smooth[i]);
    seaVals.sort((a, b) => a - b);
    const sceneBg = seaVals.length ? seaVals[seaVals.length >> 1] : NaN;
    let seaCount = 0; for (let i = 0; i < sea.length; i++) seaCount += sea[i];
    const seaKm2 = seaCount * img.pxKm2;
    const smoothFilled = Float32Array.from(smooth, v => Number.isFinite(v) ? v : sceneBg);

    const blobs = keep.map(px => {
      // work in a small box around the blob so dilations are cheap
      let x0 = w, y0 = h, x1 = 0, y1 = 0;
      for (const i of px) { const x = i % w, y = (i / w) | 0; if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
      const P = 8;
      const bx0 = Math.max(0, x0 - P), by0 = Math.max(0, y0 - P);
      const bw = Math.min(w, x1 + P + 1) - bx0, bh = Math.min(h, y1 + P + 1) - by0;
      const m = new Uint8Array(bw * bh);
      for (const i of px) m[(((i / w) | 0) - by0) * bw + (i % w) - bx0] = 1;

      const plus = [[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1]];
      let d2 = m; for (let k = 0; k < 2; k++) d2 = dilate(d2, bw, bh, plus);
      let d6 = d2; for (let k = 0; k < 4; k++) d6 = dilate(d6, bw, bh, plus);
      const er = erode(m, bw, bh, plus);

      let inSum = 0, inN = 0, outSum = 0, outN = 0, edgeSum = 0, edgeN = 0;
      let sx = 0, sy = 0;
      const edgePts = [];
      for (let yy = 0; yy < bh; yy++)
        for (let xx = 0; xx < bw; xx++) {
          const k = yy * bw + xx, gi = (yy + by0) * w + xx + bx0;
          if (m[k]) {
            // clean-up can pull in a few no-data pixels, skip those (like nanmean in python)
            if (Number.isFinite(smooth[gi])) { inSum += smooth[gi]; inN++; }
            sx += xx; sy += yy;
            if (!er[k]) { edgeSum += sobelAt(smoothFilled, w, h, xx + bx0, yy + by0); edgeN++; edgePts.push(gi); }
          } else if (d6[k] && !d2[k] && sea[gi]) { outSum += smooth[gi]; outN++; }
        }
      const n = px.length;
      const inner = inN ? inSum / inN : sceneBg, outer = outN ? outSum / outN : inner;
      const contrast = outer - inner;
      const edgeGrad = edgeN ? edgeSum / edgeN : 0;
      const edge = contrast > 0 ? edgeGrad / (contrast / 4 + 1e-6) : 0;

      // shape from second moments (same as skimage regionprops)
      const cx = sx / n, cy = sy / n;
      let mxx = 0, myy = 0, mxy = 0;
      for (let yy = 0; yy < bh; yy++)
        for (let xx = 0; xx < bw; xx++)
          if (m[yy * bw + xx]) { const dx = xx - cx, dy = yy - cy; mxx += dx * dx; myy += dy * dy; mxy += dx * dy; }
      mxx /= n; myy /= n; mxy /= n;
      const t = Math.sqrt(((mxx - myy) / 2) ** 2 + mxy * mxy);
      const l1 = (mxx + myy) / 2 + t, l2 = Math.max((mxx + myy) / 2 - t, 0);
      const major = 4 * Math.sqrt(l1), minor = Math.max(4 * Math.sqrt(l2), 1);

      const f = {
        areaKm2: n * img.pxKm2, meanDb: inner, contrastDb: contrast,
        elongation: major / minor, edge, lengthKm: major * img.pxKm,
        cx: cx + bx0, cy: cy + by0, edgePts,
      };
      const sc = scoreBlob(f, sceneBg, seaKm2);
      return Object.assign(f, { score: sc.pts, verdict: sc.verdict, why: sc.why });
    });

    blobs.sort((a, b) => b.score - a.score || b.areaKm2 - a.areaKm2);
    blobs.forEach((b, i) => b.id = i + 1);

    const warnings = [];
    if (sceneBg < -22) warnings.push("Sea is very calm in this image (low wind). Calm water also looks dark, so results here are not reliable.");
    if (sceneBg > -10) warnings.push("Sea is very rough/bright (strong wind). Oil can get mixed into the water and disappear from radar.");
    return { blobs, smooth, sceneBg, warnings };
  }

  // ---------- fake test scene (same idea as make_test_scene.py) ----------

  function rng(seed) {   // small seeded random generator (mulberry32)
    return function () {
      seed |= 0; seed = seed + 0x6D2B79F5 | 0;
      let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }

  function gamma(r, k) {  // marsaglia-tsang, mean 1 after dividing by k
    const d = k - 1 / 3, c = 1 / Math.sqrt(9 * d);
    for (;;) {
      let x, v;
      do {
        const u1 = r() || 1e-9, u2 = r();
        x = Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
        v = 1 + c * x;
      } while (v <= 0);
      v = v * v * v;
      const u = r();
      if (u < 1 - 0.0331 * x ** 4 || Math.log(u) < 0.5 * x * x + d * (1 - v + Math.log(v))) return d * v / k;
    }
  }

  function testScene(opts) {
    const o = Object.assign({ w: 1100, h: 900, wind: 0, seed: 7 }, opts || {});
    const { w, h } = o, r = rng(o.seed), db = new Float32Array(w * h);
    const trail = new Float32Array(w * h);
    for (let i = 0; i <= 600; i++) {
      const t = i / 600, X = 850 - 620 * t, Y = 200 + 380 * t + 60 * Math.sin(t * 5), R = 3 + 14 * t;
      for (let y = Math.floor(Y - R - 2); y <= Y + R + 2; y++)
        for (let x = Math.floor(X - R - 2); x <= X + R + 2; x++) {
          if (x < 0 || y < 0 || x >= w || y >= h) continue;
          const d = Math.hypot(x - X, y - Y);
          trail[y * w + x] = Math.max(trail[y * w + x], Math.min(1, Math.max(0, R + 0.5 - d)));
        }
    }
    for (let y = 0; y < h; y++)
      for (let x = 0; x < w; x++) {
        let v = -15 + o.wind + 1.5 * Math.sin(x / 260) + 0.8 * Math.cos(y / 190);
        v -= 9 * trail[y * w + x];
        v -= 6 * Math.exp(-(((x - 300) / 260) ** 2 + ((y - 230) / 160) ** 2));
        const rr = Math.hypot(x - 900, y - 720);
        v += -6 * Math.exp(-((rr / 25) ** 2)) + 2 * Math.exp(-(((rr - 45) / 8) ** 2));
        if ((x - 858) ** 2 + (y - 195) ** 2 < 9) v = 5;
        db[y * w + x] = toDb(Math.pow(10, v / 10) * gamma(r, 4.4));
      }
    return { db, w, h, pxKm: 0.0213, pxKm2: 0.0213 * 0.0221, name: "Test scene (simulated)" };
  }

  const api = { SETTINGS, analyse, testScene, toDb };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.OceanEye = api;
})(this);
