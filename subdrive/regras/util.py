"""Funções utilitárias: formatação de números e tempos, escape seguro e hashes."""

from __future__ import annotations

import hashlib
import unicodedata

# Categorias Unicode que nunca são mostradas literalmente no terminal
# (controles, formatação invisível, direção de escrita, separadores de linha).
_CATEGORIAS_ESCAPADAS = {"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"}


def fmt_int(n: int) -> str:
    """Formata inteiro com separador de milhar brasileiro: 1183 -> '1.183'."""
    return f"{n:,}".replace(",", ".")


def formatar_tempo(ms: int) -> str:
    """Converte milissegundos em HH:MM:SS,mmm (com sinal '-' se negativo)."""
    sinal = "-" if ms < 0 else ""
    ms = abs(ms)
    h, resto = divmod(ms, 3_600_000)
    m, resto = divmod(resto, 60_000)
    s, mm = divmod(resto, 1000)
    return f"{sinal}{h:02d}:{m:02d}:{s:02d},{mm:03d}"


def formatar_ms(ms: int) -> str:
    return f"{fmt_int(ms)} ms"


def sha256(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def unidades_utf16(texto: str) -> int:
    """Comprimento em unidades UTF-16 (como o leitor do aparelho conta)."""
    return len(texto.encode("utf-16-le", "surrogatepass")) // 2


def escapar(texto: str, limite: int | None = None) -> str:
    """Torna o texto seguro para o terminal: controles e caracteres invisíveis
    viram sequências como \\x1b ou \\u202e, impedindo a execução de sequências
    de terminal ou a inversão visual do texto."""
    partes = []
    for c in texto:
        o = ord(c)
        if unicodedata.category(c) in _CATEGORIAS_ESCAPADAS:
            if o < 0x100:
                partes.append(f"\\x{o:02x}")
            elif o < 0x10000:
                partes.append(f"\\u{o:04x}")
            else:
                partes.append(f"\\U{o:08x}")
        else:
            partes.append(c)
    r = "".join(partes)
    if limite is not None and len(r) > limite:
        r = r[: max(limite - 1, 1)] + "…"
    return r


def descrever_caractere(c: str) -> str:
    """'U+2026 (…)' com o caractere escapado quando invisível."""
    return f"U+{ord(c):04X} ({escapar(c)})"


def compactar_indices(indices) -> str:
    """[1,2,3,7,9,10] -> '1-3, 7, 9-10'."""
    nums = sorted(set(indices))
    if not nums:
        return ""
    faixas = []
    ini = ant = nums[0]
    for n in nums[1:]:
        if n == ant + 1:
            ant = n
            continue
        faixas.append(f"{ini}-{ant}" if ant != ini else f"{ini}")
        ini = ant = n
    faixas.append(f"{ini}-{ant}" if ant != ini else f"{ini}")
    return ", ".join(faixas)
