# Lightning Trader v0.3 GUI Structure

## Main tabs
- Cockpit
- Orders
- Position
- Algorithms
- Settings
- Logs

## Cockpit layout
1. Top Bar: SYMBOL, PRICE, BID, ASK, SPREAD, WS, API, LATENCY, MODE, CLOCK.
2. Left Control Panel: algorithm selector, strategy controls (Connect/Start/Pause/Stop), Dry-run toggle, LIVE LOCKED indicator, Emergency Stop.
3. Center Flight Instruments: Market State, Decision, Risk Level, Data Health, Position, Spread, Profit.
4. Right Trade Panel: current position fields, PnL, order status, command/fill info.
5. Bottom Event Console: last events in format `TIME | LEVEL | MODULE | CODE | MESSAGE`.

## Settings layout
Sub-tabs:
- App Settings
- Market Data Settings
- Trading Core Settings
- Safety Settings
- Selected Algorithm Settings
- API Settings

## Orders tab
Table columns:
order_id, symbol, side, type, price, qty, filled, status, age, source.
Actions:
Cancel selected, Cancel all, Refresh.
