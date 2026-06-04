/* AntiDeepfake AI — content script
   Shows a small floating overlay with the detection verdict when the
   background worker reports a result. Pure DOM, no framework.
*/
(function () {
  "use strict";

  var box = null;

  function ensureBox() {
    if (box) return box;
    box = document.createElement("div");
    box.id = "adf-overlay";
    box.style.cssText = [
      "position:fixed", "bottom:20px", "right:20px", "z-index:2147483647",
      "min-width:240px", "max-width:320px", "padding:14px 16px",
      "background:#161929", "color:#e7e9f5", "border:1px solid #232742",
      "border-radius:12px", "box-shadow:0 12px 40px rgba(0,0,0,.5)",
      "font-family:-apple-system,Segoe UI,Roboto,sans-serif", "font-size:14px",
      "line-height:1.4",
    ].join(";");
    document.documentElement.appendChild(box);
    return box;
  }

  function colorFor(score) {
    if (score >= 60) return "#2ecc71";
    if (score >= 40) return "#f5a623";
    return "#ff4d6d";
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[ch];
    });
  }

  function render(payload) {
    var el = ensureBox();
    var close = '<span style="float:right;cursor:pointer;color:#9aa0bd" id="adf-close">✕</span>';
    var head = '<div style="font-weight:800;margin-bottom:6px">AntiDeepfake AI' + close + "</div>";

    if (payload.state === "loading") {
      el.innerHTML = head + '<div style="color:#9aa0bd">' + escapeHtml(payload.message) + "</div>";
    } else if (payload.state === "error") {
      el.innerHTML = head + '<div style="color:#ff4d6d">' + escapeHtml(payload.message) + "</div>" +
        '<div style="color:#9aa0bd;font-size:12px;margin-top:6px">Set your API base & key in the extension popup.</div>';
    } else if (payload.state === "done") {
      var c = colorFor(payload.score);
      el.innerHTML = head +
        '<div style="font-size:22px;font-weight:900;color:' + c + '">' + escapeHtml(payload.verdict) + "</div>" +
        '<div style="color:#9aa0bd">Authenticity score: <b style="color:' + c + '">' + escapeHtml(payload.score) + "/100</b></div>";
    }

    var x = document.getElementById("adf-close");
    if (x) x.addEventListener("click", function () { el.remove(); box = null; });

    // Auto-dismiss successful results after a while.
    if (payload.state === "done") {
      setTimeout(function () { if (box === el) { el.remove(); box = null; } }, 8000);
    }
  }

  chrome.runtime.onMessage.addListener(function (msg) {
    if (msg && msg.type === "ADF_RESULT") render(msg.payload);
  });
})();
