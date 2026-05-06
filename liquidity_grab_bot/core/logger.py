from datetime import datetime


class BotLogger:
    def log(self, state: str, event: str, message: str) -> None:
        ts = datetime.utcnow().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{ts}] [{state}] [{event}] {message}")
