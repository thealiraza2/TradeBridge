// content.js - TradeBridge One-Click Trading Panel for TradingView

(function () {
  // Prevent duplicate injection
  if (document.getElementById("tradebridge-panel")) return;

  // 1. Create Panel DOM
  const panel = document.createElement("div");
  panel.id = "tradebridge-panel";
  panel.innerHTML = `
    <div id="tb-header">
      <span>⚡ TradeBridge</span>
      <div class="tb-window-controls">
        <button id="tb-btn-min" class="tb-btn-icon" title="Minimize">−</button>
        <button id="tb-btn-close" class="tb-btn-icon" title="Close">×</button>
      </div>
    </div>
    <div id="tb-body">
      <div class="tb-row">
        <label for="tb-symbol">Symbol</label>
        <input type="text" id="tb-symbol" class="tb-input" placeholder="e.g. XAUUSD">
      </div>

      <div id="tb-manual-entry-row" class="tb-row">
        <label for="tb-manual-entry" style="color: #f59e0b;">Manual Entry Price</label>
        <input type="number" id="tb-manual-entry" class="tb-input" step="any" placeholder="Type entry price">
      </div>

      <div class="tb-grid-2">
        <div>
          <label for="tb-sl-dist">SL Distance</label>
          <input type="number" id="tb-sl-dist" class="tb-input" step="any" value="2.0">
        </div>
        <div>
          <label for="tb-tp-dist">TP Distance</label>
          <input type="number" id="tb-tp-dist" class="tb-input" step="any" value="4.0">
        </div>
      </div>

      <div class="tb-grid-2">
        <div>
          <label for="tb-risk">Risk %</label>
          <input type="number" id="tb-risk" class="tb-input" step="0.1" min="0.1" max="5.0" value="1.0">
        </div>
        <div>
          <label for="tb-maxlot">Max Lot</label>
          <input type="number" id="tb-maxlot" class="tb-input" step="0.01" min="0.01" value="2.0">
        </div>
      </div>

      <div class="tb-buttons">
        <button id="tb-btn-buy" class="tb-btn tb-btn-buy" disabled>BUY</button>
        <button id="tb-btn-sell" class="tb-btn tb-btn-sell" disabled>SELL</button>
      </div>

      <div id="tb-status">Ready</div>
    </div>
  `;

  document.body.appendChild(panel);

  // 2. Element References
  const header = document.getElementById("tb-header");
  const btnMin = document.getElementById("tb-btn-min");
  const btnClose = document.getElementById("tb-btn-close");
  const symbolInput = document.getElementById("tb-symbol");
  const manualEntryRow = document.getElementById("tb-manual-entry-row");
  const manualEntryInput = document.getElementById("tb-manual-entry");
  const slDistInput = document.getElementById("tb-sl-dist");
  const tpDistInput = document.getElementById("tb-tp-dist");
  const riskInput = document.getElementById("tb-risk");
  const maxLotInput = document.getElementById("tb-maxlot");
  const btnBuy = document.getElementById("tb-btn-buy");
  const btnSell = document.getElementById("tb-btn-sell");
  const statusEl = document.getElementById("tb-status");

  // 3. Load defaults from storage
  if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
    chrome.storage.local.get(["default_risk_pct", "default_max_lot"], (res) => {
      if (res.default_risk_pct) riskInput.value = res.default_risk_pct;
      if (res.default_max_lot) maxLotInput.value = res.default_max_lot;
    });
  }

  // 4. Window Controls (Minimize & Close)
  btnMin.addEventListener("click", () => {
    panel.classList.toggle("collapsed");
    btnMin.textContent = panel.classList.contains("collapsed") ? "+" : "−";
  });

  btnClose.addEventListener("click", () => {
    panel.style.display = "none";
  });

  // 5. Draggable Header
  let isDragging = false;
  let startX, startY, origLeft, origTop;

  header.addEventListener("mousedown", (e) => {
    if (e.target.tagName === "BUTTON") return;
    isDragging = true;
    startX = e.clientX;
    startY = e.clientY;
    const rect = panel.getBoundingClientRect();
    origLeft = rect.left;
    origTop = rect.top;
    panel.style.bottom = "auto";
    panel.style.right = "auto";
    panel.style.left = `${origLeft}px`;
    panel.style.top = `${origTop}px`;
  });

  window.addEventListener("mousemove", (e) => {
    if (!isDragging) return;
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    panel.style.left = `${origLeft + dx}px`;
    panel.style.top = `${origTop + dy}px`;
  });

  window.addEventListener("mouseup", () => {
    isDragging = false;
  });

  // 6. Detect Symbol from Chart Title
  function detectSymbol() {
    // TradingView page title formats typically start with the ticker e.g. "XAUUSD 2650.50 ..."
    const title = document.title || "";
    const match = title.match(/^([A-Z0-9.:_-]+)/);
    if (match && match[1] && match[1] !== "TradingView") {
      return match[1].replace(/[^A-Z0-9.:_-]/g, "");
    }

    // Secondary attempt: inspect symbol search header button
    const symbolBtn = document.querySelector("#header-toolbar-symbol-search, [data-name='legend-series-item']");
    if (symbolBtn && symbolBtn.textContent) {
      const btnText = symbolBtn.textContent.trim().split(" ")[0];
      if (btnText && /^[A-Z0-9.:_-]+$/.test(btnText)) {
        return btnText;
      }
    }
    return "";
  }

  function updateSymbolState() {
    const detected = detectSymbol();
    if (detected && !symbolInput.value) {
      symbolInput.value = detected;
    }

    const currentSymbol = symbolInput.value.trim();
    if (!currentSymbol) {
      btnBuy.disabled = true;
      btnSell.disabled = true;
      statusEl.className = "";
      statusEl.textContent = "Type symbol to enable trade";
    } else {
      btnBuy.disabled = false;
      btnSell.disabled = false;
      if (statusEl.textContent === "Type symbol to enable trade") {
        statusEl.textContent = "Ready";
      }
    }
  }

  symbolInput.addEventListener("input", updateSymbolState);
  updateSymbolState();
  // Poll title changes when switching charts without page reload
  setInterval(updateSymbolState, 2000);

  // 7. Detect Current Chart Price
  function detectCurrentPrice() {
    // Attempt 1: From document title (e.g. "XAUUSD 2650.50 ...")
    const title = document.title || "";
    const titleParts = title.trim().split(/\s+/);
    if (titleParts.length >= 2) {
      const rawNum = titleParts[1].replace(/,/g, "");
      const price = parseFloat(rawNum);
      if (!isNaN(price) && price > 0) return price;
    }

    // Attempt 2: From chart legend last value element
    const legendLast = document.querySelector("[data-name='legend-last-value'], .last-value, .pane-legend-line .pane-legend-item-value");
    if (legendLast && legendLast.textContent) {
      const price = parseFloat(legendLast.textContent.replace(/,/g, "").trim());
      if (!isNaN(price) && price > 0) return price;
    }

    // Attempt 3: Manual entry fallback if user typed it
    if (manualEntryInput.value) {
      const price = parseFloat(manualEntryInput.value);
      if (!isNaN(price) && price > 0) return price;
    }

    return null;
  }

  // 8. Order Execution Dispatcher
  async function handleOrderClick(action) {
    const symbol = symbolInput.value.trim();
    if (!symbol) {
      statusEl.className = "tb-status-error";
      statusEl.textContent = "Error: Symbol is required";
      return;
    }

    const price = detectCurrentPrice();
    if (!price) {
      manualEntryRow.style.display = "block";
      manualEntryInput.focus();
      statusEl.className = "tb-status-error";
      statusEl.textContent = "Price not found — type entry manually";
      return;
    }

    const slDist = parseFloat(slDistInput.value) || 2.0;
    const tpDist = parseFloat(tpDistInput.value) || 4.0;
    const riskPct = parseFloat(riskInput.value) || 1.0;
    const maxLot = parseFloat(maxLotInput.value) || 2.0;

    let sl, tp;
    if (action === "BUY") {
      sl = price - slDist;
      tp = price + tpDist;
    } else {
      sl = price + slDist;
      tp = price - tpDist;
    }

    // Fetch storage credentials
    let webhookUrl = "http://127.0.0.1:8000/webhook";
    let webhookSecret = "";

    if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
      const settings = await new Promise((resolve) => {
        chrome.storage.local.get(["webhook_url", "webhook_secret"], resolve);
      });
      if (settings.webhook_url) webhookUrl = settings.webhook_url;
      if (settings.webhook_secret) webhookSecret = settings.webhook_secret;
    }

    if (!webhookSecret) {
      statusEl.className = "tb-status-error";
      statusEl.textContent = "Configure Secret in extension popup!";
      return;
    }

    const alertId = "tb-click-" + Date.now() + "-" + Math.floor(Math.random() * 1000);
    const payload = {
      secret: webhookSecret,
      action: action,
      symbol: symbol,
      entry: price,
      sl: sl,
      tp: tp,
      risk_pct: riskPct,
      max_lot: maxLot,
      alert_id: alertId,
      comment: "TradeBridge-Click-" + action,
    };

    statusEl.className = "tb-status-sending";
    statusEl.textContent = "Sending…";

    try {
      const resp = await fetch(webhookUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await resp.json();
      if (resp.ok && data.status === "ok") {
        const ticket = data.result ? data.result.ticket : "OK";
        statusEl.className = "tb-status-success";
        statusEl.textContent = `Trade opened, ticket ${ticket}`;
      } else {
        statusEl.className = "tb-status-error";
        statusEl.textContent = data.reason || `HTTP ${resp.status} Error`;
      }
    } catch (err) {
      statusEl.className = "tb-status-error";
      statusEl.textContent = "Network error: " + err.message;
    }
  }

  btnBuy.addEventListener("click", () => handleOrderClick("BUY"));
  btnSell.addEventListener("click", () => handleOrderClick("SELL"));
})();
