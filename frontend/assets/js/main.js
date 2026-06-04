/* AntiDeepfake AI — sales page interactions
   - Mobile nav toggle
   - Smooth scroll for in-page anchors
   - FAQ accordion
   - Testimonial slider (auto-rotating with dots)
*/
(function () {
  "use strict";

  function defaultApiBase() {
    if (/(\.|^)antideepfakeai\.com$/i.test(location.hostname)) {
      return "https://api.antideepfakeai.com";
    }
    return "http://localhost:8000";
  }

  var API_BASE = localStorage.getItem("adf_api_base") || defaultApiBase();

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[ch];
    });
  }

  function handleJson(resp) {
    return resp.json().catch(function () { return {}; }).then(function (data) {
      if (!resp.ok) throw new Error(data.detail || "The scan could not be completed.");
      return data;
    });
  }

  /* ---------- Mobile nav ---------- */
  var navToggle = document.getElementById("navToggle");
  var navLinks = document.getElementById("navLinks");
  if (navToggle && navLinks) {
    navToggle.addEventListener("click", function () {
      navLinks.classList.toggle("open");
    });
    // Close the menu after clicking a link (mobile).
    navLinks.querySelectorAll("a").forEach(function (a) {
      a.addEventListener("click", function () {
        navLinks.classList.remove("open");
      });
    });
  }

  /* ---------- One free landing-page scan ---------- */
  var trialForm = document.getElementById("trialForm");
  if (trialForm) {
    var trialFile = document.getElementById("trialFile");
    var trialStatus = document.getElementById("trialStatus");
    var trialResult = document.getElementById("trialResult");

    trialForm.addEventListener("submit", function (e) {
      e.preventDefault();
      if (!trialFile.files.length) return;
      var file = trialFile.files[0];
      var body = new FormData();
      body.append("file", file);

      trialStatus.textContent = "Uploading and analyzing with the production backend…";
      trialResult.classList.add("hidden");
      trialForm.querySelector("button").disabled = true;

      fetch(API_BASE + "/api/trial/detect", { method: "POST", body: body })
        .then(handleJson)
        .then(function (res) {
          var score = res.score == null ? "—" : Math.round(res.score);
          var notes = (res.decision_notes || []).slice(0, 2).map(escapeHtml).join("<br>");
          trialStatus.textContent = "Analysis complete.";
          trialResult.innerHTML =
            '<div class="verdict-line"><strong>' + escapeHtml(res.verdict || "Result ready") + '</strong><span class="score">' + score + "/100</span></div>" +
            '<p class="small">Evidence grade: ' + escapeHtml(res.evidence_grade || "review") + " · Detectors used: " + escapeHtml(res.detectors_used || "—") + "</p>" +
            (notes ? '<p class="small" style="margin-top:10px;">' + notes + "</p>" : "") +
            '<p class="small" style="margin-top:12px;">Create an account to keep history, download reports, and run more scans.</p>' +
            '<a class="btn btn-ghost" style="margin-top:14px;" href="app/index.html">Create account / log in</a>';
          trialResult.classList.remove("hidden");
        })
        .catch(function (err) {
          trialStatus.textContent = err.message;
        })
        .finally(function () {
          trialForm.querySelector("button").disabled = false;
        });
    });
  }

  /* ---------- Smooth scroll (with sticky-nav offset) ---------- */
  document.querySelectorAll('a[href^="#"]').forEach(function (link) {
    link.addEventListener("click", function (e) {
      var id = link.getAttribute("href");
      if (id.length < 2) return;
      var target = document.querySelector(id);
      if (!target) return;
      e.preventDefault();
      var top = target.getBoundingClientRect().top + window.pageYOffset - 80;
      window.scrollTo({ top: top, behavior: "smooth" });
    });
  });

  /* ---------- FAQ accordion ---------- */
  document.querySelectorAll(".faq-item .faq-q").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var item = btn.parentElement;
      var alreadyOpen = item.classList.contains("open");
      // Close all, then open this one (single-open accordion).
      document.querySelectorAll(".faq-item.open").forEach(function (el) {
        el.classList.remove("open");
      });
      if (!alreadyOpen) item.classList.add("open");
    });
  });

  /* ---------- Testimonial slider ---------- */
  var slides = Array.prototype.slice.call(
    document.querySelectorAll(".testimonial-slide")
  );
  var dotsWrap = document.getElementById("testimonialDots");
  if (slides.length && dotsWrap) {
    var current = 0;
    var timer = null;

    slides.forEach(function (_, i) {
      var dot = document.createElement("button");
      if (i === 0) dot.classList.add("active");
      dot.setAttribute("aria-label", "Show testimonial " + (i + 1));
      dot.addEventListener("click", function () {
        show(i);
        restart();
      });
      dotsWrap.appendChild(dot);
    });

    function show(i) {
      slides[current].classList.remove("active");
      dotsWrap.children[current].classList.remove("active");
      current = (i + slides.length) % slides.length;
      slides[current].classList.add("active");
      dotsWrap.children[current].classList.add("active");
    }

    function next() {
      show(current + 1);
    }

    function restart() {
      if (timer) clearInterval(timer);
      timer = setInterval(next, 6000);
    }

    restart();
  }
})();
