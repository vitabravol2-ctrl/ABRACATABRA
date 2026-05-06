# Liquidity Grab Bot v0.1.1 (FSM Tests & Scenario Validation)

Минимальное ядро FSM-алгоритма для симуляции паттерна liquidity grab (без live trading).

## Запуск сценариев

```bash
cd liquidity_grab_bot
python main.py --scenario success_tp
python main.py --scenario no_reclaim
python main.py --scenario timeout_exit
```

Поддерживаемые сценарии:
- `success_tp` (по умолчанию)
- `no_reclaim`
- `new_low_after_impulse`
- `spread_too_wide`
- `timeout_exit`

Если аргумент `--scenario` не указан, запускается `success_tp`.

Или через скрипты запуска:
- `scripts/run.bat`
- `scripts/run.ps1`

## Запуск тестов

```bash
cd liquidity_grab_bot
python -m unittest discover -s tests
```

Windows-скрипты:
- `scripts/test.bat`
- `scripts/test.ps1`

## Обновление из Git

- `scripts/update_from_git.bat`
- `scripts/update_from_git.ps1`

⚠️ Внимание: update-скрипты выполняют `git reset --hard origin/main` и удаляют неотслеживаемые файлы.

Добавлена защита `.env`: файл сохраняется и восстанавливается после обновления.
