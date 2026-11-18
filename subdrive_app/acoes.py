"""O que cada botão faz, sem nada de janela: as mesmas regras e frases dos comandos do SubDrive CLI.

Cada função devolve dados (e frases prontas) para a janela mostrar. Nada aqui grava por cima de um
arquivo existente: como no CLI, cada resultado vai para um arquivo novo.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import stat
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from subdrive import VERSION, core, drives, package, pgs, player, sync, update
from subdrive.sup_reader import SupError
from subdrive.ui import size_text

from . import lugares
from .textos import change, concordar, decimal, number, problem, t


class Falha(Exception):
    """Uma frase para o usuário: algo impediu a ação (nada foi gravado)."""
    def __init__(self, message, detail=None):
        super().__init__(message); self.message, self.detail = message, detail or []


def size(n) -> str:
    return size_text(n).replace(".", ",")


def seconds(ms) -> str:
    return decimal(abs(ms) / 1000)


# ------------------------------------------------------------------ verificar

@dataclass
class Item:
    """Um problema ou mudança, com as falas onde aparece: [(onde, texto, depois)]."""
    text: str
    spots: list = field(default_factory=list)


@dataclass
class Verificacao:
    path: Path
    kind: str
    ok: bool
    headline: str
    summary: str = ""
    problems: list = field(default_factory=list)   # Item
    hint: tuple = None                             # (tom, frase)
    warnings: list = field(default_factory=list)   # frases
    fixable: bool = None
    credits: int = 0
    result: object = None


def _count(n):
    return "%s %s" % (number(n), t("subtitle" if n == 1 else "subtitles"))


def _where(spot):
    if spot.cue is None:
        return ""
    return t("where", time=spot.time) if spot.time else t("where_cue", cue=spot.cue)


def verificar(path: Path) -> Verificacao:
    """Como `SubDrive-CLI verificar`: a legenda está pronta para o player? O que falta?"""
    res = core.check_path(path)
    return descrever(res)


def descrever(res) -> Verificacao:
    v = Verificacao(path=res.path, kind=res.kind, ok=res.ok, headline="", fixable=res.fixable, result=res)
    if res.ok:
        v.headline = t("ok")
        if res.cues:
            v.summary = concordar(t("summary", cues=number(res.cues), duration=res.duration), res.cues)
    else:
        v.headline = concordar(t("fails", n=len(res.problems)), len(res.problems))
        for p in res.problems:
            n = len(p.spots)
            detail = (": " + "  ".join("“%s”" % c for c in p.detail)) if p.rule == "characters" and p.detail else ""
            item = Item(concordar(problem(p.rule, n=_count(n) if n else "", detail=detail), n))
            item.spots = [(_where(s), s.text, "") for s in p.spots if s.cue is not None]
            v.problems.append(item)
        if res.kind == "pgs":
            v.hint = ("info", t("pgs_hint"))
        elif any(p.rule == "name" for p in res.problems):
            v.hint = ("info", t("name_hint"))
        elif res.fixable:
            v.hint = ("fix", t("fixable") + " " + t("fix_hint"))
        elif res.fixable is False:
            v.hint = ("warn", t("not_fixable"))
    for key, spots in res.warnings:
        if key == "credits":
            v.credits = len(spots)
            v.warnings.append(concordar(t("credits", n=len(spots), text=spots[0].text), len(spots)))
    return v


def pode_corrigir(v: Verificacao) -> bool:
    """Igual ao menu do CLI: SRT com problema, ou com falas que parecem créditos."""
    rules = [p.rule for p in v.result.problems] if v.result is not None else []
    return v.kind == "srt" and (any(r != "name" for r in rules) or bool(v.warnings))


def pode_criar_pgs(v: Verificacao) -> bool:
    return v.kind == "srt" and v.ok


# ------------------------------------------------------------------ corrigir

@dataclass
class Correcao:
    ok: bool
    output: Path = None
    nothing: bool = False
    changes: list = field(default_factory=list)     # Item (texto + antes/depois)
    remaining: list = field(default_factory=list)   # Item
    notes: list = field(default_factory=list)       # (tom, frase)
    credits: list = field(default_factory=list)     # [(onde, texto)] que parecem créditos (mantidas)


def nome_sugerido(path: Path, tail=None) -> str:
    return core.next_name(path, tail=tail).name


def corrigir(path: Path, output: str = None, remove_credits=False, write=True) -> Correcao:
    """Como `SubDrive-CLI corrigir`: grava uma cópia corrigida e deixa o original como estava.

    Com write=False só mostra o que seria ajustado (a prévia da janela)."""
    if not path.is_file():
        raise Falha(t("not_found", name=str(path)))
    if path.suffix.lower() == ".sup":
        raise Falha(t("pgs_only_check"))
    target = _target(path, output) if write else core.next_name(path)
    if write:
        if target.exists():
            raise Falha(t("exists", name=target.name))
    fix = core.fix_srt(path, remove_credits=remove_credits)
    r = Correcao(ok=fix.ok)
    if not fix.ok:
        for p in fix.remaining:
            spots = [s for s in p.spots if s.cue is not None]
            item = Item(concordar(problem(p.rule, n=_count(len(spots)) if spots else "", detail=""), len(spots)))
            item.spots = [(_where(s), s.text, "") for s in spots]
            r.remaining.append(item)
        r.notes.append(("info", t("cannot_fix_hint")))
        return r
    if not fix.changes:
        r.nothing = True
        return r
    if write:
        core.write_new(target, fix.data)
        r.output = target
    for c in fix.changes:
        spots = [s for s in c.spots if s.cue is not None]
        label = change(c.kind) + (" (%s)" % _count(len(spots)) if spots else "")
        r.changes.append(Item(label, [(_where(s), s.text, s.after) for s in spots]))
    if fix.encoding != "utf-8":
        r.notes.append(("info", t("encoding_note", enc={"cp1252": "Windows-1252", "latin-1": "Latin-1"}.get(fix.encoding, fix.encoding))))
    r.credits = [(_where(s), s.text) for s in fix.credits]
    return r


def creditos(path: Path):
    """Falas que parecem créditos ou propaganda: [(onde, texto)] (o que "remover créditos" tiraria)."""
    try:
        trial = core.fix_srt(path)
    except Exception:
        return []
    return [(_where(s), s.text) for s in trial.credits]


def _target(path: Path, output, tail=None) -> Path:
    """O arquivo novo: o nome digitado (só um nome, na mesma pasta) ou o sugerido (Filme_2.srt...)."""
    wanted = output.strip() if output and output.strip() else None
    if wanted is not None and (any(c in wanted for c in BAD_CHARS) or not wanted.strip(". ")):
        raise Falha(BAD_NAME)
    target = core.next_name(path, wanted, tail=tail)
    _safe_name(target, path)
    return target


def _safe_name(target: Path, source: Path):
    """O nome digitado é só um nome, na mesma pasta da legenda."""
    if target.parent != source.parent or not target.name.strip(". ") or any(c in target.name for c in BAD_CHARS):
        raise Falha(BAD_NAME)


BAD_CHARS = '/\\:*?"<>|'
BAD_NAME = "Use só um nome de arquivo, sem pastas nem os símbolos / \\ : * ? \" < > |."


# ------------------------------------------------------------------ PGS

FONT_DEFAULT, COLOR_DEFAULT, SIZE_DEFAULT, OUTLINE_DEFAULT = "roboto", "soft-white", 48, 2


@dataclass
class EstiloPGS:
    color: str = COLOR_DEFAULT
    font: str = FONT_DEFAULT
    bold: bool = False
    size: int = SIZE_DEFAULT
    outline: float = OUTLINE_DEFAULT

    def style(self):
        return pgs.Style(font=pgs.font(self.font)[1], bold=self.bold, size=int(self.size), outline=float(self.outline),
                         fill=pgs.color(self.color)[1])

    def describe(self):
        return t("pgs_start", font=pgs.font(self.font)[0], bold=t("bold_suffix") if self.bold else "", size=self.size,
                 outline=("%g" % self.outline).replace(".", ","), color=pgs.color(self.color)[0])


def cor_nome(en: str) -> str:
    """'dark-yellow' -> 'amarelo escuro'."""
    for e, pt, _ in pgs.COLORS:
        if e == en:
            return pt.replace("-", " ").replace("ambar", "âmbar").replace("lilas", "lilás").replace("limao", "limão")
    return en


def amostra(path: Path, limit=3):
    """Algumas falas da legenda para a prévia do PGS: [[(texto, itálico)]] por fala."""
    try:
        cues = pgs.cues_from_srt(path.read_bytes())
    except Exception:
        return []
    good = [lines for _, _, lines in cues if lines and sum(len(t) for line in lines for t, _ in line) > 12]
    if not good:
        good = [lines for _, _, lines in cues if lines]
    if not good:
        return []
    two = [g for g in good if len(g) == 2]
    pick = (two[:1] + good[len(good) // 3:len(good) // 3 + limit])[:limit]
    return pick


@dataclass
class ResultadoPGS:
    output: Path
    cues: int
    seconds: int
    mb: str


class Cancelado(Exception):
    """A pessoa cancelou: nada foi gravado."""


def criar_pgs(path: Path, estilo: EstiloPGS, output: str = None, progress=None, cancelled=lambda: False) -> ResultadoPGS:
    """Como `SubDrive-CLI pgs`: desenha cada fala e grava um .sup novo."""
    if not path.is_file() or path.suffix.lower() != ".srt":
        raise Falha(t("not_found" if not path.is_file() else "not_subtitle", name=str(path)))
    col, fnt = pgs.color(estilo.color), pgs.font(estilo.font)
    if col is None:
        raise Falha(t("bad_color", name=estilo.color))
    if fnt is None:
        raise Falha(t("bad_font", name=estilo.font))
    if not pgs.SIZES[0] <= estilo.size <= pgs.SIZES[1]:
        raise Falha(t("bad_size", a=pgs.SIZES[0], b=pgs.SIZES[1]))
    if not pgs.OUTLINES[0] <= estilo.outline <= pgs.OUTLINES[1]:
        raise Falha(t("bad_outline", a=pgs.OUTLINES[0], b=pgs.OUTLINES[1]))
    res = core.check_srt(path)
    if not res.ok:
        raise Falha(t("pgs_needs_fix"), [p.text for p in descrever(res).problems])
    target = _target(path, output, tail="." + col[0] + ".sup")
    if target.exists():
        raise Falha(t("exists", name=target.name))
    style = estilo.style()
    cues = pgs.cues_from_srt(path.read_bytes())
    missing = pgs.missing_letters(cues, style)
    if missing:
        raise Falha(t("pgs_missing", font=fnt[0], chars=" ".join(missing[:12])))
    begun = time.time()
    try:
        data = pgs.convert(cues, style, progress=progress)
    except pgs.TooLarge as e:
        raise Falha(t("pgs_too_large", where=t("where", time=core._clock(e.start_ms))))
    if cancelled():
        raise Cancelado()
    core.write_new(target, data)
    return ResultadoPGS(target, len(cues), round(time.time() - begun), decimal(len(data) / 1e6))


# ------------------------------------------------------------------ sincronia

@dataclass
class Sincronia:
    path: Path
    points_file: Path
    points: list            # [(ms do filme, deslocamento ms)]
    lines: list             # frases "em 00:10:00: 0,5 s mais cedo"


def pontos(path: Path, points_file: Path = None) -> Sincronia:
    """Os pontos de ajuste feitos no player para esta legenda (sem gravar nada)."""
    if not path.is_file() or path.suffix.lower() not in (".srt", ".sup"):
        raise Falha(t("not_found" if not path.is_file() else "not_subtitle", name=str(path)))
    points_file = points_file or sync.sync_file_for(path)
    if points_file is None or not points_file.is_file():
        raise Falha(t("sync_none", name=path.name), [t("sync_where", name=path.name)])
    try:
        points = sync.parse(points_file.read_text(encoding="ascii", errors="replace"))
    except sync.SyncError:
        raise Falha(t("sync_bad_file", name=points_file.name))
    lines = []
    for at, off in points:
        shift = t("no_shift") if off == 0 else t("earlier" if off < 0 else "later", s=seconds(off))
        lines.append(t("sync_point", at=core._clock(at), shift=shift))
    return Sincronia(path, points_file, points, lines)


@dataclass
class ResultadoSincronia:
    output: Path
    warning: Verificacao = None


def sincronizar(s: Sincronia, output: str = None) -> ResultadoSincronia:
    """Como `SubDrive-CLI sincronizar`: grava a legenda com os tempos já ajustados."""
    path = s.path
    target = _target(path, output)
    if target.exists():
        raise Falha(t("exists", name=target.name))
    try:
        data = (sync.apply_sup if path.suffix.lower() == ".sup" else sync.apply_srt)(path.read_bytes(), s.points)
    except sync.SyncError as e:
        raise Falha(t("sync_order", time=e.near) if e.code == "order" else problem("pgs_damaged"))
    except (UnicodeDecodeError, SupError):
        raise Falha(t("pgs_needs_fix" if path.suffix.lower() == ".srt" else "pgs_hint"))
    warning = None
    if path.suffix.lower() == ".srt":
        res = core.check_srt(target, data=data, name=target.name)
        if not res.ok:
            warning = descrever(res)
    core.write_new(target, data)
    return ResultadoSincronia(target, warning)


# ------------------------------------------------------------------ pendrives

@dataclass
class EstadoPendrive:
    drive: object
    title: str
    ok: bool
    lines: list           # (tom, frase)
    installed: str = ""
    format_help: list = field(default_factory=list)
    technical: list = field(default_factory=list)


def descrever_pendrive(d) -> EstadoPendrive:
    """Como `SubDrive-CLI pendrives`, para um pendrive."""
    label = d.label or str(d.path)
    title = t("drive_line", label=label, path=str(d.path).rstrip("\\/") or str(d.path), size=size(d.size))
    lines, technical = [], []
    if d.ok:
        lines.append(("ok", t("drive_ok" if not d.unknown else "drive_ok_unknown").replace("Formato FAT32, uma partição. ", "")))
        technical.append(t("drive_ok" if not d.unknown else "drive_ok_unknown"))
    else:
        if "readonly" in d.problems:
            lines.append(("fail", t("drive_readonly")))
        if any(p != "readonly" for p in d.problems):
            lines.append(("fail", t("drive_needs_format")))
        for p in d.problems:
            if p != "readonly":
                technical.append({"filesystem": t("drive_filesystem", fs=d.filesystem or "?"), "scheme": t("drive_scheme"),
                                  "partitions": t("drive_partitions", n=d.partitions)}[p])
    inst = package.installed(d.path)
    e = EstadoPendrive(d, title, d.ok, lines, t("drive_installed", version=inst[0], platform=inst[1]) if inst else "")
    e.technical = technical
    if not d.ok and "readonly" not in d.problems:
        e.format_help = como_formatar(d)
    return e


def como_formatar(d=None):
    key = "format_nt" if os.name == "nt" else "format_mac" if sys.platform == "darwin" else "format_linux"
    steps = [t(key)]
    if os.name == "nt" and d is not None and d.size > 32 * 1024 ** 3:
        steps.append(t("format_nt_big"))
    return steps


def ejetar(d) -> bool:
    return drives.eject(d)


# ------------------------------------------------------------------ preparar

def carregar_pacote(folder: Path = None):
    """O pacote do player: o escolhido, ou o que está ao lado do programa."""
    folder = folder or lugares.find_package()
    if folder is None:
        raise Falha(t("package_missing"), [t("package_missing_hint")])
    try:
        return package.load(folder)
    except package.PackageError as e:
        raise Falha(t("package_unknown") if e.code in ("unknown", "missing") else t("package_damaged", name=e.name or "manifest.json"))


def aviso_firmware(pkg) -> str:
    fw = pkg.firmware
    region = fw.get("region", "US")
    region = t("region_" + region) if region == "US" else region
    return t("firmware_check", version=fw.get("version", "?"), region=region)


def confirmar_firmware(pkg) -> str:
    fw = pkg.firmware
    region = fw.get("region", "US")
    region = t("region_" + region) if region == "US" else region
    return t("firmware_confirm", version=fw.get("version", "?"), region=region)


def firmware_guardado(pkg):
    """O firmware já baixado (pasta firmware/ ao lado do programa), ou None."""
    return player.read_firmware(player.firmware_path(lugares.program_dir(), pkg.firmware), pkg.firmware)


def firmware_escolhido(pkg, path: Path) -> bytes:
    blob = player.read_firmware(path, pkg.firmware)
    if blob is None:
        raise Falha(t("firmware_wrong", name=pkg.firmware.get("name", ""), version=pkg.firmware.get("version", "")))
    return blob


def baixar_firmware(pkg, progress=None) -> bytes:
    fw = pkg.firmware
    try:
        blob = update.fetch(fw["url"], limit=fw["bytes"] + 1, progress=progress)
    except update.UpdateError:
        raise Falha(t("firmware_offline"), [t("firmware_manual", name=fw.get("name", ""))])
    if len(blob) != fw["bytes"] or player._sha(blob) != fw["sha256"]:
        raise Falha(t("firmware_wrong", name=fw.get("name", ""), version=fw.get("version", "")))
    try:
        cache = player.firmware_path(lugares.program_dir(), fw)
        cache.parent.mkdir(exist_ok=True)
        cache.write_bytes(blob)
    except OSError:
        pass  # guardar uma cópia é só para não baixar de novo
    return blob


def montar_programa(pkg, blob: bytes):
    """BDJ.jar a partir do firmware oficial, conferido parte por parte."""
    try:
        pkg.files["BDJ.jar"] = player.make_jar(pkg, blob)
    except player.PlayerError as e:
        raise Falha(t("jar_failed", detail=e.code))


@dataclass
class Plano:
    title: str
    lines: list          # frases
    nothing: bool
    kept: int
    error: str = ""
    plan: object = None


def planejar(d, pkg, replace_subtitles=False) -> Plano:
    try:
        plan = package.plan(d.path, pkg, replace_subtitles)
    except package.PackageError as e:
        raise Falha(t("write_failed", name=e.name or str(d.path)))
    title = t("prepare_title", label=d.label or str(d.path), version=pkg.version, platform=pkg.platform)
    p = Plano(title, [], not plan.changes, len(plan.kept), plan=plan)
    if plan.write:
        p.lines.append(t("plan_copy", n=len(plan.write), size=size(plan.needed)))
    if plan.same:
        p.lines.append(t("plan_same", n=len(plan.same)))
    if plan.kept:
        p.lines.append(t("plan_kept", n=len(plan.kept)))
    if plan.stale:
        p.lines.append(t("plan_stale", n=len(plan.stale)))
    if plan.create:
        p.lines.append(t("plan_create", names=", ".join(n + "/" for n in plan.create)))
    p.lines = [_plural(x) for x in p.lines]
    if plan.changes and d.free and plan.needed > d.free:
        p.error = t("no_space", need=size(plan.needed), free=size(d.free))
    return p


def _plural(text):
    """'1 arquivo(s) para copiar' -> '1 arquivo para copiar'; '3 arquivo(s)' -> '3 arquivos'."""
    import re
    one = re.match(r"^1 ", text) is not None
    return re.sub(r"\(s\)", "" if one else "s", text).replace("estão iguais", "está igual" if one else "estão iguais") \
        .replace("serão apagados", "será apagado" if one else "serão apagados").replace("mantidas como estão", "mantida como está" if one else "mantidas como estão")


def gravar(d, pkg, replace_subtitles=False, progress=None):
    try:
        package.apply(d.path, pkg, replace_subtitles, progress=progress)
    except package.PackageError as e:
        raise Falha(t("verify_failed" if e.code == "verify" else "write_failed", name=e.name))
    except OSError:
        raise Falha(t("write_failed", name=str(d.path)))


# ------------------------------------------------------------------ atualizar

def app_key():
    """O programa com janelas deste computador, como aparece no índice assinado de cada versão."""
    return "app-" + update.program_key()[len("program-"):]


def procurar_atualizacao():
    """A versão mais nova permitida pelo canal (estável ou de teste), ou None."""
    if not update.PUBLIC_KEY:
        raise Falha(t("update_off"))
    try:
        found = update.releases()
    except update.UpdateError as e:
        raise Falha(t("update_signature" if e.code == "signature" else "update_offline"))
    return update.best(found, VERSION, update.wants_beta(lugares.program_dir()))


def notas(rel):
    return [n for n in rel.notes[:12]]


@dataclass
class ResultadoAtualizacao:
    lines: list = field(default_factory=list)       # (tom, frase)
    restart: bool = False
    drives_behind: list = field(default_factory=list)


def atualizar(rel, progress=None) -> ResultadoAtualizacao:
    """Baixa e confere tudo antes; só depois troca o pacote e o programa (como `SubDrive-CLI atualizar`)."""
    here = lugares.program_dir()
    folder = package.find_package(here)
    try:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8")) if folder else None
    except (OSError, ValueError):
        manifest = None
    out = ResultadoAtualizacao()
    try:
        prog = None
        has_program = lugares.FROZEN and app_key() in rel.files
        if has_program:
            prog = update.download(rel, app_key(), progress=progress)
        pack = update.download(rel, update.package_key(manifest), progress=progress) if manifest else None
        if prog is None and pack is None:
            raise Falha(t("update_no_program") if lugares.FROZEN else t("update_nothing_here"))
        out.lines.append(("ok", t("update_checked")))
        if pack is not None:
            update.replace_package(folder, pack)
            out.lines.append(("ok", t("update_package_done", name=str(folder))))
        else:
            out.lines.append(("info", t("update_no_package")))
        if prog is not None:
            replace_program(prog)
            out.lines.append(("ok", t("update_program_done")))
            out.restart = True
        elif lugares.FROZEN:
            out.lines.append(("info", t("update_no_program")))
        else:
            out.lines.append(("info", t("update_program_source")))
    except update.UpdateError as e:
        raise Falha(t("update_offline") if e.code == "offline" else t("update_damaged", name=e.detail))
    except OSError:
        raise Falha(t("write_failed", name=str(here)))
    for d in drives.find():
        inst = package.installed(d.path)
        if inst and update.newer(rel.version, inst[0] or "0.0.0"):
            out.drives_behind.append(t("update_drive_hint", label=d.label or d.path, version=inst[0]))
    return out


def replace_program(data: bytes):
    """Windows e Linux: troca o executável (como o CLI). macOS: troca o SubDrive.app inteiro (o download é um ZIP dele)."""
    current = lugares.executable()
    if current.suffix != ".app":
        update.replace_program(current, data)
        return
    parent = current.parent
    tmp = Path(tempfile.mkdtemp(prefix=".subdrive-", dir=parent))
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            extract(z, tmp)
        apps = [p for p in tmp.iterdir() if p.suffix == ".app" and (p / "Contents" / "Info.plist").is_file()]
        if len(apps) != 1:
            raise update.UpdateError("damaged", "app")
        old = current.with_name(current.name + ".antigo")
        if old.exists():
            shutil.rmtree(old, ignore_errors=True)
        os.replace(current, old)
        os.replace(apps[0], current)
        shutil.rmtree(old, ignore_errors=True)
    except (zipfile.BadZipFile, KeyError):
        raise update.UpdateError("damaged", "app")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def extract(z: zipfile.ZipFile, dest: Path):
    """Extrai mantendo a permissão de executar e os atalhos (links) de dentro do app."""
    root = dest.resolve()
    for info in z.infolist():
        target = (dest / info.filename).resolve()
        if root not in target.parents and target != root:
            raise update.UpdateError("damaged", info.filename)
        mode = info.external_attr >> 16
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if stat.S_ISLNK(mode):
            link = z.read(info).decode("utf-8")
            if os.path.isabs(link) or root not in (target.parent / link).resolve().parents:
                raise update.UpdateError("damaged", info.filename)
            os.symlink(link, target)
            continue
        with z.open(info) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)
        if mode & 0o111:
            target.chmod(0o755)


def limpar_programa_antigo():
    """Depois de uma atualização: apaga a cópia antiga do programa, se ficou alguma."""
    if not lugares.FROZEN:
        return
    current = lugares.executable()
    if current.suffix == ".app":
        old = current.with_name(current.name + ".antigo")
        if old.exists():
            shutil.rmtree(old, ignore_errors=True)
    else:
        update.cleanup_old_program(current)


def versoes_de_teste() -> bool:
    return update.wants_beta(lugares.program_dir())


def mudar_versoes_de_teste(on: bool):
    try:
        update.set_beta(lugares.program_dir(), on)
    except OSError:
        raise Falha(t("write_failed", name=str(update.settings_path(lugares.program_dir()))))
