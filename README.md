# Lightning Trader BTCUSDT v0.1

Базовая архитектура умного алгоритма для Binance Spot BTCUSDT:
`MarketBrain → RiskBrain → EntryBrain → ExitBrain → OrderBrain`.

## Что добавлено
- Вкладка **Algorithms**:
  - алгоритм `Lightning Trader BTCUSDT`
  - состояния ENABLED / PAUSED / DISABLED
  - режим DRY-RUN по умолчанию, LIVE заблокирован (LIVE_LOCKED)
  - кнопки Start / Pause / Stop и кнопка LIVE с предупреждением
  - компактный decision-log по шагам
- Вкладка **Settings**:
  - группы Market / Risk / Entry / Exit с параметрами из ТЗ
- Карточка пары BTCUSDT:
  - price, bid, ask, spread, 24h change, volume, WS/API status, latency
  - USDT/BTC balance
  - algorithm status, current decision, reason
  - current position, unrealized/realized PnL
- Модули:
  - `MarketBrain`, `RiskBrain`, `EntryBrain`, `ExitBrain`, `OrderBrain`, `TradeJournal`
- Reason-codes:
  - `MARKET_OK`, `MARKET_DANGER`, `DATA_STALE`, `SPREAD_TOO_SMALL`, `EDGE_TOO_SMALL`,
    `BALANCE_LOW`, `RISK_LIMIT`, `ENTRY_READY`, `ENTRY_CANCELLED`, `BUY_FILLED`,
    `SELL_PLACED`, `TAKE_PROFIT_READY`, `EMERGENCY_EXIT`, `TRAILING_ACTIVE`,
    `POSITION_CLOSED`, `WAIT`
- Безопасность:
  - только DRY-RUN по умолчанию
  - LIVE автоматически не включается
  - предупреждение перед LIVE
  - обработка ошибок API без падения GUI
  - stop останавливает логику и очищает активный ордер
  - защита от duplicate order
  - журнал решений в JSON + CSV

## Запуск
```bash
./run_pair_info.sh
```
или
```bash
python3 pair_info_card.py
```

## Тесты
```bash
python3 -m pytest -q
```

## Измененные файлы
- `pair_info_card.py`
- `tests/test_brains.py`
- `README.md`
