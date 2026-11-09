# AGENTS.md

Guia para quem mexe neste repositório, pessoa ou agente. Leia antes de mudar código.

## O que é

Kotsu (pacote `kotsu-cli`): app de terminal (Python + Textual) para receitas, despesas, categorias,
contas e parcelas do mês. Alvo principal: Windows Terminal,
funcionando igual no Linux.

## Comandos

```bash
pip install -e ".[dev]"
money --dados ./tmp                          # abre o app com uma pasta de teste
python ferramentas/verificar.py --rapido     # antes de cada commit
python ferramentas/verificar.py              # antes de cada PR (igual à CI)
python ferramentas/camadas.py                # só a regra de camadas
python ferramentas/testar_instalacao.py      # pipx instalado; usa rede só na instalação
```

## Camadas (o teste falha se forem violadas)

| Pasta | Pode importar | Não pode |
|---|---|---|
| `src/money_cli/dominio/` | só biblioteca padrão sem I/O | `armazenamento`, `tela`, `sqlite3`, `os`, `pathlib`, `io`, Textual, Rich |
| `src/money_cli/armazenamento/` | `dominio` | `tela`, Textual, Rich |
| `src/money_cli/tela/` | `dominio`, `armazenamento` | `sqlite3` direto |

`src/money_cli/__main__.py` é o ponto de montagem e pode ver tudo.
Regra financeira (totais, parcelas, parser da linha rápida) mora em `dominio/`; a tela só mostra.

## Regras de dados

- Dinheiro é `int` em centavos, sempre positivo; o sinal vem do `tipo` (receita/despesa).
  Nunca `float`.
- Todo lançamento tem conta (D21): o domínio e o banco recusam lançamento sem conta.
  Categoria é opcional.
- Datas são civis (`datetime.date`), sem fuso, gravadas como `AAAA-MM-DD`.
- Totais (receitas, despesas, saldo) nunca são gravados: o SQL calcula por mês.
- Consultas por mês usam faixa `data >= início AND data < fim` para usar o índice.
  Listas são paginadas (`limite`, `desde`).
- Na tela, valor negativo aparece só em vermelho, sem sinal (`dominio.dinheiro.formatar`).

## Banco e migrações

- Toda escrita passa por `Banco.transacao()`: grava tudo ou nada. Parcelas de uma compra
  entram numa transação só.
- Mudou o esquema? Crie `src/money_cli/armazenamento/migracoes/NNNN_nome.sql` com o próximo
  número. Nunca edite uma migração já publicada. Antes de migrar um banco existente, o app
  copia o arquivo para `money.antes-vN.sqlite`.
- Teste toda migração nova com um banco na versão anterior.
- Recorrência (D36): categoria `recorrente` + tabela `recorrencia` (modelo da série e
  `gerada_ate`). `Banco.estender_recorrencias(mes)` gera os meses que faltam e só avança, por
  isso mês excluído não volta. A tela chama isso ao desenhar, limitada a hoje + 24 meses.
- Backup é só manual (D35): a tecla `b` copia o banco para `backups/` com data e hora no
  nome, sem sobrescrever, e mantém só as 5 mais recentes (poda depois de publicar). O app não faz backup sozinho. Teste relógio e
  falhas com dados temporários. Memória (`Banco.em_memoria()`) não cria backup.

## Como trabalhar

- Nomes de código, mensagens e documentos em português.
- Decisão de produto nova ou alterada: descreva no PR e atualize o README no mesmo PR.
- Nada entra na `main` sem revisão. Trabalhe em branch e abra PR.
- Testes não usam rede nem a pasta de dados real (use `Banco.em_memoria()` ou `tmp_path`).
- README e este arquivo são atualizados no mesmo PR que muda o que eles descrevem.
- Paleta fixa em `tela/cores.py`; mude pouco e de propósito.
- Nunca versione bancos, backups ou exports (o `.gitignore` bloqueia SQLite e `*.csv`).
- Testes de instalação reais via pipx rodam fora do checkout na CI Windows/Linux;
  dependem de rede só para instalar. Testes unitários continuam sem rede.
- Commits com o e-mail noreply do GitHub.
