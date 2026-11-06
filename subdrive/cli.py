"""SubDrive command line: commands and options in English, messages in Portuguese."""
from __future__ import annotations

import argparse
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


def sup_reader_error():
    from .sup_reader import SupError
    return SupError


def main(argv=None):
    args = _parser().parse_args(argv)
    out = ui.Out("pt", emoji=False if args.no_emoji else None, color=False if args.no_color else None, cli=True)
    if args.command is None:
        _parser().print_help()
        return 0
    if args.command == "rules":
        ui.render_rules(out)
        return 0
    return {"check": cmd_check, "fix": cmd_fix, "pgs": cmd_pgs, "sync": cmd_sync}[args.command](args, out)


if __name__ == "__main__":
    sys.exit(main())
