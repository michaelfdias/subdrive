import tempfile
import unittest
import io
import zipfile
from pathlib import Path
from unittest.mock import patch

from subdrive import desktop_service as service, drives, package, update
from tests.test_pendrive import make_package, FILES


class DesktopServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.lines = []
        self.out = service.Output(self.lines.append, lambda *args: None)

    def test_fix_preserves_original_and_checks_result(self):
        path = self.root / "Film.srt"
        original = "1\n00:00:01,000 --> 00:00:03,000\nOlá — tudo bem? ♪\n".encode()
        path.write_bytes(original)
        self.assertEqual(service.subtitle_action("fix", [path], {"show": True}, self.out), 0)
        self.assertEqual(path.read_bytes(), original)
        target = self.root / "Film_2.srt"
        self.assertTrue(target.exists())
        self.assertEqual(service.subtitle_action("check", [target], {}, self.out), 0)
        saved = target.read_bytes()
        self.assertEqual(service.subtitle_action("fix", [path], {"output": "Film_2"}, self.out), 2)
        self.assertEqual(target.read_bytes(), saved)

    def test_pgs_round_trip(self):
        path = self.root / "Film.srt"
        path.write_text("1\n00:00:01,000 --> 00:00:03,000\nOlá!\n", encoding="utf-8")
        self.assertEqual(service.subtitle_action("pgs", [path], {"bold": True, "font": "inter"}, self.out), 0)
        sup = self.root / "Film.soft-white.sup"
        self.assertTrue(sup.exists())
        self.assertEqual(service.subtitle_action("check", [sup], {}, self.out), 0)

    def test_rejects_multi_file_modification(self):
        with self.assertRaisesRegex(ValueError, "apenas um"):
            service.subtitle_action("fix", [self.root, self.root], {}, self.out)

    def test_prepare_requires_preview_and_preserves_personal_files(self):
        usb, folder = self.root / "usb", self.root / "package"
        usb.mkdir(); make_package(folder, FILES)
        (usb / "preferencias.json").write_bytes(b"keep")
        drive = drives.Drive(usb, filesystem="FAT32", scheme="MBR", partitions=1, device="test").judge()
        with patch.object(drives, "find", return_value=[drive]), patch("subdrive.player.make_jar", return_value=b"jar-1"):
            preview = service.prepare_preview(folder, usb, False, folder / "firmware/fw.zip", self.out)
            self.assertEqual(list(usb.iterdir()), [usb / "preferencias.json"])
            service.prepare_apply(preview, False, False, self.out)
        self.assertEqual((usb / "preferencias.json").read_bytes(), b"keep")
        self.assertEqual(package.installed(usb), ("1.0.0", "UHD"))
        with patch.object(drives, "find", return_value=[]), self.assertRaises(ValueError):
            service.prepare_apply(preview, False, False, self.out)

    def test_updater_never_installs_terminal_binary(self):
        rel = update.Release("9.0.0", "stable", [], {update.program_key(): {}})
        with patch("sys.frozen", True, create=True), patch.object(update, "replace_program") as replace:
            with self.assertRaisesRegex(ValueError, "edição gráfica"):
                service.install_update(rel, None, self.out)
            replace.assert_not_called()

    def test_updater_accepts_separate_desktop_asset(self):
        key = update.program_key().replace("program-", "desktop-")
        rel = update.Release("9.0.0", "stable", [], {key: {}})
        with patch("sys.frozen", True, create=True), patch("sys.platform", "linux"), patch.object(update, "program_key", return_value=key.replace("desktop-", "program-")), patch.object(update, "download", return_value=b"gui") as download, patch.object(update, "replace_program") as replace:
            self.assertEqual(service.install_update(rel, None, self.out), 0)
            self.assertEqual(download.call_args.args[1], key)
            self.assertEqual(replace.call_args.args[1], b"gui")

    def test_macos_update_replaces_bundle_and_rejects_traversal(self):
        current = self.root / "SubDrive Desktop.app"
        executable = current / "Contents/MacOS/SubDrive-Desktop"
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b"old")
        def archive(entries):
            blob = io.BytesIO()
            with zipfile.ZipFile(blob, "w") as z:
                for name, value in entries.items():
                    z.writestr(name, value)
            return blob.getvalue()
        with self.assertRaises(update.UpdateError):
            service.replace_macos_app(executable, archive({"../escape": b"bad"}))
        self.assertEqual(executable.read_bytes(), b"old")
        service.replace_macos_app(executable, archive({
            "SubDrive Desktop.app/Contents/Info.plist": b"metadata",
            "SubDrive Desktop.app/Contents/MacOS/SubDrive-Desktop": b"new"}))
        self.assertEqual(executable.read_bytes(), b"new")
        self.assertEqual((current / "Contents/Info.plist").read_bytes(), b"metadata")
