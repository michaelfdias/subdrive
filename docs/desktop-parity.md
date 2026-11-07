# SubDrive Desktop: análise e paridade

Base analisada: `f55a85e9b0c05499f2480a1f299efcf9fef980d6` do repositório
`michaelfdias/subdrive`. O motor original não foi reescrito ou alterado.

## Como o CLI funciona

`__main__` chama `cli.main`. Sem argumentos, `menu.Menu` apresenta oito tarefas
em terminal, com seleção por teclas quando possível; com argumentos, argparse
oferece os mesmos comandos em inglês e português. Um arquivo passado na abertura
é verificado e recebe opções apropriadas ao tipo.

`core` lê SRT/SUP e retorna estruturas de diagnóstico. A interpretação SRT é
delegada ao mesmo pacote `regras` usado no contrato do player: codificação,
caracteres, linhas, marcação, sequência, timestamps, duração, sobreposição,
limites e nomes. `ui` traduz esses resultados para português. `fix_srt` repara
apenas o que pode reparar, revalida e nunca sobrescreve o original. A remoção de
créditos é uma escolha explícita. `write_new` usa criação exclusiva.

`pgs` usa Pillow, fontTools e fontes incluídas para renderizar SRT em imagens de
1080p, codificar paletas/RLE e gerar SUP. Verifica caracteres ausentes e limites
do player. Todas as fontes, cores e intervalos são importados das tabelas
originais. `sup_reader` verifica SUP e `sync` aplica pontos salvos pelo player
a SRT ou SUP, preservando o original e prevenindo tempos inválidos.

`drives` usa APIs e utilitários já presentes no Windows, macOS e Linux para
detectar mídias montadas, FAT32, MBR, partições, espaço e proteção contra escrita.
Não formata discos. `package` verifica hashes do manifesto, planeja as cópias,
preserva arquivos pessoais, remove fontes obsoletas e verifica os arquivos
gravados. `player` extrai o código necessário do firmware oficial com
`squashfs` e monta BDJ.jar localmente; não requer Java instalado.

`update` consulta releases, verifica assinatura Ed25519 e hashes, escolhe canal
estável/beta e baixa tudo antes de substituir pacote/programa. O índice original
contém executáveis CLI: a edição desktop exige chaves distintas para não instalar
acidentalmente o terminal sobre a GUI.

## Mapeamento completo da interface

| Recurso do CLI | Caminho na interface desktop | Implementação |
| --- | --- | --- |
| check/verificar SRT e SUP; vários arquivos ou pasta | Legendas → escolher/arrastar → Verificar | `cli.cmd_check` |
| --show/mostrar problemas por fala | Opções avançadas → Mostrar cada problema | `ui.render_check` |
| fix/corrigir SRT | Legendas → Corrigir legenda SRT | `cli.cmd_fix` |
| --output/saida; nome automático sem sobrescrever | Opções avançadas → Novo nome | `core.next_name`, `write_new` |
| --remove-credits; antes/depois | Opções avançadas → Remover créditos / Mostrar alterações | motor original |
| pgs; fonte, cor, negrito, tamanho 30–72, contorno 0–6 | Legendas → Criar PGS → Aparência | `cli.cmd_pgs`, tabelas `pgs` |
| sync/sincronizar SRT e SUP; pontos automáticos | Legendas → Aplicar sincronia do player | `cli.cmd_sync` |
| --points/pontos personalizado | Opções avançadas → Pontos de sincronia | `sync` original |
| drives/pendrives; formato, espaço, orientações | Pendrive → Procurar pendrives | `drives.find`, `ui.render_drive`, `format_help` |
| prepare/preparar; selecionar mídia/pacote | Pendrive → destino e pacote → Revisar preparação | `package.load/plan/apply` |
| --firmware local ou download verificado | Opções avançadas → Firmware local | `cli._player_program` |
| --replace-subtitles | Opções avançadas → Substituir legendas | `package.plan/apply` |
| confirmação de escrita | Resumo com destino, contagens e substituições | diálogo antes de `prepare_apply` |
| --eject; ejeção posterior | Ejetar ao terminar / Ejetar selecionado | `drives.eject` |
| update --check; notas; canal beta persistente | Ajuda e atualizações → Procurar | `update.releases/best`, config por usuário |
| update instalar pacote e programa | Instalar atualização, com confirmação | hashes/assinatura originais; programa exige `desktop-*` |
| rules/regras | Ajuda → O que é verificado e por quê | `ui.render_rules` |
| abrir arquivo via argumento/arrastar | Argumentos, drop local e evento de abertura macOS | janela desktop |
| versão, ajuda, sem cores/emoji | Cabeçalho, guia e relatório de texto | elementos próprios da GUI |

Os aliases de comandos e flags de apresentação do terminal não se tornam opções
visuais redundantes. O CLI original permanece disponível pelo código original.
A GUI oferece seletores nativos, tarefas em thread, progresso e relatório salvável.

## Empacotamento e limites verificáveis

Qt Widgets fornece uma aplicação desktop local com janela e diálogos do SO;
não há servidor, navegador ou WebView. Python, Qt, bibliotecas, certificados e
fontes são incluídos por PyInstaller. O usuário não instala dependências de
linguagem. Linux ainda depende dos componentes básicos da sessão gráfica do SO,
como qualquer aplicação desktop; a distribuição alvo é Ubuntu 22.04+ x64.

A workflow `Desktop` compila e inicia o executável congelado em Windows x64,
Linux x64, macOS Apple Silicon e macOS Intel. A execução automatizada usa Qt
offscreen: prova importação, criação da janela e saída do binário, mas não é um
teste de interação humana em cada desktop. Não foi feito teste com player ou
pendrive físico nesta sessão. Detecção, cópia e preservação são cobertas com
fixtures e simulações, além dos testes originais.

Os binários ainda não têm certificados de assinatura Windows ou notarização
Apple. O índice original ainda precisa publicar assets `desktop-<sistema>-<arch>`
assinados para a autoatualização da GUI; a atualização do pacote funciona com
as chaves existentes. Nenhuma chave privada foi criada ou assinatura contornada.

Revisão visual independente: [desktop-ux-review.md](desktop-ux-review.md).
