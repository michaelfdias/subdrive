"""Build the player program (BDJ.jar) on the user's computer, from the player's official firmware.

The package carries only SubDrive's own classes. The player's Java library comes from the official
firmware file (checked by SHA-256); SubDrive changes two of its classes so that the player starts
SubDrive, and nothing else:

* BDJCompilerOption: at the end of its class initializer, a guarded call to SubDrivePlayer.execute()
  (the original instructions are kept byte for byte; a failure of SubDrive never stops the player);
* NativeUserEventHandler: dispatchEvent first offers the remote-control key to SubDrive, then runs
  the original method body, which is kept unchanged under another name.

Every entry of the result is compared with the list in the package manifest (the BDJ.jar tested on
the player), so the program written to the USB drive is exactly the tested one.
"""
from __future__ import annotations

import hashlib
import io
import struct
import zipfile
import zlib
from pathlib import PurePosixPath

from . import squashfs

HELPER = "com/mtk/utils/SubDrivePlayer"
OPTION = "com/mtk/utils/BDJCompilerOption.class"
EVENTS = "com/philips/bluray/event/NativeUserEventHandler.class"


class PlayerError(ValueError):
    """code: firmware, library, patch, result"""
    def __init__(self, code, detail=""):
        super().__init__(code); self.code, self.detail = code, detail


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def u2(d, o): return struct.unpack_from(">H", d, o)[0]
def u4(d, o): return struct.unpack_from(">I", d, o)[0]
def p2(x): return struct.pack(">H", x)
def p4(x): return struct.pack(">I", x)


# ---------------------------------------------------------------- firmware -> library

def library_from_firmware(blob: bytes, firmware: dict) -> bytes:
    """The official firmware ZIP -> the player's Java library (.czf), both checked by SHA-256."""
    if len(blob) != firmware["bytes"] or _sha(blob) != firmware["sha256"]:
        raise PlayerError("firmware")
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            image = z.read(firmware.get("member", "PANA_DVD.FRM"))
        lib = squashfs.SquashFS(squashfs.find_image(image)).read(firmware["library"])
    except (zipfile.BadZipFile, KeyError, squashfs.SquashError):
        raise PlayerError("library")
    if _sha(lib) != firmware["library_sha256"]:
        raise PlayerError("library")
    return lib


def read_czf(data: bytes) -> dict:
    """The library is a ZIP whose members may use method 24 (raw deflate)."""
    result, total = {}, 0
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for item in z.infolist():
            path = PurePosixPath(item.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in item.filename:
                raise PlayerError("library", "unsafe member")
            if item.is_dir():
                continue
            if item.filename in result or item.file_size > 5_000_000 or total + item.file_size > 30_000_000:
                raise PlayerError("library", "limits")
            if item.compress_type == 24:
                off = item.header_offset
                start = off + 30 + struct.unpack_from("<H", data, off + 26)[0] + struct.unpack_from("<H", data, off + 28)[0]
                obj = zlib.decompressobj(-15)
                content = obj.decompress(data[start:start + item.compress_size], item.file_size + 1)
                if not obj.eof or obj.unconsumed_tail:
                    raise PlayerError("library", "stream")
            else:
                content = z.read(item.filename)
            if len(content) != item.file_size or zlib.crc32(content) != item.CRC:
                raise PlayerError("library", "integrity")
            result[item.filename] = content; total += len(content)
    return result


# ---------------------------------------------------------------- class files

def parse_cp(data):
    count = u2(data, 8); p = 10; i = 1; utf = {}
    while i < count:
        tag = data[p]; p += 1
        if tag == 1:
            n = u2(data, p); p += 2; utf[i] = data[p:p + n].decode("utf-8"); p += n
        elif tag in (7, 8):
            p += 2
        elif tag in (3, 4, 9, 10, 11, 12):
            p += 4
        elif tag in (5, 6):
            p += 8; i += 1
        else:
            raise PlayerError("patch", "constant pool tag %d" % tag)
        i += 1
    return count, p, utf


def attributes(data, p):
    n = u2(data, p); p += 2; attrs = []
    for _ in range(n):
        start = p; name = u2(data, p); size = u4(data, p + 2); payload = p + 6; p = payload + size
        attrs.append((start, name, payload, p))
    return p, attrs


class _Pool:
    """New constant pool entries appended after the original ones."""
    def __init__(self, count):
        self.idx, self.bytes = count, bytearray()

    def entry(self, tag, payload):
        n = self.idx; self.idx += 1; self.bytes.extend(bytes([tag]) + payload); return n

    def utf8(self, s):
        b = s.encode(); return self.entry(1, p2(len(b)) + b)

    def cls(self, name):
        return self.entry(7, p2(self.utf8(name)))

    def ref(self, owner, name, desc):
        return self.entry(10, p2(owner) + p2(self.entry(12, p2(name) + p2(desc))))


def patch_option(original: bytes) -> bytes:
    """BDJCompilerOption.<clinit>: keep the original instructions, then call SubDrivePlayer.execute() inside a catch-all."""
    if u2(original, 6) != 48:
        raise PlayerError("patch", "class version")
    count, cp_end, utf = parse_cp(original)
    p = cp_end + 6; p += 2 + u2(original, p) * 2
    fields = u2(original, p); p += 2
    for _ in range(fields):
        p, _ = attributes(original, p + 6)
    found = []
    methods = u2(original, p); p += 2
    for _ in range(methods):
        name = utf[u2(original, p + 2)]; p, attrs = attributes(original, p + 6)
        if name == "<clinit>":
            found.extend(a for a in attrs if utf[a[1]] == "Code")
    if len(found) != 1:
        raise PlayerError("patch", "initializer")
    start, name, cpos, end = found[0]
    n = u4(original, cpos + 4); code = original[cpos + 8:cpos + 8 + n]
    if code[-1:] != b"\xb1" or u2(original, cpos + 8 + n) != 0:
        raise PlayerError("patch", "initializer shape")
    nested = original[cpos + 10 + n:end]
    pool = _Pool(count)
    helper = pool.cls(HELPER)
    call = pool.ref(helper, pool.utf8("execute"), pool.utf8("()V"))
    throwable = pool.cls("java/lang/Throwable")
    at = n - 1  # replaces the final `return`
    newcode = code[:-1] + b"\xb8" + p2(call) + b"\xb1\x57\xb1"
    exception = p2(at) + p2(at + 3) + p2(at + 4) + p2(throwable)
    payload = p2(max(1, u2(original, cpos))) + original[cpos + 2:cpos + 4] + p4(len(newcode)) + newcode + p2(1) + exception + nested
    newattr = p2(name) + p4(len(payload)) + payload
    return original[:8] + p2(pool.idx) + original[10:cp_end] + bytes(pool.bytes) + original[cp_end:start] + newattr + original[end:]


def patch_events(data: bytes) -> bytes:
    """NativeUserEventHandler.dispatchEvent: SubDrive sees the key first; the original body runs unchanged otherwise."""
    count, cp_end, utf = parse_cp(data)
    pool = _Pool(count)
    name_original = pool.utf8("subdriveOriginalDispatchEvent")
    name_version = pool.utf8("subdriveBridgeVersion"); desc_version = pool.utf8("()I")
    owner = pool.cls("com/philips/bluray/event/NativeUserEventHandler")
    hook = pool.ref(pool.cls(HELPER), pool.utf8("deferEvent"),
                    pool.utf8("(Lcom/philips/bluray/event/NativeUserEventHandler;Lorg/dvb/event/UserEvent;)Z"))
    throwable = pool.cls("java/lang/Throwable")
    code_name = next(k for k, v in utf.items() if v == "Code")
    p = cp_end + 6; p += 2 + u2(data, p) * 2
    fields = u2(data, p); p += 2
    for _ in range(fields):
        p, _ = attributes(data, p + 6)
    methods_at = p; num = u2(data, p); p += 2; methods = []; found = 0
    for _ in range(num):
        start = p; flags, name, desc = struct.unpack_from(">HHH", data, p); p, _ = attributes(data, p + 6)
        if utf[name] != "dispatchEvent":
            methods.append(data[start:p]); continue
        if utf[desc] != "(Lorg/dvb/event/UserEvent;)V" or flags != 4:
            raise PlayerError("patch", "dispatchEvent")
        found += 1
        methods.append(p2(1) + p2(name_original) + data[start + 4:p])  # the original, renamed and made public
        original_ref = pool.ref(owner, name_original, desc)
        code = b"\x2a\x2b\xb8" + p2(hook) + b"\x99\x00\x05\xb1\x57\x2a\x2b\xb6" + p2(original_ref) + b"\xb1"
        payload = p2(2) + p2(2) + p4(len(code)) + code + p2(1) + p2(0) + p2(5) + p2(9) + p2(throwable) + p2(0)
        methods.append(p2(flags) + p2(name) + p2(desc) + p2(1) + p2(code_name) + p4(len(payload)) + payload)
    if found != 1:
        raise PlayerError("patch", "dispatchEvent")
    payload = p2(1) + p2(0) + p4(2) + b"\x04\xac" + p2(0) + p2(0)
    methods.append(p2(9) + p2(name_version) + p2(desc_version) + p2(1) + p2(code_name) + p4(len(payload)) + payload)
    return data[:8] + p2(pool.idx) + data[10:cp_end] + bytes(pool.bytes) + data[cp_end:methods_at] + p2(num + 2) + b"".join(methods) + data[p:]


# ---------------------------------------------------------------- BDJ.jar

def build_jar(library: bytes, helpers: dict, expected: dict) -> bytes:
    """library (.czf) + SubDrive's classes -> BDJ.jar, checked entry by entry against `expected` (name -> SHA-256)."""
    entries = read_czf(library)
    if any(name in entries for name in helpers):
        raise PlayerError("patch", "name clash")
    entries[OPTION] = patch_option(entries[OPTION])
    entries[EVENTS] = patch_events(entries[EVENTS])
    entries.update(helpers)
    if set(entries) != set(expected) or any(_sha(b) != expected[n] for n, b in entries.items()):
        wrong = sorted(n for n in set(entries) | set(expected) if _sha(entries.get(n, b"")) != expected.get(n))
        raise PlayerError("result", ", ".join(wrong[:3]))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, entries[name])
    data = out.getvalue()
    with zipfile.ZipFile(io.BytesIO(data)) as z:  # read back: what goes to the drive opens and matches
        if z.testzip() is not None or any(_sha(z.read(n)) != expected[n] for n in expected):
            raise PlayerError("result", "read back")
    return data


# ---------------------------------------------------------------- the official firmware on this computer

def firmware_path(program_dir, firmware: dict):
    """Where SubDrive keeps the downloaded firmware: firmware/ next to the program."""
    return program_dir / "firmware" / firmware.get("name", "firmware.zip")


def read_firmware(path, firmware: dict):
    """The firmware file at `path`, or None when it is missing or not the expected one."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return data if len(data) == firmware["bytes"] and _sha(data) == firmware["sha256"] else None


def make_jar(pkg, firmware_blob: bytes) -> bytes:
    return build_jar(library_from_firmware(firmware_blob, pkg.firmware), pkg.helpers, pkg.jar["entries"])
