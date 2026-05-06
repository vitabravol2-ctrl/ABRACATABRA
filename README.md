# Lightning Trader BTCUSDT v0.2 — GUI Cockpit

Обновлённый интерфейс переведён на компактный cockpit-формат (ttk) без изменения логики мозгов алгоритма.

## Что сделано

### 1) Главная вкладка: **BTCUSDT Cockpit**
- Верхняя панель статуса:
  - `SYMBOL`, `PRICE`, `MODE`, `ALGO`, `WS`, `API`, `LATENCY ms`
- Авиационные индикаторы:
  - `Market State`, `Decision`, `Risk Level`, `Spread`, `Data Health`, `Position`, `Profit`
- Центральная панель больших значений:
  - `Price`, `Bid`, `Ask`, `Spread bps`, `24h %`, `Volume`, `Current Position`, `uPnL`, `rPnL Today`
- Decision Panel:
  - `Decision`, `Reason`, `Text`
- Нижняя панель управления:
  - `CONNECT`, `START`, `PAUSE`, `STOP`, `DRY-RUN`, `LIVE LOCKED`

### 2) Вкладка **Logs**
- Раздельные окна для:
  - Decision log
  - Error log
  - Orders log
- Auto-scroll
- Кнопка `Save Log`
- Ограничение вывода последних записей для снижения спама

### 3) Вкладка **Settings**
Оформлена группами:
- Market
- Risk
- Entry
- Exit
- Safety

### 4) Технические изменения
- GUI работает на `tkinter.ttk` и больше не использует огромный `Text` как основной экран.
- Все данные экрана обновляются через единый цикл `update_snapshot()`.
- Логика алгоритмов `MarketBrain/RiskBrain/EntryBrain/ExitBrain/OrderBrain` сохранена.
- Режим `DRY-RUN` оставлен по умолчанию.
- `LIVE LOCKED` остаётся заблокированным и показывает предупреждение.

## Запуск
```bash
./run_pair_info.sh
```
или напрямую:
```bash
python3 pair_info_card.py
```

## Тесты
```bash
python3 -m pytest -q
```
