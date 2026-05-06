# Liquidity Grab Bot v0.1.0 (Core Kernel)

Минимальное ядро FSM-алгоритма для симуляции паттерна liquidity grab (без live trading).

## Запуск

```bash
cd liquidity_grab_bot
python main.py
```

Или через скрипты:
- `scripts/run.bat`
- `scripts/run.ps1`

## Обновление из Git

- `scripts/update_from_git.bat`
- `scripts/update_from_git.ps1`

⚠️ Внимание: update-скрипты выполняют `git reset --hard origin/main` и удаляют неотслеживаемые файлы.

Добавлена защита `.env`: файл сохраняется и восстанавливается после обновления.
