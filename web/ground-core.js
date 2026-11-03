/*
 * OceanEye ground check - the detection maths, in JavaScript.
 * Same steps and numbers as crude_detect.py, so the AI trained in Python
 * (exported to web/oil_model.json by train_model.py) works here too.
 *
 * GroundCore.analyse(rgba, width, height, model) -> {patches, status, ...}
 * rgba = pixels from a canvas (ImageData.data). Nothing leaves the browser.
 */
(function (root) {
  const S = {
    DARK_DROP: 35, SHEEN_COLOUR: 14, MIN_PATCH_AREA: 800, WINDOW: 21,
    WORK_SIDE: 800, AI_OIL: 0.6, AI_NOT_OIL: 0.4,
  };
  const GAUSS7 = [0.03125, 0.109375, 0.21875, 0.28125, 0.21875, 0.109375, 0.03125];

  // OpenCV's default border: reflect without repeating the edge pixel
  function reflect(i, n) {
    if (n === 1) return 0;
    while (i < 0 || i >= n) {
      if (i < 0) i = -i;
      if (i >= n) i = 2 * n - 2 - i;
    }
    return i;
  }

  function convolveSep(src, w, h, k) {
    const r = (k.length - 1) / 2;
    const tmp = new Float32Array(w * h), out = new Float32Array(w * h);
    for (let y = 0; y < h; y++) {
      const row = y * w;
      for (let x = 0; x < w; x++) {
        let s = 0;
        for (let j = 0; j < k.length; j++) s += k[j] * src[row + reflect(x + j - r, w)];
        tmp[row + x] = s;
      }
    }
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        let s = 0;
        for (let j = 0; j < k.length; j++) s += k[j] * tmp[reflect(y + j - r, h) * w + x];
        out[y * w + x] = s;
      }
    }
    return out;
  }

  // cv2.blur (normalised box filter) with running sums
  function boxBlur(src, w, h, size) {
    const r = (size - 1) / 2;
    const tmp = new Float64Array(w * h), out = new Float32Array(w * h);
    for (let y = 0; y < h; y++) {
      const row = y * w;
      let s = 0;
      for (let j = -r; j <= r; j++) s += src[row + reflect(j, w)];
      for (let x = 0; x < w; x++) {
        tmp[row + x] = s / size;
        s += src[row + reflect(x + r + 1, w)] - src[row + reflect(x - r, w)];
      }
    }
    for (let x = 0; x < w; x++) {
      let s = 0;
      for (let j = -r; j <= r; j++) s += tmp[reflect(j, h) * w + x];
      for (let y = 0; y < h; y++) {
        out[y * w + x] = s / size;
        s += tmp[reflect(y + r + 1, h) * w + x] - tmp[reflect(y - r, h) * w + x];
      }
    }
    return out;
  }

  function median(arr) {
    const a = Float32Array.from(arr).sort();
    const n = a.length, m = n >> 1;
    return n % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
  }

  // binary erode/dilate with a square window; pixels outside the image are ignored (OpenCV default)
  function morph(mask, w, h, size, isDilate) {
    const r = (size - 1) / 2;
    const tmp = new Uint8Array(w * h), out = new Uint8Array(w * h);
    for (let y = 0; y < h; y++) {
      const row = y * w;
      for (let x = 0; x < w; x++) {
        let v = isDilate ? 0 : 1;
        const a = Math.max(0, x - r), b = Math.min(w - 1, x + r);
        for (let i = a; i <= b; i++) {
          if (isDilate ? mask[row + i] : !mask[row + i]) { v = isDilate ? 1 : 0; break; }
        }
        tmp[row + x] = v;
      }
    }
    for (let x = 0; x < w; x++) {
      for (let y = 0; y < h; y++) {
        let v = isDilate ? 0 : 1;
        const a = Math.max(0, y - r), b = Math.min(h - 1, y + r);
        for (let i = a; i <= b; i++) {
          if (isDilate ? tmp[i * w + x] : !tmp[i * w + x]) { v = isDilate ? 1 : 0; break; }
        }
        out[y * w + x] = v;
      }
    }
    return out;
  }

  // OpenCV's exact 8-bit colour conversions (fixed-point tables), so numbers match Python
  const LAB = (() => {
    const sat16 = (v) => Math.max(0, Math.min(65535, Math.round(v)));
    const gamma = new Uint16Array(256), cbrt = new Uint16Array(3072);
    for (let i = 0; i < 256; i++) {
      const x = i / 255;
      gamma[i] = sat16(255 * 8 * (x <= 0.04045 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4)));
    }
    for (let i = 0; i < 3072; i++) {
      const x = i / (255 * 8);
      cbrt[i] = sat16(32768 * (x < 0.008856 ? x * 7.787 + 0.13793103448275862 : Math.cbrt(x)));
    }
    const M = [0.412453, 0.35758, 0.180423, 0.212671, 0.71516, 0.072169, 0.019334, 0.119193, 0.950227];
    const WP = [0.950456, 1, 1.088754];
    const C = M.map((v, i) => Math.round(4096 * v / WP[Math.floor(i / 3)]));
    const sdiv = new Int32Array(256);
    for (let i = 1; i < 256; i++) sdiv[i] = Math.round((255 << 12) / i);
    return { gamma, cbrt, C, sdiv, Lshift: -Math.floor((16 * 255 * 32768 + 50) / 100) };
  })();
  const D = (x, n) => (x + (1 << (n - 1))) >> n;
  const u8 = (v) => Math.max(0, Math.min(255, v));

  function makeMaps(rgba, w, h) {
    const n = w * h;
    const L0 = new Float32Array(n), A = new Float32Array(n), B = new Float32Array(n);
    const gray = new Float32Array(n), sat = new Float32Array(n);
    const { gamma, cbrt, C, sdiv, Lshift } = LAB;
    for (let i = 0; i < n; i++) {
      const R = rgba[4 * i], G = rgba[4 * i + 1], Bl = rgba[4 * i + 2];
      const r = gamma[R], g = gamma[G], b = gamma[Bl];
      const fX = cbrt[D(r * C[0] + g * C[1] + b * C[2], 12)];
      const fY = cbrt[D(r * C[3] + g * C[4] + b * C[5], 12)];
      const fZ = cbrt[D(r * C[6] + g * C[7] + b * C[8], 12)];
      L0[i] = u8(D(296 * fY + Lshift, 15));
      A[i] = u8(D(500 * (fX - fY) + 128 * 32768, 15));
      B[i] = u8(D(200 * (fY - fZ) + 128 * 32768, 15));
      gray[i] = (R * 4899 + G * 9617 + Bl * 1868 + 8192) >> 14;
      const mx = Math.max(R, G, Bl), mn = Math.min(R, G, Bl);
      sat[i] = ((mx - mn) * sdiv[mx] + 2048) >> 12;
    }
    const L = convolveSep(L0, w, h, GAUSS7);
    const W = S.WINDOW;
    const localStd = (ch) => {
      const sq = new Float32Array(n);
      for (let i = 0; i < n; i++) sq[i] = ch[i] * ch[i];
      const m = boxBlur(ch, w, h, W), m2 = boxBlur(sq, w, h, W);
      const out = new Float32Array(n);
      for (let i = 0; i < n; i++) out[i] = Math.sqrt(Math.max(m2[i] - m[i] * m[i], 0));
      return out;
    };
    const sa = localStd(A), sb = localStd(B);
    const sheen = new Float32Array(n);
    for (let i = 0; i < n; i++) sheen[i] = sa[i] + sb[i];
    const lap = new Float32Array(n);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const c = gray[y * w + x];
        const v = gray[reflect(y - 1, h) * w + x] + gray[reflect(y + 1, h) * w + x] +
                  gray[y * w + reflect(x - 1, w)] + gray[y * w + reflect(x + 1, w)] - 4 * c;
        lap[y * w + x] = Math.abs(v);
      }
    }
    const texture = boxBlur(lap, w, h, W);
    return { L, A, B, sheen, texture, sat,
             water: { L: median(L), sheen: median(sheen), texture: median(texture) } };
  }

  // 8-connected patches with holes filled (like OpenCV external contours drawn filled)
  function findPatches(mask, w, h) {
    const lab = new Int32Array(w * h);
    const comps = [];
    let next = 1;
    const stack = [];
    for (let s = 0; s < w * h; s++) {
      if (!mask[s] || lab[s]) continue;
      let x0 = w, y0 = h, x1 = 0, y1 = 0;
      lab[s] = next; stack.push(s);
      while (stack.length) {
        const p = stack.pop(), px = p % w, py = (p - px) / w;
        if (px < x0) x0 = px; if (px > x1) x1 = px; if (py < y0) y0 = py; if (py > y1) y1 = py;
        for (let dy = -1; dy <= 1; dy++) {
          const ny = py + dy; if (ny < 0 || ny >= h) continue;
          for (let dx = -1; dx <= 1; dx++) {
            const nx = px + dx; if (nx < 0 || nx >= w) continue;
            const q = ny * w + nx;
            if (mask[q] && !lab[q]) { lab[q] = next; stack.push(q); }
          }
        }
      }
      comps.push({ id: next, seed: s, x0, y0, x1, y1 });
      next++;
    }
    comps.sort((a, b) => (b.x1 - b.x0 + 1) * (b.y1 - b.y0 + 1) - (a.x1 - a.x0 + 1) * (a.y1 - a.y0 + 1));
    const claimed = new Uint8Array(w * h);
    const out = [];
    for (const c of comps) {
      if (claimed[c.seed]) continue;           // sits inside a bigger patch's hole
      const bw = c.x1 - c.x0 + 1, bh = c.y1 - c.y0 + 1;
      const outside = new Uint8Array(bw * bh);  // background reachable from the box edge
      const st = [];
      const tryPush = (x, y) => {
        const i = (y - c.y0) * bw + (x - c.x0);
        if (!outside[i] && lab[y * w + x] !== c.id) { outside[i] = 1; st.push(i); }
      };
      for (let x = c.x0; x <= c.x1; x++) { tryPush(x, c.y0); tryPush(x, c.y1); }
      for (let y = c.y0; y <= c.y1; y++) { tryPush(c.x0, y); tryPush(c.x1, y); }
      while (st.length) {
        const i = st.pop(), lx = i % bw, ly = (i - lx) / bw;
        if (lx > 0) tryPush(c.x0 + lx - 1, c.y0 + ly);
        if (lx < bw - 1) tryPush(c.x0 + lx + 1, c.y0 + ly);
        if (ly > 0) tryPush(c.x0 + lx, c.y0 + ly - 1);
        if (ly < bh - 1) tryPush(c.x0 + lx, c.y0 + ly + 1);
      }
      const inside = new Uint8Array(w * h);
      let area = 0;
      for (let ly = 0; ly < bh; ly++) {
        for (let lx = 0; lx < bw; lx++) {
          if (!outside[ly * bw + lx]) {
            const p = (c.y0 + ly) * w + c.x0 + lx;
            inside[p] = 1; claimed[p] = 1; area++;
          }
        }
      }
      out.push({ inside, area, x0: c.x0, y0: c.y0, x1: c.x1, y1: c.y1 });
    }
    return out;
  }

  function hullArea(pts) {
    pts.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    if (pts.length < 3) return 0;
    const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
    const lower = [], upper = [];
    for (const p of pts) {
      while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
      lower.push(p);
    }
    for (let i = pts.length - 1; i >= 0; i--) {
      const p = pts[i];
      while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
      upper.push(p);
    }
    const hull = lower.slice(0, -1).concat(upper.slice(0, -1));
    let a = 0;
    for (let i = 0; i < hull.length; i++) {
      const p = hull[i], q = hull[(i + 1) % hull.length];
      a += p[0] * q[1] - q[0] * p[1];
    }
    return Math.abs(a) / 2;
  }

  function features(maps, p, w, h) {
    const pad = 15;
    const bx0 = Math.max(0, p.x0 - pad), by0 = Math.max(0, p.y0 - pad);
    const bx1 = Math.min(w - 1, p.x1 + pad), by1 = Math.min(h - 1, p.y1 + pad);
    // ring = 31x31 dilation of the patch minus the patch
    const bw = bx1 - bx0 + 1, bh = by1 - by0 + 1;
    const local = new Uint8Array(bw * bh);
    for (let y = by0; y <= by1; y++)
      for (let x = bx0; x <= bx1; x++) local[(y - by0) * bw + (x - bx0)] = p.inside[y * w + x];
    const dil = morph(local, bw, bh, 31, true);
    const acc = () => ({ n: 0, s: 0, s2: 0 });
    const add = (o, v) => { o.n++; o.s += v; o.s2 += v * v; };
    const names = ["L", "A", "B", "sheen", "texture", "sat"];
    const In = {}, Out = {};
    names.forEach((k) => { In[k] = acc(); Out[k] = acc(); });
    let ringCount = 0;
    let sx = 0, sy = 0, sxx = 0, syy = 0, sxy = 0, n = 0;
    const rowPts = [];
    for (let y = by0; y <= by1; y++) {
      let minX = -1, maxX = -1;
      for (let x = bx0; x <= bx1; x++) {
        const i = y * w + x, li = (y - by0) * bw + (x - bx0);
        if (p.inside[i]) {
          names.forEach((k) => add(In[k], maps[k][i]));
          n++; sx += x; sy += y; sxx += x * x; syy += y * y; sxy += x * y;
          if (minX < 0) minX = x; maxX = x;
        } else if (dil[li]) {
          ringCount++;
          names.forEach((k) => add(Out[k], maps[k][i]));
        }
      }
      if (minX >= 0) { rowPts.push([minX, y]); if (maxX !== minX) rowPts.push([maxX, y]); }
    }
    if (ringCount === 0) {   // patch fills everything: use the rest of the image
      names.forEach((k) => { Out[k] = acc(); });
      for (let i = 0; i < w * h; i++) if (!p.inside[i]) names.forEach((k) => add(Out[k], maps[k][i]));
    }
    const mean = (o) => (o.n ? o.s / o.n : 0);
    const sd = (o) => (o.n ? Math.sqrt(Math.max(o.s2 / o.n - (o.s / o.n) ** 2, 0)) : 0);

    const mx = sx / n, my = sy / n;
    const cxx = sxx / n - mx * mx, cyy = syy / n - my * my, cxy = sxy / n - mx * my;
    const tr = (cxx + cyy) / 2, det = Math.sqrt(((cxx - cyy) / 2) ** 2 + cxy * cxy);
    const l1 = tr + det, l2 = tr - det;
    const elong = Math.sqrt(Math.max(l1, 0.25) / Math.max(l2, 0.25));
    const hull = hullArea(rowPts);
    const solidity = hull ? Math.min(p.area / hull, 1) : 1;

    const Lin = mean(In.L), shIn = mean(In.sheen), txIn = mean(In.texture);
    return [Lin, sd(In.L), mean(In.A), mean(In.B), sd(In.A), sd(In.B),
            mean(Out.L) - Lin, shIn, shIn - mean(Out.sheen), txIn,
            mean(Out.texture) / (txIn + 1), mean(In.sat), p.area / (w * h), elong, solidity];
  }

  function predict(model, x) {
    let s = 0;
    const xf = x.map((v) => Math.fround(v));
    for (const t of model.trees) {
      let node = 0;
      while (t.l[node] !== -1) node = xf[t.f[node]] <= t.t[node] ? t.l[node] : t.r[node];
      s += t.p[node];
    }
    return s / model.trees.length;
  }

  function analyse(rgba, w, h, model) {
    const maps = makeMaps(rgba, w, h);
    const wt = maps.water, n = w * h;
    const dark = new Uint8Array(n), shiny = new Uint8Array(n), mask = new Uint8Array(n);
    for (let i = 0; i < n; i++) {
      dark[i] = maps.L[i] < wt.L - S.DARK_DROP ? 1 : 0;
      shiny[i] = maps.sheen[i] > wt.sheen + S.SHEEN_COLOUR ? 1 : 0;
      mask[i] = dark[i] | shiny[i];
    }
    let m = morph(morph(mask, w, h, 7, false), w, h, 7, true);   // open
    m = morph(morph(m, w, h, 7, true), w, h, 7, false);          // close

    const patches = [];
    for (const p of findPatches(m, w, h)) {
      if (p.area < S.MIN_PATCH_AREA) continue;
      let nd = 0, ns = 0;
      for (let i = 0; i < n; i++) if (p.inside[i]) { nd += dark[i]; ns += shiny[i]; }
      const d = (nd / p.area) * 255 > 127, s = (ns / p.area) * 255 > 127;
      p.kind = d && s ? "DARK+SHEEN" : d ? "DARK" : "SHEEN";
      p.features = features(maps, p, w, h);
      if (model) {
        p.prob = predict(model, p.features);
        const t = model.thresholds || { oil: S.AI_OIL, reject: S.AI_NOT_OIL };   // picked by train_model.py
        p.verdict = p.prob >= t.oil ? "CONFIRMED OIL" : p.prob < t.reject ? "AI REJECTED" : "UNCERTAIN";
      } else {
        p.prob = null;
        p.verdict = "RULE ONLY";
      }
      patches.push(p);
    }
    patches.sort((a, b) => b.area - a.area);

    const v = patches.map((p) => p.verdict);
    const status = v.includes("CONFIRMED OIL") ? "OIL SPILL CONFIRMED"
      : v.includes("UNCERTAIN") || v.includes("RULE ONLY")
        ? (model ? "POSSIBLE SPILL - AI UNSURE" : "POSSIBLE SPILL (no AI yet)")
        : "CLEAR";
    return { patches, status, water: wt, width: w, height: h };
  }

  root.GroundCore = { SETTINGS: S, analyse, predict, makeMaps };
  if (typeof module !== "undefined") module.exports = root.GroundCore;
})(typeof window !== "undefined" ? window : globalThis);
