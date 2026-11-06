"""Preparação de uma nova cópia, inteiramente em memória.

Ordem: decodificação e diagnóstico -> correções estruturais escolhidas ->
remoções selecionadas -> transformações de texto escolhidas -> deslocamento
temporal -> renumeração -> serialização -> validação integral dos bytes.
A mesma função serve à conferência e à gravação, garantindo saída idêntica.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from .codificacao import (aplicar_propostas, decodificar, detectar_mojibake, detectar_perdas)
from .contrato import MAX_FIM_MS, MAX_VISIVEIS, Diagnostico, ResultadoValidacao, validar_bytes
from .creditos import detectar_creditos
from .erros import ErroUso
from .modelo import (Trecho, caracteres, de_caracteres, interpretar_flexivel, normalizar_trechos,
                     interpretar_italico, serializar_documento, texto_visivel)
from .tabelas import RE_FORMATACAO_NAO_SUPORTADA, TABELA_PONTUACAO
from .util import compactar_indices, escapar, fmt_int, formatar_ms, formatar_tempo, sha256

OPERACAO_POR_ANOMALIA = {"corrigir_estrutura": "a correção automática", "normalizar": "a correção automática"}


@dataclass
class Opcoes:
    codificacao: str | None = None
    normalizar: bool = False
    pontuacao: bool = False
    reparar_acentos: object = None  # None, "provaveis" ou conjunto de ids
    remover_formatacao: bool = False
    remover_italico: bool = False
    redividir: bool = False
    corrigir_estrutura: bool = False
    remover_entradas: set = field(default_factory=set)
    remover_linhas: dict = field(default_factory=dict)  # entrada -> {linhas}
    politica_creditos: str | None = None  # "fortes" ou "todos"
    edicoes: dict = field(default_factory=dict)  # (entrada, linha) -> texto bruto
    deslocamento_ms: int = 0

    def tem_operacao(self) -> bool:
        return bool(self.codificacao or self.normalizar or self.pontuacao or self.reparar_acentos
                    or self.remover_formatacao or self.remover_italico or self.redividir
                    or self.corrigir_estrutura or self.remover_entradas or self.remover_linhas
                    or self.politica_creditos or self.edicoes or self.deslocamento_ms)

    def descricao(self) -> list:
        d = []
        if self.codificacao:
            d.append(f"ler a origem como {self.codificacao}")
        if self.normalizar:
            d.append("normalizar: UTF-8 sem BOM, LF (inclusive CR isolado) e acentos compostos (NFC)")
        if self.corrigir_estrutura:
            d.append("corrigir estrutura inequívoca: numeração, separadores, formato dos tempos e "
                     "pares de itálico vazios")
        if self.remover_entradas:
            d.append(f"remover entradas (índices originais): {compactar_indices(self.remover_entradas)}")
        if self.remover_linhas:
            partes = [f"{e}.{l}" for e in sorted(self.remover_linhas) for l in sorted(self.remover_linhas[e])]
            d.append(f"remover linhas (entrada.linha): {', '.join(partes)}")
        if self.politica_creditos:
            d.append(f"remover candidatos a crédito/propaganda pela política '{self.politica_creditos}' "
                     "(pode haver falsos positivos)")
        if self.edicoes:
            d.append(f"{len(self.edicoes)} edição(ões) manual(is) de linha")
        if self.reparar_acentos == "provaveis":
            d.append("reparar acentuação corrompida: todas as propostas prováveis")
        elif self.reparar_acentos:
            d.append(f"reparar acentuação corrompida: propostas {compactar_indices(self.reparar_acentos)}")
        if self.pontuacao:
            d.append("converter pontuação tipográfica (aspas curvas, travessões, reticências) e "
                     "remover caracteres invisíveis")
        if self.remover_formatacao:
            d.append("remover formatação não suportada (<b>, <u>, <s>, <font>, {\\...}), mantendo o texto")
        if self.remover_italico:
            d.append("remover o itálico (a pedido)")
        if self.redividir:
            d.append(f"redividir linhas longas em até duas linhas de {MAX_VISIVEIS} caracteres")
        if self.deslocamento_ms < 0:
            d.append(f"adiantar todas as entradas em {formatar_ms(-self.deslocamento_ms)}")
        elif self.deslocamento_ms > 0:
            d.append(f"atrasar todas as entradas em {formatar_ms(self.deslocamento_ms)}")
        d.append("gravar em forma canônica: UTF-8 sem BOM, LF, uma linha vazia entre entradas, "
                 "numeração 1, 2, 3…")
        return d


@dataclass
class Mudanca:
    tipo: str
    entrada: int | None
    descricao: str
    antes: str | None = None  # texto: só para o terminal
    depois: str | None = None

    def como_dict(self) -> dict:
        d = {"tipo": self.tipo, "entrada": self.entrada, "descricao": self.descricao}
        if self.tipo == "tempo":  # tempos não são falas
            d["antes"] = self.antes
            d["depois"] = self.depois
        return d


TITULOS_MUDANCA = {
    "codificacao": "Codificação", "bom": "BOM", "finais": "Finais de linha",
    "estrutura": "Estrutura", "remocao_entrada": "Entradas removidas",
    "remocao_linha": "Linhas removidas", "edicao": "Edições manuais",
    "acento": "Acentuação reparada", "nfc": "Acentos compostos (NFC)",
    "pontuacao": "Pontuação convertida", "formatacao": "Formatação removida",
    "italico": "Itálico removido", "redivisao": "Linhas redivididas", "tempo": "Tempos deslocados",
}


@dataclass
class ResultadoPreparacao:
    opcoes: Opcoes
    validacao_entrada: ResultadoValidacao
    hash_origem: str
    codificacao_origem: str = ""
    bom_origem: bool = False
    mudancas: list = field(default_factory=list)
    pendencias: list = field(default_factory=list)  # Diagnostico (aviso)
    bloqueios: list = field(default_factory=list)  # Diagnostico (erro)
    propostas: list = field(default_factory=list)
    propostas_aplicadas: set = field(default_factory=set)
    candidatos: list = field(default_factory=list)
    candidatos_removidos: set = field(default_factory=set)
    removidas: list = field(default_factory=list)  # (posicao_original, motivo)
    mapa_indices: list = field(default_factory=list)  # (original, final)
    entradas_saida: list = field(default_factory=list)
    entradas_origem: int = 0
    bytes_saida: bytes | None = None
    hash_saida: str | None = None
    validacao_saida: ResultadoValidacao | None = None

    @property
    def ok(self) -> bool:
        return (not self.bloqueios and self.bytes_saida is not None
                and self.validacao_saida is not None and self.validacao_saida.valido)

    def mudancas_por_tipo(self) -> dict:
        grupos = {}
        for m in self.mudancas:
            grupos.setdefault(m.tipo, []).append(m)
        return grupos

    def amostra_tempos(self) -> list:
        tempos = [m for m in self.mudancas if m.tipo == "tempo"]
        if len(tempos) <= 3:
            return tempos
        return [tempos[0], tempos[len(tempos) // 2], tempos[-1]]

    def como_dict(self) -> dict:
        grupos = self.mudancas_por_tipo()
        return {
            "codificacao_origem": self.codificacao_origem,
            "bom_origem": self.bom_origem,
            "sha256_origem": self.hash_origem,
            "entradas_origem": self.entradas_origem,
            "operacoes": self.opcoes.descricao(),
            "deslocamento_ms": self.opcoes.deslocamento_ms,
            "mudancas": {
                "total": len(self.mudancas),
                "por_tipo": {t: len(v) for t, v in grupos.items()},
                "entradas_por_tipo": {t: sorted({m.entrada for m in v if m.entrada is not None})
                                      for t, v in grupos.items()},
                "estruturais": [m.descricao for m in grupos.get("estrutura", [])][:50],
                "amostra_tempos": [m.como_dict() for m in self.amostra_tempos()],
            },
            "propostas_acentos": [dict(p.como_dict(), aplicada=p.id in self.propostas_aplicadas)
                                  for p in self.propostas],
            "candidatos_creditos": [dict(c.como_dict(), removido=c.id in self.candidatos_removidos)
                                    for c in self.candidatos],
            "removidas": [{"entrada_original": e, "motivo": m} for e, m in self.removidas],
            "mapa_indices": [{"original": o, "final": f} for o, f in self.mapa_indices],
            "pendencias": [d.como_dict() for d in self.pendencias],
            "bloqueios": [d.como_dict() for d in self.bloqueios],
            "saida": {
                "entradas": len(self.entradas_saida) if self.bytes_saida is not None else None,
                "bytes": len(self.bytes_saida) if self.bytes_saida is not None else None,
                "sha256": self.hash_saida,
                "validacao": self.validacao_saida.como_dict() if self.validacao_saida else None,
            },
        }


# ------------------------------------------------------------ transformações

def _pontuar(linha) -> list:
    return normalizar_trechos([Trecho("".join(TABELA_PONTUACAO.get(c, c) for c in t.texto), t.italico)
                               for t in linha])


def _nfc(linha) -> list:
    return normalizar_trechos([Trecho(unicodedata.normalize("NFC", t.texto), t.italico) for t in linha])


def _sem_formatacao(linha) -> list:
    return normalizar_trechos([Trecho(RE_FORMATACAO_NAO_SUPORTADA.sub("", t.texto), t.italico)
                               for t in linha])


def _sem_italico(linha) -> list:
    return normalizar_trechos([Trecho(t.texto, False) for t in linha])


def precisa_redividir(linhas) -> bool:
    return len(linhas) > 2 or any(len(texto_visivel(l)) > MAX_VISIVEIS for l in linhas)


def redividir(linhas):
    """Reorganiza em até duas linhas de no máximo 64 caracteres visíveis,
    quebrando só em espaços e preservando o estilo de cada caractere.
    Retorna None se não couber sem cortar palavras."""
    chars = []
    for linha in linhas:
        cs = caracteres(linha)
        while cs and cs[0][0] == " ":
            cs.pop(0)
        while cs and cs[-1][0] == " ":
            cs.pop()
        if not cs:
            continue
        if chars:
            chars.append((" ", chars[-1][1] and cs[0][1]))
        chars.extend(cs)
    if not chars:
        return None
    melhor = None
    for p, (c, _i) in enumerate(chars):
        if c != " ":
            continue
        a, b = chars[:p], chars[p + 1:]
        if 1 <= len(a) <= MAX_VISIVEIS and 1 <= len(b) <= MAX_VISIVEIS:
            if "".join(x for x, _ in a).strip() and "".join(x for x, _ in b).strip():
                nota = abs(len(a) - len(b))
                if melhor is None or nota < melhor[0]:
                    melhor = (nota, p)
    if melhor is None:
        if len(chars) <= MAX_VISIVEIS:
            return [de_caracteres(chars)]
        return None
    p = melhor[1]
    return [de_caracteres(chars[:p]), de_caracteres(chars[p + 1:])]


def _juntar(linhas_txt) -> str:
    return " / ".join(escapar(l, 200) for l in linhas_txt)


def _aplicar(entradas, tipo, descricao, funcao, r) -> None:
    for e in entradas:
        novas = funcao(e)
        if novas is None:
            continue
        novas = [normalizar_trechos(l) for l in novas]
        if novas == e.linhas:
            continue
        antes = _juntar(e.texto_serializado())
        e.definir_linhas(novas)
        r.mudancas.append(Mudanca(tipo, e.posicao, descricao, antes, _juntar(e.texto_serializado())))


# ---------------------------------------------------------------- remoções

def _aplicar_remocoes(entradas, opcoes: Opcoes, doc, r: ResultadoPreparacao) -> list:
    sel_entradas = set(opcoes.remover_entradas)
    sel_linhas = {k: set(v) for k, v in opcoes.remover_linhas.items()}
    explicitas = bool(sel_entradas or sel_linhas or opcoes.edicoes)
    if explicitas and not doc.numeracao_intacta:
        raise ErroUso("SELECAO_AMBIGUA",
                      "a numeração do arquivo de origem está quebrada; os índices originais são ambíguos",
                      "corrija o arquivo primeiro e use a numeração da cópia corrigida")
    total = len(entradas)
    por_pos = {e.posicao: e for e in entradas}
    fora = sorted(i for i in sel_entradas | set(sel_linhas) | {k for k, _ in opcoes.edicoes}
                  if i not in por_pos)
    if fora:
        raise ErroUso("SELECAO_INVALIDA",
                      f"índices inexistentes: {compactar_indices(fora)}; o arquivo tem {fmt_int(total)} entradas",
                      "use os números de entrada mostrados na inspeção")
    for k, ls in list(sel_linhas.items()) + [((k, {l})) for (k, l) in opcoes.edicoes]:
        n = len(por_pos[k].linhas)
        ruins = sorted(l for l in ls if l < 1 or l > n)
        if ruins:
            raise ErroUso("SELECAO_INVALIDA",
                          f"a entrada {k} tem {n} linha(s); linha(s) inexistente(s): {compactar_indices(ruins)}",
                          "use o formato entrada.linha, por exemplo 12.2")
    motivos = {i: "selecionada explicitamente" for i in sel_entradas}

    if opcoes.politica_creditos:
        for c in r.candidatos:
            if opcoes.politica_creditos == "fortes" and c.nivel != "forte":
                continue
            r.candidatos_removidos.add(c.id)
            if c.entrada_inteira:
                sel_entradas.add(c.entrada)
                motivos.setdefault(c.entrada, "política de créditos: " + ", ".join(c.motivos))
            else:
                sel_linhas.setdefault(c.entrada, set()).update(c.linhas)
        r.pendencias.append(Diagnostico(
            "POLITICA_AUTOMATICA",
            f"a política '{opcoes.politica_creditos}' remove candidatos sem revisão individual; "
            "pode remover falas reais (falsos positivos)",
            "confira a lista de remoções antes de gravar", severidade="aviso"))

    # Edições manuais: substituem uma linha por texto revisado.
    for (k, ln), bruto in sorted(opcoes.edicoes.items()):
        e = por_pos[k]
        if k in sel_entradas or ln in sel_linhas.get(k, set()):
            continue
        nova, _vazios = interpretar_italico([bruto])
        antes = _juntar(e.texto_serializado())
        linhas = list(e.linhas)
        linhas[ln - 1] = nova[0]
        e.definir_linhas(linhas)
        r.mudancas.append(Mudanca("edicao", k, f"linha {ln} editada manualmente", antes,
                                  _juntar(e.texto_serializado())))

    for k, ls in sorted(sel_linhas.items()):
        if k in sel_entradas:
            continue
        e = por_pos[k]
        restantes = [l for n, l in enumerate(e.linhas, 1) if n not in ls]
        if not restantes:
            sel_entradas.add(k)
            motivos.setdefault(k, "todas as linhas selecionadas")
            continue
        antes = _juntar(e.texto_serializado())
        e.definir_linhas(restantes)
        r.mudancas.append(Mudanca("remocao_linha", k,
                                  f"linha(s) {compactar_indices(ls)} removida(s); tempos mantidos",
                                  antes, _juntar(e.texto_serializado())))

    restantes = []
    for e in entradas:
        if e.posicao in sel_entradas:
            motivo = motivos.get(e.posicao, "selecionada")
            r.removidas.append((e.posicao, motivo))
            tempo = (f"{formatar_tempo(e.inicio)} --> {formatar_tempo(e.fim)}"
                     if e.inicio is not None else "tempo indisponível")
            r.mudancas.append(Mudanca("remocao_entrada", e.posicao, f"entrada removida: {motivo}",
                                      f"{tempo} · {_juntar(e.texto_serializado())}", None))
        else:
            restantes.append(e)
    return restantes


# --------------------------------------------------------------- principal

def preparar(dados: bytes, opcoes: Opcoes) -> ResultadoPreparacao:
    r = ResultadoPreparacao(opcoes=opcoes, validacao_entrada=validar_bytes(dados),
                            hash_origem=sha256(dados))
    texto, info = decodificar(dados, opcoes.codificacao)
    r.codificacao_origem = info.descricao
    r.bom_origem = info.bom
    r.pendencias.extend(info.avisos)
    if info.nome != "utf-8":
        r.mudancas.append(Mudanca("codificacao", None,
                                  f"codificação convertida de {info.descricao} para UTF-8"))
    if info.bom:
        r.mudancas.append(Mudanca("bom", None, "BOM inicial removido"))

    doc = interpretar_flexivel(texto)
    r.entradas_origem = len(doc.entradas)
    if doc.tinha_crlf:
        r.mudancas.append(Mudanca("finais", None, "finais de linha CRLF convertidos para LF"))
    r.propostas = detectar_mojibake(doc.entradas)
    r.candidatos = detectar_creditos(doc.entradas)
    r.pendencias.extend(detectar_perdas(doc.entradas))

    for a in doc.anomalias:
        flag = a.corrigivel_por
        habilitada = ((flag == "corrigir_estrutura" and opcoes.corrigir_estrutura)
                      or (flag == "normalizar" and opcoes.normalizar))
        if habilitada:
            r.mudancas.append(Mudanca("estrutura", a.entrada,
                                      f"{a.motivo} (linha {a.linha}) — corrigido" if a.linha else
                                      f"{a.motivo} — corrigido"))
        else:
            sug = (f"{OPERACAO_POR_ANOMALIA[flag]} corrige isto sem ambiguidade"
                   if flag else "não há correção automática segura; edite o arquivo manualmente")
            r.bloqueios.append(Diagnostico(a.codigo, a.motivo, sug, a.entrada, a.linha))
    if not doc.entradas:
        r.bloqueios.append(Diagnostico("SEM_ENTRADAS", "nenhuma entrada reconhecida no arquivo",
                                       "confira se o arquivo é mesmo uma legenda SRT"))

    entradas = [e.copia() for e in doc.entradas]

    # Reparo de acentuação: somente propostas escolhidas ou política explícita.
    # As propostas se referem às linhas originais; por isso vêm antes das remoções.
    escolhidas = set()
    if opcoes.reparar_acentos == "provaveis":
        escolhidas = {p.id for p in r.propostas if p.nivel == "provavel"}
    elif opcoes.reparar_acentos:
        ids = {p.id for p in r.propostas}
        invalidas = sorted(set(opcoes.reparar_acentos) - ids)
        if invalidas:
            raise ErroUso("PROPOSTA_INEXISTENTE",
                          f"proposta(s) de acento inexistente(s): {compactar_indices(invalidas)}",
                          f"há {len(ids)} proposta(s)")
        escolhidas = set(opcoes.reparar_acentos)
    if escolhidas:
        por_linha = {}
        for p in r.propostas:
            if p.id in escolhidas:
                por_linha.setdefault((p.entrada, p.linha), []).append(p)

        def reparar(e):
            alvo = [(ln, ps) for (k, ln), ps in por_linha.items() if k == e.posicao]
            if not alvo:
                return None
            linhas = list(e.linhas)
            for ln, ps in alvo:
                linhas[ln - 1] = aplicar_propostas(linhas[ln - 1], ps)
            return linhas
        _aplicar(entradas, "acento", "acentuação corrompida reparada", reparar, r)

    entradas = _aplicar_remocoes(entradas, opcoes, doc, r)
    vivas = {e.posicao for e in entradas}
    r.propostas_aplicadas = {i for i in escolhidas
                             if any(p.id == i and p.entrada in vivas for p in r.propostas)}
    r.mudancas = [m for m in r.mudancas if not (m.tipo == "acento" and m.entrada not in vivas)]
    pendentes = [p for p in r.propostas if p.id not in r.propostas_aplicadas and p.entrada in vivas]
    if pendentes:
        r.pendencias.append(Diagnostico(
            "ACENTOS_PENDENTES",
            f"{len(pendentes)} possível(is) acento(s) corrompido(s) não reparado(s) "
            f"(propostas {compactar_indices(p.id for p in pendentes)})",
            "confira os acentos no arquivo corrigido",
            pendentes[0].entrada, None, "aviso"))

    if opcoes.normalizar:
        _aplicar(entradas, "nfc", "acentos recompostos (NFC)", lambda e: [_nfc(l) for l in e.linhas], r)
    if opcoes.pontuacao:
        _aplicar(entradas, "pontuacao", "pontuação convertida pela tabela",
                 lambda e: [_pontuar(l) for l in e.linhas], r)
    if opcoes.remover_formatacao:
        _aplicar(entradas, "formatacao", "formatação não suportada removida",
                 lambda e: [_sem_formatacao(l) for l in e.linhas], r)
    if opcoes.remover_italico:
        _aplicar(entradas, "italico", "itálico removido", lambda e: [_sem_italico(l) for l in e.linhas], r)
    if opcoes.redividir:
        sem_solucao = []

        def redividir_entrada(e):
            if not precisa_redividir(e.linhas):
                return None
            novas = redividir(e.linhas)
            if novas is None:
                sem_solucao.append(e.posicao)
            return novas
        _aplicar(entradas, "redivisao", "linhas reorganizadas sem cortar palavras", redividir_entrada, r)
        for pos in sem_solucao:
            r.pendencias.append(Diagnostico(
                "REDIVISAO_IMPOSSIVEL",
                "o texto não cabe em duas linhas de 64 caracteres sem cortar palavras",
                "edite o texto manualmente (nenhuma fala é removida automaticamente)", pos,
                None, "aviso"))

    restantes_cand = [c for c in r.candidatos if c.id not in r.candidatos_removidos
                      and c.entrada not in {e for e, _ in r.removidas}]
    if restantes_cand:
        r.pendencias.append(Diagnostico(
            "CREDITOS_PENDENTES",
            f"{len(restantes_cand)} possível(is) crédito(s) externo(s) ou propaganda pendente(s) de "
            f"revisão (entradas {compactar_indices(c.entrada for c in restantes_cand)})",
            "confira essas falas; a correção pode removê-las", None, None, "aviso"))

    d = opcoes.deslocamento_ms
    if d:
        for e in entradas:
            if e.inicio is None:
                continue
            antes = f"{formatar_tempo(e.inicio)} --> {formatar_tempo(e.fim)}"
            e.inicio += d
            e.fim += d
            r.mudancas.append(Mudanca("tempo", e.posicao, "tempo deslocado", antes,
                                      f"{formatar_tempo(e.inicio)} --> {formatar_tempo(e.fim)}"))
            if e.inicio < 0:
                r.bloqueios.append(Diagnostico(
                    "TEMPO_NEGATIVO", f"o início ficaria em {formatar_tempo(e.inicio)}",
                    "use um deslocamento menor ou edite as primeiras entradas manualmente",
                    e.posicao))
            if e.fim > MAX_FIM_MS:
                r.bloqueios.append(Diagnostico(
                    "FIM_EXCEDE_LIMITE",
                    f"o fim ficaria em {formatar_tempo(e.fim)}; máximo: {formatar_tempo(MAX_FIM_MS)}",
                    "use um deslocamento menor", e.posicao))

    if not entradas and doc.entradas:
        r.bloqueios.append(Diagnostico("SAIDA_VAZIA", "todas as entradas seriam removidas",
                                       "uma legenda vazia não é gravada; revise a seleção"))
    r.entradas_saida = entradas
    if not r.bloqueios:
        texto_saida = serializar_documento(entradas)
        r.bytes_saida = texto_saida.encode("utf-8")
        r.hash_saida = sha256(r.bytes_saida)
        r.validacao_saida = validar_bytes(r.bytes_saida)
        r.mapa_indices = [(e.posicao, n) for n, e in enumerate(entradas, 1)]
    return r
