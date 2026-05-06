# Lightning Trader v0.3 GUI Principles

## Runtime model
GUI consumes one runtime state snapshot (`PairState`) and refreshes visual components from it.
GUI only sends control commands; trading operations are performed by `LightningTraderEngine`.

## Safety model
- LIVE mode is locked and visible constantly.
- Dangerous actions (Emergency Stop, Cancel All) require confirmation.
- When data is stale or market is danger, decision falls back to WAIT.
- Emergency stop is always accessible from cockpit control panel.

## Visual philosophy
- Dark, compact cockpit-style panel composition.
- Large status values and small reason-code hints.
- Stable card sizes to reduce UI jumping.
- Logs are concentrated in event console and Logs tab.

## Data flow
GUI -> Runtime State -> Strategy/Engine -> Orders/Dry-run adapter.
No direct exchange calls from strategy layer.
