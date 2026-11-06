"""Modelo intermediário (texto, estilo e tempos) e leitura flexível para preparação.

A leitura flexível interpreta arquivos que fogem do contrato quando a
interpretação é inequívoca e registra cada diferença como `Anomalia`. Uma
anomalia só é corrigida se o usuário escolher a operação correspondente;
caso contrário a preparação recusa a saída.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from .contrato import ABERTURAS, FECHAMENTOS, RE_INDICE_FLEX, RE_TEMPO_FLEX, tempo_ms
from .util import escapar, formatar_tempo


@dataclass
class Trecho:
    texto: str
    italico: bool = False


def normalizar_trechos(trechos) -> list:
    """Junta trechos vizinhos de mesmo estilo e descarta trechos vazios."""
    saida = []
    for t in trechos:
        if not t.texto:
            continue
        if saida and saida[-1].italico == t.italico:
            saida[-1] = Trecho(saida[-1].texto + t.texto, t.italico)
        else:
            saida.append(Trecho(t.texto, t.italico))
    return saida


def caracteres(linha) -> list:
    return [(c, t.italico) for t in linha for c in t.texto]


def de_caracteres(chars) -> list:
    return normalizar_trechos([Trecho(c, i) for c, i in chars])


def texto_visivel(linha) -> str:
    return "".join(t.texto for t in linha)


def serializar_linhas(linhas) -> list:
    """Gera o texto bruto com <i>...</i>. Um itálico que continua na linha
    seguinte fica aberto na quebra (economiza tags); caso contrário fecha no fim
    da linha. O estado nunca passa para a próxima entrada."""
    saida = []
    aberto = False
    for li, linha in enumerate(linhas):
        partes = []
        for t in linha:
            if not t.texto:
                continue
            if t.italico and not aberto:
                partes.append("<i>")
                aberto = True
            elif not t.italico and aberto:
                partes.append("</i>")
                aberto = False
            partes.append(t.texto)
        if aberto:
            prox = linhas[li + 1] if li + 1 < len(linhas) else None
            primeiro = next((t for t in prox if t.texto), None) if prox else None
            if not (primeiro and primeiro.italico):
                partes.append("</i>")
                aberto = False
        saida.append("".join(partes))
    return saida


def serializar_linha_isolada(linha) -> str:
    """Uma linha sozinha, com itálico aberto e fechado nela (para edição manual)."""
    return serializar_linhas([linha])[0]


@dataclass
class Entrada:
    posicao: int  # posição original (1, 2, 3...) na leitura
    indice_bruto: str | None
    inicio: int | None
    fim: int | None
    linhas: list
    bruto: list | None  # linhas originais; usadas enquanto o texto não for alterado
    linha_fisica: int
    linha_tempo: int

    def definir_linhas(self, novas) -> None:
        self.linhas = [normalizar_trechos(l) for l in novas]
        self.bruto = None

    def texto_serializado(self) -> list:
        return list(self.bruto) if self.bruto is not None else serializar_linhas(self.linhas)

    def copia(self) -> "Entrada":
        return copy.deepcopy(self)


@dataclass
class Anomalia:
    codigo: str
    entrada: int | None
    linha: int | None
    motivo: str
    corrigivel_por: str | None  # "corrigir_estrutura", "normalizar" ou None (bloqueante)


@dataclass
class Documento:
    entradas: list = field(default_factory=list)
    anomalias: list = field(default_factory=list)
    tinha_crlf: bool = False

    @property
    def numeracao_intacta(self) -> bool:
        return all(e.indice_bruto == str(e.posicao) for e in self.entradas)


def interpretar_italico(linhas_brutas) -> tuple:
    """Interpreta <i>/</i> numa entrada. Pares válidos viram estilo; tags que
    não formam par válido ficam como texto literal (e serão recusadas pela
    validação). Pares vazios são descartados e contados."""
    tokens = []  # (indice_linha, tipo, texto)
    for li, s in enumerate(linhas_brutas):
        k = 0
        buf = []
        while k < len(s):
            if s.startswith(ABERTURAS, k):
                if buf:
                    tokens.append((li, "texto", "".join(buf)))
                    buf = []
                tokens.append((li, "abre", s[k:k + 3]))
                k += 3
            elif s.startswith(FECHAMENTOS, k):
                if buf:
                    tokens.append((li, "texto", "".join(buf)))
                    buf = []
                tokens.append((li, "fecha", s[k:k + 4]))
                k += 4
            else:
                buf.append(s[k])
                k += 1
        if buf:
            tokens.append((li, "texto", "".join(buf)))

    papel = [None] * len(tokens)
    aberto = None
    desde = 0
    for j, (_li, tipo, txt) in enumerate(tokens):
        if tipo == "texto":
            if aberto is not None:
                desde += len(txt)
        elif tipo == "abre":
            if aberto is None:
                aberto = j
                desde = 0
            else:
                papel[j] = "literal"
                desde += len(txt)
        else:
            if aberto is None:
                papel[j] = "literal"
            elif desde == 0:
                papel[aberto] = papel[j] = "vazio"
                aberto = None
            else:
                papel[aberto] = papel[j] = "tag"
                aberto = None
    if aberto is not None:
        papel[aberto] = "literal"

    resultado = [[] for _ in linhas_brutas]
    italico = False
    vazios = 0
    for j, (li, tipo, txt) in enumerate(tokens):
        if tipo == "texto" or papel[j] == "literal":
            resultado[li].append(Trecho(txt, italico))
        elif papel[j] == "tag":
            italico = tipo == "abre"
        else:
            vazios += 1
    return [normalizar_trechos(l) for l in resultado], vazios // 2


def _em_branco(s: str) -> bool:
    return s.strip(" \t") == ""


def interpretar_flexivel(texto: str) -> Documento:
    """Lê o texto decodificado em modelo intermediário, registrando anomalias."""
    doc = Documento()
    if texto.startswith("﻿"):
        texto = texto[1:]
    doc.tinha_crlf = "\r\n" in texto
    t2 = texto.replace("\r\n", "\n")
    if t2.endswith("\r"):
        t2 = t2[:-1]  # CR final tolerado pelo contrato
    if "\r" in t2:
        primeira = t2[: t2.index("\r")].count("\n") + 1
        doc.anomalias.append(Anomalia(
            "CR_ISOLADO", None, primeira,
            f"{t2.count(chr(13))} quebra(s) de linha só com CR, sem LF", "normalizar"))
        t2 = t2.replace("\r", "\n")
    linhas = t2.split("\n")
    n = len(linhas)

    def eh_indice(s):
        return RE_INDICE_FLEX.match(s) is not None

    cabecalhos = []
    for t, s in enumerate(linhas):
        if RE_TEMPO_FLEX.match(s):
            if t == 0 or _em_branco(linhas[t - 1]) or eh_indice(linhas[t - 1]):
                cabecalhos.append(t)

    inicios = []
    for k, t in enumerate(cabecalhos):
        limite = cabecalhos[k - 1] + 1 if k > 0 else 0
        if t - 1 >= limite and eh_indice(linhas[t - 1]):
            inicios.append(t - 1)
        else:
            inicios.append(t)

    primeiro = inicios[0] if cabecalhos else n
    soltas = [j for j in range(primeiro) if not _em_branco(linhas[j])]
    if soltas:
        doc.anomalias.append(Anomalia(
            "CONTEUDO_SOLTO", None, soltas[0] + 1,
            "texto antes da primeira entrada reconhecida", None))

    for k, t in enumerate(cabecalhos):
        pos = k + 1
        idx = inicios[k] if inicios[k] != t else None
        prox = inicios[k + 1] if k + 1 < len(cabecalhos) else n

        if idx is None:
            indice_bruto = None
            doc.anomalias.append(Anomalia(
                "INDICE_AUSENTE", pos, t + 1, "falta o número da entrada", "corrigir_estrutura"))
        else:
            indice_bruto = linhas[idx]
            if indice_bruto != str(pos):
                doc.anomalias.append(Anomalia(
                    "NUMERACAO", pos, idx + 1,
                    f"número '{escapar(indice_bruto, 12)}' na posição {pos}", "corrigir_estrutura"))

        m = RE_TEMPO_FLEX.match(linhas[t])
        g = [int(x) for x in m.groups()[:8]]
        inicio = fim = None
        if g[1] > 59 or g[2] > 59 or g[5] > 59 or g[6] > 59:
            doc.anomalias.append(Anomalia(
                "TEMPO_INVALIDO", pos, t + 1, "minutos ou segundos acima de 59", None))
        else:
            inicio = tempo_ms(*g[0:4])
            fim = tempo_ms(*g[4:8])
            canonico = f"{formatar_tempo(inicio)} --> {formatar_tempo(fim)}"
            if linhas[t] != canonico:
                motivo = ("configuração de posição após o tempo" if m.group(9)
                          else "tempo fora do formato exato HH:MM:SS,mmm --> HH:MM:SS,mmm")
                doc.anomalias.append(Anomalia("TEMPO_FORMATO", pos, t + 1, motivo,
                                              "corrigir_estrutura"))

        regiao = list(range(t + 1, prox))
        fim_r = len(regiao)
        while fim_r > 0 and _em_branco(linhas[regiao[fim_r - 1]]):
            fim_r -= 1
        cauda = regiao[fim_r:]
        com_espacos = [j for j in cauda if linhas[j] != ""]
        if com_espacos:
            doc.anomalias.append(Anomalia(
                "SEPARADOR_COM_ESPACOS", pos, com_espacos[0] + 1,
                "linha só com espaços usada como separador", "corrigir_estrutura"))
        corpo = regiao[:fim_r]
        if k + 1 < len(cabecalhos) and not cauda and corpo:
            doc.anomalias.append(Anomalia(
                "SEPARADOR_AUSENTE", pos, prox + 1,
                "falta a linha vazia antes da entrada seguinte", "corrigir_estrutura"))
        texto_idx = []
        for q, j in enumerate(corpo):
            if linhas[j] == "":
                resto = [x for x in corpo[q:] if linhas[x] != ""]
                doc.anomalias.append(Anomalia(
                    "CONTEUDO_SOLTO", pos, resto[0] + 1,
                    "texto depois de uma linha vazia, fora de qualquer entrada", None))
                break
            texto_idx.append(j)

        brutas = [linhas[j] for j in texto_idx]
        trechos, vazios = interpretar_italico(brutas)
        if vazios:
            doc.anomalias.append(Anomalia(
                "ITALICO_VAZIO", pos, (texto_idx[0] + 1) if texto_idx else t + 1,
                f"{vazios} par(es) de itálico sem texto", "corrigir_estrutura"))
        doc.entradas.append(Entrada(
            posicao=pos, indice_bruto=indice_bruto, inicio=inicio, fim=fim,
            linhas=trechos, bruto=None if vazios else brutas,
            linha_fisica=(idx if idx is not None else t) + 1, linha_tempo=t + 1))
    return doc


def serializar_entrada(e: Entrada, numero: int) -> str:
    if e.inicio is None or e.fim is None:
        raise ValueError("entrada sem tempo válido não pode ser serializada")
    return "\n".join([str(numero), f"{formatar_tempo(e.inicio)} --> {formatar_tempo(e.fim)}",
                      *e.texto_serializado()])


def serializar_documento(entradas) -> str:
    """Saída canônica: LF, uma linha vazia entre entradas e LF após o último texto."""
    if not entradas:
        return ""
    return "\n\n".join(serializar_entrada(e, n) for n, e in enumerate(entradas, 1)) + "\n"
