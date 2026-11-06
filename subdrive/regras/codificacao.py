"""Codificação de origem, acentuação corrompida (mojibake) e perdas irrecuperáveis."""

from __future__ import annotations

import codecs
import re
import unicodedata
from dataclasses import dataclass, field

from .contrato import Diagnostico
from .erros import ErroUso
from .modelo import caracteres, de_caracteres, texto_visivel
from .util import escapar, fmt_int

ALIASES = {
    "utf8": "utf-8", "utf-8": "utf-8", "utf-8-sig": "utf-8",
    "utf16": "utf-16", "utf-16": "utf-16", "utf-16le": "utf-16-le", "utf-16-le": "utf-16-le",
    "utf-16be": "utf-16-be", "utf-16-be": "utf-16-be",
    "cp1252": "cp1252", "windows-1252": "cp1252", "win1252": "cp1252",
    "latin1": "latin-1", "latin-1": "latin-1", "iso-8859-1": "latin-1", "iso8859-1": "latin-1",
    "iso-8859-15": "iso8859-15", "latin9": "iso8859-15",
    "mac-roman": "mac_roman", "macroman": "mac_roman", "mac_roman": "mac_roman",
}

NOMES_EXIBICAO = {
    "utf-8": "UTF-8", "utf-16": "UTF-16", "utf-16-le": "UTF-16 LE", "utf-16-be": "UTF-16 BE",
    "cp1252": "Windows-1252", "latin-1": "ISO-8859-1", "iso8859-15": "ISO-8859-15",
    "mac_roman": "Mac Roman",
}


class ErroCodificacao(ErroUso):
    """A codificação de origem é ambígua ou a escolhida não decodifica os bytes."""

    def __init__(self, codigo, motivo, sugestao="", amostras=None):
        super().__init__(codigo, motivo, sugestao)
        self.amostras = amostras or {}


@dataclass
class InfoCodificacao:
    nome: str  # nome Python normalizado
    bom: bool
    explicita: bool
    avisos: list = field(default_factory=list)

    @property
    def descricao(self) -> str:
        return NOMES_EXIBICAO.get(self.nome, self.nome)


def normalizar_nome_codificacao(nome: str) -> str:
    chave = nome.strip().lower().replace("_", "-")
    if chave in ALIASES:
        return ALIASES[chave]
    try:
        return codecs.lookup(nome).name
    except LookupError:
        raise ErroUso("CODIFICACAO_DESCONHECIDA", f"codificação desconhecida: {escapar(nome, 30)}",
                      "use, por exemplo, cp1252, latin-1, utf-8 ou utf-16") from None


def amostras_acentos(dados: bytes, codificacoes=("cp1252", "latin-1"), maximo=3) -> dict:
    """Linhas com bytes não ASCII decodificadas em cada codificação candidata,
    para o usuário comparar os acentos antes de escolher."""
    linhas = [l for l in dados.split(b"\n") if any(b > 0x7F for b in l)][:maximo]
    saida = {}
    for cod in codificacoes:
        try:
            saida[cod] = [escapar(l.rstrip(b"\r").decode(cod), 70) for l in linhas]
        except UnicodeDecodeError:
            saida[cod] = None
    return saida


def decodificar(dados: bytes, escolha: str | None = None) -> tuple:
    """Decodifica estritamente. Sem escolha: UTF-16 com BOM e UTF-8 são
    reconhecidos; qualquer outra coisa é ambígua e exige escolha explícita."""
    bom8 = dados.startswith(b"\xef\xbb\xbf")
    if escolha:
        nome = normalizar_nome_codificacao(escolha)
        try:
            if nome == "utf-16" and not dados.startswith((b"\xff\xfe", b"\xfe\xff")):
                raise ErroCodificacao(
                    "CODIFICACAO_INCOMPATIVEL", "UTF-16 sem BOM: a ordem dos bytes é ambígua",
                    "converta o arquivo para UTF-8 ou UTF-16 com BOM")
            texto = dados.decode(nome)
        except UnicodeDecodeError as e:
            raise ErroCodificacao(
                "CODIFICACAO_INCOMPATIVEL",
                f"{NOMES_EXIBICAO.get(nome, nome)} não decodifica o byte 0x{dados[e.start]:02X} "
                f"(posição {fmt_int(e.start)})",
                "escolha outra codificação e confira os acentos") from None
        bom = texto.startswith("﻿") or (nome == "utf-16")
        if texto.startswith("﻿"):
            texto = texto[1:]
        info = InfoCodificacao(nome, bom, True)
        if nome not in ("utf-8",) and not nome.startswith("utf-16"):
            try:
                dados.decode("utf-8")
                if any(b > 0x7F for b in dados):
                    info.avisos.append(Diagnostico(
                        "CODIFICACAO_SUSPEITA",
                        f"o arquivo já é UTF-8 válido, mas foi lido como {info.descricao}; "
                        "os acentos podem ficar corrompidos",
                        "o arquivo já é UTF-8; confira os acentos",
                        severidade="aviso"))
            except UnicodeDecodeError:
                pass
        return texto, info

    if dados.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            texto = dados.decode("utf-16")
        except UnicodeDecodeError:
            raise ErroCodificacao("CODIFICACAO_INCOMPATIVEL",
                                  "BOM de UTF-16, mas o conteúdo não é UTF-16 válido",
                                  "confira o arquivo de origem") from None
        nome = "utf-16-le" if dados.startswith(b"\xff\xfe") else "utf-16-be"
        if texto.startswith("﻿"):
            texto = texto[1:]
        return texto, InfoCodificacao(nome, True, False)
    try:
        texto = dados.decode("utf-8")
    except UnicodeDecodeError as e:
        nulos = b"\x00" in dados[:4096]
        sug = "utf-16-le ou utf-16-be" if nulos else "cp1252 (Windows) ou latin-1"
        raise ErroCodificacao(
            "CODIFICACAO_AMBIGUA",
            f"o arquivo não é UTF-8 (byte 0x{dados[e.start]:02X} na posição {fmt_int(e.start)}) "
            "e a codificação de origem não pode ser deduzida com segurança",
            f"escolha a codificação ({sug}) e confira os acentos",
            amostras=None if nulos else amostras_acentos(dados)) from None
    if texto.startswith("﻿"):
        texto = texto[1:]
    return texto, InfoCodificacao("utf-8", bom8, False)


# ---------------------------------------------------------------- mojibake

_BYTE_CP1252 = {}
for _b in range(0x80, 0xA0):
    try:
        _BYTE_CP1252[bytes([_b]).decode("cp1252")] = _b
    except UnicodeDecodeError:
        pass


def _byte_de(c: str):
    o = ord(c)
    if o < 0x100:
        return o
    return _BYTE_CP1252.get(c)


def _tamanho_sequencia(b) -> int:
    if b is None:
        return 0
    if 0xC2 <= b <= 0xDF:
        return 2
    if 0xE0 <= b <= 0xEF:
        return 3
    if 0xF0 <= b <= 0xF4:
        return 4
    return 0


def reparos_em_texto(s: str) -> list:
    """Trechos de `s` que são bytes UTF-8 lidos como Windows-1252/Latin-1.
    Retorna [inicio, fim, antes, depois] contíguos; nada é aplicado aqui."""
    achados = []
    k = 0
    while k < len(s):
        n = _tamanho_sequencia(_byte_de(s[k]))
        if n and k + n <= len(s):
            bs = [_byte_de(c) for c in s[k:k + n]]
            if None not in bs and all(0x80 <= x <= 0xBF for x in bs[1:]):
                try:
                    dec = bytes(bs).decode("utf-8")
                except UnicodeDecodeError:
                    dec = None
                if dec:
                    if achados and achados[-1][1] == k:
                        achados[-1][1] = k + n
                        achados[-1][2] += s[k:k + n]
                        achados[-1][3] += dec
                    else:
                        achados.append([k, k + n, s[k:k + n], dec])
                    k += n
                    continue
        k += 1
    return achados


@dataclass
class PropostaAcento:
    id: int
    entrada: int
    linha: int  # linha dentro da entrada (1 ou 2...)
    inicio: int
    fim: int
    antes: str
    depois: str
    nivel: str  # "provavel" ou "ambigua"
    contexto_antes: str
    contexto_depois: str

    def como_dict(self) -> dict:
        # Sem texto de falas: só localização e nível.
        return {"id": self.id, "entrada": self.entrada, "linha": self.linha, "nivel": self.nivel}


def _palavra(s: str, ini: int, fim: int) -> tuple:
    a = ini
    while a > 0 and not s[a - 1].isspace():
        a -= 1
    b = fim
    while b < len(s) and not s[b].isspace():
        b += 1
    return a, b


def detectar_mojibake(entradas) -> list:
    propostas = []
    for e in entradas:
        for ln, linha in enumerate(e.linhas, 1):
            vis = texto_visivel(linha)
            for ini, fim, antes, depois in reparos_em_texto(vis):
                a, b = _palavra(vis, ini, fim)
                ctx_antes = vis[a:b]
                ctx_depois = vis[a:ini] + depois + vis[fim:b]
                nivel = "ambigua" if reparos_em_texto(ctx_depois) else "provavel"
                propostas.append(PropostaAcento(
                    len(propostas) + 1, e.posicao, ln, ini, fim, antes, depois, nivel,
                    escapar(ctx_antes, 40), escapar(ctx_depois, 40)))
    return propostas


def aplicar_propostas(linha, propostas) -> list:
    """Aplica propostas (de uma mesma linha) da direita para a esquerda."""
    chars = caracteres(linha)
    for p in sorted(propostas, key=lambda p: p.inicio, reverse=True):
        estilo = chars[p.inicio][1] if p.inicio < len(chars) else False
        chars[p.inicio:p.fim] = [(c, estilo) for c in p.depois]
    return de_caracteres(chars)


_RE_INTERROGACAO = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]\?+[A-Za-zÀ-ÖØ-öø-ÿ]")
_RE_A_CRASE_PERDIDO = re.compile(r"(?<=[a-zà-ÿ])Ã(?=[ ?]|$)")


def detectar_perdas(entradas) -> list:
    """Sinais de perda anterior de bytes: não há reparo automático possível."""
    avisos = []
    for e in entradas:
        for ln, linha in enumerate(e.linhas, 1):
            vis = texto_visivel(linha)
            if "�" in vis:
                avisos.append(Diagnostico(
                    "ACENTO_IRRECUPERAVEL",
                    f"linha {ln} da entrada contém o caractere de substituição U+FFFD: "
                    "o texto original foi perdido antes",
                    "a recuperação pode ser impossível; edite manualmente sem inventar o texto",
                    e.posicao, None, "aviso"))
            if _RE_INTERROGACAO.search(vis):
                avisos.append(Diagnostico(
                    "ACENTO_POSSIVELMENTE_PERDIDO",
                    f"linha {ln} da entrada tem '?' no meio de uma palavra: pode ser letra "
                    "acentuada perdida",
                    "a recuperação pode ser impossível; revise e edite manualmente",
                    e.posicao, None, "aviso"))
            if _RE_A_CRASE_PERDIDO.search(vis):
                avisos.append(Diagnostico(
                    "ACENTO_AMBIGUO",
                    f"linha {ln} da entrada tem 'Ã' seguido de espaço: pode ser 'à' com byte perdido",
                    "revise e edite manualmente", e.posicao, None, "aviso"))
    return avisos

