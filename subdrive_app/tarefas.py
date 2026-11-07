"""Trabalho demorado (verificar, desenhar PGS, baixar, copiar) fora da janela, para ela nunca travar.

O trabalho roda numa thread; o resultado volta sempre para a thread da janela antes de chamar quem pediu.
"""
from __future__ import annotations

import threading
import time
import traceback

from PySide6.QtCore import QObject, Qt, Signal

_alive = set()


class Tarefa(QObject):
    progress = Signal(int, int)
    done = Signal(object)
    failed = Signal(object)
    _p = Signal(int, int)
    _d = Signal(object)
    _f = Signal(object)

    def __init__(self, fn, *args, with_progress=False, **kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs, self.with_progress = fn, args, kwargs, with_progress
        self._last = 0.0
        self._p.connect(self._on_progress, Qt.QueuedConnection)
        self._d.connect(self._on_done, Qt.QueuedConnection)
        self._f.connect(self._on_failed, Qt.QueuedConnection)

    def _progress(self, done, total):
        now = time.monotonic()
        if done >= total or now - self._last > 0.05:
            self._last = now
            self._p.emit(int(done), int(total))

    def _run(self):
        try:
            if self.with_progress:
                result = self.fn(*self.args, progress=self._progress, **self.kwargs)
            else:
                result = self.fn(*self.args, **self.kwargs)
        except Exception as e:  # a janela mostra a frase (Falha) ou um aviso genérico
            if not hasattr(e, "message"):
                traceback.print_exc()
            self._f.emit(e)
        else:
            self._d.emit(result)

    def _on_progress(self, d, t):
        self.progress.emit(d, t)

    def _on_done(self, result):
        _alive.discard(self)
        self.done.emit(result)

    def _on_failed(self, err):
        _alive.discard(self)
        self.failed.emit(err)

    def start(self):
        _alive.add(self)
        threading.Thread(target=self._run, daemon=True).start()
        return self


def rodar(fn, *args, done=None, failed=None, progress=None, **kwargs) -> Tarefa:
    """Roda fn(*args) em segundo plano; done/failed/progress são chamados na janela."""
    task = Tarefa(fn, *args, with_progress=progress is not None, **kwargs)
    if done:
        task.done.connect(done)
    if failed:
        task.failed.connect(failed)
    if progress:
        task.progress.connect(progress)
    return task.start()
