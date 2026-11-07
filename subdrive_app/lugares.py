"""Onde o programa está e onde procurar legendas.

"Ao lado do programa" é a pasta do SubDrive.exe (Windows), do SubDrive (Linux) ou do SubDrive.app (macOS):
é lá que ficam a pasta "pacote", a pasta "firmware" e o arquivo de preferências, como no SubDrive CLI.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from subdrive import drives, package

FROZEN = bool(getattr(sys, "frozen", False)) or bool(os.environ.get("SUBDRIVE_APP_BUNDLE"))


def _bundle_path():
    """O SubDrive.app em execução: o lançador próprio avisa por SUBDRIVE_APP_BUNDLE; o do PyInstaller fica em .app/Contents/MacOS."""
    bundle = os.environ.get("SUBDRIVE_APP_BUNDLE")
    if bundle:
        return bundle
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        if exe.parent.name == "MacOS" and exe.parent.parent.name == "Contents" and exe.parents[2].suffix == ".app":
            return str(exe.parents[2])
    return None


def app_bundle():
    """macOS: o SubDrive.app em execução (o lugar original, mesmo quando o macOS o isolou). Senão None."""
    bundle = _bundle_path()
    if sys.platform != "darwin" or not bundle:
        return None
    path = Path(bundle)
    original = _translocation_original(path)
    return original or path


def executable() -> Path:
    """O arquivo do programa (o que uma atualização troca)."""
    bundle = app_bundle()
    if bundle is not None:
        return bundle
    return Path(sys.executable).resolve()


def program_dir() -> Path:
    if FROZEN:
        return executable().parent
    return Path.cwd()


def _translocation_original(path: Path):
    """O macOS roda apps baixados de um lugar temporário ("App Translocation"); aqui se descobre o original."""
    if "apptranslocation" not in str(path).lower():
        return None
    try:
        import ctypes
        from ctypes import c_bool, c_char_p, c_long, c_void_p, byref
        cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        sec = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
        cf.CFURLCreateFromFileSystemRepresentation.restype = c_void_p
        cf.CFURLCreateFromFileSystemRepresentation.argtypes = [c_void_p, c_char_p, c_long, c_bool]
        cf.CFURLGetFileSystemRepresentation.restype = c_bool
        cf.CFURLGetFileSystemRepresentation.argtypes = [c_void_p, c_bool, c_char_p, c_long]
        cf.CFRelease.argtypes = [c_void_p]
        sec.SecTranslocateCreateOriginalPathForURL.restype = c_void_p
        sec.SecTranslocateCreateOriginalPathForURL.argtypes = [c_void_p, c_void_p]
        raw = os.fsencode(str(path))
        url = cf.CFURLCreateFromFileSystemRepresentation(None, raw, len(raw), True)
        if not url:
            return None
        try:
            err = c_void_p()
            original = sec.SecTranslocateCreateOriginalPathForURL(url, byref(err))
            if not original:
                return None
            try:
                buf = ctypes.create_string_buffer(4096)
                if not cf.CFURLGetFileSystemRepresentation(original, True, buf, 4096):
                    return None
                found = Path(os.fsdecode(buf.value))
                return found if found.exists() else None
            finally:
                cf.CFRelease(original)
        finally:
            cf.CFRelease(url)
    except Exception:
        return None


def inside_zip() -> bool:
    """Windows consegue rodar um programa direto de dentro do ZIP: é uma cópia temporária, nada fica salvo."""
    if not FROZEN or sys.platform == "darwin":
        return False
    text = str(program_dir()).lower()
    temp = str(Path(tempfile.gettempdir()).resolve()).lower()
    return ".zip" in text and (text.startswith(temp) or "\\temp" in text)


def translocated() -> bool:
    """macOS: isolado num lugar temporário e sem conseguir descobrir o original."""
    bundle = _bundle_path() if sys.platform == "darwin" else None
    return bool(bundle) and "apptranslocation" in bundle.lower() and _translocation_original(Path(bundle)) is None


def find_package():
    return package.find_package(program_dir())


def places(found_drives=None):
    """[(rótulo, pasta)] onde pode haver legendas: pendrives, pacote baixado e pasta do programa."""
    seen, out = set(), []

    def add(label, folder):
        try:
            key = folder.resolve()
            if not folder.is_dir() or key in seen:
                return
        except OSError:
            return
        seen.add(key)
        out.append((label, folder))
    for d in (drives.find() if found_drives is None else found_drives):
        add("Pendrive %s" % (d.label or str(d.path).rstrip("\\/")), d.path / "legendas")
    pkg = find_package()
    if pkg:
        add("Legendas que vêm com o SubDrive", pkg / "USB" / "legendas")
    here = program_dir()
    add("Pasta do programa", here / "legendas")
    add("Pasta do programa", here)
    cwd = Path.cwd()
    if not FROZEN and cwd not in (Path.home(), Path(cwd.anchor)):
        add("Pasta atual", cwd / "legendas")
    return out
