"""A janela do SubDrive: menu à esquerda (Legendas, Pendrive, Atualizações) e a tela escolhida à direita."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMainWindow, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from subdrive import VERSION

from . import icones, tema
from .componentes import grow, hbox, label, status_icon
from .dialogos import Corrigir, CriarPGS, Regras, Sincronizar
from .tela_ajuda import TelaAjuda
from .tela_atualizar import TelaAtualizar
from .tela_legendas import TelaLegendas
from .tela_pendrive import Monitor, TelaPendrive
from .tema import C

PAGES = [("legendas", "Legendas"), ("pendrive", "Pendrive"), ("atualizar", "Atualizações"), ("ajuda", "Ajuda")]


class Toast(QFrame):
    """Aviso curto que aparece embaixo e some sozinho."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("card")
        self.box = QHBoxLayout(self); self.box.setContentsMargins(16, 12, 18, 12); self.box.setSpacing(10)
        self.icon = QLabel(); self.text = label("", wrap=True); self.text.setMaximumWidth(560)
        self.box.addWidget(self.icon); self.box.addWidget(self.text, 1)
        self.effect = QGraphicsOpacityEffect(self); self.setGraphicsEffect(self.effect)
        self.anim = QPropertyAnimation(self.effect, b"opacity", self); self.anim.setDuration(180)
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.timeout.connect(self.fade)
        self.hide()

    def show_text(self, text, tone="info"):
        self.icon.setPixmap(status_icon(tone, 20).pixmap())
        self.text.setText(text)
        self.setStyleSheet("#card{background:%s;border:1px solid %s;border-radius:12px;}" % (C["surface"], C["strong"]))
        self.adjustSize()
        self.place()
        self.show(); self.raise_()
        self.anim.stop(); self.anim.setStartValue(0.0); self.anim.setEndValue(1.0); self.anim.start()
        self.timer.start(max(4000, 60 * len(text)))

    def place(self):
        p = self.parentWidget()
        self.adjustSize()
        self.move((p.width() - self.width()) // 2 + 110, p.height() - self.height() - 28)

    def fade(self):
        self.anim.stop(); self.anim.setStartValue(1.0); self.anim.setEndValue(0.0); self.anim.start()
        QTimer.singleShot(200, self.hide)

    def mousePressEvent(self, _):
        self.fade()


class DropCover(QFrame):
    """O aviso grande enquanto um arquivo é arrastado por cima da janela."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        box = QVBoxLayout(self); box.setAlignment(Qt.AlignCenter); box.setSpacing(10)
        self.ic = QLabel(); self.ic.setAlignment(Qt.AlignCenter)
        self.title = label("Solte para verificar", "big", wrap=False); self.title.setAlignment(Qt.AlignCenter)
        self.sub = label("Legendas .srt ou .sup, ou uma pasta com legendas", "muted", wrap=False); self.sub.setAlignment(Qt.AlignCenter)
        box.addWidget(self.ic); box.addWidget(self.title); box.addWidget(self.sub)
        self.hide()

    def appear(self):
        self.ic.setPixmap(icones.pixmap("soltar", C["accent"], 56, 1.6))
        self.setStyleSheet("DropCover{background:%s;border:3px dashed %s;border-radius:18px;}" % (C["accent_bg"], C["accent"]))
        self.setGeometry(self.parentWidget().rect().adjusted(16, 16, -16, -16))
        self.show(); self.raise_()


class Janela(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SubDrive")
        self.resize(1080, 740)
        self.setMinimumSize(900, 620)
        self.setAcceptDrops(True)
        self.build()
        self.setFocusPolicy(Qt.StrongFocus)  # o foco começa na janela; o anel aparece só ao usar Tab
        QTimer.singleShot(0, self.setFocus)
        self.monitor = Monitor(self._drives)
        self.monitor.poll()
        for k in range(len(PAGES)):
            QShortcut(QKeySequence("Ctrl+%d" % (k + 1)), self, activated=lambda k=k: self.go(k))
        QShortcut(QKeySequence.Open, self, activated=lambda: (self.go(0), self.legendas.pick_files()))
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.legendas.back)

    def build(self):
        central = QWidget(); central.setObjectName("content")
        row = QHBoxLayout(central); row.setContentsMargins(0, 0, 0, 0); row.setSpacing(0)
        row.addWidget(self._sidebar())
        self.stack = QStackedWidget()
        self.legendas = TelaLegendas()
        self.pendrive = TelaPendrive()
        self.atualizar = TelaAtualizar()
        self.ajuda = TelaAjuda()
        for page in (self.legendas, self.pendrive, self.atualizar, self.ajuda):
            self.stack.addWidget(page)
        row.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.toast = Toast(central)
        self.cover = DropCover(central)
        self.legendas.open_fix.connect(lambda e: self._dialog(Corrigir(self, e)))
        self.legendas.open_pgs.connect(lambda e: self._dialog(CriarPGS(self, e)))
        self.legendas.open_sync.connect(lambda e, p: self._dialog(Sincronizar(self, e, p)))
        self.legendas.show_rules.connect(lambda: Regras(self).exec())
        self.legendas.toast.connect(self.toast.show_text)
        self.legendas.look_for_drives.connect(lambda: self.monitor.poll())
        self.pendrive.toast.connect(self.toast.show_text)
        self.pendrive.prepared.connect(self.legendas.refresh)
        self.atualizar.go_drive.connect(lambda: self.go(1))
        self.go(0)

    def _sidebar(self):
        side = QFrame(); side.setObjectName("sidebar"); side.setFixedWidth(224)
        box = QVBoxLayout(side); box.setContentsMargins(16, 22, 16, 18); box.setSpacing(4)
        logo = QLabel(); logo.setPixmap(icones.logo(34))
        brand = QLabel("SubDrive"); brand.setObjectName("brand")
        box.addLayout(hbox(logo, brand, None, spacing=10, margins=(6, 0, 0, 0)))
        box.addSpacing(22)
        self.nav = QButtonGroup(self); self.nav.setExclusive(True)
        self.nav_buttons = []
        for k, (icon_name, text) in enumerate(PAGES):
            b = QPushButton("  " + text); b.setObjectName("navButton"); b.setCheckable(True); b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.TabFocus)
            b.setIconSize(QSize(20, 20))
            b.setToolTip("%s  (Ctrl+%d)" % (text, k + 1))
            b.clicked.connect(lambda _=False, k=k: self.go(k))
            self.nav.addButton(b, k); self.nav_buttons.append((b, icon_name))
            box.addWidget(b)
        box.addStretch(1)
        self.drive_box = QPushButton(); self.drive_box.setObjectName("driveBox"); self.drive_box.setCursor(Qt.PointingHandCursor)
        self.drive_box.setToolTip("Ver os pendrives")
        self.drive_box.clicked.connect(lambda: self.go(1))
        self.drive_state = QVBoxLayout(self.drive_box); self.drive_state.setSpacing(6); self.drive_state.setContentsMargins(10, 8, 10, 8)
        box.addWidget(self.drive_box)
        box.addSpacing(10)
        foot = QLabel("Versão " + VERSION); foot.setObjectName("sideFoot")
        box.addWidget(foot)
        self._drive_summary(None)
        return side

    def _paint_nav(self):
        for k, (b, icon_name) in enumerate(self.nav_buttons):
            b.setIcon(icones.icon(icon_name, C["accent"] if b.isChecked() else C["muted"], 20))

    def go(self, k):
        self.stack.setCurrentIndex(k)
        self.nav.button(k).setChecked(True)
        self._paint_nav()

    def _drives(self, found):
        self.legendas.set_drives(found)
        self.pendrive.set_drives(found)
        self._drive_summary(found)

    def _drive_summary(self, found):
        from .componentes import clear
        clear(self.drive_state)
        if found is None:
            self.drive_box.setFixedHeight(0)
            return
        if not found:
            self.drive_state.addLayout(hbox(status_icon("info", 16), grow(label("Nenhum pendrive", "faint")), spacing=8))
        for d in found[:3]:
            name = (d.label or str(d.path)).strip()
            text = label("%s · %s" % (name, "pronto" if d.ok else "precisa formatar" if any(p != "readonly" for p in d.problems)
                                      else "protegido contra gravação"), "faint")
            self.drive_state.addLayout(hbox(status_icon("ok" if d.ok else "fail", 16), grow(text), spacing=8))
        n = max(1, min(3, len(found)))
        self.drive_box.setFixedHeight(16 + n * 22 + (n - 1) * 6)

    def _dialog(self, dlg):
        dlg.created.connect(self.legendas.added_file)
        dlg.open_file.connect(lambda p: (self.go(0), self.legendas.add_paths([p])))
        dlg.exec()

    # ------------------------------------------------------------ arrastar e soltar / abrir com
    def open_paths(self, paths):
        paths = [Path(p) for p in paths]
        if paths:
            self.go(0)
            self.legendas.add_paths(paths)

    def _urls(self, e):
        md = e.mimeData()
        if not md.hasUrls():
            return []
        return [Path(u.toLocalFile()) for u in md.urls() if u.isLocalFile()]

    def dragEnterEvent(self, e):
        if self._urls(e):
            e.acceptProposedAction()
            self.cover.appear()

    def dragMoveEvent(self, e):
        e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self.cover.hide()

    def dropEvent(self, e):
        self.cover.hide()
        paths = self._urls(e)
        if paths:
            e.acceptProposedAction()
            self.open_paths(paths)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.toast.isVisible():
            self.toast.place()
        if self.cover.isVisible():
            self.cover.appear()

    def retheme(self):
        """O sistema trocou entre claro e escuro: as cores e os ícones são refeitos."""
        icones._cache.clear()
        state = (self.stack.currentIndex(), self.legendas.added, self.legendas.by_path, self.pendrive.pkg, self.monitor.found)
        old = self.centralWidget()
        self.build()
        old.deleteLater()
        k, added, by_path, pkg, found = state
        self.legendas.added, self.legendas.by_path = added, by_path
        if pkg is not None:
            self.pendrive.pkg, self.pendrive.pkg_folder, self.pendrive.pkg_error = pkg, pkg.folder, None
        self._drives(found)
        self.go(k)
