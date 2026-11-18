"""Tela Pendrive: os pendrives conectados, se o player lê cada um, e Preparar pendrive (passo a passo)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QCheckBox, QFileDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from subdrive import drives

from . import acoes, icones, lugares, tarefas
from .componentes import (grow, open_folder, Banner, Busy, Card, Expander, button, clear, hbox, icon_button, label, line_with_icon, scroll,
                          status_icon, vbox)
from .dialogos import Dialogo
from .tema import C
from .textos import t


class Monitor:
    """Confere os pendrives a cada poucos segundos (em segundo plano) e avisa quando algo muda."""
    def __init__(self, on_change, every_ms=3000):
        self.on_change, self.found, self.running, self.sig = on_change, [], False, None
        self.timer = QTimer(); self.timer.timeout.connect(self.poll); self.timer.start(every_ms)

    def poll(self):
        if self.running:
            return
        self.running = True
        task = tarefas.Tarefa(drives.find)
        task.done.connect(self._found)
        task.failed.connect(lambda _: setattr(self, "running", False))
        task.start()

    def _found(self, found):
        self.running = False
        sig = [(str(d.path), d.label, d.filesystem, d.scheme, d.partitions, tuple(d.problems), d.readonly, d.free // (1 << 20)) for d in found]
        if sig != self.sig:
            self.sig, self.found = sig, found
            self.on_change(found)


class TelaPendrive(QWidget):
    toast = Signal(str, str)
    prepared = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.found = None
        self.pkg = None
        self.pkg_folder = None
        self.pkg_error = None
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        inner = QWidget(); inner.setObjectName("page")
        self.box = QVBoxLayout(inner); self.box.setContentsMargins(40, 32, 40, 32); self.box.setSpacing(16)
        outer.addWidget(scroll(inner))
        self.load_package()
        self.draw()

    # ------------------------------------------------------------ pacote
    def load_package(self, folder=None):
        try:
            self.pkg = acoes.carregar_pacote(folder or self.pkg_folder)
            self.pkg_folder = self.pkg.folder
            self.pkg_error = None
        except acoes.Falha as e:
            self.pkg, self.pkg_error = None, e

    def pick_package(self):
        name = QFileDialog.getExistingDirectory(self, "Escolher a pasta do pacote SubDrive", str(lugares.program_dir()))
        if name:
            self.load_package(Path(name))
            if self.pkg is None:
                self.toast.emit(self.pkg_error.message, "fail")
            self.draw()

    # ------------------------------------------------------------ desenho
    def set_drives(self, found):
        self.found = found
        self.draw()

    def draw(self):
        clear(self.box)
        title = vbox(label("Pendrive", "title"), label("Prepare o pendrive que vai no player e confira se ele está no formato certo.", "lead"), spacing=4)
        self.box.addLayout(hbox(grow(title), button("Procurar pendrives", "ghost", icon="recarregar", slot=self.refresh), spacing=8))
        if self.pkg is None and self.pkg_error is not None:
            b = Banner("warn", self.pkg_error.detail[0] if self.pkg_error.detail else "", title=self.pkg_error.message,
                       buttons=[button("Escolher a pasta do pacote…", slot=self.pick_package)])
            self.box.addWidget(b)
        if self.found is None:
            self.box.addLayout(hbox(Busy(), grow(label("Procurando pendrives…", "muted")), spacing=12))
        elif not self.found:
            self.box.addWidget(self._empty())
        else:
            for d in self.found:
                self.box.addWidget(self._drive(d))
        if self.pkg is not None:
            adv = QWidget(); al = QVBoxLayout(adv); al.setContentsMargins(0, 0, 0, 0)
            al.addLayout(hbox(grow(label("Pacote do player: SubDrive %s (%s)  ·  %s" % (self.pkg.version, self.pkg.platform, self.pkg.folder), "faint")),
                              button("Usar outra pasta…", "ghost", slot=self.pick_package), spacing=4))
            self.box.addSpacing(4)
            self.box.addWidget(Expander("Avançado", "Esconder", adv))
        self.box.addStretch(1)

    def _empty(self):
        card = Card(margins=(32, 40, 32, 40), spacing=10)
        ic = QLabel(); ic.setPixmap(icones.pixmap("pendrive", C["accent"], 48, 1.6)); ic.setAlignment(Qt.AlignCenter)
        card.add(ic)
        h = label(t("drives_none"), "big"); h.setAlignment(Qt.AlignCenter); card.add(h)
        s = label(t("drives_none_hint"), "muted"); s.setAlignment(Qt.AlignCenter); card.add(s)
        n = label("Pode usar o pendrive que você tem: o SubDrive avisa se ele precisar ser formatado.", "faint")
        n.setAlignment(Qt.AlignCenter); card.add(n)
        return card

    def _drive(self, d):
        e = acoes.descrever_pendrive(d)
        card = Card(spacing=10, margins=(22, 18, 22, 18))
        ic = QLabel(); ic.setPixmap(icones.pixmap("pendrive", C["accent"] if e.ok else C["muted"], 30, 1.7))
        name = label(d.label or str(d.path), "big")
        free = (" · %s livres" % acoes.size(d.free)) if d.free else ""
        sub = label("%s · %s%s" % (str(d.path).rstrip("\\/") or str(d.path), acoes.size(d.size), free), "faint")
        eject = button("Ejetar", icon="ejetar", slot=lambda: self.eject(d))
        card.add(hbox(ic, grow(vbox(name, sub, spacing=0)), eject, spacing=14))
        for tone, text in e.lines:
            row, _ = line_with_icon(tone, text, size=18)
            card.add(row)
        if e.installed:
            row, _ = line_with_icon("info", e.installed, size=18)
            card.add(row)
        if e.format_help or e.technical and not e.ok:
            body = QWidget(); col = QVBoxLayout(body); col.setContentsMargins(28, 0, 0, 0); col.setSpacing(8)
            for k, step in enumerate(e.format_help, 1):
                col.addWidget(label(step))
            col.addWidget(label(t("format_never"), "faint"))
            if e.technical:
                col.addSpacing(4)
                col.addWidget(label(t("drive_details") + ": " + " ".join(e.technical), "faint"))
            ex = Expander(t("format_title"), "Esconder", body)
            ex.layout().setContentsMargins(28, 0, 0, 0)
            card.add(ex)
        if e.ok:
            prep = button("Preparar pendrive", "primary", icon="pendrive", slot=lambda: self.prepare(d))
            prep.setProperty("kind", "primary")
            if self.pkg is None:
                prep.setEnabled(False)
                prep.setToolTip(t("package_missing"))
            card.add(hbox(prep, grow(label("Instala ou atualiza o SubDrive no pendrive. Suas legendas e ajustes ficam.", "faint")), spacing=14))
        return card

    # ------------------------------------------------------------ ações
    def refresh(self):
        self.found = None
        self.draw()
        tarefas.rodar(drives.find, done=self.set_drives)

    def eject(self, d):
        self.toast.emit("Ejetando %s…" % (d.label or d.path), "info")
        tarefas.rodar(acoes.ejetar, d, done=lambda ok: (self.toast.emit(t("ejected" if ok else "eject_failed"), "ok" if ok else "warn"), self.refresh()))

    def prepare(self, d):
        if self.pkg is None:
            return
        dlg = Preparar(self, d, self.pkg)
        dlg.exec()
        self.refresh()
        if dlg.done_ok:
            self.prepared.emit()


class Preparar(Dialogo):
    """Passo a passo: firmware (só na primeira vez) → o que vai mudar → copiar e conferir → ejetar."""
    confirmed_once = False  # a versão do firmware só é perguntada uma vez enquanto o SubDrive está aberto
    def __init__(self, parent, drive, pkg):
        super().__init__(parent, "Preparar pendrive", 640, 560)
        self.drive, self.pkg = drive, pkg
        self.replace = False
        self.done_ok = False
        self.confirmed = not pkg.needs_jar or Preparar.confirmed_once
        self.lead("Instala ou atualiza o SubDrive no pendrive <b>%s</b>." % (drive.label or drive.path), rich=True)
        self.start()

    def start(self):
        if self.pkg.needs_jar:
            self.busy = True
            self._wait("Procurando o firmware oficial já baixado…")
            tarefas.rodar(acoes.firmware_guardado, self.pkg, done=self._cached, failed=self._fail)
        else:
            self.show_plan()

    def _wait(self, text):
        clear(self.body)
        self.body.addLayout(hbox(Busy(), grow(label(text, "muted")), spacing=12))
        self.buttons()

    def _fail(self, err, retry=None):
        self.busy = False
        clear(self.body)
        self.body.addWidget(self.failure(err))
        items = [button("Fechar", slot=self.reject)]
        if retry:
            items.append(button("Tentar de novo", "primary", slot=retry))
        self.buttons(*items)

    # firmware
    def _cached(self, blob):
        if blob is not None:
            self._build(blob)
            return
        self.busy = False
        clear(self.body)
        fw = self.pkg.firmware
        card = Card(spacing=10)
        card.add(hbox(status_icon("info", 22), grow(label("O primeiro preparo precisa do firmware oficial", "h2")), spacing=10))
        lab = label(t("firmware_needed", size=acoes.size(fw["bytes"]))); lab.setContentsMargins(32, 0, 0, 0)
        card.add(lab)
        self.body.addWidget(card)
        have = button("Já tenho o arquivo…", slot=self.pick_firmware)
        get = button("Baixar agora (%s)" % acoes.size(fw["bytes"]), "primary", icon="baixar", slot=self.download)
        self.body.addWidget(self._confirm_box([have, get]))
        self.buttons(self.why, have, get)

    def _confirm_box(self, gated):
        """O SubDrive só funciona no firmware 1.13: a pessoa confirma antes de seguir."""
        card = Card(tone="warn", spacing=6)
        box = QCheckBox(acoes.confirmar_firmware(self.pkg))
        box.setStyleSheet("QCheckBox{font-weight:700;}")
        box.setChecked(self.confirmed)
        where = label(t("firmware_where"), "muted"); where.setContentsMargins(28, 0, 0, 0)
        card.add(hbox(status_icon("warn", 20), grow(box), spacing=10)); card.add(where)

        self.why = label("Marque a confirmação acima para continuar.", "muted", wrap=False)

        def changed(on):
            self.confirmed = on
            Preparar.confirmed_once = Preparar.confirmed_once or on
            self.why.setVisible(not on)
            for b in gated:
                b.setEnabled(on)
        box.toggled.connect(changed)
        changed(self.confirmed)
        return card

    def pick_firmware(self):
        name, _ = QFileDialog.getOpenFileName(self, "Escolher o firmware oficial (%s)" % self.pkg.firmware.get("name", "ZIP"),
                                              str(lugares.program_dir()), "Firmware (*.zip *.ZIP)")
        if not name:
            return
        try:
            blob = acoes.firmware_escolhido(self.pkg, Path(name))
        except acoes.Falha as err:
            self._fail(err, retry=lambda: self._cached(None))
            return
        self._build(blob)

    def download(self):
        self.busy = True
        clear(self.body)
        self.bar = self.progress_row(t("firmware_downloading"))
        self.body.addWidget(self.bar)
        self.body.addWidget(label("O arquivo vem do site da Panasonic e é conferido antes de ser usado.", "faint"))
        self.buttons()
        tarefas.rodar(acoes.baixar_firmware, self.pkg, done=self._build, progress=self.bar.set,
                      failed=lambda err: self._fail(err, retry=lambda: self._cached(None)))

    def _build(self, blob):
        self.busy = True
        self._wait(t("building_jar") + "…")
        tarefas.rodar(acoes.montar_programa, self.pkg, blob, done=lambda _: self.show_plan(), failed=self._fail)

    # plano
    def show_plan(self):
        self.busy = True
        self._wait("Comparando o pendrive com o pacote…")
        tarefas.rodar(acoes.planejar, self.drive, self.pkg, self.replace, done=self._plan, failed=self._fail)

    def _plan(self, p):
        self.busy = False
        self.plan = p
        clear(self.body)
        card = Card(spacing=10)
        if p.nothing:
            row, _ = line_with_icon("ok", "O pendrive já está com o SubDrive %s. Nada a fazer." % self.pkg.version, role="h2"); card.add(row)
        else:
            row, _ = line_with_icon("info", "Vamos instalar o SubDrive %s no pendrive. Suas legendas e ajustes não serão apagados." % self.pkg.version,
                                    role="h2", size=20)
            card.add(row)
        details = QWidget(); dl = QVBoxLayout(details); dl.setContentsMargins(30, 0, 0, 0); dl.setSpacing(6)
        dl.addWidget(label(p.title, "muted"))
        for text in p.lines:
            dl.addWidget(label("• " + text, "muted"))
        dl.addWidget(label(t("plan_keep_user"), "muted"))
        if p.kept or self.replace:
            box = QCheckBox("Trocar também as legendas de exemplo que vêm no pacote (as suas com o mesmo nome)")
            box.setChecked(self.replace)
            box.toggled.connect(self._toggle_replace)
            dl.addSpacing(4); dl.addWidget(box)
        ex = Expander("Detalhes", "Esconder os detalhes", details)
        ex.layout().setContentsMargins(30, 0, 0, 0)
        if self.replace:
            ex.flip()
        card.add(ex)
        self.body.addWidget(card)
        if p.error:
            self.body.addWidget(Banner("fail", p.error))
        if p.nothing:
            self.finish(nothing=True)
            return
        go = button("Preparar", "primary", slot=self.copy)
        if not self.confirmed:
            self.body.addWidget(self._confirm_box([go]))
        go.setEnabled(not p.error and self.confirmed)
        self.buttons(self.why, button("Cancelar", slot=self.reject), go) if not self.confirmed else \
            self.buttons(button("Cancelar", slot=self.reject), go)

    def _toggle_replace(self, on):
        self.replace = on
        self.show_plan()

    # cópia
    def copy(self):
        self.busy = True
        clear(self.body)
        self.bar = self.progress_row(t("copying"))
        self.body.addWidget(self.bar)
        self.body.addWidget(label("Não tire o pendrive até terminar. Cada arquivo é conferido depois de gravado.", "faint"))
        self.buttons()
        tarefas.rodar(acoes.gravar, self.drive, self.pkg, self.replace, progress=self.bar.set,
                      done=lambda _: self.finish(), failed=lambda err: self._fail(err, retry=self.show_plan))

    def finish(self, nothing=False):
        self.busy = False
        self.done_ok = True
        if not nothing:
            clear(self.body)
            card = Card(tone="ok", spacing=8)
            card.add(hbox(status_icon("ok", 28), grow(label(t("prepared"), "big")), spacing=12))
            lab = label("Próximo passo: coloque as legendas (.srt ou .sup) na pasta legendas do pendrive. "
                        "Antes, veja na tela Legendas se elas vão funcionar.", "muted")
            lab.setContentsMargins(40, 0, 0, 0)
            card.add(lab)
            self.body.addWidget(card)
        self.eject_note = label(t("eject_hint"), "muted")
        self.body.addWidget(self.eject_note)
        folder = self.drive.path / "legendas"
        items = [button("Concluir", slot=self.accept)]
        if folder.is_dir():
            items.insert(0, button("Abrir a pasta legendas", icon="folder", slot=lambda: open_folder(folder)))
        items.append(button("Ejetar o pendrive", "primary", icon="ejetar", slot=self.eject))
        self.buttons(*items)

    def eject(self):
        self.busy = True
        self._wait("Ejetando…")
        tarefas.rodar(acoes.ejetar, self.drive, done=self._ejected, failed=lambda e: self._ejected(False))

    def _ejected(self, ok):
        self.busy = False
        clear(self.body)
        self.body.addWidget(Banner("ok" if ok else "warn", t("ejected" if ok else "eject_failed")))
        self.buttons(button("Concluir", "primary", slot=self.accept))
