"""Perguntas modais da tela. Cada uma devolve a resposta, ou None no Esc."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from money_cli.dominio.tipos import Alcance
from money_cli.tela import cores

_CSS = """
Pergunta { align: center middle; }
Pergunta > Vertical {
    width: 64; height: auto; padding: 1 2;
    border: round $accent; background: $surface;
}
Pergunta .dica { color: $text-muted; margin-top: 1; }
"""


class Pergunta(ModalScreen):
    DEFAULT_CSS = _CSS
    BINDINGS = [Binding("escape", "cancelar", "Cancelar")]

    def __init__(self, titulo: str | Text, corpo: str | Text = "", dica: str = "") -> None:
        super().__init__()
        self.titulo, self.corpo, self.dica = titulo, corpo, dica

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self.titulo, classes="titulo")
            if self.corpo:
                yield Static(self.corpo, classes="corpo")
            yield from self.extras()
            if self.dica:
                yield Static(self.dica, classes="dica")

    def extras(self) -> ComposeResult:
        yield from ()

    def action_cancelar(self) -> None:
        self.dismiss(None)


class SimOuNao(Pergunta):
    """Enter ou s = sim; Esc ou n = não (devolve None)."""

    BINDINGS = [
        Binding("enter,s", "sim", "Sim"),
        Binding("n", "cancelar", "Não"),
    ]

    def __init__(self, titulo: str | Text, corpo: str | Text = "") -> None:
        super().__init__(titulo, corpo, "Enter = sim   Esc = não")

    def action_sim(self) -> None:
        self.dismiss(True)


class EscolherCor(Pergunta):
    """Criar conta (D3, D11): 1 a 8 escolhem a cor; Enter usa a sugerida."""

    BINDINGS = [
        Binding("enter", "cor(-1)", "Sugerida"),
        *(Binding(str(i + 1), f"cor({i})", show=False) for i in range(len(cores.CONTAS))),
    ]

    def __init__(self, nome: str, sugerida: str) -> None:
        amostras = Text()
        for i, cor in enumerate(cores.CONTAS):
            marca = "▸" if cor == sugerida else " "
            amostras.append(f"{marca}{i + 1} ", style="bold" if cor == sugerida else "")
            amostras.append("██ ", style=cor)
        titulo = Text.assemble("Criar a conta ", (nome, f"bold {sugerida}"), "?")
        super().__init__(titulo, amostras, "1–8 = cor   Enter = cor marcada   Esc = não criar")
        self.sugerida = sugerida

    def action_cor(self, indice: int) -> None:
        self.dismiss(self.sugerida if indice < 0 else cores.CONTAS[indice])


class SoEstaOuTodas(Pergunta):
    """Pergunta da parcela (D12). Enter = todas (padrão)."""

    BINDINGS = [
        Binding("enter,t", "todas", "Todas"),
        Binding("s", "so_esta", "Só esta"),
    ]

    def __init__(self, acao: str, rotulo: str) -> None:
        super().__init__(
            f"{acao} a parcela {rotulo}: só esta ou todas?",
            dica="Enter ou t = todas   s = só esta   Esc = cancelar",
        )

    def action_todas(self) -> None:
        self.dismiss(Alcance.TODAS)

    def action_so_esta(self) -> None:
        self.dismiss(Alcance.SO_ESTA)


class SoEsteOuProximos(Pergunta):
    """Pergunta do lançamento recorrente (D36). Enter = só este mês (o mais seguro)."""

    BINDINGS = [
        Binding("enter,s", "so_este", "Só este mês"),
        Binding("p", "proximos", "Este e os próximos"),
    ]

    def __init__(self, acao: str) -> None:
        super().__init__(
            f"{acao} o lançamento que se repete todo mês: só este mês ou os próximos?",
            dica="Enter ou s = só este mês   p = este e os próximos   Esc = cancelar",
        )

    def action_so_este(self) -> None:
        self.dismiss(Alcance.SO_ESTA)

    def action_proximos(self) -> None:
        self.dismiss(Alcance.PROXIMAS)


class PedirTexto(Pergunta):
    """Campo de texto já preenchido. Enter confirma; Esc cancela."""

    def __init__(self, titulo: str, valor: str) -> None:
        super().__init__(titulo, dica="Enter = salvar   Esc = cancelar")
        self.valor = valor

    def extras(self) -> ComposeResult:
        yield Input(self.valor, id="texto")

    def on_mount(self) -> None:
        self.query_one("#texto", Input).focus()

    def on_input_submitted(self, evento: Input.Submitted) -> None:
        evento.stop()
        texto = evento.value.strip()
        self.dismiss(texto or None)
