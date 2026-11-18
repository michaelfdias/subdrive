# SubDrive com janelas × SubDrive CLI: onde está cada recurso

Levantamento de tudo o que o SubDrive CLI faz (`subdrive/cli.py`, `subdrive/menu.py`, `subdrive/ui.py`,
`subdrive/texts.py`) e onde cada coisa fica na janela (`subdrive_app/`). As ações da janela chamam as mesmas
funções do CLI (`subdrive.core`, `pgs`, `sync`, `drives`, `package`, `player`, `update`), sem mudar nada nelas;
`tests/test_app.py` confere que os arquivos gravados são os mesmos, byte a byte.

## Comandos e opções

| CLI | Na janela | Teste |
|---|---|---|
| `verificar <arquivo-ou-pasta>…` | **Legendas**: lista com a situação de cada legenda (pendrive, pacote, pasta do programa), "Adicionar legendas", "Adicionar pasta" ou arrastar; resumo "N de M prontas" por pasta | `Paridade.test_verificar`, `Janela` |
| `verificar --mostrar` | Detalhe da legenda → "Ver as falas com problema" (horário + texto de cada fala) | `Janela` |
| `corrigir <arquivo>` | Detalhe → **Corrigir agora** → prévia "O que será ajustado" → "Salvar cópia corrigida" | `test_corrigir_igual_ao_cli` |
| `corrigir --saida nome` | Campo "Salvar como" (nome sugerido Filme_2.srt…) | `test_corrigir_igual_ao_cli`, `test_nunca_grava_por_cima` |
| `corrigir --mostrar` | "Ver antes e depois" em cada mudança | `test_previa_nao_grava` |
| `corrigir --remover-creditos` | Caixa "Remover também as falas que parecem créditos…" (com "Ver quais são"); no aviso da legenda, "Criar uma cópia sem essas falas" | `test_corrigir_igual_ao_cli` |
| `pgs <arquivo>` | Detalhe → **Criar PGS** (só para SRT que passa na verificação, como no CLI) | `test_pgs_igual_ao_cli` |
| `pgs --cor` (20 cores) | Estilos prontos + "Personalizar" → as 20 cores | `test_pgs_igual_ao_cli` |
| `pgs --fonte` (9 fontes), `--negrito` | "Personalizar" → Fonte, Negrito | idem |
| `pgs --tamanho 30–72`, `--contorno 0–6` | "Personalizar" → controles deslizantes (contorno de 0,5 em 0,5) | idem |
| `pgs --saida` | Campo "Salvar como" (padrão Filme.<cor>.sup) | idem |
| `sincronizar <arquivo>` | Detalhe → **Aplicar a sincronia** (aparece quando o player gravou pontos para a legenda) | `test_sincronia_igual_ao_cli` |
| `sincronizar --pontos arquivo` | "Usar outro arquivo de pontos…" e "Escolher um arquivo de pontos de sincronia…" | `test_sincronia_com_outro_arquivo` |
| `sincronizar --saida` | Campo "Salvar como" | idem |
| `pendrives` | **Pendrive**: cada pendrive com formato, se o player lê, versão instalada e "Como formatar" (passos do sistema) | `test_pendrive_ruim` |
| `preparar` | Pendrive → **Preparar pendrive** (passo a passo) | `test_preparar_igual_ao_cli` |
| `preparar --pendrive` | Cada pendrive tem o próprio botão | idem |
| `preparar --pacote pasta` | Pendrive → Avançado → "Usar outra pasta…" | `test_pacote_ausente` |
| `preparar --firmware zip` | Passo do firmware → "Já tenho o arquivo…" | `test_firmware_errado_ou_sem_internet` |
| `preparar` (baixar o firmware) | Passo do firmware → "Baixar agora" (com progresso; guardado em firmware/) | `test_baixar_firmware`; no build, `tools/app_real_check.py` com o firmware oficial |
| `preparar --substituir-legendas` | Passo do plano → Detalhes → "Trocar também as legendas de exemplo…" | `test_substituir_legendas` |
| `preparar --sim` | A confirmação é o botão "Preparar" | — |
| `preparar --ejetar` | Fim do preparo → "Ejetar o pendrive"; também "Ejetar" em cada pendrive | — |
| `atualizar` | **Atualizações** → "Procurar atualização" → "Atualizar agora" (pacote do player e o próprio programa) | `Atualizacao.*` |
| `atualizar --verificar` | "Procurar atualização" mostra a versão nova e as novidades sem instalar | `test_nenhuma` |
| `atualizar --beta on/off` | Atualizações → "Receber versões de teste" (Ligado/Desligado) | `test_versoes_de_teste` |
| `atualizar --sim` | A confirmação é o botão "Atualizar agora" | — |
| `regras` | Legendas → "O que é verificado e por quê?" e a tela **Ajuda** | `Janela` |
| `--versao` | Barra lateral ("Versão 1.0.0") e Atualizações | — |
| `--ajuda` | Tela **Ajuda** (como usar, links, regras) | — |
| `--sem-emoji`, `--sem-cor` | Só fazem sentido no terminal; a janela usa ícones e cores próprios, claro ou escuro conforme o sistema | — |

## Comportamentos do menu do CLI

| CLI | Na janela |
|---|---|
| Arquivo arrastado sobre o programa ou para dentro do menu: verifica e oferece o que faz sentido | Arrastar para a janela, abrir com o programa (Windows/Linux) ou soltar no ícone (macOS): abre o detalhe da legenda com as ações possíveis |
| Procura legendas no pacote, nos pendrives, na pasta do programa e na pasta atual | Igual (grupos na tela Legendas); pendrives novos aparecem sozinhos |
| Cabeçalho com pacote e pendrives | Barra lateral com a situação de cada pendrive (clicável) e Pendrive → Avançado |
| Aviso de programa aberto de dentro do ZIP | Igual, numa janela de aviso; no macOS, descobre o lugar original quando o sistema isola o app |
| Apaga a cópia antiga do programa depois de atualizar | Igual (o `.app` inteiro no macOS) |
| Todas as frases em português | Mesmas frases do CLI (`subdrive.texts`); só mudam as que citavam o terminal ou o menu (`subdrive_app/textos.py`) |

## Conferido em cada sistema (`.github/workflows/app.yml`)

Windows, macOS Apple Silicon, macOS Intel e Linux: todos os testes; o programa empacotado com `--autoteste`
(verificar, corrigir, PGS em vários processos, sincronia); a janela aberta (no macOS também pelo Finder); e o
preparo completo com o firmware oficial da Panasonic, para BD e UHD.
