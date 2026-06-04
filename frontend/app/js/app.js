/* ==========================================================================
   AntiDeepfake AI — Product web app logic
   --------------------------------------------------------------------------
   Responsibilities:
     * API client (auth, detect, results, history) with graceful offline mode
     * Auth modal (register / login), JWT + API key persisted to localStorage
     * Scanner: drag & drop upload, progress, poll for results
     * Results rendering: gauge, method breakdown, visualizations
     * History via API, with a localStorage cache fallback
     * SIMULATED results when the backend is unreachable (for demo / sales)
   ========================================================================== */
(function () {
  "use strict";

  // ----- Configuration -----------------------------------------------------
  // Point this at your deployed backend. Defaults to localhost for dev.
  function defaultApiBase() {
    if (/(\.|^)antideepfakeai\.com$/i.test(location.hostname)) {
      return "https://api.antideepfakeai.com";
    }
    return "http://localhost:8000";
  }

  var API_BASE =
    localStorage.getItem("adf_api_base") || defaultApiBase();

  var DETECTOR_LABELS = {
    face_forgery: "Face Forgery",
    frequency_analysis: "Frequency Analysis",
    liveness: "Liveness",
    temporal_analysis: "Temporal Consistency",
    audio_sync: "Audio-Visual Sync",
    gan_fingerprint: "GAN Fingerprint",
    metadata_forensics: "Metadata Forensics",
    pixel_forensics: "Pixel Forensics",
    premium_consensus: "Premium Provider Consensus",
  };
  var DETECTOR_ORDER = Object.keys(DETECTOR_LABELS);

  // ----- Tiny helpers -------------------------------------------------------
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function token() { return localStorage.getItem("adf_token"); }
  function apiKey() { return localStorage.getItem("adf_api_key"); }
  function email() { return localStorage.getItem("adf_email"); }
  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[ch];
    });
  }

  function authHeaders() {
    var h = {};
    if (token()) h["Authorization"] = "Bearer " + token();
    else if (apiKey()) h["X-API-Key"] = apiKey();
    return h;
  }

  function saveAuth(data) {
    if (!data) return;
    if (data.access_token) localStorage.setItem("adf_token", data.access_token);
    if (data.api_key) localStorage.setItem("adf_api_key", data.api_key);
    if (data.email) localStorage.setItem("adf_email", data.email);
  }

  function logout() {
    ["adf_token", "adf_api_key", "adf_email"].forEach(function (k) {
      localStorage.removeItem(k);
    });
    location.reload();
  }

  function color(score) {
    if (score >= 60) return getComputedStyle(document.documentElement).getPropertyValue("--green").trim() || "#2bb673";
    if (score >= 40) return getComputedStyle(document.documentElement).getPropertyValue("--amber").trim() || "#e0a43b";
    return getComputedStyle(document.documentElement).getPropertyValue("--red").trim() || "#e25563";
  }

  // Map a 0-100 authenticity score to a status class (ok / warn / bad).
  function statusClass(score) {
    if (score >= 60) return "ok";
    if (score >= 40) return "warn";
    return "bad";
  }

  // ----- Local history cache (offline + quick access) -----------------------
  function localHistory() {
    try { return JSON.parse(localStorage.getItem("adf_history") || "[]"); }
    catch (e) { return []; }
  }
  function pushLocalHistory(entry) {
    if (localStorage.getItem("adf_cache_disabled") === "1") return;
    var h = localHistory();
    h.unshift(entry);
    localStorage.setItem("adf_history", JSON.stringify(h.slice(0, 100)));
  }
  function getCachedResult(scanId) {
    return localHistory().filter(function (e) { return e.scan_id === scanId; })[0];
  }

  // ----- API client ---------------------------------------------------------
  var API = {
    online: true,

    register: function (em, pw) {
      return fetch(API_BASE + "/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: em, password: pw }),
      }).then(handleJson);
    },

    login: function (em, pw) {
      return fetch(API_BASE + "/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: em, password: pw }),
      }).then(handleJson);
    },

    detect: function (file, onProgress) {
      // Use XHR so we get upload progress events.
      return new Promise(function (resolve, reject) {
        var xhr = new XMLHttpRequest();
        xhr.open("POST", API_BASE + "/api/detect?sync=true");
        var hdrs = authHeaders();
        Object.keys(hdrs).forEach(function (k) { xhr.setRequestHeader(k, hdrs[k]); });
        xhr.upload.onprogress = function (e) {
          if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
        };
        xhr.onload = function () {
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(JSON.parse(xhr.responseText));
          } else {
            reject(new Error("Server returned " + xhr.status));
          }
        };
        xhr.onerror = function () { reject(new Error("Network error")); };
        var fd = new FormData();
        fd.append("file", file);
        xhr.send(fd);
      });
    },

    results: function (scanId) {
      return fetch(API_BASE + "/api/results/" + scanId, { headers: authHeaders() }).then(handleJson);
    },

    history: function () {
      return fetch(API_BASE + "/api/history", { headers: authHeaders() }).then(handleJson);
    },

    health: function () {
      return fetch(API_BASE + "/api/health").then(function (r) { return r.ok; }).catch(function () { return false; });
    },
  };

  function handleJson(r) {
    if (!r.ok) {
      return r.json().catch(function () { return {}; }).then(function (body) {
        throw new Error(body.detail || ("HTTP " + r.status));
      });
    }
    return r.json();
  }

  // ----- SIMULATED detection (offline / demo) -------------------------------
  // Produces deterministic-ish results from the filename so the UI is fully
  // functional even with no backend (used on the sales/demo deployment).
  function simulateDetection(file) {
    function hash(str) {
      var h = 0;
      for (var i = 0; i < str.length; i++) { h = (h * 31 + str.charCodeAt(i)) >>> 0; }
      return h;
    }
    var seed = hash(file.name + file.size);
    function rng() { seed = (seed * 1103515245 + 12345) >>> 0; return (seed % 1000) / 1000; }

    var isVideo = /\.(mp4|mov|avi|mkv|webm)$/i.test(file.name);
    // Heuristic demo bias: files hinting "fake"/"ai"/"deepfake" score lower.
    var fakeBias = /fake|deepfake|ai|gan|synth|generated/i.test(file.name) ? 0.65 : 0.2;

    var breakdown = DETECTOR_ORDER.map(function (name) {
      var applicable = true;
      if (!isVideo && (name === "temporal_analysis" || name === "audio_sync")) applicable = false;
      if (name === "premium_consensus") applicable = false;
      var p = applicable ? Math.min(1, Math.max(0, fakeBias + (rng() - 0.5) * 0.4)) : 0.5;
      return {
        name: name,
        fake_probability: p,
        score: Math.round((1 - p) * 1000) / 10,
        status: applicable ? "ok" : "skipped",
        summary: applicable ? "Simulated analysis (demo mode)." : "Not applicable in demo mode.",
        contributed: applicable,
      };
    });

    var used = breakdown.filter(function (b) { return b.contributed; });
    var avgP = used.reduce(function (s, b) { return s + b.fake_probability; }, 0) / used.length;
    var score = Math.round((1 - avgP) * 1000) / 10;
    var verdict = score >= 80 ? "REAL" : score >= 60 ? "LIKELY REAL" : score >= 40 ? "SUSPICIOUS" : score >= 20 ? "LIKELY FAKE" : "FAKE";

    return {
      scan_id: "demo-" + seed.toString(16),
      status: "done",
      filename: file.name,
      media_type: isVideo ? "video" : "image",
      score: score,
      fake_probability: Math.round(avgP * 10000) / 10000,
      verdict: verdict,
      verdict_confidence: Math.round(Math.abs(score - 50) / 50 * 1000) / 10,
      detectors_used: used.length,
      num_detectors_contributing: used.length,
      evidence_grade: "demo",
      risk_band: score < 40 ? "high" : score < 60 ? "review" : "low",
      decision_notes: ["Demo-mode results are simulated. Run a signed-in scan against the live backend for evidence-grade analysis."],
      recommended_action: "Use a live backend scan before making decisions.",
      premium_signals_available: false,
      breakdown: breakdown,
      processing_time_sec: Math.round((1 + rng() * 4) * 10) / 10,
      simulated: true,
    };
  }

  // ----- Auth UI ------------------------------------------------------------
  function initAuthUI() {
    var chip = $("#userChip");
    if (chip) {
      if (email()) {
        var initial = email().charAt(0).toUpperCase();
        chip.innerHTML = '<span class="email"><span class="avatar">' + initial + '</span>' + email() + '</span>' +
          '<button class="btn btn-ghost btn-sm" id="logoutBtn">Log out</button>';
        var lb = $("#logoutBtn"); if (lb) lb.addEventListener("click", logout);
      } else {
        chip.innerHTML = '<button class="btn btn-primary btn-sm" id="openAuth">Sign in / Register</button>';
        var oa = $("#openAuth"); if (oa) oa.addEventListener("click", openAuthModal);
      }
    }

    var modal = $("#authModal");
    if (!modal) return;
    var mode = "register";
    var tabReg = $("#tabRegister"), tabLogin = $("#tabLogin");
    var errEl = $("#authErr");

    function setMode(m) {
      mode = m;
      if (tabReg && tabLogin) {
        tabReg.classList.toggle("active", m === "register");
        tabLogin.classList.toggle("active", m === "login");
      }
      $("#authSubmit").textContent = m === "register" ? "Create account" : "Log in";
    }
    if (tabReg) tabReg.addEventListener("click", function () { setMode("register"); });
    if (tabLogin) tabLogin.addEventListener("click", function () { setMode("login"); });

    var form = $("#authForm");
    if (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        errEl.textContent = "";
        var em = $("#authEmail").value.trim();
        var pw = $("#authPassword").value;
        var p = mode === "register" ? API.register(em, pw) : API.login(em, pw);
        p.then(function (data) {
          saveAuth(data);
          closeAuthModal();
          location.reload();
        }).catch(function (err) {
          errEl.textContent = err.message + (API.online ? "" : " (backend offline)");
        });
      });
    }
    var closeBtn = $("#authClose");
    if (closeBtn) closeBtn.addEventListener("click", closeAuthModal);
    setMode("register");
  }
  function openAuthModal() { var m = $("#authModal"); if (m) m.classList.add("open"); }
  function closeAuthModal() { var m = $("#authModal"); if (m) m.classList.remove("open"); }

  // ----- Sidebar toggle (mobile) -------------------------------------------
  function initSidebar() {
    var btn = $("#menuBtn"), sb = $("#sidebar");
    if (btn && sb) btn.addEventListener("click", function () { sb.classList.toggle("open"); });
  }

  // ----- Scanner page -------------------------------------------------------
  function initScanner() {
    var dz = $("#dropzone");
    if (!dz) return;
    var input = $("#fileInput");
    var progWrap = $("#progressWrap");
    var bar = $("#progressBar");
    var label = $("#progressLabel");
    var preview = $("#preview");

    dz.addEventListener("click", function () { input.click(); });
    ["dragover", "dragenter"].forEach(function (ev) {
      dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.add("dragover"); });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.remove("dragover"); });
    });
    dz.addEventListener("drop", function (e) {
      if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
    });
    input.addEventListener("change", function () {
      if (input.files.length) handleFile(input.files[0]);
    });

    function handleFile(file) {
      // Preview for images.
      if (/^image\//.test(file.type)) {
        preview.src = URL.createObjectURL(file);
        preview.style.display = "block";
      } else {
        preview.style.display = "none";
      }
      progWrap.classList.add("show");
      bar.style.width = "0%";
      label.textContent = "Uploading…";

      var done = false;
      function onProgress(frac) {
        bar.style.width = Math.round(frac * 90) + "%";
      }

      var runReal = token() || apiKey();
      var work;
      if (runReal && API.online) {
        work = API.detect(file, onProgress).then(function (res) {
          bar.style.width = "100%";
          label.textContent = "Analyzing with configured detectors…";
          return res;
        });
      } else {
        // Offline / not-authenticated -> simulate so the demo still works.
        work = new Promise(function (resolve) {
          var f = 0;
          var t = setInterval(function () {
            f += 0.12; onProgress(Math.min(f, 1));
            if (f >= 1) { clearInterval(t); resolve(simulateDetection(file)); }
          }, 150);
        });
      }

      work.then(function (res) {
        bar.style.width = "100%";
        label.textContent = "Done — opening results…";
        // Cache and navigate to results.
        var entry = {
          scan_id: res.scan_id,
          filename: res.filename || file.name,
          media_type: res.media_type,
          status: res.status,
          score: res.score,
          verdict: res.verdict,
          breakdown: res.breakdown,
          processing_time_sec: res.processing_time_sec,
          fake_probability: res.fake_probability,
          verdict_confidence: res.verdict_confidence,
          detectors_used: res.detectors_used,
          num_detectors_contributing: res.num_detectors_contributing,
          evidence_grade: res.evidence_grade,
          risk_band: res.risk_band,
          decision_notes: res.decision_notes,
          recommended_action: res.recommended_action,
          premium_signals_available: res.premium_signals_available,
          file_sha256: res.file_sha256,
          simulated: !!res.simulated,
          created_at: new Date().toISOString(),
        };
        pushLocalHistory(entry);
        localStorage.setItem("adf_last_scan", res.scan_id);
        setTimeout(function () {
          location.href = "results.html?scan=" + encodeURIComponent(res.scan_id);
        }, 500);
      }).catch(function (err) {
        label.textContent = "Error: " + err.message + " — falling back to demo mode.";
        var res = simulateDetection(file);
        pushLocalHistory({
          scan_id: res.scan_id, filename: res.filename, media_type: res.media_type,
          status: "done", score: res.score, verdict: res.verdict, breakdown: res.breakdown,
          fake_probability: res.fake_probability, verdict_confidence: res.verdict_confidence,
          detectors_used: res.detectors_used, evidence_grade: res.evidence_grade,
          risk_band: res.risk_band, decision_notes: res.decision_notes,
          recommended_action: res.recommended_action, premium_signals_available: false,
          file_sha256: res.file_sha256,
          simulated: true, created_at: new Date().toISOString(),
        });
        setTimeout(function () { location.href = "results.html?scan=" + res.scan_id; }, 900);
      });
    }
  }

  // ----- Results page -------------------------------------------------------
  function renderGauge(score) {
    var wrap = $("#gauge");
    if (!wrap) return;
    var r = 96, c = 2 * Math.PI * r;
    var pct = Math.max(0, Math.min(100, score)) / 100;
    var stroke = color(score);
    wrap.innerHTML =
      '<svg width="220" height="220">' +
      '<circle cx="110" cy="110" r="' + r + '" stroke="#232742" stroke-width="16" fill="none"/>' +
      '<circle cx="110" cy="110" r="' + r + '" stroke="' + stroke + '" stroke-width="16" fill="none"' +
      ' stroke-linecap="round" stroke-dasharray="' + c + '" stroke-dashoffset="' + (c * (1 - pct)) + '"/>' +
      "</svg>" +
      '<div class="gauge-center"><div><div class="score-num" style="color:' + stroke + '">' + score + '</div>' +
      '<div class="score-label">/ 100 authentic</div></div></div>';
  }

  function renderBreakdown(breakdown) {
    var host = $("#breakdown");
    if (!host) return;
    host.innerHTML = "";
    (breakdown || []).forEach(function (d) {
      var s = d.score != null ? d.score : Math.round((1 - d.fake_probability) * 1000) / 10;
      var row = document.createElement("div");
      row.className = "detector-row";
      row.innerHTML =
        '<div class="d-name">' + escapeHtml(DETECTOR_LABELS[d.name] || d.name) + "</div>" +
        '<div class="d-bar"><span style="width:' + s + "%;background:" + color(s) + '"></span></div>' +
        '<div class="d-score" style="color:' + color(s) + '">' + (d.status === "skipped" ? "—" : s) + "</div>" +
        '<div class="d-status">' + escapeHtml(d.status) + "</div>" +
        '<div class="d-summary">' + escapeHtml(d.summary || "") + "</div>";
      host.appendChild(row);
    });
  }

  function renderDecisionSummary(res) {
    function setText(id, value) {
      var el = $("#" + id);
      if (el) el.textContent = value == null || value === "" ? "—" : value;
    }
    setText("confidenceValue", res.verdict_confidence != null ? res.verdict_confidence + "%" : "—");
    setText("evidenceGrade", res.evidence_grade || "standard");
    setText("detectorsUsed", (res.detectors_used || res.num_detectors_contributing || 0) + " contributing");
    setText("premiumStatus", res.premium_signals_available ? "Enabled" : "Not configured");
    setText("recommendedAction", res.recommended_action || "Review the method breakdown and exported report.");

    var notes = $("#decisionNotes");
    if (notes) {
      var items = res.decision_notes || [];
      notes.innerHTML = items.length
        ? items.map(function (n) { return "<li>" + escapeHtml(n) + "</li>"; }).join("")
        : "<li>No contradictory detector signals were reported.</li>";
    }
  }

  function renderResult(res) {
    $("#resTitle").textContent = res.filename || "Scan result";
    $("#resMeta").textContent =
      (res.media_type || "") +
      (res.processing_time_sec ? " · " + res.processing_time_sec + "s" : "") +
      (res.file_sha256 ? " · SHA-256 " + res.file_sha256.slice(0, 12) + "…" : "") +
      (res.simulated ? " · DEMO MODE (simulated)" : "");
    renderGauge(Math.round(res.score));
    var vp = $("#verdictPill");
    vp.textContent = res.verdict;
    vp.className = "verdict-pill " + statusClass(res.score);
    renderDecisionSummary(res);
    renderBreakdown(res.breakdown);

    // Visualizations (only when backend produced artifacts).
    var viz = $("#vizGrid");
    if (viz) {
      var arts = res.artifacts || {};
      function vizCell(path, title) {
        if (path) {
          var url = API_BASE + "/" + path.replace(/^.*\/data\//, "data/");
          return '<div><img src="' + url + '" alt="' + title + '" onerror="this.outerHTML=\'<div class=&quot;viz-ph&quot;>' + title + ' (run a real scan)</div>\'"/></div>';
        }
        return '<div class="viz-ph">' + title + " (available after a real backend scan)</div>";
      }
      viz.innerHTML = vizCell(arts.heatmap, "Anomaly heatmap") + vizCell(arts.spectrum, "Frequency spectrum");
    }

    // Download buttons.
    var dlJson = $("#downloadJson");
    if (dlJson) {
      dlJson.addEventListener("click", function () {
        var blob = new Blob([JSON.stringify(res, null, 2)], { type: "application/json" });
        var a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = (res.scan_id || "report") + ".json";
        a.click();
      });
    }
    var dlPdf = $("#downloadPdf");
    if (dlPdf) {
      var pdfPath = (res.artifacts || {}).report_pdf;
      if (pdfPath) {
        dlPdf.addEventListener("click", function () {
          window.open(API_BASE + "/" + pdfPath.replace(/^.*\/data\//, "data/"), "_blank");
        });
      } else {
        dlPdf.title = "PDF export requires a backend scan";
        dlPdf.addEventListener("click", function () {
          alert("PDF report is generated by the backend. Run a scan while signed in to a live backend to download the PDF.");
        });
      }
    }
  }

  function initResults() {
    if (!$("#gauge")) return;
    var params = new URLSearchParams(location.search);
    var scanId = params.get("scan") || localStorage.getItem("adf_last_scan");
    if (!scanId) { $("#resTitle").textContent = "No scan selected"; return; }

    renderHistorySidebar(scanId);

    // Prefer the live backend; fall back to the local cache (e.g. demo runs).
    var cached = getCachedResult(scanId);
    if ((token() || apiKey()) && API.online && !/^demo-/.test(scanId)) {
      API.results(scanId).then(renderResult).catch(function () {
        if (cached) renderResult(cached);
        else $("#resTitle").textContent = "Could not load scan";
      });
    } else if (cached) {
      renderResult(cached);
    } else {
      $("#resTitle").textContent = "Result not found in local cache";
    }
  }

  function renderHistorySidebar(activeId) {
    var host = $("#historyList");
    if (!host) return;
    function render(items) {
      host.innerHTML = "";
      if (!items.length) { host.innerHTML = '<p style="color:var(--text-dim);font-size:.88rem;">No scans yet.</p>'; return; }
      items.slice(0, 25).forEach(function (s) {
        var a = document.createElement("a");
        if (s.scan_id === activeId) a.style.borderColor = "var(--accent)";
        a.href = "results.html?scan=" + encodeURIComponent(s.scan_id);
        a.innerHTML = "<div>" + escapeHtml(s.filename || s.scan_id) + "</div>" +
          '<div class="h-verdict">' + escapeHtml(s.verdict || s.status || "") +
          (s.score != null ? " · " + s.score : "") + "</div>";
        host.appendChild(a);
      });
    }
    // Merge backend history with local cache.
    if ((token() || apiKey()) && API.online) {
      API.history().then(function (data) {
        var merged = (data.scans || []).concat(localHistory());
        var seen = {}, uniq = [];
        merged.forEach(function (s) { if (!seen[s.scan_id]) { seen[s.scan_id] = 1; uniq.push(s); } });
        render(uniq);
      }).catch(function () { render(localHistory()); });
    } else {
      render(localHistory());
    }
  }

  // ----- Dashboard page -----------------------------------------------------
  function initDashboard() {
    var statScans = $("#statScans");
    if (!statScans) return;
    function render(items) {
      statScans.textContent = items.length;
      var fakes = items.filter(function (s) { return /FAKE|SUSPICIOUS/.test(s.verdict || ""); }).length;
      $("#statFlagged").textContent = fakes;
      var reals = items.filter(function (s) { return /REAL/.test(s.verdict || ""); }).length;
      $("#statReal").textContent = reals;
      var host = $("#recentScans");
      host.innerHTML = "";
      if (!items.length) { host.innerHTML = '<p style="color:var(--text-dim)">No scans yet. <a href="scanner.html">Run your first scan →</a></p>'; return; }
      items.slice(0, 8).forEach(function (s) {
        var a = document.createElement("a");
        a.href = "results.html?scan=" + encodeURIComponent(s.scan_id);
        a.className = "";
        a.innerHTML = '<div class="detector-row"><div class="d-name">' + escapeHtml(s.filename || s.scan_id) +
          '</div><div class="d-summary" style="padding-left:0">' + escapeHtml(s.verdict || s.status || "") +
          (s.score != null ? " · score " + s.score : "") + "</div></div>";
        host.appendChild(a);
      });
    }
    if ((token() || apiKey()) && API.online) {
      API.history().then(function (data) {
        var merged = (data.scans || []).concat(localHistory());
        var seen = {}, uniq = [];
        merged.forEach(function (s) { if (!seen[s.scan_id]) { seen[s.scan_id] = 1; uniq.push(s); } });
        render(uniq);
      }).catch(function () { render(localHistory()); });
    } else {
      render(localHistory());
    }

    var keyEl = $("#apiKeyDisplay");
    if (keyEl) keyEl.textContent = apiKey() || "Sign in to view your API key";
  }

  // ----- Copy-to-clipboard buttons -----------------------------------------
  function flashCopied(btn) {
    var orig = btn.innerHTML;
    btn.textContent = "Copied";
    setTimeout(function () { btn.innerHTML = orig; }, 1400);
  }
  function initCopyButtons() {
    $all("#copyApiKey, #copyApiKey2").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var key = apiKey();
        if (!key) { return; }
        if (navigator.clipboard) navigator.clipboard.writeText(key).then(function () { flashCopied(btn); });
        else flashCopied(btn);
      });
    });
  }

  // ----- Settings page ------------------------------------------------------
  function initSettings() {
    var apiBaseInput = $("#apiBaseInput");
    if (!apiBaseInput) return;
    apiBaseInput.value = API_BASE;
    $("#settingsEmail").textContent = email() || "Not signed in";
    var keyEl = $("#settingsApiKey");
    if (keyEl) keyEl.textContent = apiKey() || "Sign in to view your API key";

    var conn = $("#connStatus");
    API.health().then(function (ok) {
      if (conn) { conn.textContent = ok ? "Connected" : "Not reachable"; conn.style.color = ok ? "var(--green)" : "var(--red)"; }
    });

    var save = $("#saveApiBase");
    if (save) save.addEventListener("click", function () {
      var v = apiBaseInput.value.trim().replace(/\/$/, "");
      if (v) localStorage.setItem("adf_api_base", v); else localStorage.removeItem("adf_api_base");
      location.reload();
    });

    var signIn = $("#settingsSignIn");
    if (signIn) signIn.addEventListener("click", openAuthModal);
    var lo = $("#settingsLogout");
    if (lo) lo.addEventListener("click", logout);

    var clear = $("#clearCache");
    if (clear) clear.addEventListener("click", function () {
      localStorage.removeItem("adf_history");
      localStorage.removeItem("adf_last_scan");
      clear.textContent = "Cleared";
      setTimeout(function () { clear.textContent = "Clear cache"; }, 1400);
    });

    var toggle = $("#localCacheToggle");
    if (toggle) {
      toggle.checked = localStorage.getItem("adf_cache_disabled") !== "1";
      toggle.addEventListener("change", function () {
        if (toggle.checked) localStorage.removeItem("adf_cache_disabled");
        else { localStorage.setItem("adf_cache_disabled", "1"); localStorage.removeItem("adf_history"); }
      });
    }
  }

  // ----- History page -------------------------------------------------------
  function initHistory() {
    var body = $("#historyBody");
    if (!body) return;
    var all = [];
    var state = { q: "", filter: "all", sort: "created_at", dir: -1 };

    function bucket(s) {
      if (/FAKE/.test(s.verdict || "")) return "flagged";
      if (/SUSPICIOUS/.test(s.verdict || "")) return "inconclusive";
      if (/REAL/.test(s.verdict || "")) return "authentic";
      return "inconclusive";
    }

    function apply() {
      var rows = all.filter(function (s) {
        if (state.filter !== "all" && bucket(s) !== state.filter) return false;
        if (state.q && (s.filename || s.scan_id || "").toLowerCase().indexOf(state.q) === -1) return false;
        return true;
      });
      rows.sort(function (a, b) {
        var av = a[state.sort], bv = b[state.sort];
        if (state.sort === "score") { av = av || 0; bv = bv || 0; }
        else { av = (av || "").toString(); bv = (bv || "").toString(); }
        return (av < bv ? -1 : av > bv ? 1 : 0) * state.dir;
      });
      render(rows);
    }

    function render(rows) {
      body.innerHTML = "";
      var empty = $("#historyEmpty"), table = $("#historyTable");
      if (!rows.length) { if (empty) empty.style.display = "block"; if (table) table.style.display = "none"; return; }
      if (empty) empty.style.display = "none"; if (table) table.style.display = "table";
      rows.forEach(function (s) {
        var sc = s.score != null ? Math.round(s.score) : null;
        var cls = sc == null ? "warn" : statusClass(sc);
        var date = s.created_at ? new Date(s.created_at).toLocaleString() : "—";
        var tr = document.createElement("tr");
        tr.addEventListener("click", function () { location.href = "results.html?scan=" + encodeURIComponent(s.scan_id); });
        tr.innerHTML =
          "<td>" + escapeHtml(s.filename || s.scan_id) + "</td>" +
          "<td>" + escapeHtml(s.media_type || "—") + "</td>" +
          '<td><span class="pill ' + cls + '">' + escapeHtml(s.verdict || s.status || "—") + "</span></td>" +
          '<td style="font-variant-numeric:tabular-nums;">' + (sc != null ? sc : "—") + "</td>" +
          '<td style="color:var(--text-dim);">' + escapeHtml(date) + "</td>";
        body.appendChild(tr);
      });
    }

    function load(items) {
      var seen = {}, uniq = [];
      items.forEach(function (s) { if (s && s.scan_id && !seen[s.scan_id]) { seen[s.scan_id] = 1; uniq.push(s); } });
      all = uniq;
      apply();
    }

    if ((token() || apiKey()) && API.online) {
      API.history().then(function (data) { load((data.scans || []).concat(localHistory())); })
        .catch(function () { load(localHistory()); });
    } else {
      load(localHistory());
    }

    var search = $("#historySearch");
    if (search) search.addEventListener("input", function () { state.q = search.value.trim().toLowerCase(); apply(); });

    var filter = $("#historyFilter");
    if (filter) filter.addEventListener("click", function (e) {
      var b = e.target.closest("button"); if (!b) return;
      $all("button", filter).forEach(function (x) { x.classList.remove("active"); });
      b.classList.add("active");
      state.filter = b.getAttribute("data-filter");
      apply();
    });

    $all("th[data-sort]", $("#historyTable")).forEach(function (th) {
      th.addEventListener("click", function () {
        var key = th.getAttribute("data-sort");
        if (state.sort === key) state.dir *= -1; else { state.sort = key; state.dir = key === "score" ? -1 : 1; }
        apply();
      });
    });
  }

  // ----- Boot ---------------------------------------------------------------
  document.addEventListener("DOMContentLoaded", function () {
    initSidebar();
    // Probe backend health; flips to offline/demo mode on failure.
    API.health().then(function (ok) {
      API.online = ok;
      var banner = $("#offlineBanner");
      if (banner && !ok) banner.classList.remove("hidden");
    });
    initAuthUI();
    initCopyButtons();
    initDashboard();
    initScanner();
    initResults();
    initHistory();
    initSettings();
  });

  // Expose a couple of helpers for inline use / debugging.
  window.ADF = { API: API, setApiBase: function (b) { localStorage.setItem("adf_api_base", b); location.reload(); } };
})();
