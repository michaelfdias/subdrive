"""Tabelas explícitas de conversão (usadas só quando o usuário escolhe a operação)."""

from __future__ import annotations

import re

# Pontuação: substituições seguras e transparentes.
TABELA_PONTUACAO = {
    # aspas simples curvas e apóstrofos tipográficos -> '
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    # aspas duplas curvas -> "
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
    # hífens e travessões Unicode -> -
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
    "―": "-", "−": "-",
    # reticências -> ...
    "…": "...",
    # caracteres invisíveis (BOM interno, larguras zero, marcas de direção): removidos
    "﻿": "", "​": "", "‌": "", "‍": "", "‎": "", "‏": "",
    "⁠": "", "‪": "", "‫": "", "‬": "", "‭": "", "‮": "",
    "⁦": "", "⁧": "", "⁨": "", "⁩": "",
}

# Formatação: marcações não suportadas cujo conteúdo interno é mantido.
# Somente estas formas conhecidas; qualquer outro <palavra> exige revisão manual.
RE_FORMATACAO_NAO_SUPORTADA = re.compile(
    r"</?(?:b|u|s|strike|font)(?:\s[^<>]*)?>|\{\\[^{}\n]*\}", re.IGNORECASE
)
