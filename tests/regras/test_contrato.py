"""Regras do contrato SRT_LATINO_ITALICO_1 e suas fronteiras."""

import unittest

from subdrive.regras.contrato import (CONTRATO_ID, MAX_BYTES, MAX_ENTRADAS, MAX_LINHAS, validar_bytes)
from subdrive.regras.modelo import caracteres, interpretar_flexivel
from tests.regras.auxiliar import entrada, sequencia, srt, uma


def codigos(dados: bytes, severidade="erro") -> list:
    return [d.codigo for d in validar_bytes(dados).diagnosticos if d.severidade == severidade]


class TestTextoTabelaMinima(unittest.TestCase):
    """Casos mínimos da especificação, dentro de uma entrada com índice e tempo válidos."""

    def aceito(self, texto):
        r = validar_bytes(uma(texto))
        self.assertTrue(r.valido, f"{texto!r}: {[d.codigo for d in r.erros]}")
        return r

    def recusado(self, texto, *esperados):
        r = validar_bytes(uma(texto))
        self.assertFalse(r.valido, texto)
        for c in esperados:
            self.assertIn(c, [d.codigo for d in r.erros], texto)
        return r

    def test_ola_acao(self):
        self.aceito("Olá, ação!")

    def test_italico_parcial(self):
        self.aceito("Antes <i>ação</i> depois.")
        doc = interpretar_flexivel(uma("Antes <i>ação</i> depois.").decode())
        trechos = doc.entradas[0].linhas[0]
        self.assertEqual([(t.texto, t.italico) for t in trechos],
                         [("Antes ", False), ("ação", True), (" depois.", False)])

    def test_italico_atravessa_linhas_com_caixas_diferentes(self):
        self.aceito("<I>primeira\nsegunda</i>")
        doc = interpretar_flexivel(uma("<I>primeira\nsegunda</i>").decode())
        self.assertTrue(all(t.italico for l in doc.entradas[0].linhas for t in l))

    def test_linha_so_com_tag(self):
        self.recusado("<i>\ntexto</i>", "LINHA_SEM_TEXTO")

    def test_par_vazio(self):
        self.recusado("<i></i>texto", "ITALICO_VAZIO")

    def test_espaco_estilizado(self):
        self.aceito("<i> </i>x")

    def test_aninhado_orfao_aberto(self):
        self.recusado("<i><i>x</i></i>", "ITALICO_ANINHADO")
        self.recusado("x</i>", "ITALICO_FECHAMENTO_ORFAO")
        self.recusado("<i>x", "ITALICO_SEM_FECHAMENTO")

    def test_tags_desconhecidas(self):
        self.recusado('<i class="x">texto</i>', "TAG_NAO_SUPORTADA")
        self.recusado("<b>texto</b>", "TAG_NAO_SUPORTADA")
        self.recusado("< i>texto</i>", "TAG_NAO_SUPORTADA")

    def test_63_normais_e_uma_italica(self):
        texto = "a" * 63 + "<i>b</i>"
        self.aceito(texto)
        linha = interpretar_flexivel(uma(texto).decode()).entradas[0].linhas[0]
        chars = caracteres(linha)
        self.assertEqual(len(chars), 64)
        self.assertEqual(chars[63], ("b", True))
        self.assertFalse(any(i for _c, i in chars[:63]))

    def test_64_e_65_visiveis(self):
        self.aceito("a" * 64)
        r = self.recusado("a" * 65, "LINHA_LONGA")
        self.assertEqual([d.codigo for d in r.erros], ["LINHA_LONGA"])

    def test_so_espacos(self):
        r = self.recusado("   ", "LINHA_EM_BRANCO")
        self.assertEqual([d.codigo for d in r.erros], ["LINHA_EM_BRANCO"])

    def test_so_nbsp(self):
        r = self.aceito("  ")
        self.assertIn("LINHA_VISUALMENTE_VAZIA", [d.codigo for d in r.avisos])

    def test_reticencias(self):
        self.aceito("...")
        self.recusado("…", "CARACTERE_NAO_PERMITIDO")

    def test_entidade_literal(self):
        self.aceito("Tom &amp; Jerry")

    def test_caracteres_proibidos(self):
        for c in ["\t", "😀", "é", "“", "–", "‮", "Ā", "<", ">", "\x1b"]:
            with self.subTest(c=repr(c)):
                self.recusado(f"ab{c}cd", "CARACTERE_NAO_PERMITIDO")

    def test_latin1_permitido(self):
        self.aceito("ÀÁÂÃÄÅÇÈÉÊËÌÍÎÏÑÒÓÔÕÖÙÚÛÜàáâãçéêíóôõúü ¿¡ «» ° ª º ÿ")


class TestTagsELimitesBrutos(unittest.TestCase):
    def test_16_tags_aceitas_18_recusadas(self):
        l8 = "<i>a</i><i>b</i><i>c</i><i>d</i>"  # 8 tags
        self.assertTrue(validar_bytes(uma(f"{l8}\n{l8}")).valido)
        r = validar_bytes(uma(f"{l8}\n{l8}<i>e</i>"))
        self.assertEqual([d.codigo for d in r.erros], ["TAGS_EXCEDIDAS"])

    def test_128_brutos_versus_129(self):
        # Com <= 64 visíveis e <= 16 tags o máximo bruto possível é 120, então o
        # limite de 128 não pode ser isolado sem exceder tags: a única diferença
        # entre os dois casos deve ser LINHA_BRUTA_EXCEDIDA.
        pares = "<i>a</i>" * 10  # 80 brutos, 10 visíveis, 20 tags
        l128 = pares + "b" * 48  # 128 brutos, 58 visíveis
        l129 = pares + "b" * 49
        self.assertEqual(len(l128), 128)
        self.assertEqual(codigos(uma(l128)), ["TAGS_EXCEDIDAS"])
        self.assertEqual(sorted(codigos(uma(l129))), ["LINHA_BRUTA_EXCEDIDA", "TAGS_EXCEDIDAS"])

    def test_estado_reinicia_por_entrada(self):
        dados = srt(entrada(1, 1000, 2000, "<i>aberto"), entrada(2, 2000, 3000, "fecha</i>")).encode()
        r = validar_bytes(dados)
        por_entrada = {(d.entrada, d.codigo) for d in r.erros}
        self.assertIn((1, "ITALICO_SEM_FECHAMENTO"), por_entrada)
        self.assertIn((2, "ITALICO_FECHAMENTO_ORFAO"), por_entrada)


class TestBytesELinhas(unittest.TestCase):
    def test_lf_crlf_e_cr_final(self):
        base = srt(entrada(1, 1000, 2000, "Oi"), entrada(2, 2000, 3000, "Tchau"))
        self.assertTrue(validar_bytes(base.encode()).valido)
        crlf = base.replace("\n", "\r\n").encode()
        r = validar_bytes(crlf)
        self.assertTrue(r.valido)
        self.assertEqual(r.resumo["finais_de_linha"]["tipo"], "CRLF")
        cr_final = base.rstrip("\n").replace("\n", "\r\n") + "\r"
        r = validar_bytes(cr_final.encode())
        self.assertTrue(r.valido)
        self.assertTrue(r.resumo["finais_de_linha"]["cr_final"])
        misto = base.replace("\n", "\r\n", 2).encode()
        self.assertEqual(validar_bytes(misto).resumo["finais_de_linha"]["tipo"], "misto")

    def test_cr_interno_e_cr_como_separador(self):
        self.assertIn("CR_INTERNO", codigos(uma("a\rb")))
        so_cr = srt(entrada(1, 1000, 2000, "Oi"), entrada(2, 2000, 3000, "Tchau")).replace("\n", "\r")
        self.assertFalse(validar_bytes(so_cr.encode()).valido)

    def test_separador_com_espacos_nao_separa(self):
        dados = ("1\n00:00:01,000 --> 00:00:02,000\nOi\n   \n2\n00:00:02,000 --> 00:00:03,000\nTchau\n")
        c = codigos(dados.encode())
        self.assertIn("LINHA_EM_BRANCO", c)
        self.assertIn("SEPARADOR_AUSENTE", c)

    def test_linha_final_contada(self):
        r = validar_bytes(b"1\n00:00:01,000 --> 00:00:02,000\na\n")
        self.assertEqual(r.resumo["linhas"], 4)
        r = validar_bytes(b"1\n00:00:01,000 --> 00:00:02,000\na")
        self.assertEqual(r.resumo["linhas"], 3)

    def test_limite_de_linhas(self):
        base = b"1\n00:00:01,000 --> 00:00:02,000\na\n"  # 4 linhas
        ok = base + b"\n" * (MAX_LINHAS - 4)
        self.assertEqual(validar_bytes(ok).resumo["linhas"], MAX_LINHAS)
        self.assertTrue(validar_bytes(ok).valido)
        self.assertEqual(codigos(ok + b"\n"), ["LINHAS_EXCEDIDAS"])

    def _gerar_tamanho(self, alvo: int) -> bytes:
        texto = "a" * 64
        blocos = []
        tamanho = 1  # LF final
        i = 0
        while True:
            i += 1
            b = entrada(i, 1000 + (i - 1) * 1000, 1500 + (i - 1) * 1000, texto, texto)
            extra = len(b) + (2 if blocos else 0)
            if tamanho + extra > alvo:
                break
            blocos.append(b)
            tamanho += extra
        dados = (srt(*blocos) + "\n" * (alvo - tamanho)).encode()
        self.assertEqual(len(dados), alvo)
        return dados

    def test_limite_de_bytes(self):
        ok = self._gerar_tamanho(MAX_BYTES)
        r = validar_bytes(ok)
        self.assertTrue(r.valido, [d.codigo for d in r.erros][:5])
        self.assertLess(r.resumo["linhas"], MAX_LINHAS)
        self.assertEqual(codigos(ok + b"\n"), ["TAMANHO_EXCEDIDO"])

    def test_arquivo_vazio_e_so_bom(self):
        self.assertEqual(codigos(b""), ["ARQUIVO_VAZIO"])
        self.assertEqual(codigos(b"\xef\xbb\xbf"), ["SEM_ENTRADAS"])
        self.assertEqual(codigos(b"\n\n\n"), ["SEM_ENTRADAS"])

    def test_bom_inicial_e_interno(self):
        self.assertTrue(validar_bytes(b"\xef\xbb\xbf" + uma("Oi")).valido)
        self.assertTrue(validar_bytes(b"\xef\xbb\xbf" + uma("Oi")).resumo["bom"])
        self.assertIn("BOM_INTERNO", codigos(uma("O﻿i")))
        self.assertFalse(validar_bytes(b"\xef\xbb\xbf\xef\xbb\xbf" + uma("Oi")).valido)

    def test_utf8_invalido_sem_substituicao(self):
        r = validar_bytes(uma("Olá").replace("á".encode(), b"\xe1"))
        self.assertEqual([d.codigo for d in r.erros], ["UTF8_INVALIDO"])
        self.assertTrue(r.interrompido)
        self.assertIsNone(r.resumo["entradas"])
        self.assertEqual(r.resumo["codificacao_sugerida"], "cp1252")

    def test_utf16_identificado(self):
        r = validar_bytes("1\n".encode("utf-16"))
        self.assertEqual([d.codigo for d in r.erros], ["CODIFICACAO_UTF16"])


class TestEntradasETempos(unittest.TestCase):
    def test_indices(self):
        for idx in ["01", " 1", "1 ", "+1", "١", "１"]:
            with self.subTest(idx=idx):
                dados = srt(entrada(1, 1000, 2000, "Oi", indice=idx)).encode()
                self.assertIn("INDICE_INVALIDO", codigos(dados))
        fora = srt(entrada(1, 1000, 2000, "a"), entrada(3, 2000, 3000, "b")).encode()
        self.assertEqual(codigos(fora), ["INDICE_FORA_DE_SEQUENCIA"])
        nao_ordena = srt(entrada(2, 1000, 2000, "a"), entrada(1, 2000, 3000, "b")).encode()
        self.assertEqual(codigos(nao_ordena), ["INDICE_FORA_DE_SEQUENCIA"] * 2)

    def test_formato_de_tempo(self):
        validos = "1\n00:00:01,000 --> 00:00:02,000\nOi\n"
        self.assertTrue(validar_bytes(validos.encode()).valido)
        for linha in ["00:00:01.000 --> 00:00:02,000", "0:00:01,000 --> 00:00:02,000",
                      "00:00:01,000 --> 00:00:02,000 X1:10 X2:20", "00:00:01,000-->00:00:02,000",
                      "00:00:01,000 --> 00:00:02,000 ", "００:00:01,000 --> 00:00:02,000",
                      "00:00:01,00 --> 00:00:02,000"]:
            with self.subTest(linha=linha):
                self.assertIn("TEMPO_FORMATO", codigos(f"1\n{linha}\nOi\n".encode()))
        self.assertIn("TEMPO_INVALIDO", codigos(b"1\n00:60:01,000 --> 00:60:02,000\nOi\n"))
        self.assertIn("TEMPO_INVALIDO", codigos(b"1\n00:00:61,000 --> 00:00:62,000\nOi\n"))

    def test_duracoes(self):
        self.assertEqual(codigos(srt(entrada(1, 1000, 1199, "a")).encode()), ["DURACAO_CURTA"])
        self.assertEqual(codigos(srt(entrada(1, 1000, 1200, "a")).encode()), [])
        self.assertEqual(codigos(srt(entrada(1, 1000, 61000, "a")).encode()), [])
        self.assertEqual(codigos(srt(entrada(1, 1000, 61001, "a")).encode()), ["DURACAO_LONGA"])
        self.assertEqual(codigos(srt(entrada(1, 2000, 2000, "a")).encode()), ["FIM_NAO_POSTERIOR"])
        self.assertEqual(codigos(srt(entrada(1, 2000, 1000, "a")).encode()), ["FIM_NAO_POSTERIOR"])

    def test_fim_quatro_horas(self):
        h4 = 14_400_000
        self.assertEqual(codigos(srt(entrada(1, h4 - 1000, h4, "a")).encode()), [])
        self.assertEqual(codigos(srt(entrada(1, h4 - 1000, h4 + 1, "a")).encode()), ["FIM_EXCEDE_LIMITE"])

    def test_sobreposicao_e_juncao(self):
        junta = srt(entrada(1, 1000, 2000, "a"), entrada(2, 2000, 3000, "b")).encode()
        self.assertTrue(validar_bytes(junta).valido)
        sob = srt(entrada(1, 1000, 2000, "a"), entrada(2, 1999, 3000, "b")).encode()
        r = validar_bytes(sob)
        self.assertEqual([d.codigo for d in r.erros], ["SOBREPOSICAO"])
        self.assertEqual(r.resumo["sobreposicoes"], 1)

    def test_quantidade_de_entradas(self):
        ok = sequencia(MAX_ENTRADAS).encode()
        r = validar_bytes(ok)
        self.assertTrue(r.valido)
        self.assertEqual(r.resumo["entradas"], MAX_ENTRADAS)
        demais = sequencia(MAX_ENTRADAS + 1).encode()
        self.assertEqual(codigos(demais), ["ENTRADAS_EXCEDIDAS"])

    def test_linhas_de_texto(self):
        self.assertEqual(codigos(uma("a\nb\nc")), ["LINHAS_DE_TEXTO_EXCEDIDAS"])
        self.assertIn("SEM_TEXTO", codigos(b"1\n00:00:01,000 --> 00:00:02,000\n\n"))

    def test_linhas_vazias_toleradas(self):
        dados = ("\n\n" + srt(entrada(1, 1000, 2000, "a")) + "\n\n\n" + srt(entrada(2, 2000, 3000, "b"))).encode()
        self.assertTrue(validar_bytes(dados).valido)

    def test_acumula_erros_e_aponta_linha_fisica(self):
        dados = srt(entrada(1, 1000, 2000, "<i>a"), entrada(2, 2000, 2100, "b"),
                    entrada(3, 3000, 4000, "c" * 70)).encode()
        r = validar_bytes(dados)
        achados = {(d.codigo, d.entrada, d.linha) for d in r.erros}
        self.assertIn(("ITALICO_SEM_FECHAMENTO", 1, 3), achados)
        self.assertIn(("DURACAO_CURTA", 2, 6), achados)
        self.assertIn(("LINHA_LONGA", 3, 11), achados)

    def test_interrupcao_sem_inventar_entradas(self):
        dados = (srt(entrada(1, 1000, 2000, "a")) + "\ntexto solto\n\n" + srt(entrada(2, 2000, 3000, "b"))).encode()
        r = validar_bytes(dados)
        self.assertTrue(r.interrompido)
        self.assertEqual(r.linha_interrupcao, 5)
        self.assertEqual(r.resumo["estado_contagens"], "parcial")
        self.assertEqual(r.resumo["entradas"], 1)
        self.assertIsNone(r.resumo["ultimo_fim_ms"])


class TestResumo(unittest.TestCase):
    def test_resumo_exato_de_arquivo_valido(self):
        dados = srt(entrada(1, 1200, 3000, "<i>Oi</i>"), entrada(2, 3000, 5000, "Tchau"),
                    entrada(3, 6000, 9000, "Fim", "<i>de</i> tudo")).encode()
        r = validar_bytes(dados)
        self.assertTrue(r.valido)
        self.assertEqual(r.resumo, {
            "tamanho_bytes": len(dados), "codificacao": "UTF-8", "bom": False,
            "finais_de_linha": {"tipo": "LF", "lf": 12, "crlf": 0, "cr_final": False},
            "linhas": 13, "entradas": 3, "estado_contagens": "completo",
            "primeiro_inicio_ms": 1200, "ultimo_fim_ms": 9000, "intervalo_ms": 7800,
            "entradas_com_italico": 2, "erros_de_marcacao": 0, "sobreposicoes": 0,
            "violacoes_de_texto": 0,
        })

    def test_identificador_do_contrato(self):
        self.assertEqual(CONTRATO_ID, "SRT_LATINO_ITALICO_1")


if __name__ == "__main__":
    unittest.main()
