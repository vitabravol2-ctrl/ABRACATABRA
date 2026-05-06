# REPORT — Liquidity Grab Bot v0.1.0

## Что сделано
- Создано базовое ядро проекта с разделением на `core`, `data`, `scripts`.
- Реализованы модели `Tick` и `Trade`.
- Реализован `MarketBuffer` с rolling high/low, drop %, spread %, stale-check.
- Реализован `LiquidityGrabDetector` для проверки импульса, bounce/reclaim/hold/timeout.
- Реализован `LiquidityGrabFSM` с полным циклом состояний:
  `INIT -> WAIT -> IMPULSE_DETECT -> POST_IMPULSE -> RECLAIM -> HOLD_CONFIRM -> ENTRY_READY -> IN_POSITION -> EXIT -> RESET -> WAIT`.
- Реализован `MockFeed`, генерирующий сценарий до выхода по TP.
- Реализованы bat/ps1 скрипты запуска и git update (с защитой `.env`).

## Что создано
- `main.py`, `config.py`
- `core/{fsm.py,models.py,detector.py,risk.py,logger.py,__init__.py}`
- `data/{market_buffer.py,mock_feed.py,__init__.py}`
- `scripts/{run.bat,run.ps1,update_from_git.bat,update_from_git.ps1}`
- `README.md`, `REPORT.md`

## Как запускать
1. `cd liquidity_grab_bot`
2. `python main.py`

## Что проверено
- FSM переходы печатаются в консоль.
- Обнаружение импульса работает.
- Проход через reclaim/hold.
- Создание виртуальной сделки.
- Выход по TP и расчёт `pnl_pct`.

## Следующие этапы
1. Добавить unit-тесты по состояниям FSM.
2. Подготовить абстракции адаптеров под live-feed.
3. Добавить риск-модуль позиционирования и параметризацию стратегий.
4. Добавить сохранение результатов в JSON/CSV.
