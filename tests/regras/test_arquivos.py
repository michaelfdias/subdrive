"""Nomes, links, pastas e gravação atômica com conferência."""

import os
import unicodedata
import unittest
from unittest import mock

from subdrive.regras import arquivos
from subdrive.regras.arquivos import (colisao_na_pasta, conferir_gravacao, gravar_exclusivo, ler_arquivo,
                                   nome_alternativo, nome_real, nome_sugerido, validar_arquivo,
                                   validar_nome, validar_pasta, verificar_destino)
from subdrive.regras.erros import ArquivoIncompativel, ErroAcesso
from tests.regras.auxiliar import escrever, listar, pasta_temporaria, uma


def erros_nome(nome):
    return [d.codigo for d in validar_nome(nome) if d.severidade == "erro"]


class TestNomes(unittest.TestCase):
    def test_nomes_validos(self):
        for nome in ["a.srt", "Filme.srt", "Ação e reação (1999).srt", "x" * 124 + ".srt"]:
            with self.subTest(nome=nome):
                self.assertEqual(erros_nome(nome), [])

    def test_nomes_invalidos(self):
        casos = {
            ".srt": ["NOME_CURTO", "NOME_OCULTO"],
            "Filme.SRT": ["NOME_EXTENSAO"],
            "Filme.srt.txt": ["NOME_EXTENSAO"],
            ".oculto.srt": ["NOME_OCULTO"],
            "._Filme.srt": ["NOME_OCULTO"],
            "x" * 125 + ".srt": ["NOME_LONGO"],
            "a:b.srt": ["NOME_CARACTERE"],
            "a\\b.srt": ["NOME_CARACTERE"],
            "Ōsaka.srt": ["NOME_CARACTERE"],
            "a\tb.srt": ["NOME_CARACTERE"],
        }
        for nome, esperado in casos.items():
            with self.subTest(nome=nome):
                self.assertEqual(sorted(erros_nome(nome)), sorted(esperado))

    def test_nfd_nao_passa_por_ser_normalizavel(self):
        nfd = unicodedata.normalize("NFD", "Ação.srt")
        self.assertEqual(erros_nome(nfd), ["NOME_CARACTERE"])
        self.assertIn("NFD", validar_nome(nfd)[0].motivo)
        self.assertEqual(nome_alternativo(nfd), "Ação.srt")

    def test_alternativa_ascii(self):
        self.assertEqual(nome_alternativo("Ōsaka – noite.srt"), "Osaka _ noite.srt")
        self.assertEqual(erros_nome(nome_alternativo("Ōsaka – noite.srt")), [])
        self.assertEqual(nome_alternativo("Filme.SRT"), "Filme.srt")

    def test_aviso_de_portabilidade(self):
        d = validar_nome("Filme?.srt")
        self.assertEqual([x.codigo for x in d], ["NOME_PORTABILIDADE"])
        self.assertEqual(d[0].severidade, "aviso")

    def test_nome_sugerido(self):
        self.assertEqual(nome_sugerido("Filme.srt"), "Filme.preparada.srt")
        self.assertEqual(nome_sugerido("Filme.SRT"), "Filme.preparada.srt")
        longo = nome_sugerido("y" * 140 + ".srt")
        self.assertEqual(len(longo), 128)
        self.assertTrue(longo.endswith(".preparada.srt"))
        self.assertEqual(erros_nome(nome_sugerido(unicodedata.normalize("NFD", "Ação.srt"))), [])


class TestCaminhos(unittest.TestCase):
    def setUp(self):
        self.d = pasta_temporaria(self)

    def test_nome_real_revela_nfd(self):
        nfd = unicodedata.normalize("NFD", "Ação.srt")
        escrever(self.d, nfd, uma("Oi"))
        caminho_digitado = os.path.join(self.d, "Ação.srt")
        if os.path.exists(caminho_digitado) and nome_real(caminho_digitado) == nfd:
            res, nome, _ = validar_arquivo(caminho_digitado)
            self.assertFalse(res.valido)
        res, nome, _ = validar_arquivo(os.path.join(self.d, nfd))
        self.assertEqual(nome, nfd)
        self.assertIn("NOME_CARACTERE", [x.codigo for x in res.erros])

    def test_links_simbolicos_recusados(self):
        alvo = escrever(self.d, "real.srt", uma("Oi"))
        link = os.path.join(self.d, "link.srt")
        os.symlink(alvo, link)
        with self.assertRaises(ArquivoIncompativel):
            ler_arquivo(link)
        res, _n, _d = validar_arquivo(link)
        self.assertEqual([x.codigo for x in res.erros], ["LINK_SIMBOLICO"])
        sub = os.path.join(self.d, "sub")
        os.mkdir(sub)
        escrever(sub, "f.srt", uma("Oi"))
        os.symlink(sub, os.path.join(self.d, "atalho"))
        with self.assertRaises(ArquivoIncompativel):
            ler_arquivo(os.path.join(self.d, "atalho", "f.srt"))

    def test_inexistente_e_pasta(self):
        with self.assertRaises(ErroAcesso):
            ler_arquivo(os.path.join(self.d, "nao.srt"))
        with self.assertRaises(Exception) as ctx:
            ler_arquivo(self.d)
        self.assertEqual(ctx.exception.codigo, "ENTRADA_E_PASTA")

    def test_colisao_por_caixa_e_normalizacao(self):
        escrever(self.d, "Filme.Preparada.srt", b"x")
        escrever(self.d, unicodedata.normalize("NFC", "Ação.srt"), b"x")
        self.assertEqual(colisao_na_pasta(self.d, "filme.preparada.srt"), "Filme.Preparada.srt")
        with self.assertRaises(ErroAcesso) as ctx:
            verificar_destino(os.path.join(self.d, "filme.preparada.srt"))
        self.assertEqual(ctx.exception.codigo, "DESTINO_COLISAO")
        with self.assertRaises(ErroAcesso) as ctx:
            verificar_destino(os.path.join(self.d, unicodedata.normalize("NFD", "Ação.srt")))
        self.assertIn(ctx.exception.codigo, ("DESTINO_COLISAO", "DESTINO_EXISTE"))

    def test_destino_existente_e_igual_a_entrada(self):
        e = escrever(self.d, "Filme.srt", uma("Oi"))
        with self.assertRaises(ErroAcesso) as ctx:
            verificar_destino(e, e)
        self.assertEqual(ctx.exception.codigo, "SAIDA_IGUAL_ENTRADA")
        with self.assertRaises(ErroAcesso) as ctx:
            verificar_destino(e)
        self.assertEqual(ctx.exception.codigo, "DESTINO_EXISTE")
        with self.assertRaises(ErroAcesso):
            verificar_destino(os.path.join(self.d, "nao-existe", "x.srt"))


class TestPasta(unittest.TestCase):
    def setUp(self):
        self.d = pasta_temporaria(self)

    def _encher(self, n_visiveis, n_ocultos):
        for i in range(n_visiveis):
            escrever(self.d, f"F{i:02d}.srt", uma(f"Oi {i}"))
        for i in range(n_ocultos):
            escrever(self.d, f".oculto{i}", b"x")

    def test_64_itens_incluindo_ocultos(self):
        self._encher(60, 4)
        r = validar_pasta(self.d)
        self.assertEqual(r.total_itens, 64)
        self.assertTrue(r.valido)

    def test_65_itens(self):
        self._encher(60, 5)
        r = validar_pasta(self.d)
        self.assertEqual(r.total_itens, 65)
        self.assertFalse(r.valido)
        self.assertEqual([x.codigo for x in r.diagnosticos], ["PASTA_ITENS_EXCEDIDOS"])

    def test_pasta_vazia(self):
        r = validar_pasta(self.d)
        self.assertTrue(r.valido)
        self.assertEqual(r.legendas, [])

    def test_itens_ignorados_links_e_nomes(self):
        escrever(self.d, "Bom.srt", uma("Oi"))
        escrever(self.d, "Ruim.SRT", uma("Oi"))
        escrever(self.d, "._Bom.srt", b"\x00\x05\x16\x07")
        escrever(self.d, "capa.jpg", b"x")
        os.mkdir(os.path.join(self.d, "Extras"))
        escrever(os.path.join(self.d, "Extras"), "Dentro.srt", b"lixo")
        os.symlink(os.path.join(self.d, "Bom.srt"), os.path.join(self.d, "Link.srt"))
        antes = listar(self.d)
        r = validar_pasta(self.d)
        self.assertEqual(listar(self.d), antes)
        por_nome = {n: res for n, res in r.legendas}
        self.assertTrue(por_nome["Bom.srt"].valido)
        self.assertIn("NOME_EXTENSAO", [x.codigo for x in por_nome["Ruim.SRT"].erros])
        self.assertIn("NOME_OCULTO", [x.codigo for x in por_nome["._Bom.srt"].erros])
        self.assertIn("LINK_SIMBOLICO", [x.codigo for x in por_nome["Link.srt"].erros])
        ignorados = dict(r.ignorados)
        self.assertIn("capa.jpg", ignorados)
        self.assertIn("Extras", ignorados)
        self.assertNotIn("Dentro.srt", por_nome)  # sem recursão
        self.assertEqual(r.total_itens, 6)
        self.assertFalse(r.valido)


class TestGravacao(unittest.TestCase):
    def setUp(self):
        self.d = pasta_temporaria(self)

    def test_grava_e_confere(self):
        dados = uma("Oi")
        destino = os.path.join(self.d, "Saida.srt")
        gravar_exclusivo(destino, dados)
        with open(destino, "rb") as f:
            self.assertEqual(f.read(), dados)
        self.assertEqual(listar(self.d), ["Saida.srt"])  # temporário removido
        self.assertTrue(conferir_gravacao(destino, dados).ok)

    def test_nao_sobrescreve(self):
        destino = escrever(self.d, "Saida.srt", b"original")
        with self.assertRaises(ErroAcesso):
            gravar_exclusivo(destino, uma("Oi"))
        with open(destino, "rb") as f:
            self.assertEqual(f.read(), b"original")

    def test_sem_suporte_a_link_usa_o_excl(self):
        destino = os.path.join(self.d, "Saida.srt")
        erro = OSError(1, "Operation not permitted")
        with mock.patch.object(arquivos.os, "link", side_effect=erro):
            gravar_exclusivo(destino, uma("Oi"))
        self.assertEqual(listar(self.d), ["Saida.srt"])

    def test_falha_de_escrita_nao_deixa_lixo(self):
        destino = os.path.join(self.d, "Saida.srt")
        with mock.patch.object(arquivos.os, "write", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(ErroAcesso) as ctx:
                gravar_exclusivo(destino, uma("Oi"))
        self.assertEqual(ctx.exception.codigo, "FALHA_ESCRITA")
        self.assertEqual(listar(self.d), [])

    def test_conferencia_detecta_divergencia(self):
        destino = os.path.join(self.d, "Saida.srt")
        gravar_exclusivo(destino, uma("Oi"))
        conf = conferir_gravacao(destino, uma("Outro"))
        self.assertFalse(conf.ok)
        self.assertEqual([x.codigo for x in conf.problemas], ["HASH_DIVERGENTE"])


if __name__ == "__main__":
    unittest.main()
