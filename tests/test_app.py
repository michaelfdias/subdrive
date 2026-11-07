"""Testes do SubDrive com janelas: cada ação faz exatamente o que o comando do SubDrive CLI faz
(mesmos arquivos, byte a byte) e a janela abre todas as telas sem erro.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_app
"""
import io, json, os, sys, tempfile, unittest, zipfile

try:
    import PySide6  # noqa: F401  (o SubDrive com janelas precisa do PySide6: pip install -r requirements-app.txt)
except ImportError:
    raise unittest.SkipTest("PySide6 não instalado")
from argparse import Namespace
from pathlib import Path
from unittest import mock

from subdrive import cli, core, drives, package, player, ui, update
from tests.test_pendrive import FILES, make_package
from tests.test_update import KEY, Server, package_zip

from subdrive_app import acoes, lugares

GOOD = "1\n00:00:01,000 --> 00:00:03,000\nOlá, tudo bem?\n\n2\n00:00:04,000 --> 00:00:06,000\n<i>Sim, é isso.</i>\n"
BAD = ("1\n00:00:01,000 --> 00:00:03,000\nOlá — tudo bem? ♪\n\n2\n00:00:02,500 --> 00:00:06,000\n<font color=red>Sim</font>\nlinha\nlinha\n\n"
       "3\n00:01:00,000 --> 00:01:03,000\nLegendas por Equipe XYZ\n\n")


def quiet():
    return ui.Out("pt", emoji=False, color=False, stream=io.StringIO(), cli=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.d = Path(self.tmp.name)
        self.a = self.d / "gui"; self.b = self.d / "cli"
        for x in (self.a, self.b):
            (x / "legendas").mkdir(parents=True); (x / "sincronia").mkdir()
            (x / "legendas/Bom.srt").write_text(GOOD, encoding="utf-8")
            (x / "legendas/Ruim.srt").write_bytes(BAD.encode("cp1252", errors="replace"))
            (x / "sincronia/Bom.srt.txt").write_text("versao=1\nponto=0,-500\nponto=5000,1500\n", encoding="utf-8")
        self.p = [mock.patch.object(drives, "find", return_value=[])]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.tmp.cleanup()

    def same(self, name):
        self.assertEqual((self.a / "legendas" / name).read_bytes(), (self.b / "legendas" / name).read_bytes(), name)


class Paridade(Base):
    def test_verificar(self):
        for name in ("Bom.srt", "Ruim.srt"):
            v = acoes.verificar(self.a / "legendas" / name)
            res = core.check_path(self.b / "legendas" / name)
            self.assertEqual(v.ok, res.ok)
            self.assertEqual(len(v.problems), len(res.problems))
        v = acoes.verificar(self.a / "legendas/Ruim.srt")
        self.assertTrue(acoes.pode_corrigir(v)); self.assertFalse(acoes.pode_criar_pgs(v))
        self.assertIn("Não passa: 5 problemas", v.headline)

    def test_corrigir_igual_ao_cli(self):
        r = acoes.corrigir(self.a / "legendas/Ruim.srt")
        cli.cmd_fix(Namespace(path=self.b / "legendas/Ruim.srt", output=None, show=False, remove_credits=False), quiet())
        self.assertEqual(r.output.name, "Ruim_2.srt"); self.same("Ruim_2.srt")
        self.assertTrue(r.credits)  # a fala de créditos foi encontrada e mantida
        r = acoes.corrigir(self.a / "legendas/Ruim.srt", "Sem creditos", remove_credits=True)
        cli.cmd_fix(Namespace(path=self.b / "legendas/Ruim.srt", output="Sem creditos", show=False, remove_credits=True), quiet())
        self.same("Sem creditos.srt")
        self.assertTrue(acoes.verificar(r.output).ok)

    def test_previa_nao_grava(self):
        before = sorted(p.name for p in (self.a / "legendas").iterdir())
        r = acoes.corrigir(self.a / "legendas/Ruim.srt", write=False)
        self.assertTrue(r.ok and r.changes and r.output is None)
        self.assertEqual(before, sorted(p.name for p in (self.a / "legendas").iterdir()))

    def test_nunca_grava_por_cima(self):
        (self.a / "legendas/X.srt").write_text("já existe", encoding="utf-8")
        with self.assertRaises(acoes.Falha):
            acoes.corrigir(self.a / "legendas/Ruim.srt", "X")
        with self.assertRaises(acoes.Falha):
            acoes.corrigir(self.a / "legendas/Ruim.srt", "../fora")
        self.assertEqual((self.a / "legendas/X.srt").read_text(encoding="utf-8"), "já existe")

    def test_pgs_igual_ao_cli(self):
        e = acoes.EstiloPGS(color="dark-yellow", font="inter", bold=True, size=40, outline=2.5)
        r = acoes.criar_pgs(self.a / "legendas/Bom.srt", e)
        cli.cmd_pgs(Namespace(path=self.b / "legendas/Bom.srt", color="amarelo-escuro", font="inter", bold=True, size=40,
                              outline=2.5, output=None), quiet())
        self.assertEqual(r.output.name, "Bom.dark-yellow.sup"); self.same("Bom.dark-yellow.sup")
        with self.assertRaises(acoes.Falha):
            acoes.criar_pgs(self.a / "legendas/Ruim.srt", e)  # precisa corrigir antes

    def test_sincronia_igual_ao_cli(self):
        s = acoes.pontos(self.a / "legendas/Bom.srt")
        self.assertEqual(s.lines, ["00:00:00  →  0,5 s mais cedo", "00:00:05  →  1,5 s mais tarde"])
        r = acoes.sincronizar(s)
        cli.cmd_sync(Namespace(path=self.b / "legendas/Bom.srt", points=None, output=None), quiet())
        self.same("Bom_2.srt")
        self.assertIsNone(r.warning)
        with self.assertRaises(acoes.Falha):
            acoes.pontos(self.a / "legendas/Ruim.srt")  # sem pontos

    def test_sincronia_com_outro_arquivo(self):
        other = self.d / "pontos.txt"; other.write_text("versao=1\nponto=0,2000\n", encoding="utf-8")
        r = acoes.sincronizar(acoes.pontos(self.a / "legendas/Bom.srt", other), "Bom sincronizada")
        cli.cmd_sync(Namespace(path=self.b / "legendas/Bom.srt", points=other, output="Bom sincronizada"), quiet())
        self.same("Bom sincronizada.srt")


class Pendrive(Base):
    def setUp(self):
        super().setUp()
        self.jar = make_package(self.d / "pacote", FILES)
        self.p.append(mock.patch.object(player, "make_jar", return_value=self.jar)); self.p[-1].start()
        for x in ("usb-a", "usb-b"):
            (self.d / x).mkdir()
            (self.d / x / "legendas").mkdir()
            (self.d / x / "legendas/Filme.srt").write_bytes(b"minha legenda")

    def drive(self, name):
        return drives.Drive(path=self.d / name, label=name, size=8e9, free=7e9, filesystem="FAT32", scheme="MBR", partitions=1).judge()

    def test_preparar_igual_ao_cli(self):
        pkg = acoes.carregar_pacote(self.d / "pacote")
        self.assertTrue(pkg.needs_jar)
        with mock.patch.object(lugares, "program_dir", return_value=self.d / "pacote"):
            blob = acoes.firmware_guardado(pkg)
        self.assertEqual(blob, b"fw")
        acoes.montar_programa(pkg, blob)
        d = self.drive("usb-a")
        plano = acoes.planejar(d, pkg)
        self.assertEqual(plano.kept, 1)
        self.assertIn("1 legenda com o mesmo nome de uma do pacote: mantida como está", plano.lines[1])
        acoes.gravar(d, pkg)
        self.assertTrue(acoes.planejar(d, pkg).nothing)
        b = self.drive("usb-b")
        with mock.patch.object(drives, "find", return_value=[b]), mock.patch.object(cli, "_program_dir", return_value=self.d / "pacote"):
            code = cli.cmd_prepare(Namespace(drive=None, package=self.d / "pacote", replace_subtitles=False, yes=True, eject=False,
                                             firmware=None), quiet())
        self.assertEqual(code, 0)
        for f in sorted((self.d / "usb-a").rglob("*")):
            g = self.d / "usb-b" / f.relative_to(self.d / "usb-a")
            self.assertTrue(g.exists(), g)
            if f.is_file():
                self.assertEqual(f.read_bytes(), g.read_bytes(), f)
        self.assertEqual((self.d / "usb-a/legendas/Filme.srt").read_bytes(), b"minha legenda")

    def test_baixar_firmware(self):
        """Baixa (servidor simulado), confere o SHA-256, guarda em firmware/ e monta o programa do player."""
        pkg = acoes.carregar_pacote(self.d / "pacote")
        here = self.d / "programa"; here.mkdir()
        seen = []
        with mock.patch.object(lugares, "program_dir", return_value=here), \
             mock.patch.object(update, "fetch", lambda url, limit=None, progress=None: (seen.append(url), progress and progress(2, 2), b"fw")[2]):
            self.assertIsNone(acoes.firmware_guardado(pkg))
            blob = acoes.baixar_firmware(pkg, progress=lambda d, t: None)
            self.assertEqual(blob, b"fw")
            self.assertEqual(seen, [pkg.firmware["url"]])
            self.assertEqual((here / "firmware" / pkg.firmware["name"]).read_bytes(), b"fw")
            self.assertEqual(acoes.firmware_guardado(pkg), b"fw")  # na próxima vez não baixa de novo
        acoes.montar_programa(pkg, blob)
        self.assertEqual(pkg.files["BDJ.jar"], self.jar)

    def test_firmware_errado_ou_sem_internet(self):
        pkg = acoes.carregar_pacote(self.d / "pacote")
        with mock.patch.object(update, "fetch", lambda *a, **k: b"outro arquivo"):
            with self.assertRaises(acoes.Falha) as c:
                acoes.baixar_firmware(pkg)
        self.assertIn("não é o firmware esperado", c.exception.message)
        def offline(*a, **k):
            raise update.UpdateError("offline")
        with mock.patch.object(update, "fetch", offline):
            with self.assertRaises(acoes.Falha) as c:
                acoes.baixar_firmware(pkg)
        self.assertIn("internet", c.exception.message)
        bad = self.d / "fw-errado.zip"; bad.write_bytes(b"x")
        with self.assertRaises(acoes.Falha):
            acoes.firmware_escolhido(pkg, bad)
        good = self.d / "fw.zip"; good.write_bytes(b"fw")
        self.assertEqual(acoes.firmware_escolhido(pkg, good), b"fw")

    def test_substituir_legendas(self):
        pkg = acoes.carregar_pacote(self.d / "pacote"); acoes.montar_programa(pkg, b"fw")
        d = self.drive("usb-a")
        acoes.gravar(d, pkg, replace_subtitles=True)
        self.assertEqual((self.d / "usb-a/legendas/Filme.srt").read_bytes(), FILES["legendas/Filme.srt"])

    def test_pendrive_ruim(self):
        d = drives.Drive(path=self.d / "usb-a", label="X", size=64 * 1024 ** 3, filesystem="exFAT", scheme="GPT", partitions=2).judge()
        e = acoes.descrever_pendrive(d)
        self.assertFalse(e.ok)
        self.assertEqual([tone for tone, _ in e.lines], ["fail"])  # um conserto só: formatar
        self.assertEqual(len(e.technical), 3)  # exFAT, GPT e 2 partições, nos detalhes
        self.assertTrue(e.format_help)

    def test_pacote_ausente(self):
        with mock.patch.object(lugares, "program_dir", return_value=self.d / "a" / "b" / "nada"):
            with self.assertRaises(acoes.Falha) as c:
                acoes.carregar_pacote()
        self.assertIn("pacote", c.exception.message)


class Atualizacao(Base):
    def setUp(self):
        super().setUp()
        with zipfile.ZipFile(io.BytesIO(package_zip("1.0.0"))) as z:
            z.extractall(self.d / "pacote")
        self.server = Server()
        self.p += [mock.patch.object(update, "PUBLIC_KEY", KEY), mock.patch.object(update, "fetch", self.server.get),
                   mock.patch.object(lugares, "program_dir", return_value=self.d)]
        for p in self.p[-3:]:
            p.start()

    def test_nenhuma(self):
        self.assertIsNone(acoes.procurar_atualizacao())

    def test_instala_pacote_e_avisa_do_pendrive(self):
        self.server.add("1.1.0", "stable")
        rel = acoes.procurar_atualizacao()
        self.assertEqual(rel.version, "1.1.0")
        usb = self.d / "usb"; usb.mkdir(); (usb / "subdrive.json").write_text('{"version": "1.0.0", "platform": "UHD"}')
        d = drives.Drive(path=usb, label="USB", filesystem="FAT32").judge()
        with mock.patch.object(drives, "find", return_value=[d]):
            r = acoes.atualizar(rel)
        self.assertEqual(json.loads((self.d / "pacote/manifest.json").read_text())["version"], "1.1.0")
        self.assertTrue(r.drives_behind)

    def test_versoes_de_teste(self):
        self.server.add("1.1.0-beta.1", "beta")
        self.assertIsNone(acoes.procurar_atualizacao())
        acoes.mudar_versoes_de_teste(True)
        self.assertTrue(update.wants_beta(self.d))
        self.assertEqual(acoes.procurar_atualizacao().version, "1.1.0-beta.1")

    def test_assinatura_errada(self):
        from tests.test_update import OTHER
        self.server.add("1.1.0", "stable")
        with mock.patch.object(update, "PUBLIC_KEY", OTHER):
            with self.assertRaises(acoes.Falha):
                acoes.procurar_atualizacao()

    def test_atualiza_o_programa(self):
        """Programa empacotado (Windows/Linux): baixa o executável novo da chave app-<sistema>, confere e troca."""
        self.server.add("1.1.0", "stable")
        rel = acoes.procurar_atualizacao()
        prog = b"SubDrive novo"
        url = "https://x/1.1.0/app-novo"
        rel.files[acoes.app_key()] = {"name": "app-novo", "sha256": __import__("hashlib").sha256(prog).hexdigest(), "bytes": len(prog)}
        rel.urls["app-novo"] = url
        self.server.assets[url] = prog
        exe = self.d / "SubDrive"; exe.write_bytes(b"SubDrive velho")
        with mock.patch.object(lugares, "FROZEN", True), mock.patch.object(lugares, "executable", return_value=exe):
            r = acoes.atualizar(rel)
        self.assertTrue(r.restart)
        self.assertEqual(exe.read_bytes(), prog)
        self.assertEqual(json.loads((self.d / "pacote/manifest.json").read_text())["version"], "1.1.0")

    def test_versao_sem_o_programa_com_janelas(self):
        """Uma versão publicada sem a chave app-<sistema>: troca só o pacote e avisa, sem quebrar nada."""
        self.server.add("1.1.0", "stable")
        rel = acoes.procurar_atualizacao()
        exe = self.d / "SubDrive"; exe.write_bytes(b"SubDrive velho")
        with mock.patch.object(lugares, "FROZEN", True), mock.patch.object(lugares, "executable", return_value=exe):
            r = acoes.atualizar(rel)
        self.assertFalse(r.restart)
        self.assertEqual(exe.read_bytes(), b"SubDrive velho")
        self.assertTrue(any("página do projeto" in text for _, text in r.lines))

    def test_troca_do_app_no_mac(self):
        app = self.d / "SubDrive.app"; (app / "Contents/MacOS").mkdir(parents=True)
        (app / "Contents/Info.plist").write_text("velho"); (app / "Contents/MacOS/SubDrive").write_text("velho")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("SubDrive.app/Contents/Info.plist", "novo")
            info = zipfile.ZipInfo("SubDrive.app/Contents/MacOS/SubDrive"); info.external_attr = 0o100755 << 16
            z.writestr(info, "novo")
            link = zipfile.ZipInfo("SubDrive.app/Contents/Current"); link.external_attr = 0o120777 << 16
            z.writestr(link, "MacOS")
        with mock.patch.object(lugares, "executable", return_value=app):
            acoes.replace_program(buf.getvalue())
        self.assertEqual((app / "Contents/Info.plist").read_text(), "novo")
        self.assertTrue(os.access(app / "Contents/MacOS/SubDrive", os.X_OK))
        self.assertTrue((app / "Contents/Current").is_symlink())
        self.assertFalse((self.d / "SubDrive.app.antigo").exists())

    def test_zip_malicioso(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("../fora.txt", "x")
        with self.assertRaises(update.UpdateError):
            acoes.extract(zipfile.ZipFile(io.BytesIO(buf.getvalue())), self.d / "x")


class Janela(Base):
    """A janela abre, mostra as legendas e abre cada diálogo sem erro."""
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        from subdrive_app import tema
        from subdrive import pgs
        tema.load_fonts(pgs.FONT_DIR); tema.apply(cls.app)

    def pump(self, seconds=0.3):
        import time
        end = time.time() + seconds
        while time.time() < end:
            self.app.processEvents(); time.sleep(0.01)

    def test_telas_e_dialogos(self):
        from subdrive_app import dialogos, janela, tela_pendrive
        with mock.patch.object(lugares, "program_dir", return_value=self.a):
            w = janela.Janela(); w.show(); self.pump(1.5)
            names = sorted(e.path.name for e in w.legendas.by_path.values())
            self.assertEqual(names, ["Bom.srt", "Ruim.srt"])
            for _ in range(30):
                if all(e.result for e in w.legendas.by_path.values()):
                    break
                self.pump(0.2)
            ruim = next(e for e in w.legendas.by_path.values() if e.path.name == "Ruim.srt")
            bom = next(e for e in w.legendas.by_path.values() if e.path.name == "Bom.srt")
            self.assertFalse(ruim.result.ok); self.assertTrue(bom.result.ok)
            w.legendas.open(ruim); self.pump(); w.legendas.back()
            for dlg in (dialogos.Corrigir(w, ruim), dialogos.CriarPGS(w, bom), dialogos.Sincronizar(w, bom), dialogos.Regras(w)):
                dlg.show(); self.pump(1.0); dlg.busy = False; dlg.reject()
            for k in range(4):
                w.go(k); self.pump(0.2)
            w.open_paths([self.a / "legendas/Bom.srt", self.d / "nao-existe.srt"]); self.pump(0.5)
            self.assertEqual(w.legendas.stack.currentIndex(), 1)  # uma legenda só: abre o detalhe dela
            self.assertEqual(w.legendas.current.path.name, "Bom.srt")
            w.retheme(); self.pump(0.3)
            w.close()


if __name__ == "__main__":
    unittest.main()
