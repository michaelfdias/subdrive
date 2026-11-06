"""SubDrive command line: commands and options in English, messages in Portuguese."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import VERSION, core, texts, ui

EPILOG = """examples:
  subdrive check "Movie.srt"            is it ready for the player?
  subdrive check subtitles/             every .srt and .sup in a folder
  subdrive fix "Movie.srt" --show       fix it and show what changed
  subdrive fix "Movie.srt" --output "Movie fixed"
  subdrive pgs "Movie.srt"              create a PGS (soft-white, size 48, outline 2)
  subdrive pgs "Movie.srt" --color dark-yellow --font inter --bold
  subdrive sync "legendas/Movie.srt"     apply the timing adjusted on the player
  subdrive drives                       is the USB drive ready for the player?
  subdrive prepare --eject              install the package on the USB drive
  subdrive update                       look for a newer version
  subdrive rules                        what is checked and why
"""


def _parser():
    p = argparse.ArgumentParser(prog="subdrive", description="Prepare subtitles for the SubDrive player package.",
                                epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version="SubDrive " + VERSION)
    p.add_argument("--no-emoji", action="store_true", help="plain text instead of emoji")
    p.add_argument("--no-color", action="store_true", help="no colours")
    sub = p.add_subparsers(dest="command", metavar="command")
    c = sub.add_parser("check", help="check subtitle files (.srt or .sup) or a folder")
    c.add_argument("paths", nargs="+", type=Path, metavar="file-or-folder")
    c.add_argument("--show", action="store_true", help="list every subtitle with a problem")
    f = sub.add_parser("fix", help="fix a .srt so the player accepts it (saved as a new file)")
    f.add_argument("path", type=Path, metavar="file")
    f.add_argument("--output", metavar="name", help="name of the new file (default: Movie_2.srt, Movie_3.srt...)")
    f.add_argument("--show", action="store_true", help="show every change, before and after")
    f.add_argument("--remove-credits", action="store_true", help="also remove subtitles that are credits or ads")
    from . import pgs as _pgs
    g = sub.add_parser("pgs", help="create a PGS (.sup) from a .srt", formatter_class=argparse.RawDescriptionHelpFormatter,
                       epilog="colours: " + ", ".join(c[0] for c in _pgs.COLORS) + "\nfonts: " + ", ".join(f[1] for f in _pgs.FONTS))
    g.add_argument("path", type=Path, metavar="file")
    g.add_argument("--color", default="soft-white", help="colour name (default: soft-white); also sets the file suffix")
    g.add_argument("--size", type=int, default=48, help="letter size in pixels at 1080p (default: 48)")
    g.add_argument("--outline", type=float, default=2, help="outline in pixels (default: 2)")
    g.add_argument("--font", default="roboto", help="font (default: roboto)")
    g.add_argument("--bold", action="store_true", help="bold letters")
    g.add_argument("--output", metavar="name", help="name of the new file (default: Movie.<colour>.sup)")
    y = sub.add_parser("sync", help="apply the timing adjusted on the player to a .srt or .sup (saved as a new file)")
    y.add_argument("path", type=Path, metavar="file")
    y.add_argument("--points", type=Path, metavar="file", help="timing file (default: sincronia/<file name>.txt)")
    y.add_argument("--output", metavar="name", help="name of the new file (default: Movie_2.srt...)")
    sub.add_parser("drives", help="USB drives connected and whether the player can read them")
    q = sub.add_parser("prepare", help="install the player package on a USB drive")
    q.add_argument("--drive", type=Path, metavar="path", help="the drive (e.g. E:\\ or /Volumes/NAME); needed when there are several")
    q.add_argument("--package", type=Path, metavar="folder", help="the package folder (default: next to the program)")
    q.add_argument("--replace-subtitles", action="store_true", help="replace subtitles on the drive that have the same name as one in the package")
    q.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    q.add_argument("--eject", action="store_true", help="eject the drive at the end")
    u = sub.add_parser("update", help="look for a newer SubDrive and install it")
    u.add_argument("--check", action="store_true", help="only tell whether there is a newer version")
    u.add_argument("--beta", choices=("on", "off"), help="receive test versions (saved next to the program)")
    u.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    sub.add_parser("rules", help="what is checked and why")
    return p


def _expand(paths, out):
    files, missing = [], 0
    for p in paths:
        if p.is_dir():
            found = core.subtitle_files(p)
            if not found:
                out.line(out.ui("folder_empty", name=str(p)), "warn")
            files.extend(found)
        elif p.is_file():
            if p.suffix.lower() not in (".srt", ".sup"):
                out.line(out.ui("not_subtitle", name=p.name), "fail")
                missing += 1
            else:
                files.append(p)
        else:
            out.line(out.ui("not_found", name=str(p)), "fail")
            missing += 1
    return files, missing


def cmd_check(args, out):
    files, missing = _expand(args.paths, out)
    ok = 0
    for i, path in enumerate(files):
        if i:
            out.line()
        res = core.check_path(path)
        ui.render_check(out, res, args.show)
        ok += res.ok
    if len(files) > 1:
        out.line()
        out.line(out.ui("folder_summary", ok=ok, total=len(files)), "ok" if ok == len(files) else "warn")
    return 0 if files and ok == len(files) and not missing else 1


def cmd_fix(args, out):
    path = args.path
    if not path.is_file():
        out.line(out.ui("not_found", name=str(path)), "fail")
        return 2
    if path.suffix.lower() == ".sup":
        out.line(out.ui("pgs_only_check"), "info")
        return 2
    target = core.next_name(path, args.output)
    if target.exists():
        out.line(out.ui("exists", name=target.name), "fail")
        return 2
    fix = core.fix_srt(path, remove_credits=args.remove_credits)
    if fix.ok and fix.changes:
        core.write_new(target, fix.data)
        fix.output = target
    ui.render_fix(out, fix, args.show)
    return 0 if fix.ok else 1


def _seconds(ms):
    return ("%.1f" % (abs(ms) / 1000)).replace(".", ",")


def cmd_pgs(args, out):
    from . import pgs
    path = args.path
    if not path.is_file() or path.suffix.lower() != ".srt":
        out.line(out.ui("not_found" if not path.is_file() else "not_subtitle", name=str(path)), "fail")
        return 2
    col, fnt = pgs.color(args.color), pgs.font(args.font)
    if col is None:
        out.line(out.ui("bad_color", name=args.color), "fail")
        out.line(out.ui("colors_title") + " " + ", ".join(c[0] for c in pgs.COLORS), indent=3)
        return 2
    if fnt is None:
        out.line(out.ui("bad_font", name=args.font), "fail")
        out.line(out.ui("fonts_title") + " " + ", ".join(f[1] for f in pgs.FONTS), indent=3)
        return 2
    if not pgs.SIZES[0] <= args.size <= pgs.SIZES[1]:
        out.line(out.ui("bad_size", a=pgs.SIZES[0], b=pgs.SIZES[1]), "fail"); return 2
    if not pgs.OUTLINES[0] <= args.outline <= pgs.OUTLINES[1]:
        out.line(out.ui("bad_outline", a=pgs.OUTLINES[0], b=pgs.OUTLINES[1]), "fail"); return 2
    res = core.check_srt(path)
    if not res.ok:
        ui.render_check(out, res)
        out.line(out.ui("pgs_needs_fix"), "info")
        return 1
    target = core.next_name(path, args.output, tail="." + col[0] + ".sup")
    if target.exists():
        out.line(out.ui("exists", name=target.name), "fail"); return 2
    style = pgs.Style(font=fnt[1], bold=args.bold, size=args.size, outline=args.outline, fill=col[1])
    cues = pgs.cues_from_srt(path.read_bytes())
    missing = pgs.missing_letters(cues, style)
    if missing:
        out.line(out.ui("pgs_missing", font=fnt[0], chars=" ".join(missing[:12])), "fail"); return 1
    out.line(out.paint(path.name, "bold"), "file")
    out.line(out.ui("pgs_start", font=fnt[0], bold=out.ui("bold_suffix") if args.bold else "", size=args.size,
                    outline=("%g" % args.outline).replace(".", ","), color=col[0]), "pgs", 3)
    import time
    begun = time.time()
    try:
        data = pgs.convert(cues, style, progress=lambda d, t: out.progress(d, t, out.ui("progress")))
    except pgs.TooLarge as e:
        out.line(out.ui("pgs_too_large", where=out.ui("where", time=core._clock(e.start_ms))), "fail", 3); return 1
    core.write_new(target, data)
    out.line(out.ui("pgs_done", name=out.paint(target.name, "bold")), "ok", 3)
    out.line(out.paint(out.ui("pgs_stats", cues=len(cues), seconds=round(time.time() - begun),
                              mb=("%.1f" % (len(data) / 1e6)).replace(".", ",")), "dim"), indent=6)
    return 0


def cmd_sync(args, out):
    from . import sync
    path = args.path
    if not path.is_file() or path.suffix.lower() not in (".srt", ".sup"):
        out.line(out.ui("not_found" if not path.is_file() else "not_subtitle", name=str(path)), "fail")
        return 2
    points_file = args.points or sync.sync_file_for(path)
    if points_file is None or not points_file.is_file():
        out.line(out.ui("sync_none", name=path.name), "fail")
        out.line(out.ui("sync_where", name=path.name), indent=3)
        return 1
    try:
        points = sync.parse(points_file.read_text(encoding="ascii", errors="replace"))
    except sync.SyncError:
        out.line(out.ui("sync_bad_file", name=points_file.name), "fail"); return 1
    target = core.next_name(path, args.output)
    if target.exists():
        out.line(out.ui("exists", name=target.name), "fail"); return 2
    out.line(out.paint(path.name, "bold"), "file")
    try:
        data = (sync.apply_sup if path.suffix.lower() == ".sup" else sync.apply_srt)(path.read_bytes(), points)
    except sync.SyncError as e:
        out.line(out.ui("sync_order", time=e.near) if e.code == "order" else out.tr(texts.PROBLEM, "pgs_damaged"), "fail", 3)
        return 1
    except (UnicodeDecodeError, sup_reader_error()):
        out.line(out.ui("pgs_needs_fix" if path.suffix == ".srt" else "pgs_hint"), "fail", 3); return 1
    out.line(out.ui("sync_points", n=len(points)), "time", 3)
    for at, off in points:
        shift = out.ui("no_shift") if off == 0 else out.ui("earlier" if off < 0 else "later", s=_seconds(off))
        out.line(out.ui("sync_point", at=core._clock(at), shift=shift), indent=6)
    if path.suffix.lower() == ".srt":
        res = core.check_srt(target, data=data, name=target.name)
        if not res.ok:
            out.line(out.ui("sync_check"), "warn", 3)
            ui.render_check(out, res)
    core.write_new(target, data)
    out.line(out.ui("sync_done", name=out.paint(target.name, "bold")), "ok", 3)
    out.line(out.ui("sync_note"), indent=6)
    return 0


def cmd_drives(args, out):
    from . import drives, package
    found = drives.find()
    if not found:
        out.line(out.ui("drives_none"), "warn"); out.line(out.ui("drives_none_hint"), indent=3)
        return 1
    for i, d in enumerate(found):
        if i:
            out.line()
        ui.render_drive(out, d, package.installed(d.path))
        if not d.ok and "readonly" not in d.problems:
            ui.format_help(out, d)
    return 0 if any(d.ok for d in found) else 1


def _program_dir():
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path.cwd()


def cmd_prepare(args, out):
    from . import drives, package
    folder = args.package or package.find_package(_program_dir()) or package.find_package(Path.cwd())
    if folder is None:
        out.line(out.ui("package_missing"), "fail"); out.line(out.ui("package_missing_hint"), indent=3); return 2
    try:
        pkg = package.load(folder)
    except package.PackageError as e:
        out.line(out.ui("package_unknown") if e.code == "unknown" else out.ui("package_damaged", name=e.name or "manifest.json"), "fail")
        return 2
    found = drives.find()
    if args.drive:
        want = str(args.drive).rstrip("\\/").lower()
        match = [d for d in found if str(d.path).rstrip("\\/").lower() == want]
        if not match:
            out.line(out.ui("drive_missing", name=str(args.drive)), "fail"); return 2
        drive = match[0]
    else:
        usable = [d for d in found if d.ok]
        if not found:
            out.line(out.ui("drives_none"), "fail"); out.line(out.ui("drives_none_hint"), indent=3); return 1
        if len(found) > 1:
            out.line(out.ui("choose_drive"), "warn")
            for d in found:
                out.line("--drive \"%s\"  (%s)" % (d.path, d.label), indent=3)
            return 2
        drive = found[0]
    ui.render_drive(out, drive, package.installed(drive.path))
    if not drive.ok:
        if "readonly" not in drive.problems:
            ui.format_help(out, drive)
        return 1
    try:
        plan = package.plan(drive.path, pkg, args.replace_subtitles)
    except package.PackageError as e:
        out.line(out.ui("write_failed", name=e.name or str(drive.path)), "fail"); return 1
    out.line()
    out.line(out.paint(out.ui("prepare_title", label=drive.label or str(drive.path), version=pkg.version, platform=pkg.platform), "bold"), "title")
    if not plan.changes:
        out.line(out.ui("plan_nothing"), "ok", 3)
    else:
        if plan.write:
            out.line(out.ui("plan_copy", n=len(plan.write), size=ui._size(plan.needed)), indent=3)
        if plan.same:
            out.line(out.ui("plan_same", n=len(plan.same)), indent=3)
        if plan.kept:
            out.line(out.ui("plan_kept", n=len(plan.kept)), indent=3)
        if plan.stale:
            out.line(out.ui("plan_stale", n=len(plan.stale)), indent=3)
        if plan.create:
            out.line(out.ui("plan_create", names=", ".join(n + "/" for n in plan.create)), indent=3)
        out.line(out.ui("plan_keep_user"), "info", 3)
        if drive.free and plan.needed > drive.free:
            out.line(out.ui("no_space", need=ui._size(plan.needed), free=ui._size(drive.free)), "fail", 3); return 1
        if not args.yes:
            if not sys.stdin.isatty():
                out.line(out.ui("cancelled"), "info", 3); return 1
            answer = input("   " + out.ui("confirm")).strip().lower()
            if answer not in ("s", "sim", "y", "yes"):
                out.line(out.ui("cancelled"), "info", 3); return 1
        try:
            package.apply(drive.path, pkg, args.replace_subtitles, progress=lambda d, t: out.progress(d, t, out.ui("copying")))
        except package.PackageError as e:
            out.line(out.ui("verify_failed" if e.code == "verify" else "write_failed", name=e.name), "fail", 3); return 1
        except OSError:
            out.line(out.ui("write_failed", name=str(drive.path)), "fail", 3); return 1
        out.line(out.ui("prepared"), "ok", 3)
    if args.eject:
        gone = drives.eject(drive)
        out.line(out.ui("ejected" if gone else "eject_failed"), "ok" if gone else "warn", 3)
    else:
        out.line(out.ui("eject_hint"), indent=3)
    return 0


def cmd_update(args, out, ask=input):
    from . import drives, package, update
    here = _program_dir()
    if args.beta:
        update.set_beta(here, args.beta == "on")
        out.line(out.ui("beta_on" if args.beta == "on" else "beta_off"), "info")
        if args.beta == "off":
            out.line(out.ui("beta_off_note"), indent=3)
    beta = update.wants_beta(here)
    if not update.PUBLIC_KEY:
        out.line(out.ui("update_off"), "info"); return 1
    out.line(out.ui("update_searching"), "wait")
    try:
        found = update.releases()
    except update.UpdateError as e:
        out.line(out.ui("update_signature" if e.code == "signature" else "update_offline"), "fail", 3); return 1
    rel = update.best(found, VERSION, beta)
    if rel is None:
        out.line(out.ui("update_none", version=VERSION), "ok", 3); return 0
    tag = " · " + out.ui("update_beta_tag") if rel.channel == "beta" else ""
    out.line(out.paint(out.ui("update_found", new=rel.version, current=VERSION), "bold") + tag, "info", 3)
    for note in rel.notes[:12]:
        out.line("• " + note, indent=6)
    if args.check:
        return 0
    if not args.yes:
        if not sys.stdin.isatty() and ask is input:
            out.line(out.ui("cancelled"), "info", 3); return 1
        if ask("   " + out.ui("update_ask")).strip().lower() not in ("s", "sim", "y", "yes"):
            out.line(out.ui("cancelled"), "info", 3); return 1
    folder = package.find_package(here)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8")) if folder else None
    try:
        # Everything is downloaded and checked first; only then anything is replaced.
        prog = None
        if getattr(sys, "frozen", False):
            prog = update.download(rel, update.program_key(), progress=lambda d, t: out.progress(d, t, out.ui("update_downloading")))
        pack = update.download(rel, update.package_key(manifest), progress=lambda d, t: out.progress(d, t, out.ui("update_downloading"))) if manifest else None
        out.line(out.ui("update_checked"), "ok", 3)
        if pack is not None:
            update.replace_package(folder, pack)
            out.line(out.ui("update_package_done", name=str(folder)), "ok", 3)
        else:
            out.line(out.ui("update_no_package"), "info", 3)
        if prog is not None:
            update.replace_program(Path(sys.executable), prog)
            out.line(out.ui("update_program_done"), "ok", 3)
        else:
            out.line(out.ui("update_program_source"), "info", 3)
    except update.UpdateError as e:
        out.line(out.ui("update_offline") if e.code == "offline" else out.ui("update_damaged", name=e.detail), "fail", 3); return 1
    except OSError:
        out.line(out.ui("write_failed", name=str(here)), "fail", 3); return 1
    for d in drives.find():
        inst = package.installed(d.path)
        if inst and update.newer(rel.version, inst[0] or "0.0.0"):
            out.line(out.ui("update_drive_hint", label=d.label or d.path, version=inst[0]), "info", 3)
    return 0


def sup_reader_error():
    from .sup_reader import SupError
    return SupError


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    # No command (double click), or a file dragged onto the program: the Portuguese menu.
    if not argv or (len(argv) == 1 and not argv[0].startswith("-") and Path(argv[0]).is_file()):
        from . import menu
        return menu.run(Path(argv[0]) if argv else None)
    args = _parser().parse_args(argv)
    out = ui.Out("pt", emoji=False if args.no_emoji else None, color=False if args.no_color else None, cli=True)
    if args.command is None:
        _parser().print_help()
        return 0
    if args.command == "rules":
        ui.render_rules(out)
        return 0
    if getattr(sys, "frozen", False):
        from . import update
        update.cleanup_old_program(Path(sys.executable))
    return {"check": cmd_check, "fix": cmd_fix, "pgs": cmd_pgs, "sync": cmd_sync, "drives": cmd_drives,
            "prepare": cmd_prepare, "update": cmd_update}[args.command](args, out)


if __name__ == "__main__":
    sys.exit(main())
