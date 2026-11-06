"""Every sentence SubDrive shows. Menu: Portuguese ("pt"); command line: English ("en").

Short, plain sentences for people who do not know subtitle files or terminals.
"""

# What is checked and why (shown by `subdrive rules` and in the menu).
RULES = {
    "encoding": ("Texto em UTF-8", "Senão os acentos aparecem errados.",
                 "Text in UTF-8", "Otherwise accents show up wrong."),
    "characters": ("Só letras latinas (sem emoji, ♪, — ou aspas “curvas”)", "O player só tem essas letras; as outras não aparecem.",
                   "Latin letters only (no emoji, ♪, — or “curly” quotes)", "The player only has these letters; others do not show."),
    "lines": ("Até 2 linhas por fala, com até 64 letras cada", "Mais que isso não cabe na tela.",
              "Up to 2 lines per subtitle, up to 64 letters each", "More than that does not fit on the screen."),
    "markup": ("Só itálico (<i>); sem cor, posição ou outras marcações", "O player não entende as outras e recusaria o arquivo.",
               "Italics only (<i>); no colour, position or other tags", "The player does not understand others and would reject the file."),
    "numbering": ("Falas numeradas em ordem (1, 2, 3…)", "É assim que o player separa uma fala da outra.",
                  "Subtitles numbered in order (1, 2, 3…)", "That is how the player tells subtitles apart."),
    "time_format": ("Tempo no formato 00:01:02,500 --> 00:01:04,000", "Um tempo fora do formato faz o player recusar o arquivo.",
                    "Times like 00:01:02,500 --> 00:01:04,000", "A time in another format makes the player reject the file."),
    "duration": ("Cada fala dura entre 0,2 s e 60 s", "Fora disso, a fala pisca rápido demais ou fica presa na tela.",
                 "Each subtitle lasts 0.2 s to 60 s", "Otherwise it flashes too fast or stays stuck on screen."),
    "overlap": ("Uma fala só começa depois que a anterior termina", "O player mostra uma fala por vez.",
                "A subtitle starts only after the previous one ends", "The player shows one subtitle at a time."),
    "limits": ("Até 4 horas, 3.000 falas e 256 KB", "Limite de memória do player.",
               "Up to 4 hours, 3,000 subtitles and 256 KB", "The player's memory limit."),
    "name": ("Nome do arquivo simples, terminado em .srt ou .sup", "O player não abre nomes com certos símbolos.",
             "A simple file name ending in .srt or .sup", "The player cannot open names with some symbols."),
}

# One-line problem descriptions: (pt, en). {n} = how many subtitles.
PROBLEM = {
    "encoding": ("O texto não está em UTF-8: os acentos apareceriam errados.",
                 "The text is not UTF-8: accents would show up wrong."),
    "characters": ("{n} com caracteres que o player não mostra{detail}",
                   "{n} with characters the player cannot show{detail}"),
    "lines": ("{n} com mais de 2 linhas, linha longa demais ou linha vazia",
              "{n} with more than 2 lines, a line too long or an empty line"),
    "markup": ("{n} com marcação que o player não entende (só itálico é aceito)",
               "{n} with tags the player does not understand (only italics are accepted)"),
    "numbering": ("Numeração fora de ordem ou ausente ({n})", "Numbering out of order or missing ({n})"),
    "time_format": ("Tempo ou estrutura fora do formato ({n})", "Time or layout not in the expected format ({n})"),
    "duration": ("{n} curtas demais (menos de 0,2 s) ou longas demais (mais de 60 s)",
                 "{n} too short (under 0.2 s) or too long (over 60 s)"),
    "overlap": ("{n} começam antes da anterior terminar", "{n} start before the previous one ends"),
    "limits": ("O arquivo passa do limite do player (4 horas, 3.000 falas ou 256 KB)",
               "The file is over the player's limit (4 hours, 3,000 subtitles or 256 KB)"),
    "name": ("O nome do arquivo tem símbolos que o player não aceita", "The file name has symbols the player does not accept"),
    "pgs_damaged": ("O arquivo PGS está danificado ou num formato que o player não lê.",
                    "The PGS file is damaged or in a format the player cannot read."),
    "pgs_size": ("O arquivo PGS passa de 64 MB, o limite do player.", "The PGS file is over 64 MB, the player's limit."),
}

CHANGE = {
    "encoding": ("Texto convertido para UTF-8", "Text converted to UTF-8"),
    "structure": ("Numeração e formato do tempo corrigidos", "Numbering and time format fixed"),
    "accents": ("Acentos corrompidos reparados", "Broken accents repaired"),
    "punctuation": ("Pontuação trocada pela que o player mostra (… — “ ”)", "Punctuation replaced by what the player shows (… — “ ”)"),
    "markup": ("Marcações removidas (o itálico foi mantido)", "Tags removed (italics kept)"),
    "lines": ("Linhas reorganizadas em até 2", "Lines rearranged into 2 at most"),
    "characters": ("Caracteres que o player não mostra removidos", "Characters the player cannot show removed"),
    "empty": ("Falas vazias removidas", "Empty subtitles removed"),
    "overlap": ("Fim encurtado para não invadir a fala seguinte", "End shortened so it does not run into the next subtitle"),
    "duration": ("Duração ajustada para entre 0,2 s e 60 s", "Duration adjusted to 0.2-60 s"),
    "credits": ("Créditos e propagandas removidos", "Credits and ads removed"),
}

UI = {
    "subtitle": ("fala", "subtitle"), "subtitles": ("falas", "subtitles"),
    "ok": ("Pronto para o player", "Ready for the player"),
    "summary": ("{cues} falas · {duration}", "{cues} subtitles · {duration}"),
    "fails": ("Não passa: {n} problema(s)", "Does not pass: {n} problem(s)"),
    "fixable": ("Dá para corrigir tudo automaticamente.", "Everything can be fixed automatically."),
    "fix_hint": ("Use \"Corrigir uma legenda\" no menu.", "Run: subdrive fix \"{name}\""),
    "fix_hint_cli": ("Use: subdrive fix \"{name}\"", "Run: subdrive fix \"{name}\""),
    "not_fixable": ("Parte disso precisa ser editada à mão.", "Part of this needs to be edited by hand."),
    "pgs_hint": ("Gere o PGS de novo a partir do SRT.", "Create the PGS again from the SRT."),
    "name_hint": ("Renomeie o arquivo usando letras, números, espaço, - e _.", "Rename the file using letters, numbers, spaces, - and _."),
    "at": ("ex.: {where}", "e.g. {where}"),
    "where": ("em {time}", "at {time}"),
    "where_cue": ("fala nº {cue}", "subtitle no. {cue}"),
    "more": ("… e mais {n}", "… and {n} more"),
    "credits": ("{n} fala(s) parecem créditos ou propaganda (ex.: \"{text}\")",
                "{n} subtitle(s) look like credits or ads (e.g. \"{text}\")"),
    "credits_hint": ("Para removê-las ao corrigir, escolha \"remover créditos\".", "To remove them, add --remove-credits to fix."),
    "credits_hint_cli": ("Para removê-las, use --remove-credits.", "To remove them, add --remove-credits to fix."),
    "fixed": ("Corrigido e salvo como: {name}", "Fixed and saved as: {name}"),
    "original_kept": ("O original não foi alterado.", "The original was not changed."),
    "nothing_to_fix": ("Já está pronto para o player; nada a corrigir.", "Already ready for the player; nothing to fix."),
    "cannot_fix": ("Não dá para corrigir tudo automaticamente. Falta:", "It cannot all be fixed automatically. Still wrong:"),
    "cannot_fix_hint": ("Abra o arquivo num editor de texto, ajuste essas falas e verifique de novo.",
                        "Open the file in a text editor, adjust these subtitles and check again."),
    "changes": ("O que foi ajustado:", "What was adjusted:"),
    "before": ("antes", "before"), "after": ("depois", "after"),
    "show_hint": ("Para ver cada fala alterada, use \"ver detalhes\".", "To see every changed subtitle, add --show."),
    "show_hint_cli": ("Para ver cada fala alterada, use --show.", "To see every changed subtitle, add --show."),
    "exists": ("Já existe um arquivo com esse nome: {name}", "A file with that name already exists: {name}"),
    "not_found": ("Arquivo não encontrado: {name}", "File not found: {name}"),
    "not_subtitle": ("Não é uma legenda .srt ou .sup: {name}", "Not a .srt or .sup subtitle: {name}"),
    "folder_empty": ("Nenhuma legenda .srt ou .sup em {name}", "No .srt or .sup subtitles in {name}"),
    "folder_summary": ("{ok} de {total} prontas para o player", "{ok} of {total} ready for the player"),
    "rules_title": ("O que é verificado e por quê", "What is checked and why"),
    "pgs_only_check": ("PGS não é corrigido: gere de novo a partir do SRT.", "PGS files are not fixed: create them again from the SRT."),
    "encoding_note": ("O texto estava em {enc}; confira os acentos no arquivo novo.", "The text was in {enc}; check the accents in the new file."),
}


def t(table, key, lang, **values):
    entry = table[key]
    text = entry[0] if lang == "pt" else entry[1] if len(entry) == 2 else entry[2]
    return text.format(**values) if values else text
