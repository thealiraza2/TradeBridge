# TradeBridge — Pre-Flight Checklist (Phase 0)

Fill this in from YOUR machine before running anything. Nothing below is
verified until you check it yourself — do not copy values from an example.

| Item | Value / Status |
| :--- | :--- |
| **Python Version** | _run `python --version` — needs 3.11 or higher_ |
| **MT5 Demo Account** | Login: _your login_ / Server: _exact server name from MT5_ |
| **MT5 Exact Symbols** | _from MT5 Market Watch, e.g. `XAUUSD`, `XAUUSD.m` — suffixes matter_ |
| **Algorithmic Trading Enabled** | _Tools → Options → Expert Advisors → "Allow algorithmic trading" ON_ |
| **TradingView Plan** | _webhook alerts need a paid plan (Essential/Plus/Premium)_ |
| **Webhook Secret** | _generated with `python -c "import secrets; print(secrets.token_hex(32))"` — stored ONLY in `.env`, never in git_ |
| **Deployment Machine** | _Windows laptop (must stay on) or Windows VPS (recommended, 24/7)_ |

## How to verify each item

1. **Python**: `python --version` → must print 3.11.x or higher.
2. **MT5**: install the MT5 **desktop** terminal (not the web terminal — the
   Python package needs the desktop terminal on the same machine), log in
   to a demo account, and check the exact symbol names in Market Watch.
3. **Algo trading**: MT5 → Tools → Options → Expert Advisors → tick
   "Allow algorithmic trading".
4. **Secret**: generate it, put it in `.env` (copy `.env.example` first),
   and paste the SAME secret into the TradingView alert and the Chrome
   extension popup.
5. **First real proof**: start the server, send one test alert, and find
   the ticket in MT5 → Toolbox → History. A ticket number in MT5 History
   is the only proof a trade happened — a test log line is not.
