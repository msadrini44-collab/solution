/* AntiDeepfake AI — popup logic
   Lets the user configure the API base + key (stored via chrome.storage.sync)
   and shows the most recent scan result.
*/
(function () {
  "use strict";

  var apiBaseEl = document.getElementById("apiBase");
  var apiKeyEl = document.getElementById("apiKey");
  var savedEl = document.getElementById("saved");

  // Load saved settings.
  chrome.storage.sync.get(["apiBase", "apiKey"], function (cfg) {
    apiBaseEl.value = cfg.apiBase || "https://api.antideepfakeai.com";
    apiKeyEl.value = cfg.apiKey || "";
  });

  // Save settings.
  document.getElementById("saveBtn").addEventListener("click", function () {
    chrome.storage.sync.set(
      { apiBase: apiBaseEl.value.trim(), apiKey: apiKeyEl.value.trim() },
      function () {
        savedEl.textContent = "Saved";
        setTimeout(function () { savedEl.textContent = ""; }, 2000);
      }
    );
  });

  // Show last result.
  function colorFor(score) {
    if (score >= 60) return "#2ecc71";
    if (score >= 40) return "#f5a623";
    return "#ff4d6d";
  }
  chrome.storage.local.get(["lastResult"], function (data) {
    var r = data.lastResult;
    if (!r) return;
    var box = document.getElementById("lastResult");
    box.classList.add("show");
    var v = document.getElementById("lastVerdict");
    v.textContent = r.verdict + " · " + r.score + "/100";
    v.style.color = colorFor(r.score);
    document.getElementById("lastFile").textContent = r.filename || "";
  });

  // Open the web app dashboard.
  document.getElementById("openApp").addEventListener("click", function () {
    chrome.storage.sync.get(["apiBase"], function (cfg) {
      // The web app is served separately; default to the local dev server.
      chrome.tabs.create({ url: "https://antideepfakeai.com/app/index.html" });
    });
  });
})();
