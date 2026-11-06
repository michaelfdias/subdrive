"""Testes de verificação, correção e nomes de arquivo."""
import tempfile, unittest
from pathlib import Path
from subdrive import core, cli

GOOD = "1\n00:00:01,000 --> 00:00:03,000\nOlá, tudo bem?\n\n2\n00:00:03,500 --> 00:00:05,000\n<i>Sim.</i>\n"


class SubdriveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def file(self, name, text, enc="utf-8"):
        p = self.d / name; p.write_bytes(text.encode(enc)); return p

    def test_good_file_passes(self):
        r = core.check_path(self.file("Filme.srt", GOOD))
        self.assertTrue(r.ok); self.assertEqual(r.cues, 2)

    def test_windows_text_is_reported_and_fixed(self):
        p = self.file("Filme.srt", GOOD.replace("<i>Sim.</i>", "Ação"), "cp1252")
        r = core.check_path(p)
        self.assertFalse(r.ok); self.assertEqual(r.problems[0].rule, "encoding"); self.assertTrue(r.fixable)
        f = core.fix_srt(p)
        self.assertTrue(f.ok); self.assertEqual(f.encoding, "cp1252"); self.assertIn("Ação".encode(), f.data)

    def test_fix_handles_everything_common(self):
        bad = ("1\n00:00:01,000 --> 00:00:03,000\nOlá — sim ♪ 😀\n\n3\n00:00:02.500 --> 00:00:04,000\n"
               "<font color=\"red\">a</font> {\\an8}b\nc\nd\n\n4\n00:00:05,000 --> 00:00:05,050\nCurta…\n")
        f = core.fix_srt(self.file("F.srt", bad))
        self.assertTrue(f.ok, f.remaining)
        kinds = {c.kind for c in f.changes}
        self.assertTrue({"structure", "punctuation", "markup", "lines", "characters", "overlap", "duration"} <= kinds, kinds)
        self.assertTrue(core.check_srt(self.d / "F.srt", data=f.data, name="F.srt").ok)

    def test_good_file_has_nothing_to_fix(self):
        f = core.fix_srt(self.file("Filme.srt", GOOD))
        self.assertTrue(f.ok); self.assertEqual(f.changes, [])

    def test_incremental_names(self):
        p = self.file("Filme.srt", GOOD)
        self.assertEqual(core.next_name(p).name, "Filme_2.srt")
        (self.d / "Filme_2.srt").write_text("x")
        self.assertEqual(core.next_name(p).name, "Filme_3.srt")
        self.assertEqual(core.next_name(self.d / "Filme_2.srt").name, "Filme_3.srt")
        self.assertEqual(core.next_name(p, "Meu nome").name, "Meu nome.srt")

    def test_cli_fix_never_overwrites(self):
        p = self.file("Filme.srt", GOOD.replace("Sim.", "Sim…"))
        (self.d / "Novo.srt").write_text("mine")
        self.assertEqual(cli.main(["--no-emoji", "fix", str(p), "--output", "Novo"]), 2)
        self.assertEqual((self.d / "Novo.srt").read_text(), "mine")
        self.assertEqual(cli.main(["--no-emoji", "fix", str(p)]), 0)
        self.assertTrue(core.check_path(self.d / "Filme_2.srt").ok)
        self.assertEqual(p.read_text(), GOOD.replace("Sim.", "Sim…"))

    def test_pgs_check(self):
        bad = self.d / "Ruim.sup"; bad.write_bytes(b"PGxxxx")
        r = core.check_path(bad)
        self.assertFalse(r.ok); self.assertEqual(r.problems[0].rule, "pgs_damaged")

    def test_cli_check_exit_codes(self):
        self.assertEqual(cli.main(["--no-emoji", "check", str(self.file("Filme.srt", GOOD))]), 0)
        self.assertEqual(cli.main(["--no-emoji", "check", str(self.file("B.srt", GOOD.replace("Sim.", "Sim ♪")))]), 1)
        self.assertEqual(cli.main(["--no-emoji", "check", str(self.d / "nao-existe.srt")]), 1)


if __name__ == "__main__":
    unittest.main()
