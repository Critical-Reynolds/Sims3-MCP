"""Connection to the running game: process handle + mailbox, re-attached on demand."""
from __future__ import annotations

import threading
from typing import Any

from .mailbox import Mailbox, MailboxError
from .process import Process, ProcessError, find_pid


class GameNotRunning(MailboxError):
    pass


class Game:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: Process | None = None
        self._box: Mailbox | None = None

    def _attach(self) -> Mailbox:
        if self._proc is not None and not self._proc.alive():
            self._proc.close()
            self._proc = self._box = None
        if self._proc is None:
            pid = find_pid()
            if pid is None:
                raise GameNotRunning("The Sims 3 (TS3.exe) is not running.")
            self._proc = Process(pid)
            self._box = Mailbox(self._proc)
        assert self._box is not None
        return self._box

    def call(self, cmd: str, args: dict[str, Any] | None = None, timeout: float = 15.0) -> Any:
        with self._lock:
            box = self._attach()
        try:
            return box.call(cmd, args, timeout=timeout)
        except ProcessError as e:
            with self._lock:  # process likely exited; force a fresh attach next time
                if self._proc is not None:
                    self._proc.close()
                self._proc = self._box = None
            raise GameNotRunning(f"lost connection to the game: {e}") from e

    def status(self) -> dict[str, Any]:
        pid = find_pid()
        info: dict[str, Any] = {"game_running": pid is not None, "pid": pid}
        if pid is None:
            return info
        try:
            with self._lock:
                box = self._attach()
                if box.addr is None:
                    box.locate()
            info["mailbox"] = f"0x{box.addr:08X}"
            h = box._valid()
            info["world_loaded"] = bool(h and h.state == 1)
        except MailboxError as e:
            info["mailbox"] = None
            info["error"] = str(e)
        return info
