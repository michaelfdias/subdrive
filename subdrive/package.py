"""Install the player package on a USB drive (or check one that is already prepared).

Package folder: manifest.json, player/ (SubDrive's player code) and USB/ (files for the drive).
BDJ.jar is built on this computer (subdrive.player) before installing. The user's own subtitles, timing adjustments, preferences and reports are never removed or replaced.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

FOLDERS = ("legendas", "relatorios", "sincronia", "fontes")
NAME = re.compile(r"^[^/\\:.][^/\\:]{0,123}\.(srt|sup)$")
FONT_NAME = re.compile(r"^[a-z0-9-]{1,40}\.letras$|^LICENCAS\.txt$")


class PackageError(ValueError):
    """code: missing, damaged, unknown"""
    def __init__(self, code, name=""):
        super().__init__(code); self.code, self.name = code, name


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def safe_subtitle_name(name):
    return bool(NAME.match(name)) and all(32 <= ord(c) <= 126 or 160 <= ord(c) <= 255 for c in name)


@dataclass
class Package:
    folder: Path
    version: str
    platform: str           # "BD" or "UHD"
    files: dict             # path on the drive -> bytes (BDJ.jar only once built)
    package_id: str = ""
    models: list = field(default_factory=list)
    firmware: dict = field(default_factory=dict)  # official firmware the player program is built from
    jar: dict = field(default_factory=dict)       # expected BDJ.jar entries (name -> SHA-256)
    helpers: dict = field(default_factory=dict)   # SubDrive's player classes (JAR path -> bytes)

    @property
    def size(self):
        return sum(len(b) for b in self.files.values())

    @property
    def needs_jar(self):
        return "BDJ.jar" not in self.files


def _drive_name_ok(name):
    parts = name.split("/")
    return (name == "BDJ_DEBUG" or (len(parts) == 2 and parts[0] == "legendas" and safe_subtitle_name(parts[1]))
            or (len(parts) == 2 and parts[0] == "fontes" and FONT_NAME.match(parts[1])))


def load(folder: Path) -> Package:
    """A package folder: manifest.json, player/classes/ (SubDrive's player code) and USB/ (drive files)."""
    m = folder / "manifest.json"
    if not m.is_file():
        raise PackageError("missing")
    try:
        manifest = json.loads(m.read_text(encoding="utf-8"))
    except ValueError:
        raise PackageError("damaged", "manifest.json")
    if manifest.get("formato") != "subdrive-pacote-1" or manifest.get("platform") not in ("BD", "UHD"):
        raise PackageError("unknown")
    fw, jar = manifest.get("firmware") or {}, manifest.get("jar") or {}
    if not all(k in fw for k in ("url", "sha256", "bytes", "library", "library_sha256")) or not jar.get("entries"):
        raise PackageError("damaged", "manifest.json")
    files, helpers = {}, {}
    for name, meta in manifest.get("files", {}).items():
        if name.startswith("USB/") and _drive_name_ok(name[4:]):
            target = files; key = name[4:]
        elif name.startswith("player/classes/com/mtk/utils/SubDrivePlayer") and name.endswith(".class") and ".." not in name:
            target = helpers; key = name[len("player/classes/"):]
        else:
            raise PackageError("damaged", name)
        p = folder / name
        if p.is_symlink() or not p.is_file():
            raise PackageError("damaged", name)
        b = p.read_bytes()
        if len(b) != meta.get("bytes") or _sha(b) != meta.get("sha256"):
            raise PackageError("damaged", name)
        target[key] = b
    if files.get("BDJ_DEBUG") != b"" or not helpers or set(helpers) - set(jar["entries"]):
        raise PackageError("damaged", "player")
    return Package(folder, manifest.get("version", ""), manifest["platform"], files, manifest.get("package", ""),
                   manifest.get("models", []), fw, jar, helpers)


def find_package(start: Path):
    """The package next to the program (or in the given folder): itself, pacote/ or its parent."""
    for p in (start, start / "pacote", start.parent, start.parent / "pacote"):
        if (p / "manifest.json").is_file() and (p / "player").is_dir():
            return p
    return None


def installed(target: Path):
    """Version and platform already on the drive, or None."""
    m = target / "subdrive.json"
    try:
        d = json.loads(m.read_text(encoding="utf-8"))
        return d.get("version"), d.get("platform")
    except (OSError, ValueError):
        return None


@dataclass
class Plan:
    write: list = field(default_factory=list)   # files copied (new or updated)
    same: list = field(default_factory=list)    # already identical
    kept: list = field(default_factory=list)    # user's subtitle with the same name: kept as it is
    stale: list = field(default_factory=list)   # letter files of an older package: removed
    create: list = field(default_factory=list)  # folders created
    needed: int = 0                             # bytes to write

    @property
    def changes(self):
        return bool(self.write or self.stale or self.create)


def _stale(target: Path, pkg: Package):
    folder = target / "fontes"
    if not folder.is_dir() or folder.is_symlink() or not any(n.startswith("fontes/") for n in pkg.files):
        return []
    return [p for p in sorted(folder.iterdir()) if p.is_file() and not p.is_symlink() and p.suffix == ".letras"
            and ("fontes/" + p.name) not in pkg.files]


def plan(target: Path, pkg: Package, replace_subtitles=False) -> Plan:
    if not target.is_dir() or target.is_symlink():
        raise PackageError("target")
    for name in FOLDERS:
        p = target / name
        if p.is_symlink() or (p.exists() and not p.is_dir()):
            raise PackageError("target", name)
    r = Plan()
    for name in FOLDERS:
        if not (target / name).is_dir() and (name != "fontes" or any(n.startswith("fontes/") for n in pkg.files)):
            r.create.append(name)
    for name, b in pkg.files.items():
        p = target / name
        if p.is_symlink():
            raise PackageError("target", name)
        if p.is_file() and _sha(p.read_bytes()) == _sha(b):
            r.same.append(name)
        elif p.exists() and name.startswith("legendas/") and not replace_subtitles:
            r.kept.append(name)
        else:
            r.write.append(name); r.needed += len(b)
    r.stale = _stale(target, pkg)
    return r


def _atomic_write(p: Path, b: bytes):
    if p.is_symlink() or p.parent.is_symlink():
        raise PackageError("target", p.name)
    fd, tmp = tempfile.mkstemp(prefix=".subdrive-", dir=p.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(b); f.flush(); os.fsync(f.fileno())
        if _sha(Path(tmp).read_bytes()) != _sha(b):
            raise PackageError("write", p.name)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def apply(target: Path, pkg: Package, replace_subtitles=False, progress=None) -> Plan:
    r = plan(target, pkg, replace_subtitles)
    for name in FOLDERS:
        if name in r.create:
            (target / name).mkdir(exist_ok=True)
    # The player program goes last: a half-copied drive never starts a new version with old files.
    order = [n for n in r.write if n not in ("BDJ.jar", "BDJ_DEBUG")] + [n for n in ("BDJ_DEBUG", "BDJ.jar") if n in r.write]
    for k, name in enumerate(order, 1):
        _atomic_write(target / name, pkg.files[name])
        if progress:
            progress(k, len(order))
    for p in r.stale:
        p.unlink()
    _atomic_write(target / "subdrive.json", json.dumps({"version": pkg.version, "platform": pkg.platform}).encode() + b"\n")
    verify(target, pkg, r.kept)
    return r


def verify(target: Path, pkg: Package, kept=()):
    """Every package file is on the drive, byte for byte (except subtitles the user kept)."""
    for name in FOLDERS:
        if name == "fontes" and not any(n.startswith("fontes/") for n in pkg.files):
            continue
        p = target / name
        if not p.is_dir() or p.is_symlink():
            raise PackageError("verify", name)
    for name, b in pkg.files.items():
        if name in kept:
            continue
        p = target / name
        if p.is_symlink() or not p.is_file() or _sha(p.read_bytes()) != _sha(b):
            raise PackageError("verify", name)
