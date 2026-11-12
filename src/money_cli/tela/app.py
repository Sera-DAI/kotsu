"""Tela principal: mês, contas, lançamentos e a linha do rodapé (lançar, filtrar, editar)."""

from __future__ import annotations

import datetime as dt
from dataclasses import replace
from enum import Enum
from pathlib import Path

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Input, Static
from textual.widgets.data_table import RowDoesNotExist

from money_cli.armazenamento import preferencias, troca
from money_cli.armazenamento.banco import Banco
from money_cli.dominio import dinheiro, parcelas
from money_cli.dominio.filtro import SEM_FILTRO, Filtro, interpretar_filtro
from money_cli.dominio.linha import ErroDeLinha, LinhaInterpretada, interpretar, montar
from money_cli.dominio.mes import NOMES, Mes
from money_cli.dominio.tipos import Alcance, Categoria, Conta, Lancamento, NovoLancamento, Tipo
from money_cli.dominio.totais import TotaisMes
from money_cli.tela import cores
from money_cli.tela.perguntas import (
    EscolherCor,
    PedirTexto,
    SimOuNao,
    SoEstaOuTodas,
    SoEsteOuProximos,
)
from money_cli.tela.temas import Tema, proximo, tema_por_nome

DICA = "ex.: 89,90 mercado #alimentação @nubank   +3500 salário @itaú   120 geladeira 10x"
DICA_FILTRO = "filtrar: @conta   #categoria   @conta #categoria   ou só o nome"
POR_PAGINA = 200  # lançamentos por página da lista (AGENTS.md: listas paginadas)
MESES_A_FRENTE = 24  # recorrentes só são geradas até hoje + 24 meses (D36)


class Modo(Enum):
    """O que a linha do rodapé faz no Enter."""

    LANCAR = "lançar"
    FILTRAR = "filtrar"
    EDITAR = "editar"


class MoneyApp(App[None]):
    TITLE = "Money CLI"
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    Screen { layout: vertical; }
    #topo { height: auto; padding: 1 2 0 2; }
    #contas { height: auto; max-height: 8; padding: 0 2; margin-top: 1; }
    #lancamentos { height: 1fr; margin: 1 2 0 2; }
    #vazio { height: 1fr; padding: 1 2; color: $text-muted; }
    #linha { margin: 0 1; }
    #previa { height: auto; min-height: 1; padding: 0 2; }
    DataTable { border: round $primary; background: $background; }
    DataTable > .datatable--header { background: $panel; color: $primary; }
    DataTable > .datatable--even-row { background: $surface; }
    DataTable > .datatable--odd-row { background: $background; }
    DataTable > .datatable--cursor { background: $primary; color: $background; }
    Footer { background: $panel; }
    """
    BINDINGS = [
        Binding("left", "mes(-1)", "Mês anterior"),
        Binding("right", "mes(1)", "Mês seguinte"),
        Binding("l", "lancar", "Lançar"),
        Binding("slash", "filtrar", "Filtrar"),
        Binding("e", "editar", "Editar"),
        Binding("c", "copiar", "Copiar"),
        Binding("d", "excluir", "Excluir"),
        Binding("r", "renomear", "Renomear"),
        Binding("m", "mensal", "Todo mês"),
        Binding("b", "backup", "Backup"),
        Binding("t", "tema", "Tema"),
        Binding("v", "conferir", "Conferir"),
        Binding("q", "quit", "Sair"),
    ]

    def __init__(
        self, banco: Banco, hoje: dt.date | None = None, pasta_tema: Path | None = None
    ) -> None:
        super().__init__()
        self.banco = banco
        # `pasta_tema`: onde ler e gravar tema.toml; None (testes) não lê nem grava (D37).
        self._pasta_tema = pasta_tema
        saved = preferencias.ler_tema(pasta_tema) if pasta_tema else None
        self.tema_atual: Tema = tema_por_nome(saved)
        self._usar_cores(self.tema_atual)
        self.hoje = hoje or dt.date.today()
        self.mes = Mes.de(self.hoje)
        self.filtro: Filtro = SEM_FILTRO
        self._filtro_texto = ""  # como o filtro foi digitado, para reabrir com ele
        self._modo = Modo.LANCAR
        self._edicao: tuple[Lancamento, Alcance] | None = None
        self._recado: Text | None = None
        # Estado da lista paginada do mês.
        self._quantidade = 0
        self._carregados = 0
        self._contas: dict[int, Conta] = {}
        self._categorias: dict[int, str] = {}

    def compose(self) -> ComposeResult:
        yield Static(id="topo")
        yield Static(id="contas")
        yield DataTable(id="lancamentos", cursor_type="row", zebra_stripes=True)
        yield Static(id="vazio")
        # Sem selecionar tudo ao focar: copiar e editar abrem a linha preenchida.
        yield Input(placeholder=DICA, id="linha", select_on_focus=False)
        yield Static(id="previa")
        yield Footer()

    def _usar_cores(self, tema: Tema) -> None:
        cores.aplicar(tema.receita, tema.despesa, tema.neutro)

    def action_tema(self) -> None:
        """Alterna entre os temas e lembra a escolha em tema.toml (D37)."""
        self.tema_atual = proximo(self.tema_atual)
        self._usar_cores(self.tema_atual)
        self.theme = self.tema_atual.nome
        self.atualizar()
        gravou = True
        if self._pasta_tema is not None:
            gravou = preferencias.gravar_tema(self._pasta_tema, self.tema_atual.nome)
        if gravou:
            self.notify(self.tema_atual.rotulo, timeout=3)
        else:
            self.notify(
                f"{self.tema_atual.rotulo} (não foi possível lembrar a escolha)",
                severity="warning",
            )

    def on_mount(self) -> None:
        for tema in (self.tema_atual, proximo(self.tema_atual)):
            self.register_theme(tema.para_textual())
        self.theme = self.tema_atual.nome
        tabela = self.query_one("#lancamentos", DataTable)
        tabela.add_columns("Data", "Descrição", "Categoria", "Conta", "Valor")
        self.query_one("#linha", Input).display = False
        self.atualizar()

    def action_backup(self) -> None:
        """Backup manual: uma cópia nova a cada pedido, na pasta `backups/`."""
        try:
            destino = self.banco.backup_manual()
        except OSError:
            self.notify(
                "Não foi possível fazer o backup. Confira a pasta de dados.",
                severity="warning",
                timeout=10,
            )
            return
        if destino is None:
            self.notify("Banco em memória: não há arquivo para copiar.", severity="warning")
        else:
            self.notify(f"Backup salvo em {destino}", timeout=8)

    def action_conferir(self) -> None:
        """Mostra o código de conferência: igual ao do outro aparelho = mesmos dados (D39)."""
        self.notify(f"Código de conferência: {troca.codigo(self.banco)}", timeout=15)

    # --- navegação e desenho -------------------------------------------------

    def action_mes(self, passo: int) -> None:
        self.mes = self.mes.somar(passo)
        self.atualizar(topo=True)

    def atualizar(self, manter: int | None = None, topo: bool = False) -> None:
        """Redesenha tudo a partir do banco.

        O cursor volta para o lançamento `manter` (padrão: o selecionado agora); se ele saiu
        do mês ou do filtro, fica no vizinho. `topo=True` (outro mês, outro filtro) começa
        do primeiro.
        """
        self.banco.estender_recorrencias(min(self.mes, Mes.de(self.hoje).somar(MESES_A_FRENTE)))
        tabela = self.query_one("#lancamentos", DataTable)
        linha_antes = 0 if topo or not tabela.row_count else tabela.cursor_row
        carregados_antes = 0 if topo else self._carregados
        if manter is None and not topo:
            manter = self.selecionado_id()

        contas = self.banco.listar_contas()
        self._contas = {c.id: c for c in contas}
        self._categorias = {c.id: c.nome for c in self.banco.listar_categorias()}

        totais = self.banco.totais_do_mes(self.mes, self.filtro)
        self._quantidade = totais.quantidade
        self.query_one("#topo", Static).update(self.texto_topo(totais))
        self.query_one("#contas", Static).update(self.texto_contas(contas))

        tabela.clear()
        self._carregados = 0
        self.carregar_mais(tabela)
        # Recarrega as páginas que já estavam abertas, para o cursor não pular ao topo.
        while self._carregados < min(carregados_antes, self._quantidade):
            self.carregar_mais(tabela)
        if tabela.row_count:
            alvo = min(linha_antes, tabela.row_count - 1)
            if manter is not None:
                try:
                    alvo = tabela.get_row_index(str(manter))
                except RowDoesNotExist:  # saiu do mês ou do filtro: fica no vizinho
                    pass
            tabela.move_cursor(row=alvo, animate=False)

        vazio = self._quantidade == 0
        tabela.display = not vazio
        aviso = self.query_one("#vazio", Static)
        aviso.display = vazio
        if self.filtro.ativo:
            aviso.update("Nada neste mês com esse filtro. Esc tira o filtro.")
        else:
            aviso.update("Nenhum lançamento neste mês. Tecle l para lançar.")

    def texto_topo(self, totais: TotaisMes) -> Text:
        tema = self.tema_atual
        quantidade = totais.quantidade
        rosto = tema.feliz if totais.saldo >= 0 else tema.triste
        topo = Text.assemble(
            (rosto, tema.aviso),
            "  ",
            (f" {self.mes.nome.capitalize()} ", f"bold {tema.fundo} on {tema.destaque}"),
            (f"   {quantidade} lançamento{'' if quantidade == 1 else 's'}", cores.NEUTRO),
            ("\n", ""),
            ("♡ receitas ", tema.secundaria),
            (dinheiro.formatar(totais.receitas), f"bold {cores.RECEITA}"),
            ("   ✧ despesas ", tema.secundaria),
            (dinheiro.formatar(totais.despesas), f"bold {cores.DESPESA}"),
            ("   ☆ saldo ", tema.secundaria),
            (dinheiro.formatar(totais.saldo), f"bold {cores.do_saldo(totais.saldo)}"),
        )
        if self.filtro.ativo:  # segunda linha do topo, para não quebrar a primeira
            topo.append("\nfiltro: ", style=cores.NEUTRO)
            topo.append_text(self.rotulo_filtro(self.filtro))
            topo.append("   (Esc tira)", style=cores.NEUTRO)
        return topo

    def texto_contas(self, contas: list[Conta]) -> Text:
        """Uma linha por conta, na cor dela; sem lançamento no mês, "zerada" (D9, D29)."""
        if not contas:
            return Text("Sem contas ainda.", style=cores.NEUTRO)
        por_conta = self.banco.totais_por_conta(self.mes, self.filtro)
        if self.filtro.conta_id is not None:  # filtro por conta: só ela
            contas = [c for c in contas if c.id == self.filtro.conta_id]
        largura = max(len(c.nome) for c in contas)
        maior = max((x.despesas for x in por_conta.values()), default=0)
        linhas = []
        for conta in contas:
            tema = self.tema_atual
            texto = Text.assemble(
                (f"{tema.marcador} ", conta.cor), (conta.nome.ljust(largura), f"bold {conta.cor}")
            )
            t = por_conta.get(conta.id)
            if t is None:
                texto.append(f"   {tema.zerada}", style=cores.NEUTRO)
            else:
                cheias = round(10 * t.despesas / maior) if maior else 0
                texto.append("   " + tema.barra_cheia * cheias, style=conta.cor)
                texto.append(tema.barra_vazia * (10 - cheias), style=cores.NEUTRO)
                texto.append("   receitas ")
                texto.append(dinheiro.formatar(t.receitas).rjust(12), style=cores.RECEITA)
                texto.append("   despesas ")
                texto.append(dinheiro.formatar(t.despesas).rjust(12), style=cores.DESPESA)
            linhas.append(texto)
        return Text("\n").join(linhas)

    def carregar_mais(self, tabela: DataTable) -> None:
        """Acrescenta a próxima página do mês na lista."""
        pagina = self.banco.lancamentos_do_mes(self.mes, POR_PAGINA, self._carregados, self.filtro)
        for item in pagina:
            conta = self._contas.get(item.conta_id)
            descricao = item.descricao
            if item.parcela:
                descricao = f"{descricao} {item.parcela.rotulo}"
            elif item.grupo_recorrencia:
                descricao = f"{descricao} ↻"
            tabela.add_row(
                item.data.strftime("%d/%m"),
                descricao,
                self._categorias.get(item.categoria_id, ""),
                Text(conta.nome, style=conta.cor) if conta else "",
                Text(
                    dinheiro.formatar(item.valor),
                    style=cores.do_saldo(item.valor_com_sinal),
                    justify="right",
                ),
                key=str(item.id),
            )
        self._carregados += len(pagina)

    def on_data_table_row_highlighted(self, evento: DataTable.RowHighlighted) -> None:
        tabela = evento.data_table
        if evento.cursor_row >= tabela.row_count - 1 and self._carregados < self._quantidade:
            self.carregar_mais(tabela)

    # --- linha do rodapé -----------------------------------------------------

    def abrir_linha(self, modo: Modo, texto: str = "") -> None:
        self._modo = modo
        self.refresh_bindings()
        campo = self.query_one("#linha", Input)
        campo.placeholder = DICA_FILTRO if modo is Modo.FILTRAR else DICA
        campo.value = texto
        campo.cursor_position = len(texto)
        campo.display = True
        campo.focus()
        self._recado = None
        self.mostrar_previa(texto)

    def fechar_linha(self) -> None:
        campo = self.query_one("#linha", Input)
        campo.value = ""
        campo.display = False
        self._modo = Modo.LANCAR
        self._edicao = None
        self._recado = None
        self.query_one("#previa", Static).update("")
        self.query_one("#lancamentos", DataTable).focus()
        self.refresh_bindings()

    def action_lancar(self) -> None:
        self.abrir_linha(Modo.LANCAR)

    def action_filtrar(self) -> None:
        self.abrir_linha(Modo.FILTRAR, self._filtro_texto)

    def action_copiar(self) -> None:
        """Linha preenchida com o selecionado, sem data e sem parcelas (D27)."""
        item = self.selecionado()
        if item is not None:
            self.abrir_linha(Modo.LANCAR, self.linha_de(item, com_data=False))

    @work(exclusive=True)
    async def action_editar(self) -> None:
        """Linha preenchida com o lançamento inteiro; Enter altera o mesmo (D28)."""
        item = self.selecionado()
        if item is None:
            return
        alcance = await self.perguntar_alcance(item, "Editar", Alcance.SO_ESTA)
        if alcance is None:
            return
        self._edicao = (item, alcance)
        texto = self.linha_de(item, com_data=not _todas(item, alcance))
        self.abrir_linha(Modo.EDITAR, texto)

    async def perguntar_alcance(
        self, item: Lancamento, acao: str, padrao: Alcance
    ) -> Alcance | None:
        """ "Só esta ou todas?" nas parcelas (D12); "só este mês ou os próximos?" nas
        recorrentes (D36). Lançamento comum não pergunta e devolve `padrao`."""
        if item.parcela:
            return await self.push_screen_wait(SoEstaOuTodas(acao, item.parcela.rotulo))
        if item.grupo_recorrencia:
            return await self.push_screen_wait(SoEsteOuProximos(acao))
        return padrao

    def linha_de(self, item: Lancamento, com_data: bool) -> str:
        return montar(
            item.valor,
            item.tipo,
            item.descricao,
            self._contas[item.conta_id].nome,
            self._categorias.get(item.categoria_id),
            item.data if com_data else None,
        )

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        # Com a linha aberta, "/" é texto (datas como 15/10): esconde "Filtrar" do rodapé.
        if action == "filtrar" and self.focused is self.query_one("#linha", Input):
            return False
        return True

    def on_key(self, evento) -> None:
        if evento.key != "escape":
            return
        if self.focused is self.query_one("#linha", Input):
            evento.stop()
            self.fechar_linha()
        elif self.filtro.ativo and len(self.screen_stack) == 1:
            evento.stop()
            self.definir_filtro(SEM_FILTRO, "")

    def on_input_changed(self, evento: Input.Changed) -> None:
        if evento.input.id == "linha":
            self.mostrar_previa(evento.value)

    def on_input_submitted(self, evento: Input.Submitted) -> None:
        if evento.input.id != "linha":
            return
        if self._modo is Modo.FILTRAR:
            self.aplicar_filtro(evento.value)
        elif self._modo is Modo.EDITAR:
            self.salvar_edicao(evento.value)
        else:
            self.salvar_linha(evento.value)

    def mostrar_previa(self, texto: str) -> None:
        if not self.query_one("#linha", Input).display:
            return  # linha fechada: a prévia guarda o último recado ("editado: ...")
        previa = self.query_one("#previa", Static)
        if self._modo is Modo.FILTRAR:
            previa.update(self.previa_filtro(texto))
            return
        if not texto.strip():
            # Depois de salvar, a linha fica vazia mas o recado "salvo: ..." continua.
            previa.update(self._recado or Text(DICA, style=cores.NEUTRO))
            return
        self._recado = None
        try:
            linha = interpretar(texto, self.hoje)
            if self._modo is Modo.EDITAR:
                self.conferir_edicao(linha)
        except ErroDeLinha as erro:
            previa.update(Text(str(erro), style=cores.DESPESA))
            return
        if self._modo is Modo.EDITAR:
            previa.update(Text.assemble(("editar: ", cores.NEUTRO), self.texto_previa(linha)))
        else:
            previa.update(self.texto_previa(linha))

    def texto_previa(self, linha: LinhaInterpretada) -> Text:
        cor_valor = cores.RECEITA if linha.tipo is Tipo.RECEITA else cores.DESPESA
        partes: list[Text] = [
            Text.assemble((linha.tipo.value, cor_valor), " ", (_valor(linha), f"bold {cor_valor}"))
        ]
        if linha.descricao:
            partes.append(Text(linha.descricao, style="bold"))
        if linha.categoria:
            existe = self.banco.categoria_por_nome(linha.categoria)
            nome = existe.nome if existe else linha.categoria
            partes.append(Text(f"#{nome}" + ("" if existe else " (nova)")))
        conta = self.banco.conta_por_nome(linha.conta) if linha.conta else None
        if conta:
            partes.append(Text(f"@{conta.nome}", style=f"bold {conta.cor}"))
        elif linha.conta:
            partes.append(Text(f"@{linha.conta} (nova)", style="bold"))
        else:
            partes.append(Text("falta @conta", style=cores.DESPESA))
        partes.append(Text(self.periodo(linha), style=cores.NEUTRO))
        return Text(" · ").join(partes)

    def periodo(self, linha: LinhaInterpretada) -> str:
        if self._modo is Modo.EDITAR and self._edicao and _todas(*self._edicao):
            item, alcance = self._edicao
            if alcance is Alcance.PROXIMAS:
                return "este mês e os próximos, datas mantidas"
            return f"todas as {item.parcela.total} parcelas, datas mantidas"
        if (
            self._modo is Modo.LANCAR
            and linha.parcelas == 1
            and self.categoria_recorrente(linha.categoria)
        ):
            return f"{linha.data.strftime('%d/%m/%Y')}, e todo mês"
        return _periodo(linha)

    def categoria_recorrente(self, nome: str | None) -> bool:
        categoria = self.banco.categoria_por_nome(nome) if nome else None
        return categoria is not None and categoria.recorrente

    async def resolver_nomes(self, linha: LinhaInterpretada) -> tuple[Conta, int | None] | None:
        """Conta (obrigatória, D21/D22) e categoria da linha; cria as novas perguntando.

        Devolve None se faltou a conta ou a pessoa cancelou; a prévia já diz o motivo.
        """
        previa = self.query_one("#previa", Static)
        if not linha.conta:
            previa.update(Text("informe a conta com @nome", style=cores.DESPESA))
            return None
        conta = self.banco.conta_por_nome(linha.conta)
        if conta is None:
            cor = await self.push_screen_wait(EscolherCor(linha.conta, self.cor_sugerida()))
            if cor is None:
                previa.update(Text("cancelado: nada foi salvo", style=cores.NEUTRO))
                return None
            conta = self.banco.criar_conta(linha.conta, cor)

        categoria: Categoria | None = None
        if linha.categoria:
            categoria = self.banco.categoria_por_nome(linha.categoria)
            if categoria is None:
                criar = await self.push_screen_wait(
                    SimOuNao(f"Criar a categoria {linha.categoria}?")
                )
                if not criar:
                    previa.update(Text("cancelado: nada foi salvo", style=cores.NEUTRO))
                    self.atualizar()  # a conta pode ter sido criada
                    return None
                repetir = await self.push_screen_wait(
                    SimOuNao(
                        f"Repetir todo mês os lançamentos de {linha.categoria}?",
                        "Aluguel, internet, salário... Enter = sim   Esc = não",
                    )
                )
                categoria = self.banco.criar_categoria(linha.categoria, bool(repetir))
        return conta, categoria.id if categoria else None

    @work(exclusive=True)
    async def salvar_linha(self, texto: str) -> None:
        previa = self.query_one("#previa", Static)
        try:
            linha = interpretar(texto, self.hoje)
        except ErroDeLinha as erro:
            previa.update(Text(str(erro), style=cores.DESPESA))
            return
        nomes = await self.resolver_nomes(linha)
        if nomes is None:
            return
        conta, categoria_id = nomes

        recorrente = categoria_id is not None and any(
            c.id == categoria_id and c.recorrente for c in self.banco.listar_categorias()
        )
        if recorrente and linha.parcelas > 1:
            previa.update(
                Text(
                    f"#{linha.categoria} já repete todo mês: tire o {linha.parcelas}x",
                    style=cores.DESPESA,
                )
            )
            return
        grupo = self.banco.novo_grupo_parcela() if linha.parcelas > 1 else None
        novos = parcelas.gerar(linha, conta.id, categoria_id, grupo)
        if recorrente:
            novos = [replace(novos[0], grupo_recorrencia=self.banco.novo_grupo_parcela())]
        ids = self.banco.inserir_lancamentos(novos)

        self._recado = Text.assemble(
            ("salvo: ", cores.NEUTRO), self.texto_previa_salva(linha, conta)
        )
        self.query_one("#linha", Input).value = ""
        self.atualizar(manter=ids[0])
        previa.update(self._recado)

    def texto_previa_salva(self, linha: LinhaInterpretada, conta: Conta) -> Text:
        cor_valor = cores.RECEITA if linha.tipo is Tipo.RECEITA else cores.DESPESA
        return Text(" · ").join(
            [
                Text(_valor(linha), style=f"bold {cor_valor}"),
                Text(linha.descricao or "(sem descrição)"),
                Text(f"@{conta.nome}", style=f"bold {conta.cor}"),
                Text(self.periodo(linha), style=cores.NEUTRO),
            ]
        )

    def cor_sugerida(self) -> str:
        usadas = {c.cor for c in self.banco.listar_contas()}
        livres = [c for c in cores.CONTAS if c not in usadas]
        return livres[0] if livres else cores.CONTAS[len(usadas) % len(cores.CONTAS)]

    # --- editar (D28) --------------------------------------------------------

    def conferir_edicao(self, linha: LinhaInterpretada) -> None:
        if linha.parcelas > 1:
            raise ErroDeLinha("o número de parcelas não muda ao editar")
        if self._edicao and _todas(*self._edicao) and linha.com_data:
            raise ErroDeLinha("a data muda só em um lançamento: edite com 'só esta'")

    @work(exclusive=True)
    async def salvar_edicao(self, texto: str) -> None:
        if self._edicao is None:
            return
        item, alcance = self._edicao
        previa = self.query_one("#previa", Static)
        try:
            linha = interpretar(texto, self.hoje)
            self.conferir_edicao(linha)
        except ErroDeLinha as erro:
            previa.update(Text(str(erro), style=cores.DESPESA))
            return
        nomes = await self.resolver_nomes(linha)
        if nomes is None:
            return
        conta, categoria_id = nomes
        novo = NovoLancamento(
            linha.data, linha.descricao, linha.valor, linha.tipo, conta.id, categoria_id
        )
        recado = Text.assemble(("editado: ", cores.NEUTRO), self.texto_previa_salva(linha, conta))
        quantos = self.banco.editar(item.id, novo, alcance)
        self.fechar_linha()
        self.atualizar(manter=item.id)
        if quantos > 1:
            recado.append(f" ({quantos} parcelas)", style=cores.NEUTRO)
        self.query_one("#previa", Static).update(recado)

    # --- filtro (D12, D26) ---------------------------------------------------

    def resolver_filtro(self, texto: str) -> Filtro:
        """Texto do `/` em ids. Levanta `ErroDeLinha` com a mensagem para a prévia."""
        digitado = interpretar_filtro(texto)
        conta = categoria = None
        if digitado.qualquer is not None:
            nome = digitado.qualquer
            conta = self.banco.conta_por_nome(nome)
            categoria = self.banco.categoria_por_nome(nome)
            if conta and categoria:
                raise ErroDeLinha(f"há conta e categoria {nome}: use @{nome} ou #{nome}")
            if not conta and not categoria:
                raise ErroDeLinha(f"não há conta nem categoria {nome}")
        if digitado.conta is not None:
            conta = self.banco.conta_por_nome(digitado.conta)
            if conta is None:
                raise ErroDeLinha(f"não há a conta {digitado.conta}")
        if digitado.categoria is not None:
            categoria = self.banco.categoria_por_nome(digitado.categoria)
            if categoria is None:
                raise ErroDeLinha(f"não há a categoria {digitado.categoria}")
        return Filtro(conta.id if conta else None, categoria.id if categoria else None)

    def rotulo_filtro(self, filtro: Filtro) -> Text:
        partes = []
        if filtro.conta_id is not None:
            conta = self._contas[filtro.conta_id]
            partes.append(Text(f"@{conta.nome}", style=f"bold {conta.cor}"))
        if filtro.categoria_id is not None:
            nome = self._categorias[filtro.categoria_id]
            partes.append(Text(f"#{nome}", style="bold"))
        return Text(" ").join(partes)

    def previa_filtro(self, texto: str) -> Text:
        if not texto.strip():
            if self.filtro.ativo:
                return Text("Enter tira o filtro", style=cores.NEUTRO)
            return Text(DICA_FILTRO, style=cores.NEUTRO)
        try:
            filtro = self.resolver_filtro(texto)
        except ErroDeLinha as erro:
            return Text(str(erro), style=cores.DESPESA)
        return Text.assemble(("mostrar só ", cores.NEUTRO), self.rotulo_filtro(filtro))

    def aplicar_filtro(self, texto: str) -> None:
        try:
            filtro = self.resolver_filtro(texto) if texto.strip() else SEM_FILTRO
        except ErroDeLinha as erro:
            self.query_one("#previa", Static).update(Text(str(erro), style=cores.DESPESA))
            return
        self.fechar_linha()
        self.definir_filtro(filtro, texto.strip() if filtro.ativo else "")

    def definir_filtro(self, filtro: Filtro, texto: str) -> None:
        self.filtro = filtro
        self._filtro_texto = texto
        self.atualizar(topo=True)

    # --- selecionar, excluir e renomear (D12) --------------------------------

    def selecionado_id(self) -> int | None:
        tabela = self.query_one("#lancamentos", DataTable)
        if tabela.row_count == 0:
            return None
        chave = tabela.coordinate_to_cell_key(tabela.cursor_coordinate).row_key
        return int(chave.value)

    def selecionado(self) -> Lancamento | None:
        tabela = self.query_one("#lancamentos", DataTable)
        if not tabela.display:
            return None
        id_ = self.selecionado_id()
        return self.banco.lancamento(id_) if id_ is not None else None

    @work(exclusive=True)
    async def action_excluir(self) -> None:
        item = self.selecionado()
        if item is None:
            return
        if item.parcela or item.grupo_recorrencia:
            alcance = await self.perguntar_alcance(item, "Excluir", Alcance.SO_ESTA)
        else:
            ok = await self.push_screen_wait(
                SimOuNao(f"Excluir {item.descricao or 'o lançamento'}?")
            )
            alcance = Alcance.SO_ESTA if ok else None
        if alcance is None:
            return
        self.banco.excluir(item.id, alcance)
        self.atualizar()  # o excluído some; o cursor fica no vizinho

    @work(exclusive=True)
    async def action_mensal(self) -> None:
        """Liga ou desliga "todo mês" na categoria do selecionado (D36).

        Ligar vale para os próximos lançamentos da categoria e já faz do selecionado o
        começo da série. Desligar não mexe nas séries em andamento.
        """
        item = self.selecionado()
        if item is None:
            return
        if item.categoria_id is None:
            self.notify("Este lançamento não tem categoria (#nome).", severity="warning")
            return
        nome = self._categorias[item.categoria_id]
        categoria = self.banco.categoria_por_nome(nome)
        if categoria.recorrente:
            ok = await self.push_screen_wait(
                SimOuNao(
                    f"Parar de marcar #{nome} como todo mês?",
                    "Lançamentos novos não repetem. Os que já repetem continuam"
                    " até você excluir (d).",
                )
            )
            if ok:
                self.banco.definir_recorrente(categoria.id, False)
                self.notify(f"#{nome} deixou de repetir em lançamentos novos.")
        else:
            ok = await self.push_screen_wait(
                SimOuNao(
                    f"Repetir todo mês os lançamentos de #{nome}?",
                    "Este lançamento vira o começo da repetição." if not item.parcela else "",
                )
            )
            if ok:
                self.banco.definir_recorrente(categoria.id, True)
                self.banco.tornar_recorrente(item.id)
        self.atualizar(manter=item.id)

    @work(exclusive=True)
    async def action_renomear(self) -> None:
        item = self.selecionado()
        if item is None:
            return
        alcance = await self.perguntar_alcance(item, "Renomear", Alcance.SO_ESTA)
        if alcance is None:
            return
        nova = await self.push_screen_wait(PedirTexto("Nova descrição", item.descricao))
        if nova is None:
            return
        self.banco.renomear(item.id, nova, alcance)
        self.atualizar(manter=item.id)


def _todas(item: Lancamento, alcance: Alcance) -> bool:
    """Alcance maior que um lançamento: todas as parcelas ou os próximos meses."""
    if alcance is Alcance.PROXIMAS:
        return item.grupo_recorrencia is not None
    return item.parcela is not None and alcance is Alcance.TODAS


def _valor(linha: LinhaInterpretada) -> str:
    if linha.parcelas == 1:
        return dinheiro.formatar(linha.valor)
    return (
        f"{linha.parcelas}x de {dinheiro.formatar(linha.valor)} = {dinheiro.formatar(linha.total)}"
    )


def _mes_curto(data: dt.date) -> str:
    return f"{NOMES[data.month - 1][:3]}/{data.year}"


def _periodo(linha: LinhaInterpretada) -> str:
    if linha.parcelas == 1:
        return linha.data.strftime("%d/%m/%Y")
    ultima = parcelas.data_da_parcela(linha.data, linha.parcelas - 1)
    return f"{_mes_curto(linha.data)} a {_mes_curto(ultima)}"
