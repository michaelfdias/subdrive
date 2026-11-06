"""Testes da detecção de pendrive (com respostas simuladas de cada sistema) e da preparação."""
import hashlib, json, plistlib, struct, tempfile, unittest
from pathlib import Path
from unittest import mock

from subdrive import cli, drives, package


def sha(b): return hashlib.sha256(b).hexdigest()


def make_package(folder: Path, files, version="1.0.0", platform="UHD"):
    for n, b in files.items():
        p = folder / "USB" / n; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b)
    (folder / "manifest.json").write_text(json.dumps({"produto": "legendas", "platform": platform, "version": version,
        "jar_sha256": sha(files["BDJ.jar"]), "files": {n: {"bytes": len(b), "sha256": sha(b)} for n, b in files.items()}}))


FILES = {"BDJ.jar": b"jar-1", "BDJ_DEBUG": b"", "legendas/Filme.srt": b"1\n00:00:01,000 --> 00:00:02,000\nA\n",
         "fontes/inter.letras": b"letras", "fontes/LICENCAS.txt": b"OFL"}


class DriveTests(unittest.TestCase):
    def test_linux_lsblk(self):
        data = {"blockdevices": [
            {"name": "sda", "type": "disk", "tran": "sata", "rm": False, "hotplug": False, "pttype": "gpt", "children": []},
            {"name": "sdb", "type": "disk", "tran": "usb", "rm": True, "pttype": "dos", "size": 16000000000, "children": [
                {"name": "sdb1", "path": "/dev/sdb1", "type": "part", "fstype": "vfat", "fsver": "FAT32", "label": "LEGENDAS",
                 "mountpoint": "/tmp", "size": 15990000000, "ro": False}]},
            {"name": "sdc", "type": "disk", "tran": "usb", "pttype": "gpt", "children": [
                {"name": "sdc1", "type": "part", "fstype": "exfat", "mountpoint": "/tmp", "size": 64e9},
                {"name": "sdc2", "type": "part", "fstype": "vfat", "fsver": "FAT32", "mountpoint": None}]}]}
        found = drives._linux(run=lambda args: json.dumps(data).encode())
        self.assertEqual(len(found), 2)
        ok, bad = found
        self.assertTrue(ok.ok, ok.problems); self.assertEqual((ok.label, ok.filesystem, ok.scheme, ok.partitions), ("LEGENDAS", "FAT32", "MBR", 1))
        self.assertEqual(set(bad.problems), {"filesystem", "scheme", "partitions"})

    def test_mac_diskutil(self):
        info = {"Internal": False, "BusProtocol": "USB", "FilesystemName": "MS-DOS FAT32", "VolumeName": "LEGENDAS",
                "TotalSize": 16e9, "FreeSpace": 15e9, "DeviceIdentifier": "disk4s1", "ParentWholeDisk": "disk4"}
        layout = {"AllDisksAndPartitions": [{"Content": "FDisk_partition_scheme", "Partitions": [{"DeviceIdentifier": "disk4s1"}]}]}
        run = lambda args: plistlib.dumps(info if args[1] == "info" else layout)
        with mock.patch.object(Path, "iterdir", return_value=[Path("/Volumes/LEGENDAS")]), \
             mock.patch.object(Path, "is_dir", return_value=True), mock.patch.object(Path, "is_symlink", return_value=False):
            found = drives._mac(run=run)
        self.assertEqual(len(found), 1); self.assertTrue(found[0].ok, found[0].problems)
        info["FilesystemName"] = "ExFAT"
        with mock.patch.object(Path, "iterdir", return_value=[Path("/Volumes/X")]), \
             mock.patch.object(Path, "is_dir", return_value=True), mock.patch.object(Path, "is_symlink", return_value=False):
            self.assertEqual(drives._mac(run=run)[0].problems, ["filesystem"])

    def test_windows_layout_buffer(self):
        buf = bytearray(48 + 4 * 144); struct.pack_into("<II", buf, 0, 0, 4)
        struct.pack_into("<q", buf, 48 + 16, 16_000_000_000)  # one partition in use, three empty MBR slots
        self.assertEqual(drives.parse_layout(bytes(buf)), ("MBR", 1))
        struct.pack_into("<I", buf, 0, 1); struct.pack_into("<q", buf, 48 + 144 + 16, 100)
        self.assertEqual(drives.parse_layout(bytes(buf)), ("GPT", 2))


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); r = Path(self.tmp.name)
        self.usb = r / "usb"; self.usb.mkdir(); self.pkg = r / "pacote"; make_package(self.pkg, FILES)
        self.drive = drives.Drive(path=self.usb, label="LEGENDAS", size=16e9, free=15e9, filesystem="FAT32", scheme="MBR", partitions=1).judge()

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *extra):
        with mock.patch.object(drives, "find", return_value=[self.drive]):
            return cli.main(["--no-emoji", "prepare", "--package", str(self.pkg), "--yes", *extra])

    def test_fresh_install(self):
        self.assertEqual(self.run_cli(), 0)
        self.assertEqual(sorted(p.name for p in self.usb.iterdir()),
                         ["BDJ.jar", "BDJ_DEBUG", "fontes", "legendas", "relatorios", "sincronia", "subdrive.json"])
        self.assertEqual(package.installed(self.usb), ("1.0.0", "UHD"))

    def test_update_keeps_user_files_and_removes_old_letters(self):
        (self.usb / "legendas").mkdir(); (self.usb / "legendas/Meu.srt").write_bytes(b"MINE")
        (self.usb / "legendas/Filme.srt").write_bytes(b"EDITED")
        (self.usb / "sincronia").mkdir(); (self.usb / "sincronia/Meu.srt.txt").write_bytes(b"versao=1\n")
        (self.usb / "relatorios").mkdir(); (self.usb / "relatorios/relatorio-01.txt").write_bytes(b"KEEP")
        (self.usb / "preferencias.json").write_bytes(b"{}")
        (self.usb / "fontes").mkdir(); (self.usb / "fontes/antiga.letras").write_bytes(b"x"); (self.usb / "fontes/minha.txt").write_bytes(b"y")
        self.assertEqual(self.run_cli(), 0)
        for name, data in (("legendas/Meu.srt", b"MINE"), ("legendas/Filme.srt", b"EDITED"), ("sincronia/Meu.srt.txt", b"versao=1\n"),
                           ("relatorios/relatorio-01.txt", b"KEEP"), ("preferencias.json", b"{}"), ("fontes/minha.txt", b"y")):
            self.assertEqual((self.usb / name).read_bytes(), data, name)
        self.assertFalse((self.usb / "fontes/antiga.letras").exists())
        self.assertEqual(self.run_cli("--replace-subtitles"), 0)
        self.assertEqual((self.usb / "legendas/Filme.srt").read_bytes(), FILES["legendas/Filme.srt"])

    def test_refuses_unusable_drive_and_damaged_package(self):
        self.drive.filesystem = "exFAT"; self.drive.judge()
        self.assertEqual(self.run_cli(), 1); self.assertFalse((self.usb / "BDJ.jar").exists())
        self.drive.filesystem = "FAT32"; self.drive.judge()
        (self.pkg / "USB/BDJ.jar").write_bytes(b"other")
        self.assertEqual(self.run_cli(), 2); self.assertFalse((self.usb / "BDJ.jar").exists())

    def test_no_space(self):
        self.drive.free = 3
        self.assertEqual(self.run_cli(), 1); self.assertFalse((self.usb / "BDJ.jar").exists())

    def test_several_drives_need_a_choice(self):
        other = drives.Drive(path=Path("/nao/existe"), filesystem="FAT32", scheme="MBR", partitions=1).judge()
        with mock.patch.object(drives, "find", return_value=[self.drive, other]):
            self.assertEqual(cli.main(["--no-emoji", "prepare", "--package", str(self.pkg), "--yes"]), 2)
            self.assertEqual(cli.main(["--no-emoji", "prepare", "--package", str(self.pkg), "--yes", "--drive", str(self.usb)]), 0)

    def test_without_confirmation_nothing_changes(self):
        with mock.patch.object(drives, "find", return_value=[self.drive]), mock.patch("sys.stdin.isatty", return_value=True), \
             mock.patch("builtins.input", return_value="n"):
            self.assertEqual(cli.main(["--no-emoji", "prepare", "--package", str(self.pkg)]), 1)
        self.assertEqual(list(self.usb.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
