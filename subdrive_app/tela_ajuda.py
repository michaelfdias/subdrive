"""Tela Ajuda: como usar em 4 passos, o que é verificado, e onde pedir ajuda."""
from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from .componentes import Card, button, grow, hbox, label, open_url, scroll, separator, vbox
from .tema import C
from .textos import rules, t

SITE = "https://michaelfdias.github.io/subdrive/"
LINKS = [("livro", "Guia completo", SITE + "guia.html"), ("externo", "Página do projeto", SITE),
         ("conversa", "Fale comigo", "https://forms.gle/VtNmmcMs9byjnQvP8")]
STEPS = [
    ("Prepare o pendrive", "Conecte um pendrive e use a tela Pendrive (o SubDrive avisa se ele precisar ser formatado). "
                           "Na primeira vez o SubDrive baixa o firmware oficial da Panasonic."),
    ("Confira as legendas", "Na tela Legendas, arraste os arquivos .srt ou .sup. Se algo estiver errado, use Corrigir."),
    ("Copie para o pendrive", "Coloque as legendas prontas na pasta legendas do pendrive e ejete."),
    ("Use no player", "Na primeira vez:\n   a) ligue o player sem disco e espere a tela inicial;\n   b) coloque o pendrive e feche a janela que o player abrir;\n"
                      "   c) espere de 10 a 15 segundos e coloque o disco;\n   d) durante o filme, aperte a tecla VERMELHA do controle.\n"
                      "Se a legenda sumir depois de um menu do disco, aperte VERMELHA de novo."),
]


class TelaAjuda(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        inner = QWidget(); inner.setObjectName("page")
        box = QVBoxLayout(inner); box.setContentsMargins(40, 32, 40, 32); box.setSpacing(16)
        outer.addWidget(scroll(inner))
        box.addLayout(vbox(label("Ajuda", "title"), label("Como usar o SubDrive, o que ele confere e onde pedir ajuda.", "lead"), spacing=4))

        steps = Card(spacing=12)
        steps.add(label("Como usar", "h2"))
        for k, (title, text) in enumerate(STEPS, 1):
            n = label(str(k), wrap=False)
            n.setFixedSize(28, 28)
            n.setStyleSheet("background:%s;color:%s;border-radius:14px;font-weight:700;qproperty-alignment:AlignCenter;" % (C["accent_bg"], C["accent"]))
            body = label(text.replace("tecla VERMELHA", "<b style='color:%s'>tecla VERMELHA</b>" % ("#ff6b7d" if C["bg"] == "#111214" else "#c8102e")).replace("\n", "<br>")
                         .replace("VERMELHA de novo", "<b style='color:%s'>VERMELHA</b> de novo" % ("#ff6b7d" if C["bg"] == "#111214" else "#c8102e")), "muted", rich=True)
            steps.add(hbox((n, 0), grow(vbox(label(title, "h2"), body, spacing=2)), spacing=14))
        box.addWidget(steps)

        links = Card(spacing=6)
        links.add(label("Precisa de mais ajuda?", "h2"))
        row = hbox(spacing=4)
        for icon_name, text, url in LINKS:
            row.addWidget(button(text, "ghost", icon=icon_name, slot=lambda u=url: open_url(u)))
        row.addStretch(1)
        links.add(row)
        box.addWidget(links)

        card = Card(spacing=12)
        card.add(label(t("rules_title"), "h2"))
        card.add(label("Para o player aceitar uma legenda SRT, ela precisa seguir estas regras. O SubDrive confere cada uma "
                       "e, quando dá, corrige sozinho.", "muted"))
        for title, why, technical in rules():
            card.add(separator())
            card.add(vbox(label(title, "h2"), label(why, "muted"), label(technical, "faint"), spacing=2))
        box.addWidget(card)
        box.addWidget(label("O SubDrive é um projeto independente, sem ligação com a Panasonic. Use por sua conta e risco "
                            "(veja a isenção de responsabilidade na página do projeto).", "faint"))
        box.addStretch(1)
