"""Updates of the program and of the player package, only when the user asks.

Each version is a GitHub release with `subdrive-release.json` (what it contains and the SHA-256 of
every file) and `subdrive-release.json.sig` (its Ed25519 signature by the project). Nothing is used
unless the signature and every SHA-256 match. Only newer versions are offered; there is no going
back to an older one.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import re
import shutil
import ssl
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from . import VERSION, ed25519

REPOSITORY = "michaelfdias/subdrive"
RELEASES = "https://api.github.com/repos/%s/releases?per_page=30" % REPOSITORY
INDEX, SIGNATURE = "subdrive-release.json", "subdrive-release.json.sig"
# The project's public key. Empty until the first public version is signed: updates are then off.
PUBLIC_KEY = bytes.fromhex("")
SETTINGS = "subdrive-config.json"


class UpdateError(Exception):
    """code: offline, signature, damaged, write, unavailable"""
    def __init__(self, code, detail=""):
        super().__init__(code); self.code, self.detail = code, detail


# ---------------------------------------------------------------- versions

def version_key(v: str):
    """'1.2.0' > '1.2.0-beta.3' > '1.2.0-beta.2' > '1.1.9'."""
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?", v.strip())
    if not m:
        return None
    main = tuple(int(x) for x in m.groups()[:3])
    pre = m.group(4)
    if pre is None:
        return main + (1, ())
    parts = tuple((0, int(p)) if p.isdigit() else (1, p) for p in pre.split("."))
    return main + (0, parts)


def newer(a: str, b: str) -> bool:
    ka, kb = version_key(a), version_key(b)
    return ka is not None and kb is not None and ka > kb


# ---------------------------------------------------------------- settings (beta channel)

def settings_path(program_dir: Path) -> Path:
    return program_dir / SETTINGS


def wants_beta(program_dir: Path) -> bool:
    try:
        return bool(json.loads(settings_path(program_dir).read_text(encoding="utf-8")).get("versoes_de_teste"))
    except (OSError, ValueError):
        return False


def set_beta(program_dir: Path, on: bool):
    settings_path(program_dir).write_text(json.dumps({"versoes_de_teste": bool(on)}, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- network

def _context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch(url: str, limit=200 * 1024 * 1024, progress=None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "SubDrive/" + VERSION, "Accept": "application/octet-stream, application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=_context()) as r:
            total = int(r.headers.get("Content-Length") or 0)
            out = bytearray()
            while True:
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                out += chunk
                if len(out) > limit:
                    raise UpdateError("damaged", "too large")
                if progress and total:
                    progress(min(len(out), total), total)
            return bytes(out)
    except UpdateError:
        raise
    except Exception as e:
        raise UpdateError("offline", type(e).__name__)


# ---------------------------------------------------------------- releases

@dataclass
class Release:
    version: str
    channel: str                    # "stable" or "beta"
    notes: list
    files: dict                     # key -> {"name", "sha256", "bytes"}
    urls: dict = field(default_factory=dict)  # file name -> download URL


def read_index(data: bytes, signature: bytes, key: bytes = None) -> dict:
    key = PUBLIC_KEY if key is None else key
    if not key:
        raise UpdateError("unavailable")
    if not ed25519.verify(key, data, signature):
        raise UpdateError("signature")
    try:
        index = json.loads(data.decode("utf-8"))
    except ValueError:
        raise UpdateError("damaged", INDEX)
    if index.get("schema") != 1 or version_key(index.get("version", "")) is None or index.get("channel") not in ("stable", "beta"):
        raise UpdateError("damaged", INDEX)
    return index


def releases(get=None, key: bytes = None) -> list:
    """Every signed release published, newest first."""
    get = get or fetch
    try:
        listing = json.loads(get(RELEASES).decode("utf-8"))
    except ValueError:
        raise UpdateError("damaged", "releases")
    found = []
    for rel in listing if isinstance(listing, list) else []:
        if rel.get("draft"):
            continue
        urls = {a.get("name"): a.get("browser_download_url") for a in rel.get("assets", [])}
        if INDEX not in urls or SIGNATURE not in urls:
            continue
        try:
            index = read_index(get(urls[INDEX]), get(urls[SIGNATURE]), key)
        except UpdateError as e:
            if e.code in ("signature", "unavailable"):
                raise
            continue
        found.append(Release(index["version"], index["channel"], index.get("notes", []), index.get("files", {}), urls))
    found.sort(key=lambda r: version_key(r.version), reverse=True)
    return found


def best(found: list, current: str, beta: bool):
    """The newest version allowed by the channel, if newer than the current one."""
    for r in found:
        if r.channel == "beta" and not beta:
            continue
        return r if newer(r.version, current) else None
    return None


# ---------------------------------------------------------------- what this computer needs

def program_key():
    """The program build for this computer, as named in the release."""
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x86_64"
    system = "windows" if os.name == "nt" else "macos" if sys.platform == "darwin" else "linux"
    return "program-%s-%s" % (system, arch)


def package_key(manifest: dict):
    """The player package of the local package folder (e.g. package-panasonic-ub450-150-154-uhd)."""
    pid = manifest.get("package") or "panasonic-ub450-150-154-" + str(manifest.get("platform", "")).lower()
    return "package-" + pid


def download(release: Release, key: str, get=None, progress=None) -> bytes:
    get = get or fetch
    meta = release.files.get(key)
    if not meta or meta.get("name") not in release.urls:
        raise UpdateError("damaged", key)
    data = get(release.urls[meta["name"]], progress=progress) if progress else get(release.urls[meta["name"]])
    if len(data) != meta.get("bytes") or hashlib.sha256(data).hexdigest() != meta.get("sha256"):
        raise UpdateError("damaged", meta["name"])
    return data


def replace_program(current: Path, data: bytes):
    """Put the new program in place of the running one (Windows: the running file is renamed first)."""
    new = current.with_name(current.name + ".novo")
    new.write_bytes(data)
    if os.name != "nt":
        new.chmod(0o755)
    if os.name == "nt":
        old = current.with_name(current.name + ".antigo")
        if old.exists():
            old.unlink()
        os.replace(current, old)  # a running .exe can be renamed, not overwritten
    os.replace(new, current)


def cleanup_old_program(current: Path):
    old = current.with_name(current.name + ".antigo")
    try:
        if old.exists():
            old.unlink()
    except OSError:
        pass


def replace_package(folder: Path, data: bytes):
    """Unpack the new player package next to the old one, check it, then swap the folders."""
    from . import package
    parent = folder.parent
    tmp = Path(tempfile.mkdtemp(prefix=".subdrive-", dir=parent))
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist():
                target = (tmp / info.filename).resolve()
                if not str(target).startswith(str(tmp.resolve()) + os.sep) and target != tmp.resolve():
                    raise UpdateError("damaged", info.filename)
            z.extractall(tmp)
        package.load(tmp)  # every file checked against its manifest
        old = parent / (folder.name + ".antigo")
        if old.exists():
            shutil.rmtree(old)
        os.replace(folder, old)
        os.replace(tmp, folder)
        shutil.rmtree(old, ignore_errors=True)
    except (zipfile.BadZipFile, package.PackageError):
        raise UpdateError("damaged", "package")
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
