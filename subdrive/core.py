"""SubDrive core: check and fix subtitle files against the player's rules.

The rules are exactly those of the player's SRT reader (`subdrive.regras`). Nothing here prints:
results are data, rendered by `subdrive.ui`.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from . import sup_reader
from .regras import arquivos
from .regras.codificacao import ErroCodificacao, decodificar
from .regras.contrato import (DURACAO_MAX_MS, DURACAO_MIN_MS, MAX_BYTES, caractere_permitido,
                                validar_bytes)
from .regras.modelo import (Trecho, interpretar_flexivel, normalizar_trechos, serializar_documento,
                              texto_visivel)
from .regras.preparacao import Opcoes, preparar

# Each player rule, in the order shown to the user. Each diagnostic code maps to one rule.
RULES = ["encoding", "characters", "lines", "markup", "numbering", "time_format", "duration",
         "overlap", "limits", "name"]
CODE_RULE = {
    "CODIFICACAO_AMBIGUA": "encoding", "CODIFICACAO_INCOMPATIVEL": "encoding", "BOM_INTERNO": "encoding",
    "UTF8_INVALIDO": "encoding", "CODIFICACAO_UTF16": "encoding",
    "CARACTERE_NAO_PERMITIDO": "characters",
    "LINHAS_DE_TEXTO_EXCEDIDAS": "lines", "LINHA_LONGA": "lines", "LINHA_BRUTA_EXCEDIDA": "lines",
    "LINHA_EM_BRANCO": "lines", "LINHA_SEM_TEXTO": "lines", "SEM_TEXTO": "lines",
    "TAG_NAO_SUPORTADA": "markup", "ITALICO_ANINHADO": "markup", "ITALICO_FECHAMENTO_ORFAO": "markup",
    "ITALICO_SEM_FECHAMENTO": "markup", "ITALICO_VAZIO": "markup", "TAGS_EXCEDIDAS": "markup",
    "INDICE_AUSENTE": "numbering", "INDICE_FORA_DE_SEQUENCIA": "numbering", "INDICE_INVALIDO": "numbering",
    "TEMPO_AUSENTE": "time_format", "TEMPO_FORMATO": "time_format", "TEMPO_INVALIDO": "time_format",
    "SEPARADOR_AUSENTE": "time_format", "ENTRADA_INCOMPLETA": "time_format",
    "ESTRUTURA_INTERROMPIDA": "time_format", "CR_INTERNO": "time_format",
    "DURACAO_CURTA": "duration", "DURACAO_LONGA": "duration", "FIM_NAO_POSTERIOR": "duration",
    "SOBREPOSICAO": "overlap",
    "TAMANHO_EXCEDIDO": "limits", "ENTRADAS_EXCEDIDAS": "limits", "LINHAS_EXCEDIDAS": "limits",
    "FIM_EXCEDE_LIMITE": "limits", "ARQUIVO_VAZIO": "limits", "SEM_ENTRADAS": "limits",
}
SUP_LIMIT = sup_reader.LIMIT


@dataclass
class Spot:
    """Where a problem or change is: subtitle number (as in the file), start time and a short text."""
    cue: int | None
    time: str | None = None
    text: str = ""
    after: str = ""


@dataclass
class Problem:
    rule: str
    spots: list = field(default_factory=list)
    detail: str = ""  # e.g. the offending characters


@dataclass
class CheckResult:
    path: Path
    kind: str  # "srt" or "pgs"
    ok: bool = False
    problems: list = field(default_factory=list)   # Problem, blocking
    warnings: list = field(default_factory=list)   # (key, spots)
    cues: int = 0
    duration: str = ""
    fixable: bool | None = None                    # SRT only: can `fix` solve everything?
    unreadable: bool = False


@dataclass
class Change:
    kind: str
    spots: list = field(default_factory=list)


@dataclass
class FixResult:
    source: Path
    output: Path | None = None
    data: bytes | None = None
    changes: list = field(default_factory=list)    # Change
    remaining: list = field(default_factory=list)  # Problem left after the fix
    encoding: str = "utf-8"
    credits: list = field(default_factory=list)    # Spot of possible credits/ads (kept unless asked)
    credits_removed: int = 0

    @property
    def ok(self) -> bool:
        return self.data is not None and not self.remaining


def _clock(ms):
    if ms is None:
        return None
    s = ms // 1000
    return "%02d:%02d:%02d" % (s // 3600, s // 60 % 60, s % 60)


def _visible(entry) -> str:
    return " / ".join(texto_visivel(l) for l in entry.linhas)


def _short(s, n=70):
    s = s.replace("\n", " / ")
    return s if len(s) <= n else s[:n - 1] + "…"


# ------------------------------------------------------------------ check

def _document(data: bytes):
    """Best-effort reading for locating problems (never used to decide validity)."""
    for choice in (None, "cp1252", "latin-1"):
        try:
            text, _ = decodificar(data, choice)
            return interpretar_flexivel(text)
        except ErroCodificacao:
            continue
    return None


def check_srt(path: Path, data: bytes | None = None, name: str | None = None) -> CheckResult:
    data = path.read_bytes() if data is None else data
    res = CheckResult(path=path, kind="srt")
    if len(data) > 4 * MAX_BYTES:
        res.problems.append(Problem("limits"))
        res.unreadable = True
        return res
    result = validar_bytes(data)
    errors = list(result.erros)
    if any(CODE_RULE.get(d.codigo) == "encoding" for d in errors) and result.interrompido:
        # The check stops at the first non-UTF-8 byte: read it as Windows/Latin-1 to find the rest too.
        for choice in ("utf-16", "cp1252", "latin-1"):
            try:
                text, _ = decodificar(data, choice)
            except ErroCodificacao:
                continue
            errors += [d for d in validar_bytes(text.encode("utf-8")).erros if CODE_RULE.get(d.codigo) != "encoding"]
            break
    doc = _document(data)
    entries = {e.posicao: e for e in doc.entradas} if doc else {}
    res.cues = len(entries)
    if entries:
        last = max((e.fim or 0) for e in entries.values())
        res.duration = _clock(last)
    groups = {}
    for d in errors:
        rule = CODE_RULE.get(d.codigo, "time_format")
        p = groups.setdefault(rule, Problem(rule))
        e = entries.get(d.entrada) if d.entrada else None
        if d.codigo == "CARACTERE_NAO_PERMITIDO" and e is not None:
            bad = "".join(dict.fromkeys(c for c in _visible(e) if not caractere_permitido(c)))
            p.detail = "".join(dict.fromkeys(p.detail + bad))[:12]
        if len(p.spots) < 500:
            p.spots.append(Spot(d.entrada, _clock(e.inicio) if e else None, _short(_visible(e)) if e else ""))
    if result.omitidos:
        groups.setdefault("limits", Problem("limits"))
    for d in arquivos.validar_nome(name or path.name):
        if d.severidade == "erro":
            groups.setdefault("name", Problem("name", detail=d.codigo))
    res.problems = [groups[r] for r in RULES if r in groups]
    res.ok = not res.problems
    if doc:
        from .regras.creditos import detectar_creditos
        strong = [c for c in detectar_creditos(doc.entradas) if c.nivel == "forte"]
        if strong:
            res.warnings.append(("credits", [Spot(c.entrada, _clock(c.inicio), _short(c.previa)) for c in strong]))
    if not res.ok and not any(p.rule == "name" for p in res.problems):
        res.fixable = fix_srt(path, data=data).ok
    elif not res.ok:
        res.fixable = False
    return res


def check_sup(path: Path) -> CheckResult:
    res = CheckResult(path=path, kind="pgs")
    size = path.stat().st_size
    if size > SUP_LIMIT:
        res.problems.append(Problem("pgs_size"))
        return res
    try:
        cues = sup_reader.parse(path.read_bytes())
    except sup_reader.SupError as e:
        res.problems.append(Problem("pgs_damaged", detail=str(e)))
        return res
    res.cues = len(cues)
    if cues:
        res.duration = _clock(cues[-1]["end"])
    if not sup_name_ok(path.name):
        res.problems.append(Problem("name"))
    res.ok = not res.problems
    return res


def sup_name_ok(name: str) -> bool:
    return (5 <= len(name) <= 128 and name.endswith(".sup") and not name.startswith(".")
            and all((32 <= ord(c) <= 126 or 160 <= ord(c) <= 255) and c not in "/\\:" for c in name))


def check_path(path: Path) -> CheckResult:
    return check_sup(path) if path.suffix.lower() == ".sup" else check_srt(path)


def subtitle_files(folder: Path) -> list:
    return sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in (".srt", ".sup")
                   and not p.name.startswith(".")), key=lambda p: p.name.lower())


# -------------------------------------------------------------------- fix

# Characters the player cannot show and that the punctuation table does not convert.
REPLACE = {"♪": "", "♫": "", "♩": "", "♬": "", "•": "-", "­": "",
           "−": "-", "‐": "-", "‑": "-", "ʼ": "'", "′": "'", "″": '"'}


def _clean_char(c: str) -> str:
    if caractere_permitido(c):
        return c
    if c in REPLACE:
        return REPLACE[c]
    folded = unicodedata.normalize("NFKD", c)
    base = "".join(x for x in folded if caractere_permitido(x) and not unicodedata.combining(x))
    return base  # letters with foreign accents keep the base letter; emoji and symbols vanish


def _clean_line(line) -> list:
    out = []
    for t in line:
        text = "".join(_clean_char(c) for c in t.texto)
        text = re.sub(r"  +", " ", text)
        out.append(Trecho(text, t.italico))
    out = normalizar_trechos(out)
    # trim spaces at both ends
    if out:
        out[0] = Trecho(out[0].texto.lstrip(), out[0].italico)
        out[-1] = Trecho(out[-1].texto.rstrip(), out[-1].italico)
    return normalizar_trechos(out)


def _fix_timing(entries, changes):
    """Durations between 0.2 s and 60 s and no overlap, moving as little as possible."""
    overlap, duration = Change("overlap"), Change("duration")
    for k, e in enumerate(entries):
        nxt = entries[k + 1] if k + 1 < len(entries) else None
        before = (e.inicio, e.fim)
        kind = duration
        if e.fim - e.inicio > DURACAO_MAX_MS:
            e.fim = e.inicio + DURACAO_MAX_MS
        if nxt is not None and e.fim > nxt.inicio:
            e.fim, kind = nxt.inicio, overlap
        if e.fim - e.inicio < DURACAO_MIN_MS:
            target = e.inicio + DURACAO_MIN_MS
            if nxt is None or target <= nxt.inicio:
                e.fim = target
            elif nxt.fim - target >= DURACAO_MIN_MS:
                nxt.inicio = e.fim = target  # the next subtitle starts a little later
        if (e.inicio, e.fim) != before:
            fmt = lambda a, b: "%s --> %s" % (_clock_ms(a), _clock_ms(b))
            kind.spots.append(Spot(e.posicao, _clock(e.inicio), fmt(*before), fmt(e.inicio, e.fim)))
    for c in (overlap, duration):
        if c.spots:
            changes.append(c)


def _clock_ms(ms):
    return "%s,%03d" % (_clock(ms), ms % 1000)


CHANGE_KIND = {"codificacao": "encoding", "bom": None, "finais": None, "nfc": None, "estrutura": "structure",
               "acento": "accents", "pontuacao": "punctuation", "formatacao": "markup",
               "redivisao": "lines", "remocao_entrada": "credits"}


def fix_srt(path: Path, data: bytes | None = None, remove_credits: bool = False) -> FixResult:
    data = path.read_bytes() if data is None else data
    fix = FixResult(source=path)
    encoding = None
    try:
        decodificar(data, None)
    except ErroCodificacao as e:
        if e.codigo == "CODIFICACAO_AMBIGUA":
            for choice in ("cp1252", "latin-1"):
                try:
                    data.decode(choice)
                    encoding = choice
                    break
                except UnicodeDecodeError:
                    continue
        if encoding is None:
            fix.remaining.append(Problem("encoding"))
            return fix
    fix.encoding = encoding or "utf-8"
    opts = Opcoes(codificacao=encoding, normalizar=True, pontuacao=True, reparar_acentos="provaveis",
                  remover_formatacao=True, redividir=True, corrigir_estrutura=True,
                  politica_creditos="fortes" if remove_credits else None)
    r = preparar(data, opts)
    if r.bloqueios and not r.entradas_saida:
        fix.remaining.extend(Problem(CODE_RULE.get(b.codigo, "time_format"), [Spot(b.entrada)]) for b in r.bloqueios)
        return fix
    if r.bloqueios:
        fix.remaining.extend(Problem(CODE_RULE.get(b.codigo, "time_format"), [Spot(b.entrada)]) for b in r.bloqueios)
        return fix
    entries = r.entradas_saida
    starts = {e.posicao: e.inicio for e in entries}
    grouped = {}
    for m in r.mudancas:
        kind = CHANGE_KIND.get(m.tipo, m.tipo)
        if kind is None:
            continue
        c = grouped.setdefault(kind, Change(kind))
        c.spots.append(Spot(m.entrada, _clock(starts.get(m.entrada)), m.antes or "", m.depois or ""))
    fix.credits_removed = len(r.candidatos_removidos)
    if fix.credits_removed:
        grouped["credits"] = Change("credits", [Spot(e, None) for e, _ in r.removidas])
    elif r.candidatos:
        fix.credits = [Spot(c.entrada, _clock(c.inicio), _short(c.previa)) for c in r.candidatos if c.nivel == "forte"]
    order = ["encoding", "structure", "accents", "punctuation", "markup", "lines", "credits"]
    fix.changes = [grouped[k] for k in order if k in grouped] + [v for k, v in grouped.items() if k not in order]

    # Characters the player cannot show, then empty lines/subtitles, then timing.
    chars = Change("characters")
    for e in entries:
        new = [_clean_line(l) for l in e.linhas]
        new = [l for l in new if texto_visivel(l).strip()]
        if new != e.linhas:
            chars.spots.append(Spot(e.posicao, _clock(e.inicio), _visible(e), " / ".join(texto_visivel(l) for l in new)))
            e.definir_linhas(new)
    if chars.spots:
        fix.changes.append(chars)
    empty = Change("empty", [Spot(e.posicao, _clock(e.inicio)) for e in entries if not e.linhas])
    entries = [e for e in entries if e.linhas]
    if empty.spots:
        fix.changes.append(empty)
    entries.sort(key=lambda e: (e.inicio, e.fim))
    _fix_timing(entries, fix.changes)

    out = serializar_documento(entries).encode("utf-8")
    after = validar_bytes(out)
    if not after.valido:
        groups = {}
        for d in after.erros:
            rule = CODE_RULE.get(d.codigo, "time_format")
            groups.setdefault(rule, Problem(rule)).spots.append(Spot(d.entrada))
        fix.remaining = [groups[k] for k in RULES if k in groups]
        return fix
    fix.data = out
    return fix


def next_name(path: Path, wanted: str | None = None) -> Path:
    """`Filme.srt` -> `Filme_2.srt`, `Filme_3.srt`... (never an existing file).

    A wanted name is used as given (with .srt added when missing)."""
    if wanted:
        name = wanted if wanted.lower().endswith(".srt") else wanted + ".srt"
        return path.with_name(name)
    stem = re.sub(r"_(\d+)$", "", path.stem)
    n = 2
    while True:
        candidate = path.with_name("%s_%d%s" % (stem, n, path.suffix))
        if not candidate.exists():
            return candidate
        n += 1


def write_new(path: Path, data: bytes) -> None:
    """Write without ever replacing an existing file."""
    with open(path, "xb") as f:
        f.write(data)
