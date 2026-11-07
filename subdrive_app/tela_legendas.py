"""Tela Legendas: todas as legendas encontradas, se cada uma está pronta para o player e o que fazer com ela."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel, QMenu, QSizePolicy, QStackedWidget, QVBoxLayout,
                               QWidget)

from subdrive import core, sync

from . import acoes, icones, lugares, tarefas
from .componentes import (grow, spots_view, Banner, Busy, Card, Clickable, Expander, Pill, button, clear, hbox, icon_button, items_view, label,
                          line_with_icon, scroll, show_in_folder, status_icon, vbox)
from .tema import C
from .textos import concordar, number, t

KINDS = (".srt", ".sup")


class Entrada:
    def __init__(self, path: Path, place: str):
        self.path, self.place = path, place
        self.result = None      # acoes.Verificacao
        self.error = None       # frase, quando não deu para ler


class Fila:
    """Verifica as legendas uma de cada vez, em segundo plano."""
    def __init__(self, on_result):
        self.on_result, self.queue, self.running = on_result, [], False

    def add(self, entries, first=False):
        for e in entries:
            if e in self.queue:
                self.queue.remove(e)
            if first:
                self.queue.insert(0, e)
            else:
                self.queue.append(e)
        self._next()

    def _next(self):
        if self.running or not self.queue:
            return
        e = self.queue.pop(0)
        self.running = True
        task = tarefas.Tarefa(acoes.verificar, e.path)
        task.done.connect(lambda res, e=e: self._done(e, res, None))
        task.failed.connect(lambda err, e=e: self._done(e, None, err))
        task.start()

    def _done(self, e, res, err):
        self.running = False
        e.result = res
        if err is None:
            e.error = None
        else:
            e.error = getattr(err, "message", None) or "Não deu para ler este arquivo (%s)." % type(err).__name__
        try:
            self.on_result(e)
        finally:
            self._next()


class TelaLegendas(QWidget):
    open_fix = Signal(object)        # Entrada
    open_pgs = Signal(object)
    open_sync = Signal(object, object)  # Entrada, arquivo de pontos (ou None)
    show_rules = Signal()
    look_for_drives = Signal()
    toast = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.groups = []            # [(rótulo, pasta ou None, [Entrada])]
        self.added = []             # [(rótulo, pasta ou None, [Path])] escolhidos pelo usuário
        self.by_path = {}
        self.current = None
        self.fila = Fila(self._checked)
        self.drives = []

        self.stack = QStackedWidget()
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.addWidget(self.stack)
        self.stack.addWidget(self._build_list())
        self.detail = QWidget(); self.detail.setObjectName("page")
        self.detail_box = QVBoxLayout(self.detail); self.detail_box.setContentsMargins(0, 0, 0, 0)
        self.stack.addWidget(self.detail)

    # ------------------------------------------------------------ lista
    def _build_list(self):
        w = QWidget(); w.setObjectName("page")
        box = QVBoxLayout(w); box.setContentsMargins(40, 32, 40, 24); box.setSpacing(18)
        title = vbox(label("Legendas", "title"), label("Veja se cada legenda vai funcionar no player e ajuste o que precisar.", "lead"), spacing=4)
        refresh = button("Verificar de novo", "ghost", icon="recarregar", slot=self.refresh,
                         tip="Procura de novo no pendrive e nas pastas, e verifica cada legenda")
        folder = button("Adicionar pasta", icon="folder", slot=self.pick_folder)
        add = button("Adicionar legendas", "primary", icon="plus", slot=self.pick_files)
        box.addLayout(hbox(grow(title), refresh, folder, add, spacing=8))
        self.list_inner = QWidget()
        self.list_box = QVBoxLayout(self.list_inner); self.list_box.setContentsMargins(0, 0, 4, 8); self.list_box.setSpacing(8)
        box.addWidget(scroll(self.list_inner), 1)
        return w

    def set_drives(self, found):
        self.drives = found
        self.refresh(check_again=False)

    def refresh(self, check_again=True):
        """Procura de novo nos lugares de sempre (pendrives, pacote, pasta do programa) e verifica o que mudou."""
        old = self.by_path
        groups = []
        try:
            for label_, folder in lugares.places(self.drives):
                try:
                    files = [p for p in core.subtitle_files(folder) if p.suffix.lower() in KINDS]
                except OSError:
                    continue
                if files:
                    groups.append((label_, folder, files))
        except Exception:
            pass
        groups += [(lab, folder, [p for p in files if p.is_file()]) for lab, folder, files in self.added]
        self.groups, self.by_path, todo = [], {}, []
        for lab, folder, files in groups:
            entries = []
            for p in files:
                key = self._key(p)
                if key in self.by_path:
                    continue
                e = old.get(key)
                stale = e is None or check_again or self._mtime(p) != getattr(e, "mtime", None)
                if e is None:
                    e = Entrada(p, lab)
                if stale:
                    e.result, e.error, e.mtime = None, None, self._mtime(p)
                    todo.append(e)
                self.by_path[key] = e
                entries.append(e)
            if entries or folder is not None and (lab, folder) in [(a, b) for a, b, _ in self.added]:
                self.groups.append((lab, folder, entries))
        self._draw_list()
        self.fila.add(todo)
        if self.current is not None and self.stack.currentIndex() == 1:
            e = self.by_path.get(self._key(self.current.path))
            if e is None:
                self.back()
            else:
                self.current = e
                self._draw_detail()

    @staticmethod
    def _key(p):
        try:
            return p.resolve()
        except OSError:
            return p

    @staticmethod
    def _mtime(p):
        try:
            st = p.stat()
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def _draw_list(self):
        clear(self.list_box)
        if not self.drives:
            self.list_box.addWidget(Banner("info", "Conecte o pendrive do player para ver e conferir as legendas que estão nele.",
                                           buttons=[button("Procurar pendrives", icon="recarregar", slot=self.look_for_drives.emit)]))
        if not any(entries for _, _, entries in self.groups):
            self.list_box.addWidget(self._empty(), 1)
            for lab, folder, entries in self.groups:
                if folder is not None:
                    self.list_box.insertWidget(0, Banner("info", t("folder_empty", name=str(folder))))
            return
        for lab, folder, entries in self.groups:
            ready = sum(1 for e in entries if e.result is not None and e.result.ok)
            done = all(e.result is not None or e.error for e in entries)
            group = label(lab.upper(), "group", wrap=False)
            if folder is not None:
                group.setToolTip(str(folder))
            head = hbox(group, None,
                        label(t("folder_summary", ok=ready, total=len(entries)) if done and len(entries) > 1 else "", "faint", wrap=False),
                        margins=(4, 10, 4, 0))
            self.list_box.addLayout(head)
            if not entries:
                self.list_box.addWidget(label(t("folder_empty", name=str(folder)), "faint"))
            for e in entries:
                self.list_box.addWidget(self._row(e))
        self.list_box.addSpacing(6)
        self.list_box.addWidget(label("Dica: arraste legendas ou pastas para esta janela.", "faint", wrap=False), 0, Qt.AlignHCenter)
        self.list_box.addStretch(1)

    def _empty(self):
        w = QFrame(); w.setObjectName("card")
        w.setStyleSheet("#card{border:2px dashed %s;background:transparent;border-radius:16px;}" % C["strong"])
        box = QVBoxLayout(w); box.setContentsMargins(40, 48, 40, 48); box.setSpacing(12)
        ic = QLabel(); ic.setPixmap(icones.pixmap("soltar", C["accent"], 48, 1.6)); ic.setAlignment(Qt.AlignCenter)
        box.addStretch(1)
        box.addWidget(ic)
        h = label("Arraste legendas .srt ou .sup para esta janela", "big"); h.setAlignment(Qt.AlignCenter)
        box.addWidget(h)
        sub = label("ou escolha os arquivos no computador.", "muted"); sub.setAlignment(Qt.AlignCenter)
        box.addWidget(sub)
        box.addLayout(hbox(None, button("Escolher arquivos…", "primary", icon="file", slot=self.pick_files),
                           button("Escolher uma pasta…", icon="folder", slot=self.pick_folder), None))
        note = label("O SubDrive também procura sozinho na pasta legendas do pendrive, do pacote baixado e da pasta do programa.", "faint")
        note.setAlignment(Qt.AlignCenter)
        box.addSpacing(8); box.addWidget(note)
        box.addStretch(1)
        return w

    def _row(self, e):
        row = Clickable()
        row.setAccessibleName(e.path.name)
        box = QHBoxLayout(row); box.setContentsMargins(16, 12, 14, 12); box.setSpacing(14)
        ic = QLabel(); ic.setPixmap(icones.pixmap("pgs" if e.path.suffix.lower() == ".sup" else "file", C["muted"], 22))
        box.addWidget(ic)
        col = QVBoxLayout(); col.setSpacing(2)
        name = label(e.path.name, wrap=False); name.setStyleSheet("font-size:15px;font-weight:700;")
        name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        col.addWidget(name)
        meta = label(self._meta(e), "faint", wrap=False); meta.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        col.addWidget(meta)
        box.addLayout(col, 1)
        box.addWidget(self._pill(e))
        chev = QLabel(); chev.setPixmap(icones.pixmap("right", C["faint"], 18))
        box.addWidget(chev)
        row.clicked.connect(lambda e=e: self.open(e))
        row.setContextMenuPolicy(Qt.CustomContextMenu)
        row.customContextMenuRequested.connect(lambda pos, e=e, row=row: self._context(e, row.mapToGlobal(pos)))
        return row

    def _meta(self, e):
        kind = "PGS" if e.path.suffix.lower() == ".sup" else "SRT"
        if e.error:
            return kind + " · " + e.error
        if e.result is None:
            return kind
        res = e.result.result
        if res is not None and res.cues:
            return kind + " · " + concordar("%s falas · %s" % (number(res.cues), res.duration), res.cues)
        return kind

    def _pill(self, e):
        if e.error:
            return Pill("Não abriu", "fail")
        if e.result is None:
            return Pill("Verificando…", "wait")
        if e.result.ok and not e.result.warnings:
            return Pill("Pronta", "ok")
        if e.result.ok:
            n = len(e.result.warnings)
            return Pill("Pronta · %d aviso%s" % (n, "" if n == 1 else "s"), "warn")
        n = len(e.result.problems)
        return Pill("1 problema" if n == 1 else "%d problemas" % n, "fail")

    def _context(self, e, where):
        m = QMenu(self)
        m.addAction("Abrir", lambda: self.open(e))
        m.addAction("Mostrar na pasta", lambda: show_in_folder(e.path))
        if any(e.path in files for _, _, files in self.added):
            m.addAction("Tirar da lista", lambda: self.forget(e.path))
        m.exec(where)

    def forget(self, path):
        self.added = [(lab, folder, [p for p in files if p != path]) for lab, folder, files in self.added]
        self.added = [g for g in self.added if g[2] or g[1] is not None]
        self.refresh(check_again=False)

    def _checked(self, e):
        if self.by_path.get(self._key(e.path)) is not e:
            return
        self._draw_list_later()
        if self.current is e and self.stack.currentIndex() == 1:
            self._draw_detail()

    def _draw_list_later(self):
        if not hasattr(self, "_timer"):
            self._timer = QTimer(self); self._timer.setSingleShot(True); self._timer.timeout.connect(self._draw_list)
        self._timer.start(60)

    # ------------------------------------------------------------ adicionar
    def pick_files(self):
        names, _ = QFileDialog.getOpenFileNames(self, "Escolher legendas", str(lugares.program_dir()), "Legendas (*.srt *.sup *.SRT *.SUP)")
        if names:
            self.add_paths([Path(n) for n in names])

    def pick_folder(self):
        name = QFileDialog.getExistingDirectory(self, "Escolher uma pasta com legendas", str(lugares.program_dir()))
        if name:
            self.add_paths([Path(name)])

    def add_paths(self, paths, open_single=True):
        """Arquivos ou pastas escolhidos ou arrastados para a janela."""
        files, opened = [], None
        for p in paths:
            if p.is_dir():
                try:
                    found = [f for f in core.subtitle_files(p) if f.suffix.lower() in KINDS]
                except OSError:
                    found = []
                if not found:
                    self.toast.emit(t("folder_empty", name=str(p)), "warn")
                self.added = [g for g in self.added if g[1] != p] + [("Pasta " + p.name, p, found)]
            elif p.is_file() and p.suffix.lower() in KINDS:
                files.append(p)
            elif p.is_file():
                self.toast.emit(t("not_subtitle", name=p.name), "fail")
            else:
                self.toast.emit(t("not_found", name=str(p)), "fail")
        known = {self._key(e.path) for _, _, es in self.groups for e in es}
        new = [f for f in files if self._key(f) not in known]
        if new:
            mine = next((g for g in self.added if g[1] is None), None)
            if mine is None:
                mine = ("Escolhidas por você", None, [])
                self.added.append(mine)
            mine[2].extend(new)
        self.refresh(check_again=False)
        if open_single and len(files) == 1 and not any(p.is_dir() for p in paths):
            e = self.by_path.get(self._key(files[0]))
            if e is not None:
                self.fila.add([e], first=True)
                self.open(e)

    def recheck(self, path):
        e = self.by_path.get(self._key(path))
        if e is not None:
            e.result = e.error = None
            self.fila.add([e], first=True)
            self._draw_list_later()
            if self.current is e:
                self._draw_detail()

    def added_file(self, path: Path):
        """Um arquivo novo gravado pelo SubDrive (cópia corrigida, PGS, sincronizada): entra na lista."""
        if self._key(path) not in self.by_path:
            folder = path.parent
            in_place = any(self._key(folder) == self._key(f) for _, f in lugares.places(self.drives))
            if not in_place:
                mine = next((g for g in self.added if g[1] is None), None)
                if mine is None:
                    mine = ("Escolhidas por você", None, [])
                    self.added.append(mine)
                mine[2].append(path)
        self.refresh(check_again=False)

    # ------------------------------------------------------------ detalhe
    def open(self, e):
        self.current = e
        self._draw_detail()
        self.stack.setCurrentIndex(1)

    def back(self):
        self.current = None
        self.stack.setCurrentIndex(0)

    def show_list(self):
        self.back()

    def _draw_detail(self):
        clear(self.detail_box)
        e = self.current
        inner = QWidget(); inner.setObjectName("page")
        box = QVBoxLayout(inner); box.setContentsMargins(40, 24, 40, 32); box.setSpacing(16)
        back = button("Legendas", "ghost", icon="left", slot=self.back)
        box.addLayout(hbox(back, None))
        ic = QLabel(); ic.setPixmap(icones.pixmap("pgs" if e.path.suffix.lower() == ".sup" else "file", C["accent"], 34, 1.6))
        name = label(e.path.name, "title"); name.setStyleSheet("font-size:24px;")
        name.setTextInteractionFlags(Qt.TextSelectableByMouse)
        where = label(e.place + "  ·  " + str(e.path.parent), "faint")
        where.setTextInteractionFlags(Qt.TextSelectableByMouse)
        head = hbox(ic, grow(vbox(name, where, spacing=2)),
                    button("Verificar de novo", "ghost", icon="recarregar", slot=lambda: self.recheck(e.path)),
                    button("Mostrar na pasta", icon="folder", slot=lambda: show_in_folder(e.path)), spacing=14)
        box.addLayout(head)

        if e.error:
            box.addWidget(Banner("fail", e.error))
        elif e.result is None:
            card = Card()
            card.add(hbox(Busy(), grow(label("Verificando a legenda…", "muted")), spacing=12))
            box.addWidget(card)
        else:
            self._result_cards(box, e)
        box.addStretch(1)
        self.detail_box.addWidget(scroll(inner))

    def _result_cards(self, box, e):
        v = e.result
        card = Card(tone="ok" if v.ok else "fail", spacing=12)
        head = vbox(label(v.headline, "big"), label(v.summary, "muted") if v.summary else 0, spacing=2)
        top = hbox(status_icon("ok" if v.ok else "fail", 28), grow(head), spacing=14)
        fix_now = None
        if not v.ok and acoes.pode_corrigir(v):
            fix_now = button("Corrigir agora", "primary", icon="corrigir", slot=lambda: self.open_fix.emit(e))
            fix_now.setProperty("kind", "primary")
            top.addWidget(fix_now, 0, Qt.AlignTop)
        card.add(top)
        if v.problems:
            col = QVBoxLayout(); col.setSpacing(8); col.setContentsMargins(42, 2, 0, 0)
            for item in v.problems:
                row, _ = line_with_icon("fail", item.text, size=16)
                col.addLayout(row)
            card.add(col)
            spots = [it for it in v.problems if it.spots]
            if spots:
                inner = QWidget(); ib = QVBoxLayout(inner); ib.setContentsMargins(0, 0, 0, 0); ib.setSpacing(8)
                for it in spots:
                    ib.addWidget(label(it.text, "faint"))
                    ib.addWidget(spots_view(it.spots))
                ex = Expander("Ver as falas com problema", "Esconder as falas", inner)
                ex.layout().setContentsMargins(34, 0, 0, 0)
                card.add(ex)
        if v.hint:
            tone, text = v.hint
            if tone == "fix":
                text = t("fixable") if fix_now is not None else text
            row, _ = line_with_icon(tone if tone != "fix" else "ok", text, size=18)
            row.setContentsMargins(42, 4, 0, 0)
            card.add(row)
        why = button("O que é verificado e por quê?", "ghost", icon="ajuda", slot=self.show_rules.emit)
        card.add(hbox(34, why, None))
        box.addWidget(card)
        for w in v.warnings:
            buttons = []
            if v.ok and acoes.pode_corrigir(v):
                buttons = [button("Criar uma cópia sem essas falas", slot=lambda: self.open_fix.emit(e))]
            box.addWidget(Banner("warn", w, buttons=buttons))

        actions = []
        points = sync.sync_file_for(e.path)
        if points is not None:
            actions.append(("sincronia", "Aplicar a sincronia", "O SubDrive achou ajustes de tempo que você fez no player para esta legenda. "
                            "Cria uma legenda nova com eles.", lambda: self.open_sync.emit(e, None)))
        if acoes.pode_criar_pgs(v):
            actions.append(("pgs", "Criar PGS (opcional)", "A legenda já funciona. Quer outra fonte, cor ou tamanho? "
                            "Desenha a legenda com o visual que você escolher.", lambda: self.open_pgs.emit(e)))
        if actions:
            box.addSpacing(4)
            box.addWidget(label("Mais opções" if not v.ok else "O que mais dá para fazer", "h2"))
            grid = QHBoxLayout(); grid.setSpacing(12)
            for icon_name, title, text, slot in actions:
                grid.addWidget(self._action(icon_name, title, text, slot), 1)
            if len(actions) < 2:
                grid.addStretch(1)
            box.addLayout(grid)
        elif v.ok:
            box.addWidget(label("Pronta. Coloque o arquivo na pasta legendas do pendrive para usar no player." if not e.place.startswith("Pendrive")
                                else "Pronta. O player já encontra esta legenda no pendrive.", "muted"))
        if points is None:
            more = button("Escolher um arquivo de pontos de sincronia…", "ghost", slot=lambda: self._pick_points(e))
            more.setToolTip("O player grava os ajustes de tempo na pasta sincronia do pendrive. "
                            "Use isto quando o arquivo de pontos está em outro lugar.")
            box.addSpacing(4)
            box.addLayout(hbox(label("Fez ajustes de tempo no player?", "faint", wrap=False), more, None, spacing=4))

    def _action(self, icon_name, title, text, slot):
        tile = Clickable()
        tile.setAccessibleName(title)
        b = QVBoxLayout(tile); b.setContentsMargins(18, 16, 18, 16); b.setSpacing(6)
        ic = QLabel(); ic.setPixmap(icones.pixmap(icon_name, C["accent"], 26, 1.8))
        arrow = QLabel(); arrow.setPixmap(icones.pixmap("right", C["accent"], 20, 2))
        b.addLayout(hbox(ic, None, arrow))
        tl = label(title); tl.setStyleSheet("font-size:16px;font-weight:700;")
        b.addWidget(tl)
        b.addWidget(label(text, "muted"))
        b.addStretch(1)
        tile.clicked.connect(slot)
        return tile

    def _pick_points(self, e):
        start = e.path.parent.parent / "sincronia"
        name, _ = QFileDialog.getOpenFileName(self, "Escolher o arquivo de pontos de sincronia",
                                              str(start if start.is_dir() else e.path.parent), "Pontos de sincronia (*.txt)")
        if name:
            self.open_sync.emit(e, Path(name))
