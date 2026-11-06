"""Testes do menu (respostas do usuário simuladas)."""
import io, os, tempfile, unittest
from pathlib import Path
from unittest import mock

from subdrive import drives, menu, ui

SRT = "1\n00:00:01,000 --> 00:00:03,000\nOlá, tudo bem?\n\n2\n00:00:04,000 --> 00:00:06,000\n<i>Sim.</i>\n"


class MenuTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.d = Path(self.tmp.name)
        (self.d / "legendas").mkdir(); (self.d / "sincronia").mkdir()
        (self.d / "legendas/Filme.srt").write_text(SRT, encoding="utf-8")
        (self.d / "legendas/Ruim.srt").write_text(SRT.replace("Sim.", "Sim ♪…"), encoding="utf-8")
        self.cwd = os.getcwd(); os.chdir(self.d)
        self.patch = mock.patch.object(drives, "find", return_value=[]); self.patch.start()

    def tearDown(self):
        self.patch.stop(); os.chdir(self.cwd); self.tmp.cleanup()

    def run_menu(self, answers, first=None):
        answers = iter(answers); text = io.StringIO()
        m = menu.Menu(out=ui.Out("pt", emoji=False, color=False, stream=text), ask=lambda q: next(answers))
        code = m.run(first)
        return code, text.getvalue()

    def test_check_one_file(self):
        code, text = self.run_menu(["1", "1", "2", "n", "", "0"])  # Verificar > Uma legenda > Ruim.srt
        self.assertEqual(code, 0)
        self.assertIn("Não passa", text); self.assertIn("Corrigir uma legenda", text)

    def test_fix_flow_writes_a_new_file(self):
        code, text = self.run_menu(["2", "2", "", "n", "", "0"])  # Corrigir > Ruim.srt > nome padrão > sem detalhes
        self.assertTrue((self.d / "legendas/Ruim_2.srt").is_file(), text)
        self.assertIn("Corrigido e salvo como: Ruim_2.srt", text)

    def test_pgs_flow(self):
        code, text = self.run_menu(["3", "1", "8", "2", "s", "40", "", "", "0"])  # amarelo escuro, Inter, negrito, 40
        self.assertTrue((self.d / "legendas/Filme.dark-yellow.sup").is_file(), text)

    def test_sync_flow(self):
        (self.d / "sincronia/Filme.srt.txt").write_text("versao=1\nponto=0,-500\n", encoding="utf-8")
        code, text = self.run_menu(["4", "1", "", "0"])
        self.assertTrue((self.d / "legendas/Filme_2.srt").is_file(), text)
        self.assertIn("0,5 s mais cedo", text)

    def test_file_dragged_onto_the_program(self):
        code, text = self.run_menu(["1", "", "n", "", "0"], first=self.d / "legendas/Ruim.srt")  # Corrigir
        self.assertTrue((self.d / "legendas/Ruim_2.srt").is_file(), text)

    def test_file_dragged_into_the_menu(self):
        code, text = self.run_menu(["'%s'" % (self.d / "legendas/Filme.srt"), "0", "", "0"])
        self.assertIn("Pronto para o player", text)

    def test_wrong_answers_are_explained(self):
        code, text = self.run_menu(["9", "x", "0"])
        self.assertIn("Digite um dos números do menu.", text)

    def test_ctrl_c_ends_quietly(self):
        def boom(q): raise KeyboardInterrupt
        m = menu.Menu(out=ui.Out("pt", emoji=False, color=False, stream=io.StringIO()), ask=boom)
        self.assertEqual(m.run(), 0)

    def test_zip_warning(self):
        with mock.patch.object(menu, "program_dir", return_value=Path(r"C:\Users\Ana\AppData\Local\Temp\Temp1_SubDrive.zip\SubDrive")), \
             mock.patch("tempfile.gettempdir", return_value=r"C:\Users\Ana\AppData\Local\Temp"):
            code, text = self.run_menu([""])
        self.assertEqual(code, 1); self.assertIn("Extraia o ZIP", text)

    def test_clean_path(self):
        self.assertEqual(menu.clean_path("'/Users/ana/Meu Filme.srt' "), "/Users/ana/Meu Filme.srt")
        self.assertEqual(menu.clean_path('"C:\\Filmes\\Meu Filme.srt"'), "C:\\Filmes\\Meu Filme.srt")
        if os.name != "nt":
            self.assertEqual(menu.clean_path("/Users/ana/Meu\\ Filme\\ \\(2\\).srt"), "/Users/ana/Meu Filme (2).srt")


if __name__ == "__main__":
    unittest.main()


class FullScreenTests(unittest.TestCase):
    """The same menu with arrow keys, as on a real terminal."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.d = Path(self.tmp.name)
        (self.d / "legendas").mkdir()
        (self.d / "legendas/Filme.srt").write_text(SRT, encoding="utf-8")
        (self.d / "legendas/Ruim.srt").write_text(SRT.replace("Sim.", "Sim ♪…"), encoding="utf-8")
        self.cwd = os.getcwd(); os.chdir(self.d)
        self.patch = mock.patch.object(drives, "find", return_value=[]); self.patch.start()

    def tearDown(self):
        self.patch.stop(); os.chdir(self.cwd); self.tmp.cleanup()

    def run_menu(self, keys, answers=()):
        from subdrive import screen
        keys, answers = iter(keys), iter(answers); text = io.StringIO()
        m = menu.Menu(out=ui.Out("pt", emoji=False, color=False, stream=text), ask=lambda q: next(answers),
                      keys=lambda: next(keys), full=True)
        return m.run(), text.getvalue()

    def test_arrows_choose_and_screen_is_restored(self):
        S = __import__("subdrive.screen", fromlist=["x"])
        # main: down to "Corrigir" → Enter; file list: down to Ruim.srt → Enter; name: default; details: n; any key; Sair
        keys = [S.DOWN, S.ENTER, S.DOWN, S.ENTER, "n", "x", S.UP, S.ENTER]
        code, text = self.run_menu(keys, answers=[""])
        self.assertEqual(code, 0)
        self.assertTrue((self.d / "legendas/Ruim_2.srt").is_file(), text)
        self.assertIn("\033[?1049h", text); self.assertTrue(text.rstrip().endswith("\033[?1049l"))
        self.assertIn("\033[H\033[2J", text)  # each screen replaces the previous one

    def test_digits_esc_and_ctrl_c(self):
        S = __import__("subdrive.screen", fromlist=["x"])
        keys = ["1", S.ESC, "x"]  # Verificar, then Esc goes back, any key
        def boom(): raise KeyboardInterrupt
        it = iter(keys)
        text = io.StringIO()
        m = menu.Menu(out=ui.Out("pt", emoji=False, color=False, stream=text), ask=lambda q: "", keys=lambda: next(it) if True else None, full=True)
        with mock.patch.object(m, "keys", side_effect=list(keys) + [KeyboardInterrupt()]):
            self.assertEqual(m.run(), 0)
        self.assertTrue(text.getvalue().rstrip().endswith("\033[?1049l"))
