"""Contrato SRT_LATINO_ITALICO_1 e validação estrita.

A validação apenas lê: nunca corrige, normaliza ou reordena. Transformações
ficam em `preparacao.py` e são operações separadas.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .tabelas import RE_FORMATACAO_NAO_SUPORTADA, TABELA_PONTUACAO
from .util import descrever_caractere, escapar, fmt_int, formatar_tempo, unidades_utf16

CONTRATO_ID = "SRT_LATINO_ITALICO_1"
CONTRATO_VERSAO = 1

MAX_BYTES = 262_144
MAX_LINHAS = 15_000
MAX_ENTRADAS = 3_000
MAX_FIM_MS = 14_400_000  # 4 horas
DURACAO_MIN_MS = 200
DURACAO_MAX_MS = 60_000
MAX_VISIVEIS = 64
MAX_BRUTOS = 128
MAX_TAGS = 16
NOME_MIN = 5
NOME_MAX = 128
MAX_ITENS_PASTA = 64

# Limite de diagnósticos guardados (os demais são apenas contados).
LIMITE_DIAGNOSTICOS = 1000

FRASE_ESCOPO = (
    "Esta verificação confere o arquivo, não o sincronismo, a tradução, "
    "a edição do filme, o pendrive ou a reprodução no aparelho."
)
FRASE_NAO_VERIFICADO = (
    "Sincronismo com a edição do filme e reprodução no aparelho não foram verificados."
)

RE_INDICE = re.compile(r"[1-9][0-9]*")
RE_TEMPO = re.compile(
    r"([0-9]{2}):([0-9]{2}):([0-9]{2}),([0-9]{3}) --> ([0-9]{2}):([0-9]{2}):([0-9]{2}),([0-9]{3})"
)
# Formas próximas, só para diagnóstico/recuperação (nunca aceitas pelo contrato).
RE_INDICE_FLEX = re.compile(r"[ \t﻿]*([0-9]+)[ \t]*\Z")
RE_TEMPO_FLEX = re.compile(
    r"[ \t]*([0-9]{1,2}):([0-9]{1,2}):([0-9]{1,2})[,.]([0-9]{3})[ \t]*-->[ \t]*"
    r"([0-9]{1,2}):([0-9]{1,2}):([0-9]{1,2})[,.]([0-9]{3})([ \t]+\S.*?)?[ \t]*\Z"
)
RE_TAG_GENERICA = re.compile(r"<[^<>\n]{0,64}>")

ABERTURAS = ("<i>", "<I>")
FECHAMENTOS = ("</i>", "</I>")

# Caracteres <= U+0020 removidos só nas extremidades na regra de linha vazia.
BORDAS_VAZIAS = "".join(chr(c) for c in range(0x21))


def caractere_permitido(c: str) -> bool:
    """Texto: U+0020..U+007E (exceto < e >) ou U+00A0..U+00FF."""
    o = ord(c)
    return (0x20 <= o <= 0x7E and c not in "<>") or (0xA0 <= o <= 0xFF)


def tempo_ms(h: int, m: int, s: int, ms: int) -> int:
    return ((h * 60 + m) * 60 + s) * 1000 + ms


@dataclass
class Diagnostico:
    codigo: str
    motivo: str
    sugestao: str = ""
    entrada: int | None = None
    linha: int | None = None
    severidade: str = "erro"  # "erro" ou "aviso"

    def como_dict(self) -> dict:
        return {
            "codigo": self.codigo,
            "severidade": self.severidade,
            "entrada": self.entrada,
            "linha": self.linha,
            "motivo": self.motivo,
            "sugestao": self.sugestao,
        }

    def localizacao(self) -> str:
        partes = []
        if self.entrada is not None:
            partes.append(f"entrada {fmt_int(self.entrada)}")
        if self.linha is not None:
            partes.append(f"linha {fmt_int(self.linha)}")
        return ", ".join(partes)


@dataclass
class ResultadoValidacao:
    diagnosticos: list = field(default_factory=list)
    interrompido: bool = False
    linha_interrupcao: int | None = None
    resumo: dict = field(default_factory=dict)
    omitidos: int = 0

    @property
    def erros(self) -> list:
        return [d for d in self.diagnosticos if d.severidade == "erro"]

    @property
    def avisos(self) -> list:
        return [d for d in self.diagnosticos if d.severidade == "aviso"]

    @property
    def valido(self) -> bool:
        return not self.erros and self.omitidos == 0

    def adicionar(self, d: Diagnostico) -> None:
        if len(self.diagnosticos) >= LIMITE_DIAGNOSTICOS:
            self.omitidos += 1
        else:
            self.diagnosticos.append(d)

    def erro(self, codigo, motivo, sugestao="", entrada=None, linha=None) -> None:
        self.adicionar(Diagnostico(codigo, motivo, sugestao, entrada, linha, "erro"))

    def aviso(self, codigo, motivo, sugestao="", entrada=None, linha=None) -> None:
        self.adicionar(Diagnostico(codigo, motivo, sugestao, entrada, linha, "aviso"))

    def como_dict(self) -> dict:
        return {
            "valido": self.valido,
            "erros": len(self.erros) + self.omitidos,
            "avisos": len(self.avisos),
            "interrompido": self.interrompido,
            "linha_interrupcao": self.linha_interrupcao,
            "diagnosticos": [d.como_dict() for d in self.diagnosticos],
            "diagnosticos_omitidos": self.omitidos,
        }


def _resumo_vazio(tamanho: int) -> dict:
    return {
        "tamanho_bytes": tamanho,
        "codificacao": None,
        "bom": None,
        "finais_de_linha": None,
        "linhas": None,
        "entradas": None,
        "estado_contagens": "indisponivel",
        "primeiro_inicio_ms": None,
        "ultimo_fim_ms": None,
        "intervalo_ms": None,
        "entradas_com_italico": None,
        "erros_de_marcacao": None,
        "sobreposicoes": None,
        "violacoes_de_texto": None,
    }


def _sugestao_caractere(c: str) -> str:
    if c in TABELA_PONTUACAO:
        destino = TABELA_PONTUACAO[c]
        if destino:
            return f"a correção automática converte para '{destino}'"
        return "a correção automática remove este caractere invisível"
    if unicodedata.combining(c):
        return "acento decomposto: a correção automática recompõe (NFC)"
    if c in "<>":
        return "'<' e '>' só são aceitos nas tags <i> e </i>; edite o texto manualmente"
    if c == "\t" or unicodedata.category(c) == "Cc":
        return "remova o caractere de controle (edição manual)"
    return "caractere fora do conjunto aceito; edite o texto manualmente"


def _sugestao_tag(tag: str) -> str:
    if RE_FORMATACAO_NAO_SUPORTADA.fullmatch(tag):
        return "a correção automática retira a marcação e mantém o texto"
    if re.fullmatch(r"</?\s*i\b[^<>]*>", tag, re.IGNORECASE):
        return "itálico só é aceito como <i> e </i>, sem espaços ou atributos; edite manualmente"
    return "marcação desconhecida; revise e edite manualmente (pode ser texto entre < >)"


@dataclass
class _EstatTexto:
    italico_valido: bool = False
    erro_marcacao: bool = False
    violacoes: int = 0


def _validar_texto(linhas_texto, pos: int, res: ResultadoValidacao) -> _EstatTexto:
    """Valida as linhas de texto de uma entrada (itálico, caracteres e limites)."""
    est = _EstatTexto()
    aberto = False
    linha_abertura = None
    desde = 0  # caracteres de texto desde a abertura do itálico
    tags = 0
    pares = 0
    for num, s in linhas_texto:
        visivel = []
        invalidos = []
        k = 0
        n = len(s)
        while k < n:
            if s.startswith(ABERTURAS, k):
                tags += 1
                if aberto:
                    res.erro("ITALICO_ANINHADO", "itálico aberto dentro de outro itálico",
                             "feche o itálico antes de abrir outro", pos, num)
                    est.erro_marcacao = True
                else:
                    aberto = True
                    desde = 0
                    linha_abertura = num
                k += 3
                continue
            if s.startswith(FECHAMENTOS, k):
                tags += 1
                if not aberto:
                    res.erro("ITALICO_FECHAMENTO_ORFAO", "fechamento de itálico sem abertura",
                             "remova o </i> ou acrescente o <i> correspondente", pos, num)
                    est.erro_marcacao = True
                elif desde == 0:
                    res.erro("ITALICO_VAZIO", "par de itálico sem texto (<i></i>)",
                             "remova o par vazio (a correção automática faz isso)", pos, num)
                    est.erro_marcacao = True
                    aberto = False
                else:
                    aberto = False
                    pares += 1
                k += 4
                continue
            c = s[k]
            if c == "<":
                m = RE_TAG_GENERICA.match(s, k)
                if m:
                    tag = m.group()
                    res.erro("TAG_NAO_SUPORTADA", f"marcação não suportada: {escapar(tag, 40)}",
                             _sugestao_tag(tag), pos, num)
                    est.erro_marcacao = True
                    visivel.append(tag)
                    if aberto:
                        desde += len(tag)
                    k = m.end()
                    continue
            # CR interno e BOM interno já são diagnosticados por linha física.
            if c not in "\r﻿" and not caractere_permitido(c):
                invalidos.append((k + 1, c))
            visivel.append(c)
            if aberto:
                desde += 1
            k += 1

        vis = "".join(visivel)
        brutos = unidades_utf16(s)
        nvis = unidades_utf16(vis)
        violou = False
        if brutos > MAX_BRUTOS:
            res.erro("LINHA_BRUTA_EXCEDIDA",
                     f"{fmt_int(brutos)} caracteres brutos (com tags); máximo: {MAX_BRUTOS}",
                     "reduza o texto ou as marcações desta linha", pos, num)
            violou = True
        if nvis == 0:
            res.erro("LINHA_SEM_TEXTO", "linha sem texto visível (só marcação ou vazia)",
                     "cada linha precisa ter texto; mova a tag para a linha com texto", pos, num)
            violou = True
        elif nvis > MAX_VISIVEIS:
            res.erro("LINHA_LONGA", f"{fmt_int(nvis)} caracteres visíveis; máximo: {MAX_VISIVEIS}",
                     "a correção automática tenta reorganizar em até duas linhas", pos, num)
            violou = True
        if nvis > 0:
            nucleo = vis.strip(BORDAS_VAZIAS)
            if nucleo == "":
                res.erro("LINHA_EM_BRANCO", "linha só com espaços",
                         "remova a linha ou escreva o texto", pos, num)
                violou = True
            elif nucleo.strip(" ") == "":
                res.aviso("LINHA_VISUALMENTE_VAZIA",
                          "linha só com espaço não separável (NBSP); aceita, mas aparece vazia",
                          "confira se a linha deveria ter texto", pos, num)
        if invalidos:
            col, c = invalidos[0]
            extra = f" e mais {len(invalidos) - 1}" if len(invalidos) > 1 else ""
            res.erro("CARACTERE_NAO_PERMITIDO",
                     f"caractere não permitido {descrever_caractere(c)} na coluna {col}{extra}",
                     _sugestao_caractere(c), pos, num)
            violou = True
        if violou:
            est.violacoes += 1

    if aberto:
        res.erro("ITALICO_SEM_FECHAMENTO", "itálico sem fechamento",
                 "acrescente </i> no fim do trecho em itálico", pos, linha_abertura)
        est.erro_marcacao = True
    if tags > MAX_TAGS:
        res.erro("TAGS_EXCEDIDAS", f"{tags} tags de itálico na entrada; máximo: {MAX_TAGS}",
                 "junte trechos em itálico ou remova marcações", pos, linhas_texto[0][0])
        est.erro_marcacao = True
    est.italico_valido = pares > 0 and not est.erro_marcacao
    return est


def _parece_tempo(s: str) -> bool:
    return RE_TEMPO.fullmatch(s) is not None or RE_TEMPO_FLEX.match(s) is not None


def _validar_estrutura(linhas: list, res: ResultadoValidacao) -> None:
    resumo = res.resumo
    n = len(linhas)
    i = 0
    pos = 0
    fim_anterior = None
    tempos = []  # (inicio, fim) ou None por entrada
    ital = marc = sobre = viol = 0

    while i < n:
        if linhas[i] == "":
            i += 1
            continue
        pos += 1
        if pos == MAX_ENTRADAS + 1:
            res.erro("ENTRADAS_EXCEDIDAS", f"mais de {fmt_int(MAX_ENTRADAS)} entradas",
                     "divida a legenda em arquivos menores", pos, i + 1)
        s = linhas[i]
        if RE_INDICE.fullmatch(s):
            if int(s) != pos:
                res.erro("INDICE_FORA_DE_SEQUENCIA", f"índice {escapar(s, 12)}; esperado {pos}",
                         "a correção automática renumera as entradas", pos, i + 1)
            t = i + 1
        elif _parece_tempo(s):
            res.erro("INDICE_AUSENTE", "falta o número da entrada antes do tempo",
                     "a correção automática renumera as entradas", pos, i + 1)
            t = i
        elif i + 1 < n and _parece_tempo(linhas[i + 1]):
            res.erro("INDICE_INVALIDO",
                     f"índice inválido: '{escapar(s, 20)}' (use só dígitos, sem zeros à esquerda, "
                     "espaços ou sinais)",
                     "a correção automática renumera as entradas", pos, i + 1)
            t = i + 1
        else:
            pos -= 1
            res.erro("ESTRUTURA_INTERROMPIDA",
                     "esperado o número de uma entrada; a estrutura não pode ser recuperada "
                     "com segurança a partir daqui",
                     "confira esta linha no editor de texto (texto solto, linha vazia no meio "
                     "de uma entrada ou tempo malformado)", None, i + 1)
            res.interrompido = True
            res.linha_interrupcao = i + 1
            break

        if t >= n:
            res.erro("ENTRADA_INCOMPLETA", "o arquivo termina logo depois do número da entrada",
                     "complete ou remova a última entrada", pos, i + 1)
            tempos.append(None)
            break

        lt = linhas[t]
        inicio = fim = None
        if lt == "":
            res.erro("TEMPO_AUSENTE", "falta a linha de tempo da entrada",
                     "acrescente 'HH:MM:SS,mmm --> HH:MM:SS,mmm'", pos, t + 1)
            tempos.append(None)
            fim_anterior = None
            i = t
            continue
        m = RE_TEMPO.fullmatch(lt)
        if m:
            g = [int(x) for x in m.groups()]
            problemas = []
            if g[1] > 59 or g[5] > 59:
                problemas.append("minutos acima de 59")
            if g[2] > 59 or g[6] > 59:
                problemas.append("segundos acima de 59")
            if problemas:
                res.erro("TEMPO_INVALIDO", "tempo inválido: " + " e ".join(problemas),
                         "corrija o tempo manualmente", pos, t + 1)
            else:
                inicio = tempo_ms(*g[0:4])
                fim = tempo_ms(*g[4:8])
        else:
            if RE_TEMPO_FLEX.match(lt):
                sug = "a correção automática normaliza este formato sem ambiguidade"
            else:
                sug = "formato exigido: HH:MM:SS,mmm --> HH:MM:SS,mmm (29 caracteres, sem posição)"
            res.erro("TEMPO_FORMATO",
                     f"linha de tempo fora do formato exato ({len(lt)} caracteres; exigido: 29)",
                     sug, pos, t + 1)

        # Linhas de texto até a linha vazia (ou fim do arquivo).
        j = t + 1
        texto = []
        while j < n and linhas[j] != "":
            if (RE_INDICE_FLEX.match(linhas[j]) and j + 1 < n
                    and _parece_tempo(linhas[j + 1])):
                res.erro("SEPARADOR_AUSENTE", "falta a linha vazia antes da entrada seguinte",
                         "a correção automática insere o separador", pos, j + 1)
                break
            texto.append((j + 1, linhas[j]))
            j += 1

        if not texto:
            res.erro("SEM_TEXTO", "a entrada não tem linha de texto",
                     "escreva o texto ou remova a entrada", pos, t + 1)
        else:
            if len(texto) > 2:
                res.erro("LINHAS_DE_TEXTO_EXCEDIDAS",
                         f"{len(texto)} linhas de texto; máximo permitido: 2",
                         "a correção automática tenta reorganizar em até duas linhas",
                         pos, texto[2][0])
                viol += 1
            est = _validar_texto(texto, pos, res)
            ital += est.italico_valido
            marc += est.erro_marcacao
            viol += est.violacoes

        if inicio is not None:
            if fim <= inicio:
                res.erro("FIM_NAO_POSTERIOR",
                         f"o fim ({formatar_tempo(fim)}) não é posterior ao início "
                         f"({formatar_tempo(inicio)})", "corrija o tempo manualmente", pos, t + 1)
            else:
                dur = fim - inicio
                if dur < DURACAO_MIN_MS:
                    res.erro("DURACAO_CURTA", f"duração de {fmt_int(dur)} ms; mínimo: 200 ms",
                             "ajuste o tempo manualmente (a ferramenta não altera durações)",
                             pos, t + 1)
                elif dur > DURACAO_MAX_MS:
                    res.erro("DURACAO_LONGA",
                             f"duração de {fmt_int(dur)} ms; máximo: {fmt_int(DURACAO_MAX_MS)} ms",
                             "ajuste o tempo manualmente (a ferramenta não altera durações)",
                             pos, t + 1)
            if fim > MAX_FIM_MS:
                res.erro("FIM_EXCEDE_LIMITE",
                         f"termina em {formatar_tempo(fim)}; máximo: {formatar_tempo(MAX_FIM_MS)}",
                         "confira o deslocamento de tempo aplicado", pos, t + 1)
            if fim_anterior is not None and inicio < fim_anterior:
                res.erro("SOBREPOSICAO",
                         f"começa em {formatar_tempo(inicio)}, antes do fim da entrada anterior "
                         f"({formatar_tempo(fim_anterior)})",
                         "ajuste manualmente; a ferramenta não reordena nem corta tempos",
                         pos, t + 1)
                sobre += 1
            fim_anterior = fim
            tempos.append((inicio, fim))
        else:
            tempos.append(None)
            fim_anterior = None
        i = j

    if pos == 0 and not res.interrompido:
        res.erro("SEM_ENTRADAS", "nenhuma entrada encontrada (arquivo vazio, só BOM ou só linhas vazias)",
                 "escolha o arquivo de legenda correto")

    resumo["entradas"] = pos
    resumo["estado_contagens"] = "parcial" if res.interrompido else "completo"
    resumo["entradas_com_italico"] = ital
    resumo["erros_de_marcacao"] = marc
    resumo["sobreposicoes"] = sobre
    resumo["violacoes_de_texto"] = viol
    if tempos and tempos[0] is not None:
        resumo["primeiro_inicio_ms"] = tempos[0][0]
    if tempos and tempos[-1] is not None and not res.interrompido:
        resumo["ultimo_fim_ms"] = tempos[-1][1]
    if resumo["primeiro_inicio_ms"] is not None and resumo["ultimo_fim_ms"] is not None:
        resumo["intervalo_ms"] = resumo["ultimo_fim_ms"] - resumo["primeiro_inicio_ms"]


def _sugestao_codificacao(dados: bytes) -> str | None:
    if dados.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    if b"\x00" in dados[:4096]:
        return "utf-16 (sem BOM)"
    try:
        dados.decode("cp1252")
        return "cp1252"
    except UnicodeDecodeError:
        return "latin-1"


def validar_bytes(dados: bytes) -> ResultadoValidacao:
    """Valida bytes exatamente como o leitor do contrato os leria."""
    res = ResultadoValidacao(resumo=_resumo_vazio(len(dados)))
    resumo = res.resumo
    n = len(dados)
    if n == 0:
        res.erro("ARQUIVO_VAZIO", "o arquivo está vazio (0 bytes)", "escolha o arquivo de legenda correto")
        res.interrompido = True
        return res
    if n > MAX_BYTES:
        res.erro("TAMANHO_EXCEDIDO", f"{fmt_int(n)} bytes; máximo: {fmt_int(MAX_BYTES)} bytes",
                 "a legenda é grande demais para o contrato; divida o arquivo")
    resumo["bom"] = dados.startswith(b"\xef\xbb\xbf")
    try:
        texto = dados.decode("utf-8")  # estrito: nunca 'ignore' ou 'replace'
    except UnicodeDecodeError as e:
        linha = dados.count(b"\n", 0, e.start) + 1
        sug = _sugestao_codificacao(dados)
        resumo["codificacao"] = "UTF-8 inválida"
        resumo["codificacao_sugerida"] = sug
        resumo["bom"] = None
        if sug == "utf-16":
            res.erro("CODIFICACAO_UTF16", "o arquivo está em UTF-16; o contrato exige UTF-8",
                     "prepare uma cópia: UTF-16 com BOM é convertido para UTF-8 automaticamente",
                     None, 1)
        else:
            res.erro("UTF8_INVALIDO",
                     f"byte 0x{dados[e.start]:02X} inválido em UTF-8 (posição {fmt_int(e.start)})",
                     f"provável codificação legada ({sug}); a correção automática converte para UTF-8 "
                     "(confira os acentos no arquivo corrigido)",
                     None, linha)
        res.interrompido = True
        res.linha_interrupcao = linha
        return res

    resumo["codificacao"] = "UTF-8"
    if texto.startswith("﻿"):
        texto = texto[1:]
    brutas = texto.split("\n")  # somente LF; preserva campos vazios, inclusive o último
    total = len(brutas)
    resumo["linhas"] = total
    if total > MAX_LINHAS:
        res.erro("LINHAS_EXCEDIDAS", f"{fmt_int(total)} linhas; máximo: {fmt_int(MAX_LINHAS)}",
                 "remova linhas vazias extras ou divida o arquivo", None, MAX_LINHAS + 1)
    linhas = []
    lf = crlf = 0
    cr_final = False
    for num, linha in enumerate(brutas, 1):
        ultima = num == total
        if linha.endswith("\r"):
            linha = linha[:-1]
            if ultima:
                cr_final = True
            else:
                crlf += 1
        elif not ultima:
            lf += 1
        if "\r" in linha:
            res.erro("CR_INTERNO", "caractere CR (\\r) fora do fim da linha",
                     "a correção automática converte CR isolado em LF", None, num)
        if "﻿" in linha:
            res.erro("BOM_INTERNO", "BOM (U+FEFF) fora do início do arquivo",
                     "a correção automática remove o BOM interno", None, num)
        linhas.append(linha)
    if crlf and lf:
        tipo = "misto"
    elif crlf:
        tipo = "CRLF"
    elif lf:
        tipo = "LF"
    else:
        tipo = "nenhum"
    resumo["finais_de_linha"] = {"tipo": tipo, "lf": lf, "crlf": crlf, "cr_final": cr_final}
    _validar_estrutura(linhas, res)
    res.diagnosticos.sort(key=lambda d: (d.linha is not None, d.linha or 0))
    return res
