# TradeBridge — Automated TradingView to MetaTrader 5 Bridge

TradeBridge is an execution-only bridge that places trades in **MetaTrader 5 (MT5)** directly from **TradingView** charts. It receives webhook alerts from Pine Script indicators or manual one-click execution from a Chrome extension, validates the payload, applies strict safety filters, calculates precise position lot sizes based on account risk %, and opens trades via the MetaTrader 5 Python engine.

> **Project status (read this first):** The bridge code is complete and its test suite passes on a fresh checkout (43 tests, MT5 calls mocked in tests — as unit tests should). **Live execution against a real MT5 terminal has not been verified yet.** Before using it with real money, run the demo-account checklist in `PRE_FLIGHT.md` and confirm a real ticket in MT5 History. Do not treat any past test output as proof of a live trade.

> **EXECUTION ONLY**: The bridge executes only what the trader configures. It contains no trading strategy of its own. The Pine Script ships with an *optional example* EMA-crossover trigger that is **OFF by default** — turn it on only if you want an example signal; otherwise use your own levels or manual alerts.

---

## Architecture & Data Flow

```text
       TRADINGVIEW                               TRADEBRIDGE VPS / HOST
┌────────────────────────┐              ┌─────────────────────────────────────┐
│ Pine Script v5 Alert   │              │   Cloudflare Tunnel (HTTPS)         │
│         OR             │──(Webhook)──>│   (Zero open ports / firewall safe) │
│ One-Click Chrome Panel │              └──────────────────┬──────────────────┘
└────────────────────────┘                                 │
                                                           ▼
                                        ┌─────────────────────────────────────┐
                                        │  FastAPI Bridge Server (Port 8000)  │
                                        │  1. Secret Authentication           │
                                        │  2. Deduplication (alert_id)        │
                                        │  3. Safety Gates:                   │
                                        │     - Kill Switch                   │
                                        │     - Max Positions Limit           │
                                        │     - Max Daily Loss %              │
                                        │  4. Risk & Lot-Size Calculator      │
                                        │     - Floor Rounding (Never up)     │
                                        │     - Lot Ceiling (max_lot)         │
                                        └──────────────────┬──────────────────┘
                                                           │
                                                           ▼ (IPC Python API)
                                        ┌─────────────────────────────────────┐
                                        │  MetaTrader 5 Terminal (x64)        │
                                        │  - Real-time tick & contract specs  │
                                        │  - Market order with SL/TP          │
                                        └──────────────────┬──────────────────┘
                                                           │
                                                           ▼
                                        ┌─────────────────────────────────────┐
                                        │  Broker Demo / Live Account         │
                                        └─────────────────────────────────────┘
```

---

## System Requirements

- **Operating System**: Windows 10/11 or Windows Server 2019/2022 (minimum 2 GB RAM, 1 vCPU).
- **Python**: Version `3.11.x` (64-bit).
- **MetaTrader 5**: Desktop terminal installed with an active demo or live account.
- **TradingView**: Account with webhook alert capability (Essential, Plus, or Premium plan).
- **Browser**: Google Chrome or Chromium-based browser (for the One-Click Trading extension).

---

## Step-by-Step Setup Guide (From Zero to First Trade in 30 Minutes)

### Step 1: Clone or Copy Project Files
Place the `tradebridge` folder on your machine or VPS:
```powershell
cd "C:\TradeBridge"
```

### Step 2: Create Virtual Environment & Install Dependencies
Use the exact pinned dependencies to prevent version conflicts:
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Verify the installation with the test suite:
```powershell
pytest tests/ -v
```
*(All 43 unit and integration tests should pass on a fresh checkout. The tests mock the MT5 terminal — they prove the logic, not a live trade. See the Project status note at the top.)*

### Step 3: Configure Environment Variables (`.env`)
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```
Open `.env` and fill in your actual credentials:
```ini
# MT5 demo account credentials
MT5_LOGIN=your_mt5_login
MT5_PASSWORD=your_mt5_password
MT5_SERVER=YourBroker-Demo

# Secret token (must match TradingView alert payload)
# Generate one with: python -c "import secrets; print(secrets.token_hex(32))"
# NEVER commit a real secret to git, and never paste it into this README.
WEBHOOK_SECRET=paste_your_generated_secret_here

# Trading defaults
DEFAULT_RISK_PCT=1.0
DEFAULT_MAX_LOT=2.0
MAX_POSITIONS=5
MAX_DAILY_LOSS_PCT=3.0
MODE=demo
```

### Step 4: Configure MetaTrader 5 Terminal
1. Open the MT5 Desktop Terminal and log in to your demo account (check **Save password**).
2. Go to **Tools → Options → Expert Advisors**:
   - Check **"Allow algorithmic trading"**.
   - Ensure "Disable algorithmic trading when account/profile changed" is unchecked.
3. Open Market Watch and confirm your broker's symbol names (e.g., `XAUUSD`, `EURUSD`). If your broker uses suffixes (like `XAUUSD.m`), add them to `config/symbols.json`.

### Step 5: Start the Server
Launch the server using the startup script:
```powershell
.\start_tradebridge.bat
```
Visit `http://127.0.0.1:8000/health` in your browser. You should see something like (your own login and balance will appear here):
```json
{
  "status": "ok",
  "mt5_connected": true,
  "account": "your_mt5_login",
  "balance": "your_balance",
  "mode": "demo"
}
```

### Step 6: TradingView Pine Script Setup
1. Open TradingView, open Pine Editor, and paste the code from `pine/tradebridge_sender.pine`.
2. Click **Add to chart**.
3. In indicator settings:
   - Paste your `webhookSecret`.
   - Set default `riskPct` and `maxLot`.
4. Click the three dots on the indicator → **Add alert on TradeBridge Sender**:
   - Condition: `TradeBridge Sender` → `Any alert() function call`.
   - Webhook URL: Paste your server webhook URL (`https://<YOUR_TUNNEL_URL>/webhook`).

### Step 7: Chrome Extension Installation (One-Click Panel)
1. In Google Chrome, navigate to `chrome://extensions/`.
2. Enable **Developer mode** (toggle in the top-right corner).
3. Click **Load unpacked** and select the `tradebridge/extension` directory.
4. Click the TradeBridge icon in Chrome toolbar:
   - Server Webhook URL: `https://<YOUR_TUNNEL_URL>/webhook`
   - Webhook Secret: Paste your secret token.
   - Click **Test Connection** (turns green) and click **Save Settings**.
5. Open any TradingView chart (`https://www.tradingview.com/chart/`). The floating **⚡ TradeBridge** panel appears at the bottom-right.

### Step 8: VPS 24/7 Deployment
To run TradeBridge 24/7 without keeping your personal laptop on:
1. Copy the project to your Windows VPS.
2. In Administrator PowerShell:
   ```powershell
   cd C:\TradeBridge\scripts
   powershell -ExecutionPolicy Bypass -File .\setup_scheduled_tasks.ps1
   powershell -ExecutionPolicy Bypass -File .\setup_cloudflare_tunnel.ps1
   ```
3. Cloudflare Tunnel exposes `127.0.0.1:8000` securely via HTTPS with **zero open ports** in the firewall.
4. The watchdog script monitors `/health` every 5 minutes and automatically restarts the bridge if down.

---

## Risk & Position-Sizing Formula

TradeBridge calculates lot sizing strictly from cash risk, stop loss distance, and contract specifications. It **always rounds DOWN** to the nearest broker volume step to ensure the account never risks even a penny more than authorized.

$$\text{risk\_amount} = \text{balance} \times \left(\frac{\text{risk\_pct}}{100}\right)$$

$$\text{sl\_distance} = |\text{entry} - \text{sl}|$$

$$\text{sl\_in\_units} = \frac{\text{sl\_distance}}{\text{pip\_size}} \quad (\text{pips for forex, dollars for gold})$$

$$\text{loss\_per\_lot} = \text{sl\_in\_units} \times \text{tick\_value\_per\_unit}$$

$$\text{raw\_lot} = \frac{\text{risk\_amount}}{\text{loss\_per\_lot}}$$

$$\text{lot} = \min\left(\text{floor\_to\_step}(\text{raw\_lot}), \text{max\_lot}\right)$$

### Worked Examples

1. **XAUUSD (Gold)**:
   - Balance = $10,000 | Risk = 1.0% ($100 risk amount)
   - Entry = $3,902.00 | Stop Loss = $3,900.00 ($2.00 distance)
   - Gold tick value = $100.0 per $1.00 move per 1.0 lot.
   - Loss per lot = $2.00 × $100.00 = $200.00
   - Raw lot = $100 / $200 = **0.50 lot**.

2. **EURUSD (Forex)**:
   - Balance = $10,000 | Risk = 1.0% ($100 risk amount)
   - Entry = 1.08200 | Stop Loss = 1.08000 (20 pips away)
   - EURUSD tick value = $10.0 per pip per 1.0 lot.
   - Loss per lot = 20 pips × $10.00 = $200.00
   - Raw lot = $100 / $200 = **0.50 lot**.

3. **XAUUSD (Small Risk)**:
   - Balance = $5,000 | Risk = 0.5% ($25 risk amount)
   - Stop Loss = $5.00 away.
   - Loss per lot = $5.00 × $100.00 = $500.00
   - Raw lot = $25 / $500 = **0.05 lot**.

4. **Floor Rounding & Ceiling**:
   - If raw calculated lot is `0.579` with step `0.01`, TradeBridge rounds down to `0.57` (never `0.58`).
   - If a tiny stop loss calculates `5.00` lots and `max_lot` is `2.00`, TradeBridge caps execution at `2.00` lots.

---

## Safety Systems Overview

| Safety Gate | Trigger / Rule | Action |
| :--- | :--- | :--- |
| **Kill Switch** | Toggled via `/kill` or Dashboard | Instantly rejects all incoming webhooks (`400 Bad Request`). |
| **Lot Ceiling** | Calculated lot exceeds `max_lot` | Automatically caps execution volume at `max_lot`. |
| **Max Open Positions** | Open positions count in MT5 reaches `max_positions` | Rejects new incoming alerts (`max open positions reached`). |
| **Max Daily Loss** | Closed net losses today reach `max_daily_loss_pct` | Blocks all new trades until UTC midnight (`daily loss limit reached`). |
| **Deduplication** | Alert ID already processed | Rejects duplicate alert within 24 hours (`duplicate alert_id`). |
| **Stale Price Deviation** | Alert price differs from current market by > 50 points | Rejects stale alert to avoid bad fills (`price deviation exceeds max`). |
| **Secret Masking** | Logs and UI responses | Webhook secret and passwords are redacted (`***REDACTED***`). |

---

## Daily Use

> *"After setup, you only press BUY on TradingView. Nothing else is needed."*

Once the bridge is active:
1. Open TradingView on your laptop, tablet, or phone.
2. When your setup appears, click **BUY** or **SELL** on the chart panel (or let your Pine Script alert fire).
3. The order executes instantly in MT5 demo with exact calculated lot sizing, stop loss, and take profit.
4. Monitor active positions and logs from the TradeBridge Dashboard (`http://<SERVER_IP>:8000/dashboard`).

---

## Troubleshooting & Common Errors

| Symptom / Error | Root Cause | Solution |
| :--- | :--- | :--- |
| `IPC initialize failed, MetaTrader 5 x64 not found` | MT5 terminal is not open or not installed in standard 64-bit directory. | Launch MT5 desktop manually and log in before starting TradeBridge. |
| `400 Bad Request: invalid secret` | Secret in TradingView alert does not match `WEBHOOK_SECRET` in `.env`. | Re-copy secret token from `.env` into TradingView alert / extension popup. |
| `400 Bad Request: duplicate alert_id` | Same alert payload was received more than once. | Verify your indicator generates a unique `alert_id` (e.g. `time + counter`). |
| `400 Bad Request: kill switch active` | Kill switch is engaged in the dashboard. | Open dashboard (`/dashboard`) and toggle Kill Switch OFF. |
| `Stale alert rejected: price deviation exceeds max` | Market moved significantly before webhook was delivered. | Normal protection against delayed webhooks. Tighten entry deviation if needed. |
| `400 Bad Request: BUY requires sl < entry < tp` | Invalid stop loss or take profit price levels. | Verify chart price levels: BUY requires SL below entry and TP above entry. |
| `daily loss limit reached` | Account hit the maximum daily loss threshold for today. | Safety system working as intended. TradeBridge unlocks automatically at UTC midnight. |

---

## Roman Urdu Quick-Start (Roman Urdu Mein Rehnumai)

TradeBridge ko shuru karne ke asan tareen 4 marhalay:

1. **Setup aur Login**:
   - Apne computer ya VPS par Python 3.11 aur MetaTrader 5 install karein.
   - MT5 mein demo account login karein aur **Tools → Options → Expert Advisors** mein ja kar **"Allow algorithmic trading"** ko tick (ON) karein.
2. **Server Chalayein**:
   - `start_tradebridge.bat` ko double click karke chalayein.
   - Browser mein `http://127.0.0.1:8000/health` check karein; wahan `mt5_connected: true` nazar aana chahiye.
3. **TradingView aur Extension**:
   - Chrome extension load karein (`tradebridge/extension` folder ko `chrome://extensions` par developer mode mein "Load unpacked" karein).
   - Popup mein apna webhook secret aur URL daal kar Save karein.
4. **Trading Shuru Karein**:
   - TradingView chart kholein. Neeche dayen taraf **⚡ TradeBridge** ka panel aa jayega.
   - Sirf **BUY** ya **SELL** dabayein — trade foran MT5 demo account mein sahi lot size, SL, aur TP ke sath execute ho jayegi. Kisi aur cheez ko chherne ki zaroorat nahi hai.

---

## Stretch Goals (Future Roadmap)

*(Planned architectural extensions — listed for roadmap tracking only; not implemented in core bridge)*:

1. **MQL5 EA Alternative Executor**:
   - A native MQL5 Expert Advisor reading orders from local named pipes or sockets for environments where the Python MetaTrader5 package is restricted.
2. **Partial Close & Break-Even Automation**:
   - Dashboard buttons to automatically move Stop Loss to breakeven (`entry + 1 pip`) or close 50% of the position when RR 1:1 is hit.
3. **Telegram / Discord Execution Bot**:
   - Instant push notifications sent to a private Telegram channel with fill receipts, ticket numbers, slippage stats, or rejection warnings.
4. **Pending Limit & Stop Orders**:
   - Support for `BUY_LIMIT`, `SELL_LIMIT`, `BUY_STOP`, and `SELL_STOP` when the user's alert entry price is placed away from current market ask/bid.
