"""Paleta fixa do app. Mudanças aqui são poucas e de propósito (boas práticas)."""

# Cores de valor e de texto apagado; mudam com o tema (`aplicar`, D37).
RECEITA = "#4ec27a"
DESPESA = "#e5534b"
NEUTRO = "#8b949e"


def aplicar(receita: str, despesa: str, neutro: str) -> None:
    """Troca as cores de valor para as do tema atual."""
    global RECEITA, DESPESA, NEUTRO
    RECEITA, DESPESA, NEUTRO = receita, despesa, neutro


# Cores oferecidas ao criar uma conta (D3). Legíveis em fundo escuro
# no Windows Terminal e em terminais Linux com truecolor.
CONTAS = (
    "#8a2be2",  # roxo
    "#ff7a00",  # laranja
    "#1f8fff",  # azul
    "#e8c547",  # amarelo
    "#2ec4b6",  # ciano
    "#ff5fa2",  # rosa
    "#9bd34a",  # verde-limão
    "#c0c0c0",  # prata
)


def do_saldo(centavos: int) -> str:
    """Negativo aparece só em vermelho, sem o sinal."""
    return DESPESA if centavos < 0 else RECEITA
