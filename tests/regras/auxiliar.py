"""Geradores de fixtures sintéticas em memória (nenhum filme real)."""

from __future__ import annotations

import os
import tempfile

from subdrive.regras.util import formatar_tempo


def entrada(i, ini_ms, fim_ms, *linhas, indice=None) -> str:
    idx = str(i) if indice is None else indice
    return "\n".join([idx, f"{formatar_tempo(ini_ms)} --> {formatar_tempo(fim_ms)}", *linhas])


def srt(*blocos) -> str:
    return "\n\n".join(blocos) + "\n"


def uma(texto: str, ini=1000, fim=2000) -> bytes:
    """Arquivo com uma única entrada válida em índice e tempo; `texto` pode ter \\n."""
    return srt(entrada(1, ini, fim, *texto.split("\n"))).encode("utf-8")


def sequencia(n: int, texto="Fala {i}", passo=1000, dur=500, inicio=1000) -> str:
    return srt(*(entrada(i, inicio + (i - 1) * passo, inicio + (i - 1) * passo + dur,
                         texto.format(i=i)) for i in range(1, n + 1)))


def pasta_temporaria(caso) -> str:
    """Pasta temporária com caminho real (no macOS /var é link para /private/var)."""
    d = os.path.realpath(tempfile.mkdtemp(prefix="subdrive-teste-"))
    caso.addCleanup(_apagar_arvore, d)
    return d


def _apagar_arvore(d: str) -> None:
    import shutil
    shutil.rmtree(d, ignore_errors=True)


def escrever(pasta: str, nome: str, dados: bytes) -> str:
    caminho = os.path.join(pasta, nome)
    with open(caminho, "wb") as f:
        f.write(dados)
    return caminho


def listar(pasta: str) -> list:
    """Lista recursiva (para provar que nada foi criado)."""
    saida = []
    for raiz, dirs, arqs in os.walk(pasta):
        for n in dirs + arqs:
            saida.append(os.path.relpath(os.path.join(raiz, n), pasta))
    return sorted(saida)
