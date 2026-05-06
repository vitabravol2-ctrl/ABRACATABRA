# REPORT — Lightning Trader v0.3 Multi Algorithm

## Что сделано
- GUI разделён на Cockpit + Algorithms + App Settings + Algorithm Settings + Safety Settings.
- Добавлен **Algorithm Manager** с выбором активного алгоритма.
- Введён базовый интерфейс `BaseStrategy` и пакет `strategies/` для масштабирования.
- Добавлены конфиги `config/app_settings.json` и `config/strategy_settings.json`.
- DRY-RUN по умолчанию сохранён, LIVE остаётся LOCKED.
- Одновременно подразумевается один активный алгоритм (selected_algo в состоянии Cockpit).

## Совместимость
- Базовые brain-классы (`MarketBrain`, `RiskBrain`, `EntryBrain`, `ExitBrain`) сохранены, тесты продолжают проходить.

## Multi Algorithm Architecture
1. **UI layer** (`PairInfoCardApp`) показывает рынок + состояние выбранной стратегии.
2. **Engine layer** (`LightningTraderEngine`) выполняет цикл принятия решения.
3. **Strategy layer** (`strategies/*.py`) содержит расширяемые стратегии через `BaseStrategy`.
4. **Config layer** (`config/*.json`) разделяет app-level и strategy-level конфигурацию.
5. **Persistence layer** (`journals/`, `logs/`) хранит журналы и логи.
