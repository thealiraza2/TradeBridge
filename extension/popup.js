// popup.js - Handles extension configuration and connection testing

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("settings-form");
  const webhookUrlInput = document.getElementById("webhook_url");
  const webhookSecretInput = document.getElementById("webhook_secret");
  const defaultRiskInput = document.getElementById("default_risk_pct");
  const defaultMaxLotInput = document.getElementById("default_max_lot");
  const testBtn = document.getElementById("btn-test");
  const statusDiv = document.getElementById("test-status");

  // Load existing settings from chrome.storage.local
  if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
    chrome.storage.local.get(
      ["webhook_url", "webhook_secret", "default_risk_pct", "default_max_lot"],
      (res) => {
        if (res.webhook_url) webhookUrlInput.value = res.webhook_url;
        if (res.webhook_secret) webhookSecretInput.value = res.webhook_secret;
        if (res.default_risk_pct) defaultRiskInput.value = res.default_risk_pct;
        if (res.default_max_lot) defaultMaxLotInput.value = res.default_max_lot;
      }
    );
  }

  // Save settings
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const data = {
      webhook_url: webhookUrlInput.value.trim(),
      webhook_secret: webhookSecretInput.value.trim(),
      default_risk_pct: parseFloat(defaultRiskInput.value) || 1.0,
      default_max_lot: parseFloat(defaultMaxLotInput.value) || 2.0,
    };

    if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
      chrome.storage.local.set(data, () => {
        statusDiv.className = "status-ok";
        statusDiv.textContent = "Settings saved successfully!";
        setTimeout(() => { statusDiv.textContent = ""; }, 3000);
      });
    } else {
      statusDiv.className = "status-ok";
      statusDiv.textContent = "Settings saved (browser session)!";
    }
  });

  // Test Connection
  testBtn.addEventListener("click", async () => {
    const rawUrl = webhookUrlInput.value.trim();
    if (!rawUrl) {
      statusDiv.className = "status-err";
      statusDiv.textContent = "Please enter a server webhook URL first.";
      return;
    }

    statusDiv.className = "";
    statusDiv.textContent = "Testing connection...";

    // Derive /health URL from /webhook
    let healthUrl = rawUrl;
    if (healthUrl.endsWith("/webhook")) {
      healthUrl = healthUrl.slice(0, -8) + "/health";
    } else if (healthUrl.endsWith("/webhook/")) {
      healthUrl = healthUrl.slice(0, -9) + "/health";
    } else {
      healthUrl = healthUrl.replace(/\/+$/, "") + "/health";
    }

    try {
      const resp = await fetch(healthUrl, { method: "GET" });
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }
      const data = await resp.json();
      if (data.status === "ok") {
        const mt5Status = data.mt5_connected ? "MT5 Connected" : "MT5 Offline";
        statusDiv.className = "status-ok";
        statusDiv.textContent = `Server Connected (${mt5Status})`;
      } else {
        statusDiv.className = "status-err";
        statusDiv.textContent = "Server returned non-OK response.";
      }
    } catch (err) {
      statusDiv.className = "status-err";
      statusDiv.textContent = `Cannot connect: ${err.message}`;
    }
  });
});
