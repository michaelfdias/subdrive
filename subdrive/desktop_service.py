"""Desktop orchestration; subtitle/player rules remain in the upstream engine."""
from __future__ import annotations

import io
import json
import sys
from argparse import Namespace
from pathlib import Path

from . import VERSION, cli, core, drives, package, ui, update


def program_dir():
    here = cli._program_dir()
    if sys.platform == "darwin" and getattr(sys, "frozen", False):
        for parent in here.parents:
            if parent.suffix == ".app":
                return parent.parent
    return here


class Output(ui.Out):
    def __init__(self, emit, progress):
        super().__init__(emoji=False, color=False, stream=io.StringIO())
        self.emit, self.report_progress = emit, progress

    def line(self, text="", icon=None, indent=0):
        self.emit(str(text))

    def progress(self, done, total, label="Processando…"):
        self.report_progress(done, total, label)


def subtitle_action(action, paths, options, out):
    if not paths:
        raise ValueError("Escolha uma legenda ou pasta primeiro.")
    args = dict(show=False, output=None, remove_credits=False, points=None,
                color="soft-white", font="roboto", bold=False, size=48, outline=2)
    args.update(options)
    if action == "check":
        return cli.cmd_check(Namespace(paths=paths, **args), out)
    if len(paths) != 1 or not paths[0].is_file():
        raise ValueError("Para esta ação, escolha apenas um arquivo de legenda.")
    if action in ("fix", "pgs") and paths[0].suffix.lower() != ".srt":
        raise ValueError("Esta ação usa uma legenda SRT. Arquivos SUP podem ser verificados ou sincronizados.")
    code = {"fix": cli.cmd_fix, "pgs": cli.cmd_pgs, "sync": cli.cmd_sync}[action](
        Namespace(path=paths[0], **args), out)
    if code == 0:
        out.line("Pasta de destino: " + str(paths[0].parent.resolve()))
    return code


def prepare_preview(folder, target, replace, firmware, out):
    """Read and build first; never write a USB drive before a reviewed plan."""
    pkg = package.load(folder)
    candidates = [d for d in drives.find() if d.path == target]
    if not candidates:
        raise ValueError("O pendrive foi desconectado. Reconecte e procure novamente.")
    drive = candidates[0]
    ui.render_drive(out, drive, package.installed(target))
    if not drive.ok:
        ui.format_help(out, drive)
        raise ValueError("O pendrive precisa de ajuste. Veja as orientações abaixo.")
    if not cli._player_program(Namespace(firmware=firmware, yes=True), pkg, out):
        raise ValueError("Não foi possível preparar o programa do player. Confira o firmware e tente novamente.")
    plan = package.plan(target, pkg, replace)
    if drive.free and plan.needed > drive.free:
        raise ValueError("Não há espaço suficiente no pendrive.")
    return drive, pkg, plan


def prepare_apply(preview, replace, eject, out):
    drive, pkg, _ = preview
    # Recheck the device after the confirmation dialog; never choose another USB.
    found = [d for d in drives.find() if d.path == drive.path and d.device == drive.device]
    if not found or not found[0].ok:
        raise ValueError("O pendrive mudou ou foi desconectado. Confira o destino novamente.")
    package.apply(drive.path, pkg, replace, progress=out.progress)
    out.line("Pendrive preparado e arquivos verificados.")
    if eject:
        if not drives.eject(drive):
            raise ValueError("Os arquivos foram copiados, mas não foi possível ejetar. Ejete pelo sistema antes de retirar.")
        out.line("Pendrive ejetado. Pode retirar com segurança.")
    else:
        out.line("Ejete o pendrive pelo sistema antes de retirar.")
    return 0


def find_update(folder, beta, settings, out):
    update.set_beta(settings, beta)
    releases = update.releases()
    current = VERSION
    if folder:
        current = package.load(folder).version or VERSION
    rel = update.best(releases, current, beta)
    if rel:
        out.line("Versão disponível: " + rel.version)
        for note in rel.notes:
            out.line(str(note))
    else:
        out.line("Você já tem a versão mais recente neste canal.")
    return rel


def install_update(rel, folder, out):
    # Original program-* assets are TERMINAL binaries. A GUI must never install them.
    desktop_key = update.program_key().replace("program-", "desktop-")
    prog = update.download(rel, desktop_key, progress=out.progress) if getattr(sys, "frozen", False) and desktop_key in rel.files else None
    pack = None
    if folder:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        pack = update.download(rel, update.package_key(manifest), progress=out.progress)
    if prog is None and pack is None:
        raise ValueError("Esta versão não contém uma edição gráfica assinada. Selecione um pacote do player para atualizar o pacote.")
    if pack is not None:
        update.replace_package(folder, pack)
        out.line("Pacote do player atualizado. Prepare o pendrive novamente para copiar a atualização.")
    if prog is not None:
        update.replace_program(Path(sys.executable), prog)
        out.line("Aplicativo atualizado. Feche e abra novamente.")
    else:
        out.line("A edição gráfica não foi alterada: não há um executável desktop assinado nesta versão.")
    return 0
