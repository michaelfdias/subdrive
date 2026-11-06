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
        (self.d / "sincronia/Filme.srt.txt").write_text("versao=1\nponto=0,-500\n")
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
