# Revisão independente de experiência de uso

Data: 7 de novembro de 2026. Revisor: agente independente `ux_review`, separado do autor da interface. Escopo exclusivo: clareza das tarefas, apresentação visual, interação e acessibilidade. Esta revisão não certifica paridade funcional, segurança do motor ou distribuição multiplataforma.

## Método e evidência

- Leitura dos fluxos originais em `subdrive/menu.py` e dos controles/estados em `subdrive/desktop.py`.
- Inspeção de quatro capturas Qt reais fornecidas pelo autor: início, PGS, pendrive e ajuda.
- Nova execução independente da interface com PySide6 e `QT_QPA_PLATFORM=offscreen` no Linux, em 1000 × 820 e no mínimo permitido de 700 × 640.
- Capturas após correção em `/workspace/subdrive-review/revised-{home,pgs,usb,help,minimum}.png` e inspeção visual individual.
- Consulta pontual à API `QAccessible` para nomes e políticas de foco dos campos.

Não houve teste com usuários, leitor de tela real, desktop Windows ou macOS. O modo offscreen verifica o layout renderizado pelo Qt; não substitui validação de integração com cada sistema, seleção de arquivo nativa ou escalas de tela reais.

## Problemas encontrados e retorno ao autor

| Prioridade | Achado | Resultado da revisão |
| --- | --- | --- |
| Alta | Estilo aplicado à página propagava o fundo claro aos botões primários, deixando texto branco pouco legível. | Corrigido com seletor específico da página e estado desabilitado explícito. Confirmado nas novas capturas. |
| Alta | Resultado vazio ocupava cerca de 205 px permanentemente; ações principais de PGS e pendrive ficavam abaixo da área visível, inclusive na janela padrão. | Corrigido: resultado inicialmente oculto e ação principal fixa fora da rolagem. Confirmado nas duas dimensões. |
| Média | Alguns combos eram identificados pela API acessível somente pelo valor atual, sem contexto como fonte ou cor; botões de seleção repetiam “Escolher…”. | Recomendados nomes acessíveis explícitos e associação de rótulos. A consulta pontual não equivale a teste de leitor de tela. |
| Baixa | Abrir pasta permanecia ativo sem seleção e não produzia resposta; salvar relatório estava disponível com conteúdo vazio. | Recomendado desabilitar ações sem contexto. |
| Baixa | Campo de pacote expunha nomes internos como `manifest.json`. | Recomendado orientar a escolher a pasta extraída do download. |

## Avaliação dos fluxos revisados

A divisão em Legendas, Pendrive e Ajuda e atualizações reduz o número de escolhas simultâneas. A ação inicial é verificar compatibilidade. Correção, PGS e sincronia são tarefas alternativas no mesmo seletor, com explicação curta e opções avançadas recolhidas. PGS expõe fonte, cor, tamanho, contorno e negrito apenas quando selecionado. A interface informa que os originais são preservados.

O fluxo de pendrive identifica caminho e rótulo e apresenta resumo antes da escrita. A confirmação distingue a preservação da substituição de legendas. Os controles explicam a origem dos pontos de sincronia e a necessidade de um pacote do player. As mensagens de andamento e o bloqueio de fechamento durante operações evitam uma saída acidental, embora não exista cancelamento de operações longas.

Na versão corrigida, a hierarquia visual é clara: títulos, descrições, controles e uma ação principal destacada. Texto principal escuro sobre fundo claro e primário branco sobre verde escuro permanecem legíveis nas capturas inspecionadas. A janela mínima exige rolagem para formulários longos, mas mantém a ação principal à vista. O desenho usa widgets desktop e não depende de navegador.

## Parecer

Os dois bloqueadores visuais encontrados foram corrigidos e verificados independentemente. A interface atende à organização simples por tarefa e apresenta um visual consistente nas capturas Linux Qt examinadas. A aprovação visual é limitada a esse ambiente; a aceitação final para as três plataformas requer abrir os executáveis em Windows, Linux e macOS e verificar escala, foco de teclado, diálogos nativos e leitura assistiva em cada sistema. Não declarar essa etapa como realizada com base apenas nesta revisão.
