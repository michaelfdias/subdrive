"""USB drives on Windows, macOS and Linux, and whether the player can read them.

The player reads the first partition of the drive, formatted as FAT32, on a drive with MBR
partitioning and a single partition. Nothing here formats or writes anything.
"""
from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Drive:
    path: Path              # where it is mounted (E:\\, /Volumes/NAME, /media/user/NAME)
    label: str = ""
    size: int = 0           # bytes
    free: int = 0
    filesystem: str = ""    # "FAT32", "exFAT", "NTFS", ...
    scheme: str = ""        # "MBR", "GPT" or "" when unknown
    partitions: int = 0     # 0 = unknown
    removable: bool = True
    device: str = ""        # system name, for ejecting
    problems: list = field(default_factory=list)  # "filesystem", "scheme", "partitions", "readonly"
    unknown: list = field(default_factory=list)   # checks that could not be made on this system
    readonly: bool = False

    def judge(self):
        self.problems = []
        if self.filesystem.upper() != "FAT32":
            self.problems.append("filesystem")
        if self.scheme and self.scheme != "MBR":
            self.problems.append("scheme")
        elif not self.scheme:
            self.unknown.append("scheme")
        if self.partitions > 1:
            self.problems.append("partitions")
        elif not self.partitions:
            self.unknown.append("partitions")
        if self.readonly:
            self.problems.append("readonly")
        return self

    @property
    def ok(self):
        return not self.problems


def _run(args, timeout=15):
    return subprocess.run(args, capture_output=True, timeout=timeout, check=True).stdout


# ---------------------------------------------------------------- macOS

def _mac(run=_run):
    found = []
    volumes = Path("/Volumes")
    for v in sorted(volumes.iterdir()) if volumes.is_dir() else []:
        if v.is_symlink() or not v.is_dir():
            continue
        try:
            d = plistlib.loads(run(["diskutil", "info", "-plist", str(v)]))
        except Exception:
            continue
        if d.get("Internal", d.get("DeviceInternal", True)) is not False:
            continue
        fs = d.get("FilesystemName", "") or d.get("FilesystemType", "")
        drive = Drive(path=v, label=d.get("VolumeName", v.name), size=d.get("TotalSize", 0) or d.get("Size", 0),
                      free=d.get("FreeSpace", 0) or d.get("APFSContainerFree", 0),
                      filesystem="FAT32" if "FAT32" in fs.upper() else fs.replace("MS-DOS ", "").strip(),
                      removable=d.get("BusProtocol") == "USB", device=d.get("DeviceIdentifier", ""),
                      readonly=bool(d.get("ReadOnlyMedia") or d.get("ReadOnlyVolume")))
        parent = d.get("ParentWholeDisk")
        try:
            layout = plistlib.loads(run(["diskutil", "list", "-plist", parent])).get("AllDisksAndPartitions", [])
            content = layout[0].get("Content", "") if layout else ""
            drive.scheme = {"FDisk_partition_scheme": "MBR", "GUID_partition_scheme": "GPT"}.get(content, "")
            drive.partitions = len(layout[0].get("Partitions", [])) if layout else 0
            if content == "" and layout and not layout[0].get("Partitions"):
                drive.scheme, drive.partitions = "none", 1  # formatted without a partition table
        except Exception:
            pass
        if not drive.free:
            try:
                drive.free = shutil.disk_usage(v).free
            except OSError:
                pass
        found.append(drive.judge())
    return found


# ---------------------------------------------------------------- Linux

def _linux(run=_run):
    try:
        data = json.loads(run(["lsblk", "-J", "-b", "-o", "NAME,PATH,TYPE,FSTYPE,FSVER,LABEL,MOUNTPOINT,RM,HOTPLUG,TRAN,PTTYPE,SIZE,RO"]))
    except Exception:
        return []
    found = []
    for disk in data.get("blockdevices", []):
        if disk.get("type") != "disk":
            continue
        usb = disk.get("tran") == "usb" or str(disk.get("hotplug")) in ("1", "True", "true") or str(disk.get("rm")) in ("1", "True", "true")
        if not usb:
            continue
        children = disk.get("children") or []
        parts = [c for c in children if c.get("type") == "part"]
        candidates = parts or [disk]  # a "superfloppy" without partition table
        for p in candidates:
            mount = p.get("mountpoint")
            if not mount:
                continue
            fs = (p.get("fstype") or "").lower()
            ver = p.get("fsver") or ""
            name = "FAT32" if fs == "vfat" and ver.upper() == "FAT32" else ver if fs == "vfat" else (p.get("fstype") or "")
            drive = Drive(path=Path(mount), label=p.get("label") or Path(mount).name, size=int(p.get("size") or 0),
                          filesystem=name, scheme={"dos": "MBR", "gpt": "GPT"}.get(disk.get("pttype") or "", ""),
                          partitions=len(parts), device=p.get("path") or "/dev/" + p.get("name", ""),
                          readonly=str(p.get("ro")) in ("1", "True", "true"))
            if not parts:
                drive.scheme, drive.partitions = "none", 1
            try:
                drive.free = shutil.disk_usage(mount).free
            except OSError:
                pass
            found.append(drive.judge())
    for d in found:
        if d.scheme == "none":  # no MBR: the player needs a partition table
            d.problems = [p for p in d.problems if p != "scheme"] + ["scheme"]
    return found


# ---------------------------------------------------------------- Windows

IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS = 0x00560000
IOCTL_DISK_GET_DRIVE_LAYOUT_EX = 0x00070050


def parse_layout(buf: bytes):
    """DRIVE_LAYOUT_INFORMATION_EX -> (scheme, partitions in use)."""
    import struct
    style, count = struct.unpack_from("<II", buf, 0)
    used = 0
    for i in range(count):
        at = 48 + i * 144
        if at + 144 > len(buf):
            break
        length = struct.unpack_from("<q", buf, at + 16)[0]
        if length > 0:
            used += 1
    return {0: "MBR", 1: "GPT"}.get(style, ""), used


def _windows():
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateFileW.restype = wintypes.HANDLE
    found = []
    mask = k.GetLogicalDrives()
    for i in range(26):
        if not mask >> i & 1:
            continue
        root = "%s:\\" % chr(65 + i)
        kind = k.GetDriveTypeW(root)
        if kind not in (2, 3):  # removable or fixed (USB hard drives show as fixed)
            continue
        vol, fs = ctypes.create_unicode_buffer(261), ctypes.create_unicode_buffer(261)
        flags = wintypes.DWORD()
        if not k.GetVolumeInformationW(root, vol, 261, None, None, ctypes.byref(flags), fs, 261):
            continue
        free, total = ctypes.c_ulonglong(), ctypes.c_ulonglong()
        k.GetDiskFreeSpaceExW(root, ctypes.byref(free), ctypes.byref(total), None)
        drive = Drive(path=Path(root), label=vol.value, size=total.value, free=free.value, filesystem=fs.value,
                      removable=kind == 2, device="%s:" % chr(65 + i), readonly=bool(flags.value & 0x00080000))
        if kind == 3 and not _windows_usb(k, root):
            continue  # internal disk
        scheme, parts = _windows_layout(k, chr(65 + i))
        drive.scheme, drive.partitions = scheme, parts
        found.append(drive.judge())
    return found


def _windows_open(k, name):
    INVALID = ctypes_invalid()
    h = k.CreateFileW(name, 0, 3, None, 3, 0, None)  # no access rights needed for these queries
    return None if h in (None, INVALID) else h


def ctypes_invalid():
    import ctypes
    return ctypes.c_void_p(-1).value


def _windows_disk_number(k, letter):
    import ctypes, struct
    h = _windows_open(k, "\\\\.\\%s:" % letter)
    if h is None:
        return None
    try:
        buf = ctypes.create_string_buffer(64); got = ctypes.c_ulong()
        if not k.DeviceIoControl(h, IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS, None, 0, buf, 64, ctypes.byref(got), None):
            return None
        count, = struct.unpack_from("<I", buf.raw, 0)
        return struct.unpack_from("<I", buf.raw, 8)[0] if count else None
    finally:
        k.CloseHandle(h)


def _windows_layout(k, letter):
    import ctypes
    n = _windows_disk_number(k, letter)
    if n is None:
        return "", 0
    h = _windows_open(k, "\\\\.\\PhysicalDrive%d" % n)
    if h is None:
        return "", 0
    try:
        buf = ctypes.create_string_buffer(8192); got = ctypes.c_ulong()
        if not k.DeviceIoControl(h, IOCTL_DISK_GET_DRIVE_LAYOUT_EX, None, 0, buf, 8192, ctypes.byref(got), None):
            return "", 0
        return parse_layout(buf.raw[:got.value])
    finally:
        k.CloseHandle(h)


def _windows_usb(k, root):
    """A fixed drive counts only when it is on USB (STORAGE_BUS_TYPE 7)."""
    import ctypes, struct
    h = _windows_open(k, "\\\\.\\%s" % root[:2])
    if h is None:
        return False
    try:
        query = struct.pack("<II4s", 0, 0, b"\0" * 4)  # StorageDeviceProperty, PropertyStandardQuery
        buf = ctypes.create_string_buffer(1024); got = ctypes.c_ulong()
        if not k.DeviceIoControl(h, 0x002D1400, query, len(query), buf, 1024, ctypes.byref(got), None):
            return False
        return struct.unpack_from("<I", buf.raw, 28)[0] == 7  # BusType
    finally:
        k.CloseHandle(h)


# ---------------------------------------------------------------- common

def find():
    """USB drives connected now, each judged for the player."""
    try:
        if sys.platform == "darwin":
            return _mac()
        if os.name == "nt":
            return _windows()
        return _linux()
    except Exception:
        return []


def eject(drive: Drive) -> bool:
    """Ask the system to eject; True when the drive is gone."""
    try:
        if sys.platform == "darwin":
            subprocess.run(["diskutil", "eject", drive.device or str(drive.path)], capture_output=True, timeout=30, check=True)
        elif os.name == "nt":
            ps = "(New-Object -comObject Shell.Application).Namespace(17).ParseName('%s').InvokeVerb('Eject')" % drive.device
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=30, check=True)
        else:
            subprocess.run(["udisksctl", "unmount", "-b", drive.device], capture_output=True, timeout=30, check=True)
    except Exception:
        return False
    import time
    for _ in range(20):
        if not drive.path.exists() or (os.name != "nt" and not os.path.ismount(drive.path)):
            return True
        time.sleep(0.5)
    return False
