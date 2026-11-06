"""Testes da atualização: assinatura, canal de testes, sem downgrade e troca segura dos arquivos."""
import hashlib, io, json, os, sys, tempfile, unittest, zipfile
from pathlib import Path
from unittest import mock

from subdrive import cli, ed25519, update

SEED = bytes(range(32))           # test key only
KEY = ed25519.public_key(SEED)
OTHER = ed25519.public_key(bytes(32))


def sha(b): return hashlib.sha256(b).hexdigest()


def package_zip(version):
    files = {"BDJ.jar": b"jar-" + version.encode(), "BDJ_DEBUG": b""}
    manifest = {"produto": "legendas", "platform": "UHD", "version": version, "jar_sha256": sha(files["BDJ.jar"]),
                "files": {n: {"bytes": len(b), "sha256": sha(b)} for n, b in files.items()}}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest))
        for n, b in files.items():
            z.writestr("USB/" + n, b)
    return buf.getvalue()


class Server:
    """Fake GitHub releases listing + assets."""
    def __init__(self):
        self.assets, self.listing = {}, []

    def add(self, version, channel, seed=SEED, tamper=None):
        pack = package_zip(version); prog = b"program " + version.encode()
        files = {"package-panasonic-ub450-uhd": {"name": "pkg-%s.zip" % version, "sha256": sha(pack), "bytes": len(pack)},
                 update.program_key(): {"name": "prog-%s" % version, "sha256": sha(prog), "bytes": len(prog)}}
        index = json.dumps({"schema": 1, "version": version, "channel": channel, "notes": ["Novidade %s" % version], "files": files}).encode()
        sig = ed25519.sign(seed, index)
        base = "https://x/%s/" % version
        self.assets.update({base + update.INDEX: index, base + update.SIGNATURE: sig, base + "pkg-%s.zip" % version: tamper or pack,
                            base + "prog-%s" % version: prog})
        self.listing.append({"tag_name": version, "assets": [{"name": n, "browser_download_url": base + n}
                                                             for n in (update.INDEX, update.SIGNATURE, "pkg-%s.zip" % version, "prog-%s" % version)]})

    def get(self, url, progress=None):
        if url == update.RELEASES:
            return json.dumps(self.listing).encode()
        return self.assets[url]


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.d = Path(self.tmp.name)
        self.pkg = self.d / "pacote"
        with zipfile.ZipFile(io.BytesIO(package_zip("1.0.0"))) as z:
            z.extractall(self.pkg)
        self.server = Server()
        self.patches = [mock.patch.object(update, "PUBLIC_KEY", KEY), mock.patch.object(update, "fetch", self.server.get),
                        mock.patch.object(cli, "_program_dir", return_value=self.d), mock.patch("subdrive.drives.find", return_value=[]),
                        mock.patch.object(cli, "VERSION", "1.0.0")]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in self.patches: p.stop()
        self.tmp.cleanup()

    def run_update(self, *extra, answer="s"):
        return cli.main(["--no-emoji", "update", *extra]) if "--yes" in extra or "--check" in extra else \
            cli.cmd_update(cli._parser().parse_args(["update", *extra]), cli.ui.Out("pt", emoji=False, color=False), ask=lambda q: answer)

    def test_versions(self):
        self.assertTrue(update.newer("1.1.0", "1.0.0")); self.assertTrue(update.newer("1.1.0", "1.1.0-beta.3"))
        self.assertTrue(update.newer("1.1.0-beta.10", "1.1.0-beta.9")); self.assertFalse(update.newer("1.0.0", "1.0.0"))
        self.assertFalse(update.newer("1.0.0", "1.1.0-beta.1"))

    def test_signature_is_required(self):
        index = b'{"schema": 1}'
        with self.assertRaises(update.UpdateError) as e:
            update.read_index(index, ed25519.sign(bytes(32), index), KEY)
        self.assertEqual(e.exception.code, "signature")
        self.server.add("1.1.0", "stable", seed=bytes(32))
        self.assertEqual(self.run_update("--yes"), 1)
        self.assertEqual(json.loads((self.pkg / "manifest.json").read_text(encoding="utf-8"))["version"], "1.0.0")

    def test_channels_and_no_downgrade(self):
        self.server.add("1.1.0-beta.1", "beta"); self.server.add("1.0.1", "stable")
        found = update.releases(self.server.get, KEY)
        self.assertEqual(update.best(found, "1.0.0", beta=False).version, "1.0.1")
        self.assertEqual(update.best(found, "1.0.0", beta=True).version, "1.1.0-beta.1")
        self.assertIsNone(update.best(found, "1.1.0-beta.1", beta=False))  # leaving the test channel never goes back
        self.assertIsNone(update.best(found, "1.2.0", beta=True))

    def test_updates_the_package_folder(self):
        self.server.add("1.0.1", "stable")
        self.assertEqual(self.run_update("--yes"), 0)
        self.assertEqual(json.loads((self.pkg / "manifest.json").read_text(encoding="utf-8"))["version"], "1.0.1")
        self.assertEqual((self.pkg / "USB/BDJ.jar").read_bytes(), b"jar-1.0.1")
        self.assertEqual(sorted(p.name for p in self.d.iterdir()), ["pacote"])  # nothing left behind

    def test_altered_download_changes_nothing(self):
        self.server.add("1.0.1", "stable", tamper=b"not the package")
        self.assertEqual(self.run_update("--yes"), 1)
        self.assertEqual(json.loads((self.pkg / "manifest.json").read_text(encoding="utf-8"))["version"], "1.0.0")

    def test_already_newest_and_check_only(self):
        self.server.add("1.0.0", "stable")
        self.assertEqual(self.run_update("--yes"), 0)
        self.server.add("1.0.2", "stable")
        self.assertEqual(self.run_update("--check"), 0)
        self.assertEqual(json.loads((self.pkg / "manifest.json").read_text(encoding="utf-8"))["version"], "1.0.0")

    def test_answer_no(self):
        self.server.add("1.0.1", "stable")
        self.assertEqual(self.run_update(answer="n"), 1)
        self.assertEqual(json.loads((self.pkg / "manifest.json").read_text(encoding="utf-8"))["version"], "1.0.0")

    def test_beta_setting_is_saved(self):
        self.server.add("1.1.0-beta.1", "beta")
        self.assertEqual(self.run_update("--check", "--beta", "on"), 0)
        self.assertTrue(update.wants_beta(self.d))
        self.assertEqual(self.run_update("--check", "--beta", "off"), 0)
        self.assertFalse(update.wants_beta(self.d))

    def test_program_replacement(self):
        prog = self.d / ("SubDrive.exe" if os.name == "nt" else "SubDrive"); prog.write_bytes(b"old")
        update.replace_program(prog, b"new")
        self.assertEqual(prog.read_bytes(), b"new")
        update.cleanup_old_program(prog)
        self.assertEqual([p.name for p in self.d.iterdir() if p.name.startswith("SubDrive")], [prog.name])

    def test_zip_paths_cannot_escape(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("../fora.txt", b"x")
        with self.assertRaises(update.UpdateError):
            update.replace_package(self.pkg, buf.getvalue())
        self.assertFalse((self.d / "fora.txt").exists())

    def test_off_until_the_key_exists(self):
        with mock.patch.object(update, "PUBLIC_KEY", b""):
            self.assertEqual(self.run_update("--check"), 1)


if __name__ == "__main__":
    unittest.main()


class ReleaseToolTests(unittest.TestCase):
    def test_index_is_signed_and_readable(self):
        import subprocess
        with tempfile.TemporaryDirectory() as t:
            t = Path(t); f = t / "SubDrive-Linux"; f.write_bytes(b"prog")
            r = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "tools/make_release_index.py"),
                                "--version", "1.0.0", "--channel", "stable", "--out", str(t / "out"), "program-linux-x86_64=%s" % f],
                               env=dict(os.environ, SUBDRIVE_SIGNING_KEY=SEED.hex()), capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            index = update.read_index((t / "out" / update.INDEX).read_bytes(), (t / "out" / update.SIGNATURE).read_bytes(), KEY)
            self.assertEqual(index["files"]["program-linux-x86_64"]["sha256"], sha(b"prog"))
