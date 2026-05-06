# REPORT — Liquidity Grab Bot v0.1.1

## Что добавлено
- Расширен `MockFeed`: добавлены 5 сценариев для позитивной и негативной валидации FSM.
- `main.py` обновлён: добавлен CLI-аргумент `--scenario` с дефолтом `success_tp`.
- Добавлены unit-тесты для `MarketBuffer` и `LiquidityGrabDetector`.
- Добавлены scenario-тесты FSM, подтверждающие корректные входы/отказы/выходы.
- Добавлены скрипты запуска тестов: `scripts/test.bat` и `scripts/test.ps1`.
- README обновлён инструкциями по сценариям и тестам.

## Проверенные сценарии
- `success_tp`: ожидается 1 сделка, `exit_reason=TP`.
- `no_reclaim`: ожидается 0 сделок.
- `new_low_after_impulse`: ожидается 0 сделок.
- `spread_too_wide`: ожидается 0 сделок.
- `timeout_exit`: ожидается 1 сделка, `exit_reason=TIMEOUT`.

## Какие тесты проходят
- `tests/test_market_buffer.py`:
  - rolling high/low
  - drop_pct
  - spread_pct
  - stale detection
- `tests/test_detector.py`:
  - impulse true/false
  - bounce true/false
  - reclaim true/false
  - hold true/false
  - timeout true/false
- `tests/test_fsm_scenarios.py`:
  - success TP
  - no reclaim
  - new low reset
  - spread too wide
  - timeout exit

## Команды готовности
```bash
cd liquidity_grab_bot
python main.py --scenario success_tp
python main.py --scenario no_reclaim
python main.py --scenario timeout_exit
python -m unittest discover -s tests
```
