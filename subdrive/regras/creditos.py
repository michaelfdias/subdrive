"""Sugestões locais de créditos externos e propaganda (nunca removidos sozinhos).

Os padrões são transparentes: cada candidato informa o motivo. Posição no
início ou no fim do arquivo é só um indício. Uma fala real pode conter um
nome, um endereço ou a palavra "tradução"; por isso tudo passa por revisão.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .modelo import texto_visivel
from .util import escapar, formatar_tempo


def _normalizar(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


# (expressão, motivo, forte?)
_PADROES = [
    (r"https?://|\bwww\.", "endereço de site (URL)", True),
    (r"\b[a-z0-9][a-z0-9-]{2,}(?:\.[a-z0-9-]+)*\.(?:com|net|org|info|biz|tv|io|me|xyz|top|club|"
     r"site|online|app|link|ly|cc|ws)(?:\.[a-z]{2})?\b", "domínio de site", True),
    (r"\b[a-z0-9][a-z0-9-]{2,}\.(?:com|net|org)\.br\b", "domínio de site", True),
    (r"[\w.+-]+@[a-z0-9-]+\.[a-z]{2,}", "endereço de e-mail", True),
    (r"(?:^|\s)@[a-z0-9_.]{3,}", "perfil de rede social (@)", True),
    (r"\b(?:legendas?|legendad[oa]s?|legendagem)\s*(?:por\b|by\b|:|feitas?\s+por|criadas?\s+por|"
     r"traduzidas?\s+por|sincronizadas?\s+por|revisadas?\s+por)", "crédito de legenda", True),
    (r"\b(?:traducao|traduzid[oa]s?|revisao|revisad[oa]s?|sincronia|sincronizacao|sincronizad[oa]s?|"
     r"ressincronizacao|resync|correcao|correcoes|adaptacao|timing)\s*(?:por\b|by\b|:)",
     "crédito de tradução/revisão/sincronia", True),
    (r"\b(?:subtitles?|subs|subtitled|translated|translation|synced|synchronized|resynced|"
     r"corrected|corrections|ripped|encoded|captioned|captions?)\s*(?:by\b|:)",
     "crédito de legenda (inglês)", True),
    (r"\b(?:equipe|team|grupo)\s+(?:de\s+)?(?:legendas?|subs|subtitles?|traducao)\b"
     r"|\b(?:legendas?|subs|subtitles?)\s+(?:team|equipe)\b", "equipe de legenda", True),
    (r"\b(?:opensubtitles|addic7ed|subscene|podnapisi|legendas\s*\.?\s*tv|legendasdivx|legendei|"
     r"yify|yts|rarbg|subdl|tvsubtitles)\b", "site de legendas conhecido", True),
    (r"\b(?:publicidade|anuncie|advertise|advertisement|sponsored|patrocinad[oa]\s+por|"
     r"patreon|ko-?fi|paypal|apoia-se|support us)\b", "anúncio ou pedido de apoio", True),
    # Indícios fracos: só contam no início/fim ou em combinação.
    (r"\b(?:legendas?|legendagem|tradutor(?:es)?|traducao|revisor(?:es)?|revisao|sincronia|"
     r"subtitles?|subs)\b", "menção a legenda/tradução", False),
    (r"\b(?:equipe|team)\b", "menção a equipe", False),
    (r"\b(?:instagram|facebook|twitter|tiktok|youtube|telegram|whatsapp|discord|twitch|kwai)\b",
     "rede social", False),
    (r"\b(?:siga-nos|sigam|siga|follow us|inscreva-se|subscribe|compartilhe)\b",
     "convite para seguir ou se inscrever", False),
    (r"\b(?:baixe|download|assista|acesse|visite|visit)\b", "convite para baixar/acessar", False),
    (r"\b(?:gratis|vpn|pix|cupom|coupon|desconto|discount|promocao|donate|doe)\b",
     "termo promocional", False),
]
_COMPILADOS = [(re.compile(p), motivo, forte) for p, motivo, forte in _PADROES]
EXTREMIDADE = 3  # entradas iniciais/finais consideradas "início/fim"


@dataclass
class Candidato:
    id: int
    entrada: int
    inicio: int | None
    fim: int | None
    nivel: str  # "forte" ou "fraco"
    motivos: list
    linhas: list  # linhas da entrada que casaram com os padrões
    total_linhas: int
    extremidade: bool
    previa: str = field(repr=False, default="")

    @property
    def entrada_inteira(self) -> bool:
        return set(self.linhas) >= set(range(1, self.total_linhas + 1))

    def como_dict(self) -> dict:
        # Sem o texto da fala.
        return {
            "id": self.id, "entrada": self.entrada,
            "inicio": formatar_tempo(self.inicio) if self.inicio is not None else None,
            "nivel": self.nivel, "motivos": self.motivos, "linhas": self.linhas,
            "total_linhas": self.total_linhas, "inicio_ou_fim_do_arquivo": self.extremidade,
        }


def analisar_linha(texto: str) -> tuple:
    """Retorna (motivos_fortes, motivos_fracos) encontrados numa linha."""
    norm = _normalizar(texto)
    fortes, fracos = [], []
    for rx, motivo, forte in _COMPILADOS:
        if rx.search(norm):
            (fortes if forte else fracos).append(motivo)
    return fortes, fracos


def detectar_creditos(entradas) -> list:
    candidatos = []
    total = len(entradas)
    for k, e in enumerate(entradas):
        extremo = k < EXTREMIDADE or k >= total - EXTREMIDADE
        linhas_fortes, linhas_fracas = [], []
        motivos_fortes, motivos_fracos = [], []
        for ln, linha in enumerate(e.linhas, 1):
            fortes, fracos = analisar_linha(texto_visivel(linha))
            if fortes:
                linhas_fortes.append(ln)
                motivos_fortes += [m for m in fortes if m not in motivos_fortes]
            if fracos:
                linhas_fracas.append(ln)
                motivos_fracos += [m for m in fracos if m not in motivos_fracos]
        if motivos_fortes:
            nivel = "forte"
            linhas = sorted(set(linhas_fortes))
        elif motivos_fracos and (extremo or len(motivos_fracos) >= 2):
            nivel = "fraco"
            linhas = sorted(set(linhas_fracas))
        else:
            continue
        motivos = motivos_fortes + [m for m in motivos_fracos if m not in motivos_fortes]
        if extremo:
            motivos.append("no início ou no fim do arquivo")
        previa = " / ".join(escapar(texto_visivel(l), 60) for l in e.linhas)
        candidatos.append(Candidato(len(candidatos) + 1, e.posicao, e.inicio, e.fim, nivel,
                                    motivos, linhas, len(e.linhas), extremo, previa))
    return candidatos
