"""Janelas que abrem por cima: corrigir, criar PGS, aplicar a sincronia e o que é verificado."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageFont
from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractButton, QCheckBox, QComboBox, QDialog, QFileDialog, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QProgressBar, QSizePolicy, QSlider, QVBoxLayout, QWidget)

from subdrive import pgs

from . import acoes, icones, tarefas
from .componentes import (grow, Banner, Busy, Card, Expander, button, clear, hbox, items_view, label, line_with_icon, scroll,
                          show_in_folder, spots_view, status_icon, vbox)
from .tema import C
from .textos import number, rules, t


class Dialogo(QDialog):
    created = Signal(object)   # Path do arquivo novo
    open_file = Signal(object)

    def __init__(self, parent, title, width=620, height=560):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(width, height)
        self.busy = False
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        inner = QWidget(); inner.setObjectName("page")
        self.box = QVBoxLayout(inner); self.box.setContentsMargins(28, 24, 28, 12); self.box.setSpacing(14)
        head = label(title, "title"); head.setStyleSheet("font-size:22px;")
        self.head = head
        self.box_head = QVBoxLayout(); self.box_head.setSpacing(4); self.box_head.addWidget(head)
        self.box.addLayout(self.box_head)
        self.body = QVBoxLayout(); self.body.setSpacing(14)
        self.box.addLayout(self.body)
        self.box.addStretch(1)
        root.addWidget(scroll(inner), 1)
        foot = QWidget(); foot.setObjectName("page")
        self.foot = QHBoxLayout(foot); self.foot.setContentsMargins(28, 12, 28, 22); self.foot.setSpacing(10)
        root.addWidget(foot)
        self.inner, self.footw, self.max_h = inner, foot, height

    def fit(self):
        """A altura acompanha o conteúdo (sem sobra embaixo nem barra de rolagem à toa)."""
        h = self.inner.sizeHint().height() + self.footw.sizeHint().height() + 6
        self.resize(self.width(), max(240, min(self.max_h, h)))

    def lead(self, text, rich=False):
        lab = label(text, "lead", rich=rich)
        self.box_head.addWidget(lab)
        return lab

    def buttons(self, *items):
        clear(self.foot)
        self.foot.addStretch(1)
        for b in items:
            self.foot.addWidget(b)
        for b in reversed(items):
            if b.property("kind") == "primary":
                b.setDefault(True); b.setAutoDefault(True); b.setFocus()
                break
        QTimer.singleShot(0, self.fit)

    def reject(self):
        if not self.busy:
            super().reject()

    def closeEvent(self, e):
        if self.busy:
            e.ignore()
        else:
            super().closeEvent(e)

    def name_field(self, suggested, note="O arquivo novo fica na mesma pasta da legenda."):
        field = QLineEdit(suggested)
        field.setPlaceholderText(suggested)
        field.setAccessibleName("Nome do arquivo novo")
        col = vbox(label("Salvar como", "h2"), field, label(note, "faint"), spacing=6)
        return field, col

    def progress_row(self, text):
        bar = QProgressBar(); bar.setRange(0, 100); bar.setValue(0); bar.setTextVisible(False)
        lab = label(text, "muted")
        pct = label("0%", "faint", wrap=False)
        w = QWidget(); col = QVBoxLayout(w); col.setContentsMargins(0, 0, 0, 0); col.setSpacing(8)
        col.addLayout(hbox(lab, None, pct)); col.addWidget(bar)
        w.set = lambda d, total: (bar.setValue(int(100 * d / max(1, total))), pct.setText("%d%%" % (100 * d // max(1, total))))
        return w

    def success(self, title, lines=(), path=None, notes=()):
        """A tela final, quando deu certo: o nome do arquivo novo e o que fazer com ele."""
        clear(self.body)
        card = Card(tone="ok", spacing=8)
        card.add(hbox(status_icon("ok", 28), grow(label(title, "big")), spacing=12))
        for text in lines:
            lab = label(text, "muted"); lab.setContentsMargins(40, 0, 0, 0)
            card.add(lab)
        self.body.addWidget(card)
        for tone, text in notes:
            self.body.addWidget(Banner(tone, text))
        items = []
        if path is not None:
            items.append(button("Mostrar na pasta", icon="folder", slot=lambda: show_in_folder(path)))
            items.append(button("Ver se ficou pronta", slot=lambda: (self.open_file.emit(path), self.accept())))
        items.append(button("Concluir", "primary", slot=self.accept))
        self.buttons(*items)

    def failure(self, err):
        msg = getattr(err, "message", None) or "Algo deu errado (%s)." % type(err).__name__
        b = Banner("fail", msg)
        for d in getattr(err, "detail", []) or []:
            lab = label("• " + d, "muted"); lab.setContentsMargins(32, 0, 0, 0)
            b.box.addWidget(lab)
        return b


# ------------------------------------------------------------------ corrigir

class Corrigir(Dialogo):
    def __init__(self, parent, entry):
        super().__init__(parent, "Corrigir legenda", 660, 720)
        self.path = entry.path
        self.lead("Cria uma cópia corrigida de <b>%s</b>. O original fica como está." % _esc(self.path.name), rich=True)
        self.credit_list = []
        self.remove = None
        self.field = None
        # Já funciona e só tem falas de créditos: abrir para tirá-las é o motivo de estar aqui.
        self._removing = bool(entry.result is not None and entry.result.ok and entry.result.warnings)
        self._loading()
        tarefas.rodar(acoes.corrigir, self.path, None, self._removing, False, done=self._preview, failed=self._failed)

    def _loading(self):
        clear(self.body)
        self.body.addLayout(hbox(Busy(), grow(label("Vendo o que precisa ser ajustado…", "muted")), spacing=12))
        self.buttons(button("Cancelar", slot=self.reject))

    def _failed(self, err):
        self.busy = False
        clear(self.body)
        self.body.addWidget(self.failure(err))
        self.buttons(button("Fechar", "primary", slot=self.reject))

    def _preview(self, r):
        clear(self.body)
        if not r.ok:
            b = Banner("fail", t("cannot_fix"))
            self.body.addWidget(b)
            iv = items_view(r.remaining, "fail"); self.body.addWidget(iv)
            for tone, text in r.notes:
                self.body.addWidget(Banner(tone, text))
            self.buttons(button("Fechar", "primary", slot=self.reject))
            return
        credits = self.credit_list or r.credits
        if r.changes:
            self.body.addWidget(label("O que será ajustado", "h2"))
            self.body.addWidget(items_view(r.changes, "fix", "Ver antes e depois", "Esconder"))
        elif not credits:
            self.body.addWidget(Banner("ok", t("nothing_to_fix")))
            self.buttons(button("Fechar", "primary", slot=self.reject))
            return
        else:
            self.body.addWidget(Banner("ok", "A legenda já está pronta para o player."))
        if credits:
            self.credit_list = credits
            n = len(credits)
            text = ("Remover também a fala que parece crédito ou propaganda" if n == 1 else
                    "Remover também as %s falas que parecem créditos ou propaganda" % number(n))
            self.remove = QCheckBox(text)
            self.remove.setChecked(self._removing)
            self.remove.toggled.connect(self._toggle_credits)
            card = Card(tone="warn", spacing=8)
            card.add(self.remove)
            ex = Expander("Ver quais são", "Esconder", spots_view([(w, x, "") for w, x in credits]))
            card.add(ex)
            self.body.addWidget(card)
        for tone, text in r.notes:
            if "acentos foram convertidos" not in text:  # já está em "O que será ajustado"
                self.body.addWidget(Banner(tone, text))
        self.field, col = self.name_field(acoes.nome_sugerido(self.path))
        self.body.addLayout(col)
        save = button("Salvar cópia corrigida", "primary", slot=self._save)
        save.setEnabled(bool(r.changes))
        self.buttons(button("Cancelar", slot=self.reject), save)

    _removing = False

    def _toggle_credits(self, on):
        self._removing = on
        self._loading()
        tarefas.rodar(acoes.corrigir, self.path, None, on, False, done=self._preview, failed=self._failed)

    def _save(self):
        self.busy = True
        name = self.field.text().strip() if self.field else None
        clear(self.body)
        self.body.addLayout(hbox(Busy(), grow(label("Corrigindo e conferindo de novo…", "muted")), spacing=12))
        self.buttons()
        tarefas.rodar(acoes.corrigir, self.path, name, self._removing, True, done=self._saved, failed=self._failed)

    def _saved(self, r):
        self.busy = False
        if not r.ok or r.output is None:
            self._preview(r)
            return
        self.created.emit(r.output)
        self.success(t("fixed", name=r.output.name), [t("original_kept")], r.output, r.notes)


# ------------------------------------------------------------------ PGS

class Previa(QWidget):
    """Uma tela de TV 16:9 com a fala desenhada como no PGS (mesmo desenho, reduzido)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = None
        self.setMinimumSize(360, 203)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return int(w * 9 / 16)

    def sizeHint(self):
        return QSize(480, 270)

    def set_image(self, img):
        self.image = img
        self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing); p.setRenderHint(QPainter.SmoothPixmapTransform)
        w = self.width(); h = int(w * 9 / 16)
        if h > self.height():
            h = self.height(); w = int(h * 16 / 9)
        x0 = (self.width() - w) / 2
        rect = QRectF(x0, 0, w, h)
        path = QPainterPath(); path.addRoundedRect(rect, 10, 10)
        g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        g.setColorAt(0, QColor("#2b3340")); g.setColorAt(0.55, QColor("#3b3a36")); g.setColorAt(1, QColor("#14161a"))
        p.fillPath(path, g)
        p.setClipPath(path)
        if self.image is not None:
            p.drawImage(rect, self.image)
        p.setClipping(False)
        p.setPen(QPen(QColor(C["strong"]), 1)); p.setBrush(Qt.NoBrush); p.drawPath(path)


class _Desenho(pgs.Renderer):
    """O desenhista do PGS, sem ler a tabela de letras da fonte (só para a prévia, que precisa ser rápida)."""
    def __init__(self, style):
        regular, italic = style.files()
        engine = ImageFont.Layout.BASIC
        self.font = ImageFont.truetype(str(regular), style.size * pgs.SS, layout_engine=engine)
        self.italic = ImageFont.truetype(str(italic), style.size * pgs.SS, layout_engine=engine)
        self.style = style


def desenhar_previa(style, cue_lines):
    """A tela 1920×1080 com a fala posicionada como o PGS faz (centralizada, 64 px acima da borda)."""
    r = _Desenho(style)
    images = [im for im in (r.line(runs) for runs in cue_lines) if im is not None]
    canvas = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    y = 1080 - pgs.BOTTOM
    for im in reversed(images):
        y -= im.size[1]
        canvas.alpha_composite(im, ((1920 - im.size[0]) // 2, max(0, y)))
        y -= pgs.GAP
    data = canvas.tobytes("raw", "RGBA")
    return QImage(data, 1920, 1080, QImage.Format_RGBA8888).copy()


class Amostra(QAbstractButton):
    """Um quadradinho de cor."""
    def __init__(self, en, rgb, parent=None):
        super().__init__(parent)
        self.en, self.rgb = en, rgb
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setFixedSize(34, 34)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(acoes.cor_nome(en).capitalize())
        self.setAccessibleName(acoes.cor_nome(en))

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.35)
        r, g, b = self.rgb
        if self.isChecked() or self.hasFocus():
            p.setPen(QPen(QColor(C["accent"] if self.isChecked() else C["focus"]), 3)); p.setBrush(Qt.NoBrush)
            p.drawEllipse(QRectF(1.5, 1.5, 31, 31))
        p.setPen(QPen(QColor(0, 0, 0, 60), 1)); p.setBrush(QColor(r, g, b))
        p.drawEllipse(QRectF(6, 6, 22, 22))


PRESETS = [
    ("Clássico", "Branco suave, do jeito de sempre", dict(color="soft-white", font="roboto", bold=False, size=48, outline=2.0)),
    ("Amarelo", "Fácil de achar na tela, em negrito", dict(color="dark-yellow", font="roboto", bold=True, size=48, outline=2.0)),
    ("Para ler de longe", "Letra maior, com contorno mais forte", dict(color="white", font="atkinson", bold=True, size=60, outline=3.5)),
    ("Discreto", "Cinza claro e um pouco menor", dict(color="light-gray", font="sourcesans3", bold=False, size=42, outline=1.5)),
]


class Estilo(QAbstractButton):
    """Um estilo pronto: título + descrição, marcado quando está em uso."""
    def __init__(self, title, text, parent=None):
        super().__init__(parent)
        self.title, self.text_ = title, text
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(title + ": " + text)
        self.setMinimumHeight(54)

    def sizeHint(self):
        return QSize(300, 56)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        on = self.isChecked()
        p.setPen(QPen(QColor(C["accent"] if on else (C["focus"] if self.hasFocus() else C["line"])), 2 if on or self.hasFocus() else 1))
        p.setBrush(QColor(C["accent_bg"] if on else (C["hover"] if self.underMouse() else C["surface"])))
        p.drawRoundedRect(r, 10, 10)
        f = self.font(); f.setPixelSize(15); f.setBold(True); p.setFont(f); p.setPen(QColor(C["text"] if self.isEnabled() else C["faint"]))
        p.drawText(QRectF(14, 7, self.width() - 50, 22), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        f.setBold(False); f.setPixelSize(13); p.setFont(f); p.setPen(QColor(C["muted"] if self.isEnabled() else C["faint"]))
        p.drawText(QRectF(14, 28, self.width() - 50, 20), Qt.AlignLeft | Qt.AlignVCenter, self.text_)
        if on:
            p.drawPixmap(int(self.width() - 34), int(self.height() / 2 - 10), icones.pixmap("ok", C["accent"], 20, 2))

    def enterEvent(self, e):
        self.update(); super().enterEvent(e)

    def leaveEvent(self, e):
        self.update(); super().leaveEvent(e)


class CriarPGS(Dialogo):
    def __init__(self, parent, entry):
        super().__init__(parent, "Criar PGS", 1000, 700)
        self.path = entry.path
        self.lead("Grava uma legenda nova, em imagens (PGS, .sup), a partir de <b>%s</b>, com a letra do jeito que você escolher. "
                  "O original fica como está." % _esc(self.path.name), rich=True)
        self.sample = acoes.amostra(self.path) or [[[("Exemplo de legenda", False)]]]
        self.sample_index = 0
        self.name_edited = False
        self._build()

    def _build(self):
        clear(self.body)
        cols = QHBoxLayout(); cols.setSpacing(28)
        left = QVBoxLayout(); left.setSpacing(12)

        left.addWidget(label("Estilo", "h2"))
        self.preset_buttons = []
        for k, (title, text, values) in enumerate(PRESETS):
            b = Estilo(title, text)
            b.clicked.connect(lambda _=False, v=values: self._apply(v))
            self.preset_buttons.append((b, values))
            left.addWidget(b)

        self.custom_note = label("✓  Estilo personalizado (o seu)", "muted")
        self.custom_note.setStyleSheet("font-weight:700;")
        left.addWidget(self.custom_note)
        custom = QWidget(); cl = QVBoxLayout(custom); cl.setContentsMargins(0, 0, 0, 0); cl.setSpacing(10)
        cl.addWidget(label("Fonte", "h2"))
        self.font = QComboBox()
        self.font.setAccessibleName("Fonte")
        for shown, prefix in pgs.FONTS:
            self.font.addItem(shown, prefix)
        self.font.currentIndexChanged.connect(self._changed)
        self.bold = QCheckBox("Negrito")
        self.bold.toggled.connect(self._changed)
        cl.addLayout(hbox(grow(self.font), self.bold, spacing=16))
        self.size_slider, size_row, self.size_value = self._slider("Tamanho da letra", pgs.SIZES[0], pgs.SIZES[1], acoes.SIZE_DEFAULT, 1)
        cl.addLayout(size_row)
        self.outline_slider, out_row, self.outline_value = self._slider("Contorno preto", pgs.OUTLINES[0] * 2, pgs.OUTLINES[1] * 2,
                                                                        acoes.OUTLINE_DEFAULT * 2, 2)
        cl.addLayout(out_row)
        self.color_name = label("", "muted", wrap=False)
        cl.addLayout(hbox(label("Cor da letra", "h2"), None, self.color_name))
        grid = QGridLayout(); grid.setSpacing(2)
        self.swatches = []
        for k, (en, pt, rgb) in enumerate(pgs.COLORS):
            sw = Amostra(en, ((rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255))
            sw.toggled.connect(self._color_changed)
            grid.addWidget(sw, k // 7, k % 7)
            self.swatches.append(sw)
        cl.addLayout(grid)
        self.custom = Expander("Personalizar cor, fonte e tamanho", "Ver os estilos prontos", custom)
        # Com as opções abertas, os estilos prontos saem da frente (cabe tudo sem rolar).
        self.custom.toggle.clicked.connect(lambda: ([b.setVisible(not custom.isVisible()) for b, _ in self.preset_buttons], self._changed()))
        left.addSpacing(4)
        left.addWidget(self.custom)
        left.addStretch(1)

        right = QVBoxLayout(); right.setSpacing(10)
        self.preview = Previa()
        self.preview.setMaximumHeight(280)
        right.addWidget(self.preview)
        nav = hbox(grow(label("Prévia numa tela de TV, do tamanho que vai aparecer.", "faint")), spacing=6)
        if len(self.sample) > 1:
            nav.addWidget(button("Outra fala", "ghost", icon="right", slot=self._next_sample))
        right.addLayout(nav)
        self.summary = label("", "muted")
        right.addWidget(self.summary)
        self.field, col = self.name_field("", "Fica na mesma pasta da legenda. A cor vai em inglês no nome: é como o painel do player a mostra.")
        self.field.textEdited.connect(self._name_edited)
        right.addSpacing(6)
        right.addLayout(col)
        self.status = QVBoxLayout(); self.status.setSpacing(8)
        right.addLayout(self.status)
        right.addStretch(1)

        lw = QWidget(); lw.setObjectName("page"); lw.setLayout(left)
        left.setContentsMargins(0, 0, 12, 0)
        side = scroll(lw)  # só a coluna das opções rola; a prévia e o nome ficam sempre à vista
        side.setFixedWidth(336)
        side.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Ignored)
        cols.addWidget(side)
        cols.addLayout(right, 1)
        self.body.addLayout(cols)
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.timeout.connect(self._render)
        self.create = button("Criar PGS", "primary", slot=self._create)
        self.buttons(button("Cancelar", slot=self.reject), self.create)
        self._apply(PRESETS[0][2])

    def _apply(self, values):
        self._applying = True
        for sw in self.swatches:
            if sw.en == values["color"]:
                sw.setChecked(True)
        self.font.setCurrentIndex(max(0, self.font.findData(values["font"])))
        self.bold.setChecked(values["bold"])
        self.size_slider.setValue(values["size"])
        self.outline_slider.setValue(int(values["outline"] * 2))
        self._applying = False
        self._changed()

    def _slider(self, title, low, high, value, scale):
        s = QSlider(Qt.Horizontal); s.setRange(int(low), int(high)); s.setValue(int(value)); s.setAccessibleName(title)
        s.setPageStep(scale * 2)
        val = label("", wrap=False); val.setStyleSheet("font-weight:700;"); val.setMinimumWidth(44); val.setAlignment(Qt.AlignRight)
        s.valueChanged.connect(self._changed)
        col = vbox(hbox(label(title, "h2"), None, val), s, spacing=6)
        return s, col, val

    def estilo(self):
        color = next((sw.en for sw in self.swatches if sw.isChecked()), acoes.COLOR_DEFAULT)
        return acoes.EstiloPGS(color=color, font=self.font.currentData(), bold=self.bold.isChecked(),
                               size=self.size_slider.value(), outline=self.outline_slider.value() / 2)

    def _color_changed(self, on):
        if on:
            self._changed()

    def _name_edited(self, _):
        self.name_edited = True

    def _changed(self, *_):
        if getattr(self, "_applying", False):
            return
        e = self.estilo()
        self.color_name.setText(acoes.cor_nome(e.color).capitalize())
        self.size_value.setText("%d%s" % (e.size, " (padrão)" if e.size == acoes.SIZE_DEFAULT else ""))
        self.outline_value.setText(("%g" % e.outline).replace(".", ",") + (" (padrão)" if e.outline == acoes.OUTLINE_DEFAULT else ""))
        current = dict(color=e.color, font=e.font, bold=e.bold, size=e.size, outline=e.outline)
        for b, values in self.preset_buttons:
            b.setChecked(values == current)
        self.custom_note.setVisible(not any(values == current for _, values in self.preset_buttons))
        self.summary.setText("%s · %s%s · tamanho %d · contorno %s" % (acoes.cor_nome(e.color).capitalize(), pgs.font(e.font)[0],
                             " negrito" if e.bold else "", e.size, ("%g" % e.outline).replace(".", ",")))
        if not self.name_edited:
            self.field.setText(acoes.nome_sugerido(self.path, tail="." + e.color + ".sup"))
        self.timer.start(90)

    def _next_sample(self):
        self.sample_index = (self.sample_index + 1) % len(self.sample)
        self._render()

    def _render(self):
        try:
            self.preview.set_image(desenhar_previa(self.estilo().style(), self.sample[self.sample_index]))
        except Exception:
            self.preview.set_image(None)

    def _controls(self):
        return [self.create, self.field, self.font, self.bold, self.size_slider, self.outline_slider, self.custom.toggle,
                *self.swatches, *(b for b, _ in self.preset_buttons)]

    def _create(self):
        self.busy = True
        self.cancelled = False
        clear(self.status)
        for w in self._controls():
            w.setEnabled(False)
        self.bar = self.progress_row(t("progress"))
        self.bar.setMinimumWidth(360)
        clear(self.foot)
        self.foot.addWidget(self.bar, 1)
        self.foot.addSpacing(16)
        self.foot.addWidget(button("Cancelar", slot=self._cancel))
        tarefas.rodar(acoes.criar_pgs, self.path, self.estilo(), self.field.text(), done=self._done, failed=self._failed,
                      progress=self.bar.set, cancelled=lambda: self.cancelled)

    def _cancel(self):
        """Fecha na hora; o desenho que já começou termina sozinho e nada é gravado."""
        self.cancelled = True
        self.busy = False
        self.reject()

    def _failed(self, err):
        self.busy = False
        if isinstance(err, acoes.Cancelado):
            return
        clear(self.status)
        self.status.addWidget(self.failure(err))
        for w in self._controls():
            w.setEnabled(True)
        self.buttons(button("Cancelar", slot=self.reject), self.create)

    def _done(self, r):
        self.busy = False
        self.created.emit(r.output)
        self.max_h = 420
        self.resize(640, 420)
        clear(self.box_head)
        head = label("Criar PGS", "title"); head.setStyleSheet("font-size:22px;"); self.box_head.addWidget(head)
        self.success(t("pgs_done", name=r.output.name),
                     [self.estilo().describe().split(": ", 1)[-1].replace(", cor " + self.estilo().color, ", cor " + acoes.cor_nome(self.estilo().color)), t("pgs_stats", cues=number(r.cues), seconds=r.seconds, mb=r.mb)], r.output)


# ------------------------------------------------------------------ sincronia

class Sincronizar(Dialogo):
    def __init__(self, parent, entry, points_file=None):
        super().__init__(parent, "Aplicar a sincronia", 640, 640)
        self.path = entry.path
        self.lead("Cria uma legenda nova a partir de <b>%s</b>, com os ajustes de tempo que você fez no player. "
                  "O original fica como está." % _esc(self.path.name), rich=True)
        self.load(points_file)

    def load(self, points_file=None):
        clear(self.body)
        try:
            self.s = acoes.pontos(self.path, points_file)
        except acoes.Falha as err:
            self.s = None
            self.body.addWidget(self.failure(err))
            self.buttons(button("Escolher arquivo de pontos…", slot=self.pick), button("Fechar", "primary", slot=self.reject))
            return
        card = Card(spacing=8)
        card.add(hbox(status_icon("info", 20), grow(label(t("sync_points", n=len(self.s.points)).rstrip(":").replace("ponto(s) de ajuste aplicado(s)", "ponto de ajuste" if len(self.s.points) == 1 else "pontos de ajuste"), "h2")), spacing=10))
        card.add(label("A partir deste momento do filme  →  a legenda fica:", "faint"))
        for line in self.s.lines:
            lab = label(line); lab.setContentsMargins(30, 0, 0, 0)
            card.add(lab)
        src = label("Arquivo de pontos: " + str(self.s.points_file), "faint"); src.setContentsMargins(30, 4, 0, 0)
        card.add(src)
        self.body.addWidget(card)
        self.body.addLayout(hbox(button("Usar outro arquivo de pontos…", "ghost", slot=self.pick), None))
        self.field, col = self.name_field(acoes.nome_sugerido(self.path))
        self.body.addLayout(col)
        self.buttons(button("Cancelar", slot=self.reject), button("Criar legenda sincronizada", "primary", slot=self.apply))

    def pick(self):
        start = self.path.parent.parent / "sincronia"
        name, _ = QFileDialog.getOpenFileName(self, "Escolher o arquivo de pontos de sincronia",
                                              str(start if start.is_dir() else self.path.parent), "Pontos de sincronia (*.txt)")
        if name:
            self.load(Path(name))

    def apply(self):
        self.busy = True
        name = self.field.text()
        clear(self.body)
        self.body.addLayout(hbox(Busy(), grow(label("Aplicando os ajustes…", "muted")), spacing=12))
        self.buttons()
        tarefas.rodar(acoes.sincronizar, self.s, name, done=self._done, failed=self._failed)

    def _failed(self, err):
        self.busy = False
        clear(self.body)
        self.body.addWidget(self.failure(err))
        self.buttons(button("Fechar", slot=self.reject), button("Tentar de novo", "primary", slot=lambda: self.load(self.s.points_file)))

    def _done(self, r):
        self.busy = False
        self.created.emit(r.output)
        notes = []
        self.success(t("sync_done", name=r.output.name), [t("sync_note")], r.output)
        if r.warning is not None:
            b = Banner("warn", t("sync_check"))
            b.box.addWidget(items_view(r.warning.problems, "fail"))
            self.body.addWidget(b)


# ------------------------------------------------------------------ regras

class Regras(Dialogo):
    def __init__(self, parent):
        super().__init__(parent, t("rules_title"), 640, 760)
        self.lead("Para o player aceitar uma legenda SRT, ela precisa seguir estas regras. O SubDrive confere cada uma "
                  "e, quando dá, corrige sozinho.")
        card = Card(spacing=12)
        for k, (title, why, technical) in enumerate(rules()):
            if k:
                card.add(_sep())
            card.add(vbox(label(title, "h2"), label(why, "muted"), label(technical, "faint"), spacing=2))
        self.body.addWidget(card)
        self.body.addWidget(label("Um PGS (.sup) precisa ter até 64 MB e um nome simples. Para mudar um PGS, crie de novo a partir do SRT.", "faint"))
        self.buttons(button("Fechar", "primary", slot=self.accept))


def _sep():
    from .componentes import separator
    return separator()


def _esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
