# Lightning Trader v0.3 — Multi Algorithm Cockpit

## Архитектура

Приложение перестроено под мульти-алгоритмический режим с единым Cockpit и отдельным Algorithm Manager.

### Вкладки GUI
- **Cockpit**: SYMBOL, PRICE, BID/ASK, SPREAD, WS/API/LATENCY, MARKET STATE, SELECTED ALGO, ALGO STATUS, DECISION, POSITION, PNL, RISK.
- **Algorithms**: список алгоритмов, управление активным алгоритмом (select/enable/start/stop).
- **App Settings**: глобальные настройки приложения.
- **Algorithm Settings**: редактируемые поля настроек выбранного алгоритма.
- **Safety Settings**: DRY-RUN default, LIVE LOCKED, single active algo.

### Algorithm Manager
Поддерживаемые стратегии:
- Lightning Trader BTCUSDT
- Basic Scalper
- Adaptive Grid
- Martingale Scalper placeholder
- Empty Strategy Template

Для каждой стратегии доступны поля:
`name`, `version`, `status`, `description`, `risk_profile`, `enabled`, `compatible_symbols`, `settings_schema`.

### Структура папок
- `strategies/` — базовый интерфейс и стратегии
- `config/` — `app_settings.json`, `strategy_settings.json`
- `journals/` — журнал сделок
- `logs/` — технические логи

## Запуск
```bash
python3 pair_info_card.py
```

## Тесты
```bash
python3 -m pytest -q
```
