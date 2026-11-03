/*
 * OceanEye website - "Check from the ground" section.
 * Camera or photo -> GroundCore.analyse (web/ground-core.js) -> picture + table.
 * Uses the AI in web/oil_model.json if it exists (made by train_model.py).
 * Everything runs in the browser; no picture is uploaded anywhere.
 */
(function () {
  const APP_URL = "https://oceaneye-ycl.streamlit.app/";
  const LIVE_EVERY_MS = 1500;
  const COL = {
    "CONFIRMED OIL": [230, 59, 46], "UNCERTAIN": [242, 165, 22],
    "RULE ONLY": [242, 165, 22], "AI REJECTED": [61, 139, 217],
  };
  const $ = (id) => document.getElementById(id);
  if (!$("ground") || !window.GroundCore) return;

  let model = null, stream = null, liveTimer = null, last = null, busy = false;
  const video = document.createElement("video");
  video.playsInline = true; video.muted = true;
  const work = document.createElement("canvas");

  // the AI file is about 470 KB (120 KB when compressed), so it is only fetched when this section comes
  // near the screen or is used, not when the page first opens
  let modelPromise = null;
  function loadModel() {
    if (!modelPromise) {
      $("g-ai").textContent = "Loading the AI model...";
      modelPromise = fetch("web/oil_model.json")
        .then((r) => (r.ok ? r.json() : null))
        .then((m) => {
          model = m;
          $("g-ai").textContent = m
            ? `AI model loaded (${m.trees.length} trees). ${m.summary || ""}`
            : "AI model not found, so only the rules (stage 1) are used.";
        })
        .catch(() => { $("g-ai").textContent = "Couldn't load the AI model, so only the rules (stage 1) are used."; });
    }
    return modelPromise;
  }
  if ("IntersectionObserver" in window) {
    const watcher = new IntersectionObserver((hits) => {
      if (hits.some((h) => h.isIntersecting)) { watcher.disconnect(); loadModel(); }
    }, { rootMargin: "600px" });
    watcher.observe($("ground"));
  } else {
    loadModel();
  }

  function setStatus(t) { $("g-status").textContent = t; }

  // draw any image/video onto the work canvas at the analysis size
  function grab(src, sw, sh) {
    const s = Math.min(1, GroundCore.SETTINGS.WORK_SIDE / Math.max(sw, sh));
    work.width = Math.round(sw * s); work.height = Math.round(sh * s);
    const ctx = work.getContext("2d", { willReadFrequently: true });
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(src, 0, 0, work.width, work.height);
    return ctx.getImageData(0, 0, work.width, work.height);
  }

  function num(id) { const v = parseFloat($(id).value); return isFinite(v) && v > 0 ? v : null; }

  async function run(img) {
    await loadModel();
    const t0 = performance.now();
    const res = GroundCore.analyse(img.data, img.width, img.height, model);
    res.ms = Math.round(performance.now() - t0);
    draw(img, res);
    report(res);
    last = res;
    updateConfirm();
  }

  function draw(img, res) {
    const view = $("g-view"), out = $("g-result");
    for (const c of [view, out]) { c.width = img.width; c.height = img.height; }
    view.getContext("2d").putImageData(img, 0, 0);
    const o = new ImageData(new Uint8ClampedArray(img.data), img.width, img.height);
    const w = img.width, h = img.height, d = o.data;
    for (const p of res.patches) {
      const [r, g, b] = COL[p.verdict];
      for (let y = p.y0; y <= p.y1; y++) {
        for (let x = p.x0; x <= p.x1; x++) {
          const i = y * w + x;
          if (!p.inside[i]) continue;
          const edge = x === 0 || y === 0 || x === w - 1 || y === h - 1 ||
            !p.inside[i - 1] || !p.inside[i + 1] || !p.inside[i - w] || !p.inside[i + w];
          const a = edge ? 1 : 0.3, k = 4 * i;
          d[k] = d[k] * (1 - a) + r * a; d[k + 1] = d[k + 1] * (1 - a) + g * a; d[k + 2] = d[k + 2] * (1 - a) + b * a;
        }
      }
    }
    const ctx = out.getContext("2d");
    ctx.putImageData(o, 0, 0);
    ctx.font = "600 13px 'IBM Plex Mono', monospace";
    ctx.lineWidth = 3;
    res.patches.forEach((p, i) => {
      const ai = p.prob == null ? "" : ` ${Math.round(p.prob * 100)}%`;
      const t = `#${i + 1}${ai}`, y = Math.max(p.y0 - 6, 14);
      ctx.strokeStyle = "rgba(0,0,0,.7)"; ctx.strokeText(t, p.x0, y);
      ctx.fillStyle = `rgb(${COL[p.verdict].join(",")})`; ctx.fillText(t, p.x0, y);
    });
  }

  function report(res) {
    const wcm = num("g-w"), hcm = num("g-h");
    const total = res.width * res.height;
    const kept = res.patches.filter((p) => p.verdict !== "AI REJECTED");
    const px = kept.reduce((s, p) => s + p.area, 0);
    const area = wcm && hcm ? `${(px / total * wcm * hcm).toFixed(1)} cm²`
      : `${(100 * px / total).toFixed(2)}% of the picture`;
    const probs = kept.filter((p) => p.prob != null).map((p) => p.prob);
    const conf = probs.length ? `, AI confidence ${Math.round(Math.max(...probs) * 100)}%` : "";
    setStatus(`${res.status}. Spill area: ${area}${conf}. (${res.patches.length} patch(es) checked in ${res.ms} ms)`);
    res.areaText = area;

    if (!res.patches.length) { $("g-table").innerHTML = ""; return; }
    const rows = res.patches.map((p, i) => {
      const a = wcm && hcm ? (p.area / total * wcm * hcm).toFixed(1) + " cm²"
        : (100 * p.area / total).toFixed(2) + "%";
      const ai = p.prob == null ? "-" : Math.round(p.prob * 100) + "%";
      return `<tr><td>${i + 1}</td><td>${p.kind}</td><td>${p.verdict.toLowerCase()}</td><td>${ai}</td><td>${a}</td></tr>`;
    }).join("");
    $("g-table").innerHTML = `<table><thead><tr><th>#</th><th>type</th><th>verdict</th><th>AI says oil</th>
      <th>area</th></tr></thead><tbody>${rows}</tbody></table>`;
  }

  function updateConfirm() {
    const a = $("g-confirm");
    const lat = parseFloat($("g-lat").value), lon = parseFloat($("g-lon").value);
    const q = new URLSearchParams();
    if (isFinite(lat) && isFinite(lon)) { q.set("lat", lat); q.set("lon", lon); }
    if ($("g-date").value) q.set("date", $("g-date").value);
    if (last) q.set("ground", last.status);
    a.href = APP_URL + (q.toString() ? "?" + q : "");
    $("g-confirm-note").textContent = isFinite(lat) && isFinite(lon)
      ? "Opens the full app with this spot filled in. Go to the Camera & photo check tab and press Set the satellite scan to this spot."
      : "Add the latitude and longitude above so the full app knows where to look.";
  }

  // ---------- camera ----------
  let facing = "environment";   // back camera first, the flip button switches
  async function startCamera() {
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: facing }, width: { ideal: 1280 } }, audio: false,
      });
    } catch (e) {
      setStatus("Couldn't open the camera: " + e.message + ". Allow camera access, or upload a photo instead.");
      return;
    }
    video.srcObject = stream;
    await video.play();
    $("g-cam").textContent = "Stop camera";
    $("g-snap").disabled = false; $("g-live").disabled = false; $("g-flip").disabled = false;
    setStatus("Camera on. Point it at the water and press Check this frame.");
    preview();
  }

  function stopCamera() {
    clearInterval(liveTimer); liveTimer = null; $("g-live").checked = false;
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null;
    $("g-cam").textContent = "Start camera";
    $("g-snap").disabled = true; $("g-live").disabled = true; $("g-flip").disabled = true;
  }

  function preview() {
    if (!stream) return;
    if (!liveTimer && video.videoWidth) {
      const img = grab(video, video.videoWidth, video.videoHeight);
      const v = $("g-view"); v.width = img.width; v.height = img.height;
      v.getContext("2d").putImageData(img, 0, 0);
    }
    requestAnimationFrame(preview);
  }

  function checkFrame() {
    if (!stream || !video.videoWidth || busy) return;
    busy = true;
    setTimeout(() => {
      try { run(grab(video, video.videoWidth, video.videoHeight)); } finally { busy = false; }
    }, 0);
  }

  $("g-cam").addEventListener("click", () => (stream ? stopCamera() : startCamera()));
  $("g-flip").addEventListener("click", () => {
    facing = facing === "environment" ? "user" : "environment";
    if (stream) { stopCamera(); startCamera(); }
  });
  $("g-snap").addEventListener("click", checkFrame);
  $("g-live").addEventListener("change", (e) => {
    clearInterval(liveTimer); liveTimer = null;
    if (e.target.checked) { checkFrame(); liveTimer = setInterval(checkFrame, LIVE_EVERY_MS); }
  });

  // ---------- example photos (openly licensed, from Wikimedia Commons) ----------
  let examples = null;
  async function loadExample(kind) {
    try {
      if (!examples) examples = await fetch("web/examples/examples.json").then((r) => r.json());
      const ex = examples[kind];
      stopCamera();
      setStatus("Loading the example photo...");
      const im = new Image();
      await new Promise((ok, bad) => { im.onload = ok; im.onerror = () => bad(new Error("image didn't load")); im.src = ex.file; });
      run(grab(im, im.naturalWidth, im.naturalHeight));
      $("g-credit").textContent = `Example photo: ${ex.title} by ${ex.author} (${ex.licence}). ${ex.page}`;
    } catch (e) {
      setStatus("Couldn't load the example: " + e.message);
    }
  }
  $("g-ex-oil").addEventListener("click", () => loadExample("oil"));
  $("g-ex-clean").addEventListener("click", () => loadExample("clean"));
  if (window.wireDrop) wireDrop($("g-drop"), $("g-file"));

  // ---------- photo ----------
  $("g-file").addEventListener("change", (e) => {
    const f = e.target.files[0];
    if (!f) return;
    $("g-credit").textContent = "";
    stopCamera();
    const url = URL.createObjectURL(f);
    const im = new Image();
    im.onload = () => {
      setStatus("Checking the photo...");
      setTimeout(() => { run(grab(im, im.naturalWidth, im.naturalHeight)); URL.revokeObjectURL(url); }, 0);
    };
    im.onerror = () => setStatus("Couldn't read that file - try a JPG or PNG.");
    im.src = url;
  });

  for (const id of ["g-w", "g-h"]) $(id).addEventListener("input", () => last && report(last));
  for (const id of ["g-lat", "g-lon", "g-date"]) $(id).addEventListener("input", updateConfirm);
  $("g-date").value = new Date().toISOString().slice(0, 10);
  updateConfirm();
})();
