"""Terminal output for people who are not used to terminals: short lines, one status icon each."""
from __future__ import annotations

import os
import sys

from . import texts
from .texts import t

ICONS = {"ok": ("✅", "[OK]"), "fail": ("❌", "[X]"), "warn": ("⚠️ ", "[!]"), "fix": ("🔧", "[*]"),
         "file": ("📄", "-"), "folder": ("📁", "-"), "info": ("ℹ️ ", "[i]"), "title": ("🎬", ""),
         "pgs": ("🖼️ ", "[>]"), "time": ("⏱️ ", "[>]"), "wait": ("⏳", "[..]")}


def _windows_vt() -> bool:
    """Turn on colours in the Windows console (Windows 10+); False when not possible."""
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not k.GetConsoleMode(h, ctypes.byref(mode)):
            return False
        return bool(k.SetConsoleMode(h, mode.value | 0x0004))
    except Exception:
        return False


class Out:
    def __init__(self, lang="pt", emoji=None, color=None, stream=None, cli=False):
        self.lang, self.cli = lang, cli
        self.stream = stream or sys.stdout
        if hasattr(self.stream, "reconfigure"):
            try:
                self.stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
        tty = hasattr(self.stream, "isatty") and self.stream.isatty()
        if emoji is None:
            # The old Windows console (conhost) cannot draw emoji; Windows Terminal sets WT_SESSION.
            emoji = tty and (os.name != "nt" or bool(os.environ.get("WT_SESSION") or os.environ.get("TERM_PROGRAM")))
        if color is None:
            color = tty and not os.environ.get("NO_COLOR") and (os.name != "nt" or _windows_vt())
        self.emoji, self.color = emoji, color

    def icon(self, name):
        e, plain = ICONS[name]
        return e if self.emoji else plain

    def paint(self, text, tone):
        if not self.color:
            return text
        code = {"red": "31", "green": "32", "yellow": "33", "dim": "2", "bold": "1"}[tone]
        return "\033[%sm%s\033[0m" % (code, text)

    def line(self, text="", icon=None, indent=0):
        prefix = " " * indent + (self.icon(icon) + " " if icon and self.icon(icon) else "")
        print(prefix + text, file=self.stream)

    def progress(self, done, total, label):
        """One line redrawn in place on a terminal; only the final state elsewhere."""
        tty = hasattr(self.stream, "isatty") and self.stream.isatty()
        if not tty and done < total:
            return
        width = 24; filled = width * done // max(1, total)
        bar = ("█" * filled + "░" * (width - filled)) if self.emoji else ("#" * filled + "." * (width - filled))
        text = "   %s %s  [%s] %3d%%" % (self.icon("wait"), label, bar, 100 * done // max(1, total))
        print(("\r" if tty else "") + text, end="\n" if done >= total else "", file=self.stream, flush=True)

    def tr(self, table, key, **values):
        return t(table, key, self.lang, **values)

    def ui(self, key, **values):
        # On the command line, hints name the commands and options instead of the menu.
        if self.cli and key + "_cli" in texts.UI:
            key += "_cli"
        return t(texts.UI, key, self.lang, **values)


def _count(out, n):
    return "%d %s" % (n, out.ui("subtitle" if n == 1 else "subtitles"))


def _where(out, spot):
    if spot.cue is None:
        return ""
    return out.ui("where", cue=spot.cue, time=spot.time) if spot.time else out.ui("where_cue", cue=spot.cue)


def render_check(out, res, show=False):
    out.line(out.paint(res.path.name, "bold"), "file")
    if res.ok:
        extra = "  " + out.paint(out.ui("summary", cues=res.cues, duration=res.duration), "dim") if res.cues else ""
        out.line(out.ui("ok") + extra, "ok", 3)
    else:
        out.line(out.ui("fails", n=len(res.problems)), "fail", 3)
        for p in res.problems:
            n = len(p.spots)
            detail = (": " + " ".join(p.detail)) if p.rule == "characters" and p.detail else ""
            text = out.tr(texts.PROBLEM, p.rule, n=_count(out, n) if n else "", detail=detail)
            out.line("• " + text, indent=6)
            spots = [s for s in p.spots if s.cue is not None]
            if spots and not show:
                out.line(out.paint(out.ui("at", where=_where(out, spots[0])), "dim"), indent=8)
            elif spots:
                for s in spots:
                    out.line(out.paint(_where(out, s), "dim") + ("  " + s.text if s.text else ""), indent=8)
        if res.kind == "pgs":
            out.line(out.ui("pgs_hint"), "info", 3)
        elif any(p.rule == "name" for p in res.problems):
            out.line(out.ui("name_hint"), "info", 3)
        elif res.fixable:
            out.line(out.ui("fixable") + " " + out.ui("fix_hint", name=res.path.name), "fix", 3)
        elif res.fixable is False:
            out.line(out.ui("not_fixable"), "warn", 3)
    for key, spots in res.warnings:
        if key == "credits":
            out.line(out.ui("credits", n=len(spots), text=spots[0].text), "warn", 3)


def render_fix(out, fix, show=False):
    out.line(out.paint(fix.source.name, "bold"), "file")
    if not fix.ok:
        out.line(out.ui("cannot_fix"), "fail", 3)
        for p in fix.remaining:
            spots = [s for s in p.spots if s.cue is not None]
            n = len(spots)
            out.line("• " + out.tr(texts.PROBLEM, p.rule, n=_count(out, n) if n else "", detail=""), indent=6)
            if spots:
                out.line(out.paint(out.ui("at", where=_where(out, spots[0])), "dim"), indent=8)
        out.line(out.ui("cannot_fix_hint"), "info", 3)
        return
    if not fix.changes:
        out.line(out.ui("nothing_to_fix"), "ok", 3)
        return
    out.line(out.ui("changes"), "fix", 3)
    for c in fix.changes:
        n = len([s for s in c.spots if s.cue is not None])
        label = out.tr(texts.CHANGE, c.kind)
        out.line("• " + label + (" (%s)" % _count(out, n) if n else ""), indent=6)
        if show:
            for s in c.spots:
                if s.cue is None:
                    continue
                out.line(out.paint(_where(out, s), "dim"), indent=8)
                if s.text or s.after:
                    out.line(out.paint("- " + s.text, "red"), indent=10)
                    out.line(out.paint("+ " + s.after, "green"), indent=10)
    if fix.encoding != "utf-8":
        out.line(out.ui("encoding_note", enc={"cp1252": "Windows-1252", "latin-1": "Latin-1"}.get(fix.encoding, fix.encoding)), "warn", 3)
    if fix.credits:
        out.line(out.ui("credits", n=len(fix.credits), text=fix.credits[0].text), "warn", 3)
        out.line(out.ui("credits_hint"), indent=6)
    if fix.output is not None:
        out.line(out.ui("fixed", name=out.paint(fix.output.name, "bold")), "ok", 3)
        out.line(out.ui("original_kept"), indent=6)
    if not show:
        out.line(out.paint(out.ui("show_hint"), "dim"), indent=3)


def render_rules(out):
    out.line(out.paint(out.ui("rules_title"), "bold"), "title")
    for key, (pt_title, pt_why, en_title, en_why) in texts.RULES.items():
        title, why = (pt_title, pt_why) if out.lang == "pt" else (en_title, en_why)
        out.line("• " + out.paint(title, "bold"), indent=1)
        out.line(why, indent=3)


def size_text(n):
    for unit, k in (("GB", 1e9), ("MB", 1e6), ("KB", 1e3)):
        if n >= k:
            v = n / k
            return ("%.0f %s" if v >= 10 else "%.1f %s") % (v, unit)
    return "%d B" % n


def _size(n):
    return size_text(n).replace(".", ",")


def format_help(out, drive=None):
    import os, sys
    out.line(out.ui("format_title"), "info", 3)
    key = "format_nt" if os.name == "nt" else "format_mac" if sys.platform == "darwin" else "format_linux"
    out.line(out.ui(key), indent=6)
    if os.name == "nt" and drive is not None and drive.size > 32 * 1024 ** 3:
        out.line(out.ui("format_nt_big"), indent=6)
    out.line(out.paint(out.ui("format_never"), "dim"), indent=6)


def render_drive(out, drive, installed=None):
    label = drive.label or str(drive.path)
    out.line(out.paint(out.ui("drive_line", label=label, path=str(drive.path).rstrip("\\/") or str(drive.path), size=_size(drive.size)), "bold"), "folder")
    if drive.ok:
        out.line(out.ui("drive_ok" if not drive.unknown else "drive_ok_unknown"), "ok", 3)
    else:
        for p in drive.problems:
            text = {"filesystem": out.ui("drive_filesystem", fs=drive.filesystem or "?"),
                    "scheme": out.ui("drive_scheme"), "partitions": out.ui("drive_partitions", n=drive.partitions),
                    "readonly": out.ui("drive_readonly")}[p]
            out.line(text, "fail", 3)
    if installed:
        out.line(out.ui("drive_installed", version=installed[0], platform=installed[1]), "info", 3)
