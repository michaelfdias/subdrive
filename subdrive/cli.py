"""SubDrive command line: commands and options in English, messages in Portuguese."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import VERSION, core, ui

EPILOG = """examples:
  subdrive check "Movie.srt"            is it ready for the player?
  subdrive check subtitles/             every .srt and .sup in a folder
  subdrive fix "Movie.srt" --show       fix it and show what changed
  subdrive fix "Movie.srt" --output "Movie fixed"
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


def main(argv=None):
    args = _parser().parse_args(argv)
    out = ui.Out("pt", emoji=False if args.no_emoji else None, color=False if args.no_color else None, cli=True)
    if args.command is None:
        _parser().print_help()
        return 0
    if args.command == "rules":
        ui.render_rules(out)
        return 0
    return {"check": cmd_check, "fix": cmd_fix}[args.command](args, out)


if __name__ == "__main__":
    sys.exit(main())
