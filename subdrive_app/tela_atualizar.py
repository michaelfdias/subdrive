"""Tela Atualizações: procurar versão nova (só quando a pessoa pede), instalar e versões de teste."""
from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from subdrive import VERSION

from . import acoes, icones, lugares, tarefas
from .componentes import grow, Banner, Busy, Card, Pill, Switch, button, clear, hbox, label, line_with_icon, open_url, scroll, vbox
from .tema import C
from .textos import t

SITE = "https://michaelfdias.github.io/subdrive/"
LINKS = [("livro", "Guia completo", SITE + "guia.html"), ("externo", "Página do projeto", SITE),
         ("conversa", "Fale comigo", "https://forms.gle/VtNmmcMs9byjnQvP8")]


class TelaAtualizar(QWidget):
    go_drive = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.release = None
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        inner = QWidget(); inner.setObjectName("page")
        box = QVBoxLayout(inner); box.setContentsMargins(40, 32, 40, 32); box.setSpacing(16)
        outer.addWidget(scroll(inner))
        box.addLayout(vbox(label("Atualizações", "title"),
                           label("O SubDrive só procura versões novas quando você pede, e confere se o arquivo é mesmo do projeto antes de instalar.", "lead"),
                           spacing=4))

        card = Card(spacing=12, margins=(22, 20, 22, 20))
        logo = QLabel(); logo.setPixmap(icones.logo(44))
        card.add(hbox(logo, grow(vbox(label("SubDrive " + VERSION, "big"), label("Versão instalada", "faint"), spacing=0)),
                      button("Procurar atualização", "primary", icon="atualizar", slot=self.search), spacing=14))
        self.result = QVBoxLayout(); self.result.setSpacing(10)
        card.add(self.result)
        box.addWidget(card)

        beta = Card(spacing=6, margins=(22, 18, 22, 18))
        self.switch = Switch()
        self.switch.setAccessibleName("Receber versões de teste")
        self.switch.setChecked(acoes.versoes_de_teste())
        self.switch_text = label("Ligado" if self.switch.isChecked() else "Desligado", "muted", wrap=False)
        self.switch.toggled.connect(self.set_beta)
        beta.add(hbox((vbox(label("Receber versões de teste", "h2"),
                           label("Para quem quer testar novidades antes e enviar relatórios.", "muted"),
                           spacing=2), 1), self.switch_text, self.switch, spacing=12))
        self.beta_note = label("", "faint")
        self.beta_note.hide()
        beta.add(self.beta_note)
        box.addWidget(beta)

        box.addStretch(1)

    # ------------------------------------------------------------ versões de teste
    def set_beta(self, on):
        self.switch_text.setText("Ligado" if on else "Desligado")
        try:
            acoes.mudar_versoes_de_teste(on)
        except acoes.Falha as e:
            self.beta_note.setText(e.message); self.beta_note.show()
            return
        self.beta_note.setText(t("beta_on") if on else t("beta_off") + " " + t("beta_off_note"))
        self.beta_note.show()

    # ------------------------------------------------------------ procurar
    def _busy(self, text):
        clear(self.result)
        self.result.addLayout(hbox(Busy(), grow(label(text, "muted")), spacing=12))

    def search(self):
        self._busy(t("update_searching"))
        tarefas.rodar(acoes.procurar_atualizacao, done=self._found, failed=self._failed)

    def _failed(self, err):
        clear(self.result)
        self.result.addWidget(Banner("fail", getattr(err, "message", None) or t("update_offline")))

    def _found(self, rel):
        clear(self.result)
        self.release = rel
        if rel is None:
            row, _ = line_with_icon("ok", t("update_none", version=VERSION)); self.result.addLayout(row)
            return
        card = Card(tone="accent", spacing=8)
        head = hbox(status_icon_label(), grow(label(t("update_found", new=rel.version, current=VERSION), "h2")), spacing=10)
        if rel.channel == "beta":
            head.insertWidget(2, Pill(t("update_beta_tag"), "info"))
        card.add(head)
        for note in acoes.notas(rel):
            lab = label("• " + note); lab.setContentsMargins(30, 0, 0, 0)
            card.add(lab)
        self.result.addWidget(card)
        self.result.addLayout(hbox(None, button("Agora não", slot=lambda: clear(self.result)),
                                   button("Atualizar agora", "primary", icon="baixar", slot=self.install)))

    def install(self):
        clear(self.result)
        self.bar = _progress(t("update_downloading"))
        self.result.addWidget(self.bar)
        tarefas.rodar(acoes.atualizar, self.release, done=self._installed, failed=self._failed, progress=self.bar.set)

    def _installed(self, r):
        clear(self.result)
        for tone, text in r.lines:
            row, _ = line_with_icon(tone, text); self.result.addLayout(row)
        for text in r.drives_behind:
            self.result.addWidget(Banner("info", text, buttons=[button("Ir para Pendrive", slot=self.go_drive.emit)]))
        if r.restart:
            self.result.addLayout(hbox(None, button("Reiniciar o SubDrive", "primary", icon="atualizar", slot=restart)))


def status_icon_label():
    from .componentes import status_icon
    return status_icon("info", 20)


def _progress(text):
    from PySide6.QtWidgets import QProgressBar
    bar = QProgressBar(); bar.setRange(0, 100); bar.setTextVisible(False)
    lab = label(text, "muted"); pct = label("", "faint", wrap=False)
    w = QWidget(); col = QVBoxLayout(w); col.setContentsMargins(0, 0, 0, 0); col.setSpacing(8)
    col.addLayout(hbox(lab, None, pct)); col.addWidget(bar)
    w.set = lambda d, total: (bar.setValue(int(100 * d / max(1, total))), pct.setText("%d%%" % (100 * d // max(1, total))))
    return w


def restart():
    """Abre a versão nova e fecha esta."""
    exe = lugares.executable()
    try:
        if exe.suffix == ".app":
            subprocess.Popen(["open", "-n", str(exe)])
        else:
            subprocess.Popen([str(exe)], cwd=str(exe.parent), close_fds=True)
    except OSError:
        pass
    QApplication.quit()
