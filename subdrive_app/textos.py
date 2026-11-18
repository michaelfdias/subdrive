"""Frases do SubDrive com janelas.

Usa as mesmas frases do SubDrive CLI (subdrive.texts) e troca só as que falam do menu de terminal
ou de opções de linha de comando por frases que falam dos botões desta janela.
"""
from __future__ import annotations

from subdrive import texts

# Frases próprias da janela, ou trocadas porque citavam o menu/terminal.
GUI = {
    "fix_hint": "Use o botão Corrigir.",
    "credits_hint": "Para removê-las, marque \"Remover créditos e propagandas\" ao corrigir.",
    "show_hint": "",
    "update_drive_hint": "O pendrive {label} tem a versão {version}. Prepare o pendrive de novo para levar a versão nova ao player.",
    "update_program_done": "Programa atualizado. Feche e abra o SubDrive de novo para usar a versão nova.",
    "update_program_source": "O SubDrive está rodando pelo código-fonte: o programa não é trocado.",
    "update_no_package": "Não encontrei o pacote do player ao lado do programa; só o programa foi atualizado.",
    "update_no_program": "Esta versão ainda não tem o SubDrive com janelas para este computador. Baixe-o na página do projeto.",
    "update_nothing_here": "Não há nada para atualizar aqui: o pacote do player não está ao lado do programa e o programa não é trocado.",
    "package_missing_hint": "Use a pasta extraída do ZIP baixado, ou escolha a pasta do pacote.",
    "firmware_manual": "Se preferir, baixe {name} do site da Panasonic e escolha o arquivo em \"Já tenho o arquivo\".",
    "choose_drive": "Há mais de um pendrive. Escolha qual preparar.",
    "inside_zip_title": "Extraia o ZIP primeiro",
    "inside_zip": ("O SubDrive está sendo aberto de dentro do arquivo ZIP. Extraia o ZIP (botão direito → Extrair tudo) "
                   "e abra o SubDrive da pasta extraída. Senão, nada do que ele gravar fica salvo."),
    "translocated_title": "Mova a pasta do SubDrive",
    "translocated": ("O macOS abriu o SubDrive numa pasta temporária, e assim ele não encontra o pacote ao lado dele. "
                     "Feche o SubDrive, arraste a pasta inteira do SubDrive para outro lugar (por exemplo, Documentos) e abra de novo."),
    "crash": "Algo deu errado ({name}). Se repetir, avise o projeto com esta mensagem.",
    "encoding_note": "Os acentos foram convertidos para o formato que o player lê. Se algum parecer estranho, abra o arquivo novo para conferir.",
    "format_title": "Como formatar",
    "firmware_needed": ("Para montar o programa do player, o SubDrive usa o firmware oficial da Panasonic ({size}). "
                        "Ele é baixado uma vez só e fica guardado no computador."),
    "drive_needs_format": "Este pendrive precisa ser formatado para o player conseguir ler. Formatar apaga tudo o que está nele.",
    "drive_details": "Detalhes técnicos",
    "sync_point": "{at}  →  {shift}",
    "eject_hint": "Clique em Ejetar antes de tirar o pendrive do computador.",
    "firmware_confirm": "Conferi no player: o firmware é a versão {version} ({region}).",
    "firmware_where": "No player: Configurações → Sistema → Informações do Firmware.",
}

# Problemas: a consequência primeiro, em palavras simples (o termo técnico vem depois).
GUI_PROBLEM = {
    "encoding": "Os acentos apareceriam errados no player (o texto não está em UTF-8).",
    "lines": "{n} que não cabem na tela do jeito que estão (linhas demais, longas demais ou vazias)",
}
GUI_CHANGE = {
    "encoding": "Acentos ajustados para o player (texto convertido para UTF-8)",
}

# O que é verificado: título simples, porquê, e o detalhe técnico (o do SubDrive CLI) em letra menor.
GUI_RULES = {
    "encoding": ("Acentos legíveis", "Sem isso, os acentos aparecem errados no player."),
    "characters": ("Só letras que o player tem", "Emoji e alguns símbolos simplesmente não aparecem no player."),
    "lines": ("Falas curtas", "Falas longas demais não cabem na tela."),
    "markup": ("Sem enfeites no texto", "Cor, posição e outras marcações fazem o player recusar o arquivo."),
    "numbering": ("Falas em ordem", "É assim que o player separa uma fala da outra."),
    "time_format": ("Horários no formato certo", "Um horário escrito de outro jeito faz o player recusar o arquivo."),
    "duration": ("Cada fala na tela pelo tempo certo", "Rápida demais, a fala pisca; longa demais, fica presa na tela."),
    "overlap": ("Uma fala de cada vez", "O player mostra uma fala por vez."),
    "limits": ("Tamanho que cabe no player", "Acima do limite de memória, o player não abre a legenda."),
    "name": ("Nome de arquivo simples", "O player não abre arquivos com certos símbolos no nome."),
}


def t(key: str, **values) -> str:
    """Frase em português: a da janela, senão a do SubDrive CLI."""
    if key in GUI:
        text = GUI[key]
        return text.format(**values) if values else text
    return texts.t(texts.UI, key, "pt", **values)


def problem(key: str, **values) -> str:
    if key in GUI_PROBLEM:
        return GUI_PROBLEM[key].format(**values) if values else GUI_PROBLEM[key]
    return texts.t(texts.PROBLEM, key, "pt", **values)


def change(key: str) -> str:
    if key in GUI_CHANGE:
        return GUI_CHANGE[key]
    return texts.t(texts.CHANGE, key, "pt")


def rules():
    """[(título simples, porquê, detalhe técnico)] do que é verificado, na ordem do CLI."""
    return [(GUI_RULES[k][0], GUI_RULES[k][1], pt_title) if k in GUI_RULES else (pt_title, pt_why, "")
            for k, (pt_title, pt_why, _, _) in texts.RULES.items()]


def number(n) -> str:
    """1234 -> '1.234' (como se escreve no Brasil)."""
    return "{:,}".format(int(n)).replace(",", ".")


def decimal(v, digits=1) -> str:
    return ("%.*f" % (digits, v)).replace(".", ",")


SINGULAR = [("começam antes", "começa antes"), ("curtas demais", "curta demais"), ("longas demais", "longa demais"),
            (" falas ·", " fala ·"), ("problema(s)", "problema"), ("arquivo(s)", "arquivo"), ("legenda(s)", "legenda"),
            ("ponto(s)", "ponto"), ("aplicado(s)", "aplicado"), ("fala(s) parecem", "fala parece")]
PLURAL = [("problema(s)", "problemas"), ("arquivo(s)", "arquivos"), ("legenda(s)", "legendas"), ("ponto(s)", "pontos"),
          ("aplicado(s)", "aplicados"), ("fala(s)", "falas")]


def concordar(text: str, n: int) -> str:
    """Ajusta "1 falas", "1 fala começam", "3 problema(s)"... para o número certo."""
    for a, b in (SINGULAR if n == 1 else PLURAL):
        text = text.replace(a, b)
    return text
