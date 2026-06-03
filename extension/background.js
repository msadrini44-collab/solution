/* AntiDeepfake AI — extension service worker (Manifest V3)
   - Registers the "Check for deepfake" context-menu item on images.
   - On click, downloads the image and POSTs it to the detection API.
   - Streams a quick result back to the content script for an on-page overlay.
*/

const DEFAULT_API_BASE = "http://localhost:8000";

// Read the configured API base + key from storage (set in the popup).
async function getConfig() {
  const { apiBase, apiKey } = await chrome.storage.sync.get(["apiBase", "apiKey"]);
  return { apiBase: apiBase || DEFAULT_API_BASE, apiKey: apiKey || "" };
}

// Create the context menu on install.
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "adf-check-image",
    title: "🛡️ Check for deepfake",
    contexts: ["image"],
  });
});

// Handle context-menu clicks.
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== "adf-check-image" || !info.srcUrl) return;
  await analyzeImage(info.srcUrl, tab.id);
});

// Allow the popup / content script to trigger analysis too.
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.type === "ADF_ANALYZE" && msg.srcUrl) {
    analyzeImage(msg.srcUrl, sender.tab ? sender.tab.id : null)
      .then((res) => sendResponse({ ok: true, result: res }))
      .catch((err) => sendResponse({ ok: false, error: String(err) }));
    return true; // async response
  }
});

async function analyzeImage(srcUrl, tabId) {
  const { apiBase, apiKey } = await getConfig();

  notify(tabId, { state: "loading", message: "Analyzing image…" });

  try {
    // Fetch the image bytes (service workers can fetch cross-origin).
    const imgResp = await fetch(srcUrl);
    if (!imgResp.ok) throw new Error("Could not download image");
    const blob = await imgResp.blob();

    const form = new FormData();
    const name = (srcUrl.split("/").pop() || "image").split("?")[0] || "image.jpg";
    form.append("file", blob, name);

    const headers = {};
    if (apiKey) headers["X-API-Key"] = apiKey;

    const resp = await fetch(`${apiBase}/api/detect?sync=true`, {
      method: "POST",
      headers,
      body: form,
    });
    if (!resp.ok) throw new Error(`API error ${resp.status}`);
    const result = await resp.json();

    // Cache the latest result for the popup to display.
    await chrome.storage.local.set({ lastResult: result });

    notify(tabId, {
      state: "done",
      verdict: result.verdict,
      score: result.score,
      message: `${result.verdict} · ${result.score}/100`,
    });
    return result;
  } catch (err) {
    notify(tabId, { state: "error", message: String(err.message || err) });
    throw err;
  }
}

function notify(tabId, payload) {
  if (tabId == null) return;
  chrome.tabs.sendMessage(tabId, { type: "ADF_RESULT", payload }).catch(() => {
    /* content script may not be present on some pages; ignore */
  });
}
