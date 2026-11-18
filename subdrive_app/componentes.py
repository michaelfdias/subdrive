"""Peças da janela: cartões, avisos, listas que abrem, botões e a chave liga/desliga."""
from __future__ import annotations

import math
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, QTimer, QUrl, Property, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
                               QVBoxLayout, QWidget)

from . import icones
from .tema import C


def polish(w):
    w.style().unpolish(w); w.style().polish(w)


def label(text="", role=None, tone=None, wrap=True, selectable=False, rich=False):
    lab = QLabel(text)
    if role:
        lab.setProperty("role", role)
    if tone:
        lab.setProperty("tone", tone)
    lab.setWordWrap(wrap)
    lab.setTextFormat(Qt.RichText if rich else Qt.PlainText)
    if rich:
        lab.setOpenExternalLinks(True)
    if selectable:
        lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lab


def button(text, kind=None, icon=None, tip=None, slot=None, icon_color=None):
    b = QPushButton(text)
    if kind:
        b.setProperty("kind", kind)
    if icon:
        color = icon_color or (C["on_accent"] if kind == "primary" else C["accent"] if kind == "ghost" else C["text"])
        b.setIcon(icones.icon(icon, color, 18))
        b.setIconSize(QSize(18, 18))
    if tip:
        b.setToolTip(tip)
        b.setAccessibleName(tip)
    b.setCursor(Qt.PointingHandCursor)
    if slot:
        b.clicked.connect(slot)
    return b


def icon_button(name, tip, slot=None, color=None):
    b = button("", "icon", tip=tip, slot=slot)
    b.setIcon(icones.icon(name, color or C["muted"], 20))
    b.setIconSize(QSize(20, 20))
    return b


TONE_ICON = {"ok": "ok", "fail": "fail", "warn": "warn", "info": "info", "fix": "corrigir", "accent": "info"}


def tone_color(tone):
    return {"ok": C["ok"], "fail": C["fail"], "warn": C["warn"], "info": C["info"], "fix": C["accent"], "accent": C["accent"]}.get(tone, C["muted"])


def status_icon(tone, size=20):
    lab = QLabel()
    lab.setPixmap(icones.pixmap(TONE_ICON.get(tone, "info"), tone_color(tone), size, 2))
    lab.setFixedSize(size, size)
    lab.setAlignment(Qt.AlignTop)
    return lab


class Card(QFrame):
    def __init__(self, tone=None, margins=(20, 18, 20, 18), spacing=10, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        if tone:
            self.setProperty("tone", tone)
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(*margins)
        self.box.setSpacing(spacing)

    def add(self, w, stretch=0):
        if isinstance(w, QWidget):
            self.box.addWidget(w, stretch)
        else:
            self.box.addLayout(w, stretch)
        return w


def line_with_icon(tone, text, role=None, size=18, rich=False):
    """Ícone de situação + frase que quebra linha."""
    row = QHBoxLayout()
    row.setSpacing(10)
    ic = status_icon(tone, size)
    row.addWidget(ic, 0, Qt.AlignTop)
    lab = label(text, role=role, rich=rich)
    lab.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    row.addWidget(lab, 1)
    return row, lab


class Banner(Card):
    """Aviso colorido: ícone, título opcional, texto e botões."""
    def __init__(self, tone, text, title=None, buttons=(), parent=None):
        super().__init__(tone=tone, margins=(16, 14, 16, 14), spacing=8, parent=parent)
        top = QHBoxLayout(); top.setSpacing(12)
        top.addWidget(status_icon(tone, 20), 0, Qt.AlignTop)
        col = QVBoxLayout(); col.setSpacing(4)
        if title:
            col.addWidget(label(title, role="h2"))
        self.text = label(text)
        col.addWidget(self.text)
        top.addLayout(col, 1)
        self.box.addLayout(top)
        if buttons:
            row = QHBoxLayout(); row.addSpacing(32)
            for b in buttons:
                row.addWidget(b)
            row.addStretch(1)
            self.box.addLayout(row)


def separator():
    f = QFrame(); f.setObjectName("sep"); f.setFrameShape(QFrame.NoFrame)
    return f


class Expander(QWidget):
    """Um botão "Ver…" que mostra ou esconde o que está embaixo."""
    def __init__(self, closed_text, open_text, content: QWidget, parent=None):
        super().__init__(parent)
        self.closed_text, self.open_text, self.content = closed_text, open_text, content
        box = QVBoxLayout(self); box.setContentsMargins(0, 0, 0, 0); box.setSpacing(6)
        self.toggle = button(closed_text, "ghost", icon="down", slot=self.flip)
        self.toggle.setLayoutDirection(Qt.RightToLeft)
        row = QHBoxLayout(); row.setContentsMargins(0, 0, 0, 0); row.addWidget(self.toggle); row.addStretch(1)
        box.addLayout(row)
        box.addWidget(content)
        content.setVisible(False)

    def flip(self):
        show = not self.content.isVisible()
        self.content.setVisible(show)
        self.toggle.setText(self.open_text if show else self.closed_text)
        self.toggle.setIcon(icones.icon("up" if show else "down", C["accent"], 18))


def spots_view(spots, limit=300):
    """As falas onde algo aparece: horário + texto (e o depois, para mudanças)."""
    w = QFrame()
    w.setObjectName("card")
    w.setProperty("tone", None)
    box = QVBoxLayout(w); box.setContentsMargins(14, 10, 14, 10); box.setSpacing(6)
    for where, text, after in spots[:limit]:
        row = QHBoxLayout(); row.setSpacing(12)
        wl = label(where, role="mono", wrap=False); wl.setMinimumWidth(92); wl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        row.addWidget(wl, 0, Qt.AlignTop)
        col = QVBoxLayout(); col.setSpacing(2)
        if after:
            before = label("− " + (text or ""), selectable=True); before.setStyleSheet("color:%s" % C["fail"])
            now = label("+ " + after, selectable=True); now.setStyleSheet("color:%s" % C["ok"])
            col.addWidget(before); col.addWidget(now)
        else:
            col.addWidget(label(text or "", selectable=True))
        row.addLayout(col, 1)
        box.addLayout(row)
    if len(spots) > limit:
        box.addWidget(label("… e mais %d" % (len(spots) - limit), role="faint"))
    return w


def items_view(items, tone, open_label="Ver as falas", close_label="Esconder as falas"):
    """Lista de problemas ou mudanças; cada um pode abrir as falas onde aparece."""
    w = QWidget()
    box = QVBoxLayout(w); box.setContentsMargins(0, 0, 0, 0); box.setSpacing(10)
    for it in items:
        row, _ = line_with_icon(tone, it.text, size=16)
        box.addLayout(row)
        if it.spots:
            n = len(it.spots)
            ex = Expander("%s (%d)" % (open_label, n) if n > 1 else open_label, close_label, spots_view(it.spots))
            ex.layout().setContentsMargins(24, 0, 0, 0)
            box.addWidget(ex)
    return w


def scroll(widget):
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    sa.setWidget(widget)
    return sa


def clear(layout):
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.hide(); w.setParent(None); w.deleteLater()
        elif item.layout() is not None:
            clear(item.layout())


def show_in_folder(path: Path):
    """Abre a pasta do arquivo no gerenciador de arquivos do sistema (com o arquivo marcado quando dá)."""
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)])
            return
        if os.name == "nt":
            subprocess.Popen(["explorer", "/select,", str(path)])
            return
    except OSError:
        pass
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent if path.is_file() else path)))


def open_folder(folder: Path):
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


def open_url(url):
    QDesktopServices.openUrl(QUrl(url))


class Switch(QAbstractButton):
    """Chave liga/desliga."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(46, 26)
        self._pos = 0.0
        self.anim = QPropertyAnimation(self, b"pos", self)
        self.anim.setDuration(140)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    def _animate(self, on):
        self.anim.stop(); self.anim.setStartValue(self._pos); self.anim.setEndValue(1.0 if on else 0.0); self.anim.start()

    def setChecked(self, on):
        super().setChecked(on)
        self.anim.stop(); self._pos = 1.0 if on else 0.0; self.update()

    def get_pos(self):
        return self._pos

    def set_pos(self, v):
        self._pos = v; self.update()

    pos = Property(float, get_pos, set_pos)

    def sizeHint(self):
        return QSize(46, 26)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        off, on = QColor(C["strong"]), QColor(C["accent"])
        mix = QColor(int(off.red() + (on.red() - off.red()) * self._pos), int(off.green() + (on.green() - off.green()) * self._pos),
                     int(off.blue() + (on.blue() - off.blue()) * self._pos))
        p.setPen(Qt.NoPen); p.setBrush(mix)
        p.drawRoundedRect(QRectF(0, 0, 46, 26), 13, 13)
        p.setBrush(QColor("#ffffff"))
        x = 3 + self._pos * 20
        p.drawEllipse(QRectF(x, 3, 20, 20))
        if self.hasFocus():
            p.setPen(QPen(QColor(C["focus"]), 2)); p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(1, 1, 44, 24), 12, 12)


class Busy(QWidget):
    """Círculo girando, para quando não dá para saber quanto falta."""
    def __init__(self, size=22, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.angle = 0
        self.timer = QTimer(self); self.timer.timeout.connect(self._tick); self.timer.start(16)

    def _tick(self):
        self.angle = (self.angle + 6) % 360; self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(2.5, 2.5, self.width() - 5, self.height() - 5)
        p.setPen(QPen(QColor(C["line"]), 3)); p.drawEllipse(r)
        pen = QPen(QColor(C["accent"]), 3); pen.setCapStyle(Qt.RoundCap); p.setPen(pen)
        p.drawArc(r, int(-self.angle * 16), int(100 * 16))


class Pill(QFrame):
    """Selo de situação: ícone + texto (a cor nunca é a única pista)."""
    ICON = {"ok": "ok", "fail": "fail", "warn": "warn", "info": "info", "wait": None}

    def __init__(self, text, tone, parent=None):
        super().__init__(parent)
        self.setObjectName("pill")
        row = QHBoxLayout(self); row.setContentsMargins(9, 3, 11, 3); row.setSpacing(5)
        self.icon = QLabel(); self.text = QLabel()
        row.addWidget(self.icon); row.addWidget(self.text)
        self.set(text, tone)

    def set(self, text, tone):
        fg = {"ok": C["ok"], "fail": C["fail"], "warn": C["warn"], "wait": C["muted"], "info": C["info"]}.get(tone, C["muted"])
        bg = {"ok": C["ok_bg"], "fail": C["fail_bg"], "warn": C["warn_bg"], "wait": C["line"], "info": C["info_bg"]}.get(tone, C["bg"])
        name = self.ICON.get(tone)
        self.icon.setVisible(name is not None)
        if name:
            self.icon.setPixmap(icones.pixmap(name, fg, 15, 2.2))
        self.text.setText(text)
        self.text.setStyleSheet("color:%s;font-size:13px;font-weight:700;background:transparent;" % fg)
        self.setStyleSheet("#pill{background:%s;border-radius:12px;}" % bg)
        self.setAccessibleName(text)


class Clickable(QFrame):
    """Uma linha inteira que funciona como botão (mouse e teclado)."""
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("row")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit(); return
        super().keyPressEvent(e)

    def focusInEvent(self, e):
        self.setStyleSheet("#row{border:2px solid %s;}" % C["focus"]); super().focusInEvent(e)

    def focusOutEvent(self, e):
        self.setStyleSheet(""); super().focusOutEvent(e)


def grow(item):
    """Marca um item de hbox/vbox para ocupar o espaço que sobra."""
    return (item, 1)


def hbox(*items, spacing=10, margins=(0, 0, 0, 0)):
    row = QHBoxLayout(); row.setSpacing(spacing); row.setContentsMargins(*margins)
    for it in items:
        if isinstance(it, tuple):
            it, stretch = it
            if isinstance(it, QWidget):
                row.addWidget(it, stretch)
            else:
                row.addLayout(it, stretch)
        elif it is None:
            row.addStretch(1)
        elif isinstance(it, int):
            row.addSpacing(it)
        elif isinstance(it, QWidget):
            row.addWidget(it)
        else:
            row.addLayout(it)
    return row


def vbox(*items, spacing=10, margins=(0, 0, 0, 0)):
    col = QVBoxLayout(); col.setSpacing(spacing); col.setContentsMargins(*margins)
    for it in items:
        if it is None:
            col.addStretch(1)
        elif isinstance(it, int):
            col.addSpacing(it)
        elif isinstance(it, QWidget):
            col.addWidget(it)
        else:
            col.addLayout(it)
    return col
