"""Interpretação de deslocamentos de tempo (adiantar/atrasar) com aritmética exata (Decimal, sem float)."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .erros import ErroUso
from .util import escapar

_RE_VALOR = re.compile(r"\s*([0-9]+(?:[.,][0-9]+)?)\s*(ms|s|min)\s*\Z", re.IGNORECASE)
_RE_SO_NUMERO = re.compile(r"\s*[0-9]+(?:[.,][0-9]+)?\s*\Z")
_FATORES = {"ms": 1, "s": 1000, "min": 60_000}
EXEMPLOS = "exemplos: 750ms, 1s, 1,5s, \"2 min\""


def interpretar_deslocamento(valor: str) -> int:
    """'1,5s' -> 1500. Sempre não negativo; a direção vem da opção escolhida."""
    v = (valor or "").strip()
    if not v:
        raise ErroUso("DESLOCAMENTO_INVALIDO", "valor de deslocamento vazio", EXEMPLOS)
    if v[0] in "+-":
        raise ErroUso("DESLOCAMENTO_COM_SINAL",
                      f"o valor '{escapar(v, 20)}' tem sinal; a direção é dada pela opção",
                      "escolha adiantar (legenda aparece antes) ou atrasar (aparece depois), "
                      "sempre sem sinal")
    m = _RE_VALOR.match(v)
    if not m:
        if _RE_SO_NUMERO.match(v):
            raise ErroUso("DESLOCAMENTO_SEM_UNIDADE", f"falta a unidade em '{escapar(v, 20)}'",
                          "informe ms, s ou min; " + EXEMPLOS)
        raise ErroUso("DESLOCAMENTO_INVALIDO",
                      f"valor ou unidade não reconhecido: '{escapar(v, 20)}'",
                      "use um número e a unidade ms, s ou min; " + EXEMPLOS)
    numero_txt, unidade = m.group(1), m.group(2).lower()
    if unidade == "ms" and re.search(r"[.,]", numero_txt):
        raise ErroUso("DESLOCAMENTO_SUBMILISSEGUNDO",
                      f"'{escapar(v, 20)}': milissegundos devem ser inteiros",
                      "escreva sem separador de milhar ou decimal, por exemplo 1500ms")
    try:
        numero = Decimal(numero_txt.replace(",", "."))
    except InvalidOperation:  # pragma: no cover - já filtrado pela expressão
        raise ErroUso("DESLOCAMENTO_INVALIDO", f"número inválido: '{escapar(v, 20)}'", EXEMPLOS)
    total = numero * _FATORES[unidade]
    if not total.is_finite() or total != total.to_integral_value():
        raise ErroUso("DESLOCAMENTO_SUBMILISSEGUNDO",
                      f"'{escapar(v, 20)}' não corresponde a um número inteiro de milissegundos",
                      "a menor precisão aceita é 1 ms")
    return int(total)


def descrever_direcao(deslocamento_ms: int) -> str:
    if deslocamento_ms < 0:
        return "adiantar"
    if deslocamento_ms > 0:
        return "atrasar"
    return "manter"
