"""The menu opened by a double click: everything in Portuguese, one question at a time."""
from __future__ import annotations

import os
import re
import sys
import tempfile
from argparse import Namespace
from pathlib import Path

from . import VERSION, cli, core, drives, package, pgs, sync, ui


def clean_path(text: str) -> str:
    """A path typed or dragged into the window: quotes and the macOS/Linux escapes removed."""
    t = text.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "'\"":
        return os.path.expanduser(t[1:-1])
    if t.startswith("& '") and t.endswith("'"):  # PowerShell drag-and-drop
        return t[3:-1]
    if os.name != "nt":
        t = re.sub(r"\\(.)", r"\1", t)
    return os.path.expanduser(t)


def program_dir() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path.cwd()


def inside_zip(folder: Path) -> bool:
    """Windows can run a program straight from a ZIP: it is then a temporary copy, nothing is saved."""
    text = str(folder).lower()
    temp = str(Path(tempfile.gettempdir()).resolve()).lower()
    return ".zip" in text and (text.startswith(temp) or "\\temp" in text) or "apptranslocation" in text


class Menu:
    def __init__(self, out=None, ask=input):
        self.out = out or ui.Out("pt")
        self.ask_raw = ask

    # ------------------------------------------------------------ input helpers
    def ask(self, question, default=""):
        try:
            answer = self.ask_raw("   " + question + " ").strip()
        except EOFError:
            raise KeyboardInterrupt
        return answer or default

    def yes(self, question, default=False):
        answer = self.ask(question + (" (S/n)" if default else " (s/N)")).lower()
        return default if not answer else answer in ("s", "sim", "y", "yes")

    def pause(self):
        self.ask("Enter para voltar ao menu.")

    def choose(self, title, options, default=None):
        """options: list of labels. Returns the index, or None to go back."""
        o = self.out
        o.line(o.paint(title, "bold"), indent=1)
        for k, label in enumerate(options, 1):
            o.line("%2d  %s" % (k, label), indent=3)
        o.line(" 0  Voltar", indent=3)
        while True:
            answer = self.ask("Escolha uma opção%s:" % (" (Enter = %d)" % (default + 1) if default is not None else ""))
            if not answer and default is not None:
                return default
            if answer.isdigit() and 0 <= int(answer) <= len(options):
                return None if answer == "0" else int(answer) - 1
            o.line("Digite um dos números acima.", "warn", 3)

    # ------------------------------------------------------------ where subtitles are
    def places(self):
        """(label, folder) where subtitles can be: package, program folder, current folder, USB drives."""
        seen, out = set(), []

        def add(label, folder):
            try:
                key = folder.resolve()
            except OSError:
                return
            if folder.is_dir() and key not in seen:
                seen.add(key); out.append((label, folder))
        pkg = package.find_package(program_dir())
        if pkg:
            add("pacote baixado", pkg / "USB" / "legendas")
        for d in drives.find():
            add("pendrive %s" % (d.label or d.path), d.path / "legendas")
        for label, folder in (("pasta do programa", program_dir()), ("pasta atual", Path.cwd())):
            add(label, folder / "legendas")
            add(label, folder)
        return out

    def subtitles(self, kinds=(".srt", ".sup")):
        found = []
        for label, folder in self.places():
            try:
                found += [(label, p) for p in core.subtitle_files(folder) if p.suffix.lower() in kinds]
            except OSError:
                continue
        return found

    def pick_file(self, kinds=(".srt", ".sup"), title="Qual legenda?"):
        o = self.out
        found = self.subtitles(kinds)
        if found:
            o.line(o.paint(title, "bold"), indent=1)
            for k, (label, p) in enumerate(found, 1):
                o.line("%2d  %s  %s" % (k, p.name, o.paint("(" + label + ")", "dim")), indent=3)
            o.line("Ou arraste o arquivo para esta janela e aperte Enter.", "info", 3)
        else:
            o.line("Arraste o arquivo da legenda para esta janela e aperte Enter.", "info", 1)
        o.line(" 0  Voltar", indent=3)
        while True:
            answer = self.ask(">")
            if answer == "0" or not answer:
                return None
            if answer.isdigit() and 1 <= int(answer) <= len(found):
                return found[int(answer) - 1][1]
            p = Path(clean_path(answer))
            if p.is_file() and p.suffix.lower() in kinds:
                return p
            o.line("Não encontrei esse arquivo de legenda (%s)." % " ou ".join(kinds), "warn", 3)

    # ------------------------------------------------------------ header
    def header(self):
        o = self.out
        o.line()
        o.line(o.paint("SubDrive", "bold") + "   versão " + VERSION, "title")
        pkg = package.find_package(program_dir())
        if pkg:
            o.line("Pacote: " + str(pkg), "folder", 3)
        found = drives.find()
        if not found:
            o.line("Pendrive: nenhum conectado", "info", 3)
        for d in found:
            state = "pronto para o player" if d.ok else "precisa de ajuste (opção 6)"
            o.line("Pendrive: %s (%s) · %s" % (d.label or d.path, str(d.path).rstrip("\\/") or d.path, state), "ok" if d.ok else "warn", 3)
        o.line()

    # ------------------------------------------------------------ actions
    def check(self):
        o = self.out
        places = self.places()
        options = ["Uma legenda"] + ["Todas em: %s" % label for label, _ in places]
        k = self.choose("Verificar", options, default=0)
        if k is None:
            return
        if k == 0:
            path = self.pick_file()
            if path is None:
                return
            files = [path]
        else:
            files = core.subtitle_files(places[k - 1][1])
            if not files:
                o.line("Nenhuma legenda nessa pasta.", "info", 3); return
        details = self.yes("Mostrar cada fala com problema?")
        o.line()
        cli.cmd_check(Namespace(paths=files, show=details), o)

    def fix(self):
        o = self.out
        path = self.pick_file((".srt",))
        if path is None:
            return
        res = core.check_srt(path)
        o.line(); ui.render_check(o, res)
        if res.ok and not res.warnings:
            return
        trial = core.fix_srt(path)
        remove = bool(trial.credits) and self.yes("Remover as falas que parecem créditos ou propaganda?")
        if res.ok and not remove:
            return
        suggested = core.next_name(path).name
        name = self.ask("Nome do arquivo novo (Enter = %s):" % suggested)
        show = self.yes("Mostrar cada fala alterada?")
        o.line()
        cli.cmd_fix(Namespace(path=path, output=name or None, show=show, remove_credits=remove), o)

    def make_pgs(self):
        o = self.out
        path = self.pick_file((".srt",), "De qual SRT?")
        if path is None:
            return
        colors = ["%s (%s)" % (pt.replace("-", " "), en) for en, pt, _ in pgs.COLORS]
        c = self.choose("Cor", colors, default=1)
        if c is None:
            return
        f = self.choose("Fonte", [shown for shown, _ in pgs.FONTS], default=0)
        if f is None:
            return
        bold = self.yes("Negrito?")
        size = self._number("Tamanho da letra, de %d a %d (Enter = 48):" % pgs.SIZES, 48, *pgs.SIZES)
        outline = self._number("Contorno, de %d a %d (Enter = 2):" % pgs.OUTLINES, 2, *pgs.OUTLINES)
        o.line()
        cli.cmd_pgs(Namespace(path=path, color=pgs.COLORS[c][0], font=pgs.FONTS[f][1], bold=bold, size=size,
                              outline=outline, output=None), o)

    def _number(self, question, default, low, high):
        while True:
            answer = self.ask(question).replace(",", ".")
            if not answer:
                return default
            try:
                v = float(answer)
            except ValueError:
                v = None
            if v is not None and low <= v <= high:
                return int(v) if v == int(v) else v
            self.out.line("Use um número de %d a %d." % (low, high), "warn", 3)

    def sync(self):
        o = self.out
        with_points = [(label, p) for label, p in self.subtitles() if sync.sync_file_for(p)]
        if not with_points:
            o.line("Nenhuma legenda tem ajuste de sincronia feito no player.", "info", 1)
            o.line("No player, os ajustes ficam em sincronia/ no pendrive. Conecte o pendrive usado no player.", indent=3)
            return
        k = self.choose("Qual legenda?", ["%s  (%s)" % (p.name, label) for label, p in with_points])
        if k is None:
            return
        o.line()
        cli.cmd_sync(Namespace(path=with_points[k][1], points=None, output=None), o)

    def prepare(self):
        o = self.out
        found = drives.find()
        if not found:
            o.line(o.ui("drives_none"), "warn", 1); o.line(o.ui("drives_none_hint"), indent=3); return
        if len(found) > 1:
            k = self.choose("Qual pendrive?", ["%s (%s)" % (d.label or d.path, d.path) for d in found])
            if k is None:
                return
            drive = found[k]
        else:
            drive = found[0]
        o.line()
        code = cli.cmd_prepare(Namespace(drive=drive.path, package=None, replace_subtitles=False, yes=False, eject=False), o)
        if code == 0 and self.yes("Ejetar o pendrive agora?", default=True):
            gone = drives.eject(drive)
            o.line(o.ui("ejected" if gone else "eject_failed"), "ok" if gone else "warn", 3)

    def drives_info(self):
        self.out.line()
        cli.cmd_drives(Namespace(), self.out)

    def updates(self):
        from . import update
        o = self.out
        beta = update.wants_beta(program_dir())
        k = self.choose("Atualização", ["Procurar atualização",
                                        "Versões de teste: %s" % ("ligadas (desligar)" if beta else "desligadas (ligar, para quem quer testar novidades e enviar relatórios)")], default=0)
        if k is None:
            return
        if k == 1:
            o.line()
            cli.cmd_update(Namespace(check=True, beta="off" if beta else "on", yes=False), o, ask=self.ask_raw)
            return
        o.line()
        cli.cmd_update(Namespace(check=False, beta=None, yes=False), o, ask=self.ask_raw)

    def rules(self):
        self.out.line(); ui.render_rules(self.out)

    # ------------------------------------------------------------ main loop
    def run(self, first_file=None):
        o = self.out
        if inside_zip(program_dir()):
            o.line("O SubDrive está sendo aberto de dentro do arquivo ZIP.", "warn")
            o.line("Extraia o ZIP primeiro (botão direito → Extrair tudo) e abra o SubDrive da pasta extraída.", indent=3)
            o.line("Senão, nada do que ele gravar fica salvo.", indent=3)
            self.ask("Enter para sair.")
            return 1
        try:
            if first_file is not None:
                self.opened_with(first_file)
            while True:
                self.header()
                actions = [("Verificar legendas", self.check), ("Corrigir uma legenda", self.fix),
                           ("Criar PGS a partir de um SRT", self.make_pgs), ("Aplicar a sincronia feita no player", self.sync),
                           ("Preparar pendrive", self.prepare), ("Ver pendrives e o formato", self.drives_info),
                           ("Procurar atualização", self.updates), ("O que é verificado e por quê", self.rules)]
                for k, (label, _) in enumerate(actions, 1):
                    o.line("%d  %s" % (k, label), indent=3)
                o.line("0  Sair", indent=3)
                answer = self.ask("Escolha uma opção:")
                if answer == "0":
                    return 0
                if answer.isdigit() and 1 <= int(answer) <= len(actions):
                    o.line()
                    actions[int(answer) - 1][1]()
                    o.line(); self.pause()
                elif answer:
                    p = Path(clean_path(answer))  # a file dragged straight into the menu
                    if p.is_file():
                        self.opened_with(p)
                    else:
                        o.line("Digite um dos números do menu.", "warn", 3)
        except KeyboardInterrupt:
            o.line(); o.line("Até logo.", indent=1)
            return 0

    def opened_with(self, path: Path):
        """A file dragged onto the program or into the menu: check it, then offer what makes sense."""
        o = self.out
        o.line()
        if path.suffix.lower() not in (".srt", ".sup"):
            o.line(o.ui("not_subtitle", name=path.name), "fail"); self.pause(); return
        res = core.check_path(path)
        ui.render_check(o, res)
        options = []
        if path.suffix.lower() == ".srt":
            if not res.ok or res.warnings:
                options.append(("Corrigir", lambda: self._fix_file(path)))
            if res.ok:
                options.append(("Criar PGS", lambda: self._pgs_file(path)))
        if sync.sync_file_for(path):
            options.append(("Aplicar a sincronia feita no player", lambda: cli.cmd_sync(Namespace(path=path, points=None, output=None), o)))
        if options:
            o.line()
            k = self.choose("O que fazer com %s?" % path.name, [label for label, _ in options])
            if k is not None:
                o.line(); options[k][1]()
        o.line(); self.pause()

    def _fix_file(self, path):
        self.pick_file = lambda *a, **k: path  # reuse the questions of "Corrigir" for this file
        try:
            self.fix()
        finally:
            del self.pick_file

    def _pgs_file(self, path):
        self.pick_file = lambda *a, **k: path
        try:
            self.make_pgs()
        finally:
            del self.pick_file


def run(first_file=None):
    code = Menu().run(first_file)
    return code
