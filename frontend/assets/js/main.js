/* AntiDeepfake AI — sales page interactions
   - Mobile nav toggle
   - Smooth scroll for in-page anchors
   - FAQ accordion
   - Testimonial slider (auto-rotating with dots)
*/
(function () {
  "use strict";

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
