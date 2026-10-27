"""Manual KILL-file control."""

from __future__ import annotations

from pathlib import Path

from tradebot.risk.killswitch import KillLevel, KillSwitch


class KillFileController:
    def __init__(self, kill_switch: KillSwitch, path: str | Path = "KILL") -> None:
        self.kill_switch = kill_switch
        self.path = Path(path)

    def check(self) -> bool:
        if not self.path.is_file():
            return False
        reason = self.path.read_text(encoding="utf-8").strip() or "KILL file present"
        self.kill_switch.trigger(KillLevel.FLATTEN, reason)
        return True
