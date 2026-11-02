// demo.js - buttons, drawing, table for the "Try it" section
(function () {
  const $ = id => document.getElementById(id);
  const COL = { "likely oil": [230, 59, 46], "possible oil": [232, 150, 12], "probably look-alike": [61, 139, 217] };
  let current = null;   // the image we last loaded

  // fig 1: show / hide the outlines the program drew, so you can compare with the plain radar image
  const toggle = $("toggle-outlines"), outlines = $("outlines"), tags = $("tags");
  toggle.addEventListener("click", () => {
    const on = toggle.getAttribute("aria-pressed") !== "true";
    toggle.setAttribute("aria-pressed", on);
    outlines.classList.toggle("off", !on);
    tags.classList.toggle("off", !on);
    toggle.textContent = on ? "Hide what the program marked" : "Show what the program marked";
  });

  // sliders
  [["contrast", "o-contrast", 1], ["minarea", "o-minarea", 2], ["bgkm", "o-bg", 1]].forEach(([s, o, d]) => {
    $(s).addEventListener("input", () => { $(o).textContent = (+$(s).value).toFixed(d); });
  });
  const settings = () => ({ contrastDb: +$("contrast").value, minAreaKm2: +$("minarea").value, backgroundKm: +$("bgkm").value });

  function status(t) { $("status").textContent = t; }

  // let the browser repaint the status text before the heavy work
  const later = fn => new Promise(res => setTimeout(() => res(fn()), 30));

  async function run() {
    if (!current) return;
    status(`analysing ${current.w}×${current.h} pixels...`);
    const t0 = performance.now();
    const res = await later(() => OceanEye.analyse(current, settings()));
    draw(current, res);
    table(res);
    $("warnings").innerHTML = res.warnings.map(w => `<p class="warn">${w}</p>`).join("");
    const oil = res.blobs.filter(b => b.verdict === "likely oil").length;
    status(`${current.name}: ${res.blobs.length} dark patch(es), ${oil} likely oil. ` +
      `Sea brightness ${res.sceneBg.toFixed(1)} dB. Took ${((performance.now() - t0) / 1000).toFixed(1)} s.`);
    $("btn-rerun").disabled = false;
  }

  function grey(v) { return Math.max(0, Math.min(255, ((v + 28) / 20) * 255)); }

  function draw(img, res) {
    const { w, h } = img;
    const a = $("cv-radar"), b = $("cv-result");
    a.width = b.width = w; a.height = b.height = h;
    const ca = a.getContext("2d"), cb = b.getContext("2d");
    const pa = ca.createImageData(w, h);
    for (let i = 0; i < w * h; i++) {
      const v = res.smooth[i];
      const g = Number.isFinite(v) ? grey(v) : 0;
      pa.data[i * 4] = pa.data[i * 4 + 1] = pa.data[i * 4 + 2] = g;
      pa.data[i * 4 + 3] = 255;
    }
    ca.putImageData(pa, 0, 0);
    const pb = new ImageData(new Uint8ClampedArray(pa.data), w, h);
    const thick = Math.max(1, Math.round(w / 500));
    for (const blob of res.blobs) {
      const c = COL[blob.verdict];
      for (const i of blob.edgePts) {
        const x = i % w, y = (i / w) | 0;
        for (let dy = -thick + 1; dy < thick; dy++)
          for (let dx = -thick + 1; dx < thick; dx++) {
            const xx = x + dx, yy = y + dy;
            if (xx < 0 || yy < 0 || xx >= w || yy >= h) continue;
            const k = (yy * w + xx) * 4;
            pb.data[k] = c[0]; pb.data[k + 1] = c[1]; pb.data[k + 2] = c[2];
          }
      }
    }
    cb.putImageData(pb, 0, 0);
    const fs = Math.max(12, Math.round(w / 45));
    cb.font = `bold ${fs}px monospace`;
    cb.textAlign = "center"; cb.textBaseline = "middle";
    for (const blob of res.blobs) {
      const c = COL[blob.verdict];
      cb.fillStyle = `rgb(${c})`;
      cb.fillRect(blob.cx - fs * 0.7, blob.cy - fs * 0.7, fs * 1.4, fs * 1.4);
      cb.fillStyle = "#fff";
      cb.fillText(blob.id, blob.cx, blob.cy + 1);
    }
  }

  function table(res) {
    if (!res.blobs.length) { $("table-wrap").innerHTML = "<p>No dark patches that look like oil.</p>"; return; }
    let h = "<table><tr><th>#</th><th>Verdict</th><th>Score</th><th>Area km²</th><th>Length km</th>" +
      "<th>Contrast dB</th><th>Long/thin</th><th>Edge</th><th>Why</th></tr>";
    for (const b of res.blobs) {
      const cls = b.verdict === "likely oil" ? "red" : b.verdict === "possible oil" ? "orange" : "blue";
      h += `<tr><td>${b.id}</td><td><span class="k ${cls}">${b.verdict}</span></td><td>${b.score}</td>` +
        `<td>${b.areaKm2.toFixed(2)}</td><td>${b.lengthKm.toFixed(1)}</td><td>${b.contrastDb.toFixed(1)}</td>` +
        `<td>${b.elongation.toFixed(1)}</td><td>${b.edge.toFixed(2)}</td><td>${b.why.join("; ")}</td></tr>`;
    }
    $("table-wrap").innerHTML = h + "</table>";
  }

  // ---- buttons ----
  $("btn-test").addEventListener("click", async () => {
    status("making the test scene...");
    current = await later(() => OceanEye.testScene());
    run();
  });
  $("btn-rerun").addEventListener("click", run);

  $("file").addEventListener("change", async e => {
    const f = e.target.files[0];
    if (!f) return;
    try {
      status(`reading ${f.name}...`);
      current = await loadTiff(f);
      run();
    } catch (err) {
      console.error(err);
      status("Couldn't read that file: " + err.message);
    }
  });

  async function loadTiff(file) {
    if (typeof GeoTIFF === "undefined") throw new Error("GeoTIFF library didn't load (check internet).");
    const tiff = await GeoTIFF.fromArrayBuffer(await file.arrayBuffer());
    const image = await tiff.getImage();
    let w = image.getWidth(), h = image.getHeight();
    const r = await image.readRasters();
    const band = r[0], mask = r.length > 1 ? r[1] : null;
    const nodata = image.getGDALNoData();
    if (band instanceof Uint8Array && r.length >= 3)
      throw new Error("this looks like a coloured picture, not raw radar data. Download the 32-bit float TIFF.");

    // pixel size
    const [rx, ry] = image.getResolution();
    const bb = image.getBoundingBox();
    const keys = image.getGeoKeys() || {};
    let pxW, pxH;
    if (keys.GTModelTypeGeoKey === 2 || Math.abs(rx) < 0.5) {   // degrees
      const lat = (bb[1] + bb[3]) / 2;
      pxW = Math.abs(rx) * 111.32 * Math.cos(lat * Math.PI / 180);
      pxH = Math.abs(ry) * 110.57;
    } else {   // metres
      pxW = Math.abs(rx) / 1000; pxH = Math.abs(ry) / 1000;
    }

    // dB or linear?
    const sample = [];
    for (let i = 0; i < band.length; i += 97) if (Number.isFinite(band[i]) && band[i] !== nodata && band[i] !== 0) sample.push(band[i]);
    sample.sort((a, b) => a - b);
    const isDb = sample.length && sample[sample.length >> 1] < 0;

    let db = new Float32Array(w * h);
    for (let i = 0; i < w * h; i++) {
      let v = band[i];
      const bad = !Number.isFinite(v) || v === nodata || (mask && mask[i] === 0) || (!isDb && v <= 0);
      db[i] = bad ? NaN : (isDb ? v : OceanEye.toDb(v));
    }

    // big images are slow in a browser, so shrink by averaging blocks
    const f = Math.ceil(Math.max(w, h) / 1400);
    if (f > 1) {
      const W = Math.floor(w / f), H = Math.floor(h / f), out = new Float32Array(W * H);
      for (let y = 0; y < H; y++)
        for (let x = 0; x < W; x++) {
          let s = 0, n = 0;
          for (let dy = 0; dy < f; dy++)
            for (let dx = 0; dx < f; dx++) {
              const v = db[(y * f + dy) * w + x * f + dx];
              if (Number.isFinite(v)) { s += Math.pow(10, v / 10); n++; }
            }
          out[y * W + x] = n > f * f / 2 ? OceanEye.toDb(s / n) : NaN;
        }
      db = out; w = W; h = H; pxW *= f; pxH *= f;
    }
    return { db, w, h, pxKm: pxW, pxKm2: pxW * pxH, name: file.name };
  }
})();
