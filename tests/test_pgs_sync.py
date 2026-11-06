"""Testes da criação de PGS e da aplicação da sincronia feita no player."""
import tempfile, unittest
from pathlib import Path

from subdrive import cli, core, pgs, sup_reader, sync

SRT = ("1\n00:00:01,000 --> 00:00:03,000\nOlá, tudo bem?\n\n"
       "2\n00:00:04,000 --> 00:00:06,000\nDuas linhas, João\n<i>e itálico à direita.</i>\n\n"
       "3\n00:01:10,000 --> 00:01:12,500\nWWW MMM iii lll 000\n")


class PgsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.d = Path(self.tmp.name)
        (self.d / "legendas").mkdir(); (self.d / "sincronia").mkdir()
        self.srt = self.d / "legendas" / "Filme.srt"; self.srt.write_text(SRT, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_colors_and_fonts_by_name(self):
        self.assertEqual(pgs.color("Amarelo-Escuro")[0], "dark-yellow")
        self.assertEqual(pgs.color("verde-limão")[0], "lime")
        self.assertEqual(pgs.color("soft white")[1], (0xE0, 0xE0, 0xE0))
        self.assertIsNone(pgs.color("roxo"))
        self.assertEqual(pgs.font("Open Sans")[1], "opensans")
        self.assertEqual(len(pgs.COLORS), 20)
        for _, prefix in pgs.FONTS:
            for w in ("400", "700"):
                self.assertTrue((pgs.FONT_DIR / ("%s-%s.ttf" % (prefix, w))).is_file())
                self.assertTrue((pgs.FONT_DIR / ("%s-italic-%s.ttf" % (prefix, w))).is_file())

    def test_every_font_has_every_letter_the_player_accepts(self):
        letters = "".join(chr(c) for c in list(range(33, 127)) + list(range(161, 256)) if c not in (60, 62, 173))
        cues = [(0, 1000, [[(letters, False)], [(letters, True)]])]
        for _, prefix in pgs.FONTS:
            for bold in (False, True):
                self.assertEqual(pgs.missing_letters(cues, pgs.Style(font=prefix, bold=bold)), [], prefix)

    def test_convert_is_read_by_the_player_rules(self):
        data = pgs.convert(pgs.cues_from_srt(self.srt.read_bytes()), pgs.Style(), workers=1)
        cues = sup_reader.parse(data)
        self.assertEqual([c["start"] for c in cues], [1000, 4000, 70000])
        self.assertEqual(len(cues[1]["objects"]), 2)

    def test_parallel_drawing_gives_the_same_file(self):
        cues = pgs.cues_from_srt(self.srt.read_bytes())
        self.assertEqual(pgs.convert(cues, pgs.Style(), workers=1), pgs.convert(cues, pgs.Style(), workers=2))

    def test_too_large_is_refused(self):
        cues = [(0, 2000, [[("M" * 64, False)], [("M" * 64, False)]])]
        with self.assertRaises(pgs.TooLarge):
            pgs.convert(cues, pgs.Style(size=72), workers=1)

    def test_cli_names_and_never_overwrites(self):
        self.assertEqual(cli.main(["--no-emoji", "pgs", str(self.srt)]), 0)
        self.assertTrue((self.d / "legendas/Filme.soft-white.sup").is_file())
        self.assertEqual(cli.main(["--no-emoji", "pgs", str(self.srt)]), 0)
        self.assertTrue((self.d / "legendas/Filme_2.soft-white.sup").is_file())
        self.assertEqual(cli.main(["--no-emoji", "pgs", str(self.srt), "--color", "amarelo", "--font", "inter", "--bold"]), 0)
        self.assertTrue(core.check_path(self.d / "legendas/Filme.yellow.sup").ok)
        self.assertEqual(cli.main(["--no-emoji", "pgs", str(self.srt), "--color", "roxo"]), 2)
        self.assertEqual(cli.main(["--no-emoji", "pgs", str(self.srt), "--size", "200"]), 2)

    def test_cli_refuses_a_subtitle_that_needs_fixing(self):
        bad = self.d / "Ruim.srt"; bad.write_text(SRT.replace("Olá", "Olá ♪"), encoding="utf-8")
        self.assertEqual(cli.main(["--no-emoji", "pgs", str(bad)]), 1)
        self.assertFalse(list(self.d.glob("Ruim*.sup")))


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.d = Path(self.tmp.name)
        (self.d / "legendas").mkdir(); (self.d / "sincronia").mkdir()
        self.srt = self.d / "legendas" / "Filme.srt"; self.srt.write_text(SRT, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_offset_between_points_as_the_player(self):
        points = [(10000, -1000), (20000, 1000)]
        self.assertEqual(sync.offset(points, 0), -1000)
        self.assertEqual(sync.offset(points, 15000), 0)
        self.assertEqual(sync.offset(points, 99000), 1000)
        self.assertEqual(sync.film_time([(0, -1500)], 3000), 1500)

    def test_bad_sync_files(self):
        for text in ("x", "versao=1\nponto=1,700000", "versao=1\nponto=10,0\nponto=5,0", "versao=1\nlixo"):
            with self.assertRaises(sync.SyncError):
                sync.parse(text)
        self.assertEqual(sync.parse("sincronia=1\nponto=1000,-200\n"), [(1000, -200)])

    def test_cli_finds_the_player_file_and_writes_a_new_subtitle(self):
        (self.d / "sincronia/Filme.srt.txt").write_text("versao=1\nponto=60000,-500\n", encoding="utf-8")
        self.assertEqual(cli.main(["--no-emoji", "sync", str(self.srt)]), 0)
        new = (self.d / "legendas/Filme_2.srt").read_text(encoding="utf-8")
        self.assertIn("00:00:00,500 --> 00:00:02,500", new)
        self.assertIn("00:01:09,500 --> 00:01:12,000", new)
        self.assertEqual(self.srt.read_text(encoding="utf-8"), SRT)
        self.assertTrue(core.check_path(self.d / "legendas/Filme_2.srt").ok)

    def test_cli_sync_of_a_pgs(self):
        sup = self.d / "legendas/Filme.soft-white.sup"
        sup.write_bytes(pgs.convert(pgs.cues_from_srt(self.srt.read_bytes()), pgs.Style(), workers=1))
        (self.d / "sincronia/Filme.soft-white.sup.txt").write_text("versao=1\nponto=0,2000\n", encoding="utf-8")
        self.assertEqual(cli.main(["--no-emoji", "sync", str(sup)]), 0)
        cues = sup_reader.parse((self.d / "legendas/Filme_2.soft-white.sup").read_bytes())
        self.assertEqual(cues[0]["start"], 3000)

    def test_cli_without_points(self):
        self.assertEqual(cli.main(["--no-emoji", "sync", str(self.srt)]), 1)


if __name__ == "__main__":
    unittest.main()
