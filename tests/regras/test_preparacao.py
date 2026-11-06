"""Preparação: leitura flexível, codificação, acentos, pontuação, estilo, créditos e tempo."""

import unittest

from subdrive.regras.codificacao import ErroCodificacao, decodificar, reparos_em_texto
from subdrive.regras.contrato import validar_bytes
from subdrive.regras.creditos import detectar_creditos
from subdrive.regras.erros import ErroUso
from subdrive.regras.modelo import (caracteres, interpretar_flexivel, serializar_documento,
                                 serializar_linhas)
from subdrive.regras.preparacao import Opcoes, preparar, redividir
from subdrive.regras.tempo import interpretar_deslocamento
from tests.regras.auxiliar import entrada, sequencia, srt, uma


def texto_saida(r) -> str:
    return r.bytes_saida.decode("utf-8")


class TestLeituraFlexivel(unittest.TestCase):
    def test_arquivo_valido_e_preservado_byte_a_byte(self):
        dados = srt(entrada(1, 1000, 2000, "<I>primeira", "segunda</i>"),
                    entrada(2, 2000, 3000, "Antes <i>ação</i> depois."),
                    entrada(3, 3000, 4000, "<i>a</i><i>b</i>")).encode()
        r = preparar(dados, Opcoes())
        self.assertTrue(r.ok)
        self.assertEqual(r.bytes_saida, dados)

    def test_canonicaliza_bom_crlf_e_linhas_extras(self):
        base = srt(entrada(1, 1000, 2000, "Oi"), entrada(2, 2000, 3000, "Tchau"))
        sujo = ("﻿\r\n" + base.replace("\n", "\r\n") + "\r\n\r\n").encode()
        r = preparar(sujo, Opcoes())
        self.assertTrue(r.ok)
        self.assertEqual(r.bytes_saida, base.encode())

    def test_anomalias_exigem_corrigir_estrutura(self):
        quebrado = ("01\n00:00:01.000 --> 00:00:02,000 X1:10\nOi\n2\n0:00:02,000 --> 00:00:03,000\nTchau\n"
                    "   \n\n00:00:04,000 --> 00:00:05,000\nSem índice\n")
        r = preparar(quebrado.encode(), Opcoes())
        self.assertFalse(r.ok)
        cods = {b.codigo for b in r.bloqueios}
        self.assertTrue({"NUMERACAO", "TEMPO_FORMATO", "SEPARADOR_AUSENTE", "SEPARADOR_COM_ESPACOS",
                         "INDICE_AUSENTE"} <= cods, cods)
        r = preparar(quebrado.encode(), Opcoes(corrigir_estrutura=True))
        self.assertTrue(r.ok, [b.codigo for b in r.bloqueios])
        self.assertEqual(texto_saida(r), srt(entrada(1, 1000, 2000, "Oi"), entrada(2, 2000, 3000, "Tchau"),
                                             entrada(3, 4000, 5000, "Sem índice")))
        self.assertTrue(any(m.tipo == "estrutura" for m in r.mudancas))

    def test_conteudo_solto_nunca_e_descartado(self):
        dados = "1\n00:00:01,000 --> 00:00:02,000\nOi\n\nperdido\n\n2\n00:00:02,000 --> 00:00:03,000\nb\n"
        r = preparar(dados.encode(), Opcoes(corrigir_estrutura=True))
        self.assertFalse(r.ok)
        self.assertIn("CONTEUDO_SOLTO", [b.codigo for b in r.bloqueios])
        self.assertIsNone(r.bytes_saida)

    def test_cr_isolado_so_com_normalizar(self):
        dados = srt(entrada(1, 1000, 2000, "Oi"), entrada(2, 2000, 3000, "Tchau")).replace("\n", "\r").encode()
        self.assertFalse(preparar(dados, Opcoes()).ok)
        r = preparar(dados, Opcoes(normalizar=True))
        self.assertTrue(r.ok)

    def test_nao_ordena_nem_corrige_sobreposicao(self):
        dados = srt(entrada(1, 5000, 6000, "b"), entrada(2, 1000, 2000, "a")).encode()
        r = preparar(dados, Opcoes(corrigir_estrutura=True))
        self.assertFalse(r.ok)
        self.assertIn("SOBREPOSICAO", [d.codigo for d in r.validacao_saida.erros])

    def test_italico_vazio_removido_com_corrigir_estrutura(self):
        r = preparar(uma("<i></i>texto"), Opcoes(corrigir_estrutura=True))
        self.assertTrue(r.ok)
        self.assertIn("\ntexto\n", texto_saida(r))

    def test_serializacao_nao_quebra_tags(self):
        linhas = interpretar_flexivel(uma("<i>a\nb</i> c").decode()).entradas[0].linhas
        self.assertEqual(serializar_linhas(linhas), ["<i>a", "b</i> c"])
        linhas = interpretar_flexivel(uma("<i>a</i>\nb").decode()).entradas[0].linhas
        self.assertEqual(serializar_linhas(linhas), ["<i>a</i>", "b"])


class TestCodificacao(unittest.TestCase):
    def test_cp1252_exige_escolha_explicita(self):
        dados = srt(entrada(1, 1000, 2000, "ação “x”")).encode("cp1252")
        with self.assertRaises(ErroCodificacao) as ctx:
            preparar(dados, Opcoes())
        self.assertEqual(ctx.exception.codigo, "CODIFICACAO_AMBIGUA")
        self.assertIn("cp1252", ctx.exception.amostras)
        r = preparar(dados, Opcoes(codificacao="cp1252", normalizar=True, pontuacao=True))
        self.assertTrue(r.ok)
        self.assertIn('ação "x"', texto_saida(r))
        self.assertEqual(r.codificacao_origem, "Windows-1252")

    def test_utf16_com_bom_reconhecido(self):
        texto = srt(entrada(1, 1000, 2000, "ação"))
        for cod in ("utf-16", "utf-16-be"):
            dados = texto.encode(cod) if cod == "utf-16" else b"\xfe\xff" + texto.encode("utf-16-be")
            r = preparar(dados, Opcoes())
            self.assertTrue(r.ok)
            self.assertEqual(texto_saida(r), texto)

    def test_codificacao_errada_nao_decodifica(self):
        dados = srt(entrada(1, 1000, 2000, "a")).encode() + b"\x81"
        with self.assertRaises(ErroUso):
            preparar(dados, Opcoes(codificacao="cp1252"))

    def test_bom_utf8_removido(self):
        texto = srt(entrada(1, 1000, 2000, "a"))
        r = preparar(b"\xef\xbb\xbf" + texto.encode(), Opcoes())
        self.assertEqual(texto_saida(r), texto)
        self.assertTrue(r.bom_origem)

    def test_nfd_para_nfc(self):
        nfd = uma("ação")
        self.assertFalse(validar_bytes(nfd).valido)
        r = preparar(nfd, Opcoes(normalizar=True))
        self.assertTrue(r.ok)
        self.assertIn("ação", texto_saida(r))
        self.assertNotIn("acao", texto_saida(r))

    def test_mojibake_recuperavel_so_quando_escolhido(self):
        dados = uma("aÃ§Ã£o e nÃ£o")
        r = preparar(dados, Opcoes())
        self.assertEqual([(p.antes, p.depois, p.nivel) for p in r.propostas],
                         [("Ã§Ã£", "çã", "provavel"), ("Ã£", "ã", "provavel")])
        self.assertIn("aÃ§Ã£o", texto_saida(r))  # nada aplicado sem escolha
        self.assertIn("ACENTOS_PENDENTES", [p.codigo for p in r.pendencias])
        r = preparar(dados, Opcoes(reparar_acentos={2}))
        self.assertIn("aÃ§Ã£o e não", texto_saida(r))
        r = preparar(dados, Opcoes(reparar_acentos="provaveis"))
        self.assertIn("ação e não", texto_saida(r))
        with self.assertRaises(ErroUso):
            preparar(dados, Opcoes(reparar_acentos={9}))

    def test_mojibake_ambiguo_duplo(self):
        duplo = "ação".encode("utf-8").decode("cp1252").encode("utf-8").decode("cp1252")
        r = preparar(uma(duplo), Opcoes())
        self.assertTrue(r.propostas)
        self.assertEqual({p.nivel for p in r.propostas}, {"ambigua"})

    def test_palavras_validas_nao_sao_corrigidas(self):
        self.assertEqual(reparos_em_texto("ação, SÃO PAULO, Ãngulo, é"), [])

    def test_mojibake_preserva_italico(self):
        r = preparar(uma("<i>aÃ§Ã£o</i> x"), Opcoes(reparar_acentos="provaveis"))
        self.assertIn("<i>ação</i> x", texto_saida(r))

    def test_irrecuperavel_avisa(self):
        r = preparar(uma("n�o e a??o"), Opcoes())
        cods = [p.codigo for p in r.pendencias]
        self.assertIn("ACENTO_IRRECUPERAVEL", cods)
        self.assertIn("ACENTO_POSSIVELMENTE_PERDIDO", cods)
        self.assertFalse(r.ok)  # U+FFFD não é permitido no arquivo final

    def test_decodificacao_estrita(self):
        with self.assertRaises(ErroCodificacao):
            decodificar(b"\xff\xfe\x00")


class TestPontuacaoEstiloRedivisao(unittest.TestCase):
    def test_tabela_de_pontuacao(self):
        r = preparar(uma("“Oi” ‘a’ – — fim…"), Opcoes(pontuacao=True))
        self.assertIn("\"Oi\" 'a' - - fim...", texto_saida(r))

    def test_expansao_revalidada(self):
        texto = "a" * 63 + "…"  # 64 visíveis; vira 66
        r = preparar(uma(texto), Opcoes(pontuacao=True))
        self.assertFalse(r.ok)
        self.assertIn("LINHA_LONGA", [d.codigo for d in r.validacao_saida.erros])
        r = preparar(uma(texto), Opcoes(pontuacao=True, redividir=False))
        self.assertIsNotNone(r.bytes_saida)

    def test_sem_mapeamento_fica_pendente(self):
        r = preparar(uma("a•b"), Opcoes(pontuacao=True))
        self.assertIn("•", texto_saida(r))
        self.assertFalse(r.ok)

    def test_remover_formatacao_mantem_texto(self):
        r = preparar(uma('<b>Oi</b> <font color="red">mundo</font> {\\an8}<i>x</i> <palavra>'),
                     Opcoes(remover_formatacao=True))
        self.assertIn("Oi mundo <i>x</i> <palavra>", texto_saida(r))
        self.assertFalse(r.ok)  # <palavra> exige revisão, nunca é apagada

    def test_remover_italico_so_explicito(self):
        self.assertIn("<i>x</i>", texto_saida(preparar(uma("<i>x</i>"), Opcoes(pontuacao=True))))
        self.assertNotIn("<i>", texto_saida(preparar(uma("<i>x</i>"), Opcoes(remover_italico=True))))

    def test_redividir_preserva_estilo(self):
        texto = "Esta fala comprida tem <i>uma parte em itálico</i> no meio e continua depois até o fim"
        r = preparar(uma(texto), Opcoes(redividir=True))
        self.assertTrue(r.ok, [d.codigo for d in r.validacao_saida.erros])
        linhas = interpretar_flexivel(texto_saida(r)).entradas[0].linhas
        self.assertEqual(len(linhas), 2)
        por_linha = ["".join(c for c, i in caracteres(l) if i) for l in linhas]
        self.assertEqual(" ".join(x for x in por_linha if x), "uma parte em itálico")
        self.assertEqual(r.entradas_saida[0].inicio, 1000)

    def test_redividir_tres_linhas_e_italico_atravessando(self):
        r = preparar(uma("<i>um dois\ntrês quatro\ncinco</i>"), Opcoes(redividir=True))
        self.assertTrue(r.ok)
        self.assertEqual(texto_saida(r).split("\n")[2:4], ["<i>um dois três", "quatro cinco</i>"])

    def test_redividir_impossivel_nao_corta(self):
        self.assertIsNone(redividir(interpretar_flexivel(uma("x" * 70).decode()).entradas[0].linhas))
        r = preparar(uma("x" * 70), Opcoes(redividir=True))
        self.assertIn("REDIVISAO_IMPOSSIVEL", [p.codigo for p in r.pendencias])
        self.assertIn("x" * 70, texto_saida(r))


class TestCreditos(unittest.TestCase):
    def doc(self, *textos):
        return interpretar_flexivel(srt(*(entrada(i, i * 1000, i * 1000 + 500, *t.split("\n"))
                                          for i, t in enumerate(textos, 1)))).entradas

    def test_detecta_candidatos_com_motivo(self):
        textos = ["Legendas por Equipe X", "Oi", "Tudo bem?", "Sim", "Não", "Talvez", "Ok", "Visite www.exemplo.com"]
        cands = detectar_creditos(self.doc(*textos))
        self.assertEqual([c.entrada for c in cands], [1, 8])
        self.assertEqual({c.nivel for c in cands}, {"forte"})
        self.assertIn("crédito de legenda", cands[0].motivos)

    def test_falsos_positivos_no_meio(self):
        textos = ["Oi"] * 4 + ["A equipe chegou.", "Siga a estrada.", "Ele estudou tradução."] + ["Ok"] * 4
        self.assertEqual(detectar_creditos(self.doc(*textos)), [])

    def test_creditos_do_filme_preservados(self):
        textos = ["Oi"] * 4 + ["Fim"] + ["Dirigido por Fulano de Tal", "Produção: Estúdio Exemplo"]
        self.assertEqual(detectar_creditos(self.doc(*textos)), [])

    def test_fraco_no_meio_com_dois_indicios(self):
        textos = ["Oi"] * 4 + ["Siga-nos no Instagram"] + ["Ok"] * 4
        cands = detectar_creditos(self.doc(*textos))
        self.assertEqual([(c.entrada, c.nivel) for c in cands], [(5, "fraco")])

    def test_remocao_selecionada_mantem_tempos_e_renumera(self):
        dados = srt(entrada(1, 1000, 2000, "Legendas por X"), entrada(2, 3000, 4000, "Fala"),
                    entrada(3, 5000, 6000, "Outra")).encode()
        r = preparar(dados, Opcoes(remover_entradas={1}))
        self.assertTrue(r.ok)
        self.assertEqual(texto_saida(r), srt(entrada(1, 3000, 4000, "Fala"), entrada(2, 5000, 6000, "Outra")))
        self.assertEqual(r.mapa_indices, [(2, 1), (3, 2)])
        self.assertEqual(r.removidas, [(1, "selecionada explicitamente")])

    def test_dialogo_misturado_preservado(self):
        dados = srt(entrada(1, 1000, 2000, "- Olá!", "Legendas por Equipe X"), entrada(2, 3000, 4000, "Oi")).encode()
        r = preparar(dados, Opcoes(politica_creditos="fortes"))
        self.assertTrue(r.ok)
        self.assertEqual(texto_saida(r), srt(entrada(1, 1000, 2000, "- Olá!"), entrada(2, 3000, 4000, "Oi")))
        self.assertIn("POLITICA_AUTOMATICA", [p.codigo for p in r.pendencias])
        r = preparar(dados, Opcoes(remover_linhas={1: {2}}))
        self.assertEqual(texto_saida(r), srt(entrada(1, 1000, 2000, "- Olá!"), entrada(2, 3000, 4000, "Oi")))

    def test_sem_politica_nada_e_removido(self):
        dados = srt(entrada(1, 1000, 2000, "Legendas por X"), entrada(2, 3000, 4000, "Fala")).encode()
        r = preparar(dados, Opcoes())
        self.assertEqual(r.bytes_saida, dados)
        self.assertIn("CREDITOS_PENDENTES", [p.codigo for p in r.pendencias])

    def test_remover_tudo_recusado(self):
        r = preparar(uma("Legendas por X"), Opcoes(remover_entradas={1}))
        self.assertFalse(r.ok)
        self.assertIn("SAIDA_VAZIA", [b.codigo for b in r.bloqueios])

    def test_selecao_com_numeracao_quebrada_recusada(self):
        dados = srt(entrada(1, 1000, 2000, "a"), entrada(5, 3000, 4000, "b")).encode()
        with self.assertRaises(ErroUso) as ctx:
            preparar(dados, Opcoes(remover_entradas={2}))
        self.assertEqual(ctx.exception.codigo, "SELECAO_AMBIGUA")

    def test_indice_inexistente(self):
        with self.assertRaises(ErroUso):
            preparar(uma("a"), Opcoes(remover_entradas={2}))
        with self.assertRaises(ErroUso):
            preparar(uma("a"), Opcoes(remover_linhas={1: {3}}))


class TestTempo(unittest.TestCase):
    def test_unidades_e_decimais(self):
        casos = {"750ms": 750, "1s": 1000, "1,5s": 1500, "1.5s": 1500, "2min": 120000,
                 "0,25 min": 15000, " 3 s ": 3000, "0s": 0, "0ms": 0, "1,001s": 1001, "10MS": 10}
        for valor, ms in casos.items():
            with self.subTest(valor=valor):
                self.assertEqual(interpretar_deslocamento(valor), ms)

    def test_valores_invalidos(self):
        for valor in ["", "1", "1h", "-1s", "+1s", "1,0005s", "1.5ms", "abc", "1,5", "inf s", "nan s",
                      "1e3ms", "1 2s", "1.000ms"]:
            with self.subTest(valor=valor):
                with self.assertRaises(ErroUso):
                    interpretar_deslocamento(valor)

    def test_adiantar_e_atrasar_exatos(self):
        dados = srt(entrada(1, 10_000, 12_000, "a"), entrada(2, 59_500, 60_500, "b"),
                    entrada(3, 3_599_800, 3_600_600, "c")).encode()
        r = preparar(dados, Opcoes(deslocamento_ms=-1000))
        self.assertEqual([(e.inicio, e.fim) for e in r.entradas_saida],
                         [(9000, 11000), (58500, 59500), (3_598_800, 3_599_600)])
        self.assertIn("00:00:09,000 --> 00:00:11,000", texto_saida(r))
        r = preparar(dados, Opcoes(deslocamento_ms=500))
        self.assertIn("00:00:10,500 --> 00:00:12,500", texto_saida(r))
        self.assertIn("00:01:00,000 --> 00:01:01,000", texto_saida(r))
        self.assertIn("01:00:00,300 --> 01:00:01,100", texto_saida(r))
        r = preparar(dados, Opcoes(deslocamento_ms=interpretar_deslocamento("2min")))
        self.assertIn("00:02:10,000 --> 00:02:12,000", texto_saida(r))

    def test_ida_e_volta_e_duracoes(self):
        original = sequencia(50, passo=1234, dur=777).encode()
        ida = preparar(original, Opcoes(deslocamento_ms=interpretar_deslocamento("1,5s")))
        volta = preparar(ida.bytes_saida, Opcoes(deslocamento_ms=-1500))
        self.assertEqual(volta.bytes_saida, original)
        base = preparar(original, Opcoes())
        self.assertEqual([e.fim - e.inicio for e in ida.entradas_saida],
                         [e.fim - e.inicio for e in base.entradas_saida])

    def test_zero_nao_altera(self):
        dados = sequencia(3).encode()
        r = preparar(dados, Opcoes(deslocamento_ms=0))
        self.assertEqual(r.bytes_saida, dados)
        self.assertFalse([m for m in r.mudancas if m.tipo == "tempo"])

    def test_negativo_bloqueia_e_lista_entradas(self):
        dados = srt(entrada(1, 500, 1000, "a"), entrada(2, 800, 1500, "b"), entrada(3, 5000, 6000, "c")).encode()
        r = preparar(dados, Opcoes(deslocamento_ms=-900))
        self.assertFalse(r.ok)
        self.assertIsNone(r.bytes_saida)
        self.assertEqual([(b.codigo, b.entrada) for b in r.bloqueios],
                         [("TEMPO_NEGATIVO", 1), ("TEMPO_NEGATIVO", 2)])

    def test_limite_superior(self):
        dados = srt(entrada(1, 14_399_000, 14_400_000, "a")).encode()
        r = preparar(dados, Opcoes(deslocamento_ms=1))
        self.assertEqual([b.codigo for b in r.bloqueios], ["FIM_EXCEDE_LIMITE"])

    def test_so_deslocamento_preserva_texto_e_italico(self):
        dados = srt(entrada(1, 1000, 2000, "<I>Oi</i>, “x”"), entrada(2, 3000, 4000, "aÃ§Ã£o")).encode()
        r = preparar(dados, Opcoes(deslocamento_ms=100))
        self.assertIn("<I>Oi</i>, “x”", texto_saida(r))
        self.assertIn("aÃ§Ã£o", texto_saida(r))


class TestPreservacao(unittest.TestCase):
    def test_texto_nao_selecionado_intacto(self):
        dados = srt(entrada(1, 1000, 2000, "Oi…"), entrada(2, 3000, 4000, "<b>x</b>")).encode()
        r = preparar(dados, Opcoes(pontuacao=True))
        self.assertIn("<b>x</b>", texto_saida(r))

    def test_serializacao_canonica(self):
        dados = srt(entrada(1, 1000, 2000, "a")).encode()
        doc = interpretar_flexivel(dados.decode())
        self.assertEqual(serializar_documento(doc.entradas).encode(), dados)


if __name__ == "__main__":
    unittest.main()
