"""Abre a janela do SubDrive."""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from subdrive import pgs

from . import acoes, icones, lugares, tema
from .textos import t


class App(QApplication):
    """No macOS, arquivos soltos sobre o ícone do SubDrive chegam como um evento, não como argumento."""
    def __init__(self, argv):
        super().__init__(argv)
        self.window = None
        self.pending = []

    def event(self, e):
        if e.type() == QEvent.FileOpen:
            path = e.file()
            if path:
                if self.window is not None:
                    self.window.open_paths([path])
                else:
                    self.pending.append(path)
            return True
        return super().event(e)


def _files(argv):
    return [a for a in argv if not a.startswith("-") and Path(a).exists()]


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    if len(argv) >= 3 and argv[1] == "--autoteste":
        from . import autoteste
        return autoteste.run(Path(argv[2]))
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SubDrive.SubDrive")
        except Exception:
            pass
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = App(argv)
    app.setApplicationName("SubDrive")
    app.setApplicationDisplayName("SubDrive")
    app.setStyle("Fusion")
    tema.load_fonts(pgs.FONT_DIR)
    tema.apply(app)
    app.setWindowIcon(icones.app_icon())

    def crash(kind, value, tb):
        traceback.print_exception(kind, value, tb)
        try:
            QMessageBox.critical(None, "SubDrive", t("crash", name=kind.__name__))
        except Exception:
            pass
    sys.excepthook = crash

    if lugares.inside_zip():
        QMessageBox.warning(None, t("inside_zip_title"), t("inside_zip"))
        return 1
    acoes.limpar_programa_antigo()

    from .janela import Janela
    win = Janela()
    app.window = win
    try:
        app.styleHints().colorSchemeChanged.connect(lambda *_: (tema.apply(app), win.retheme()))
    except Exception:
        pass
    win.show()
    if lugares.translocated():
        QMessageBox.information(win, t("translocated_title"), t("translocated"))
    win.open_paths(_files(argv[1:]) + app.pending)
    app.pending = []
    return app.exec()
