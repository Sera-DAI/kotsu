"""Formatação de valores em centavos inteiros."""


def formatar(centavos: int) -> str:
    """Formata centavos como BRL sem sinal: 123456 -> '1.234,56'.

    O sinal nunca aparece no texto: negativo é mostrado só em vermelho pela tela.
    """
    reais, cents = divmod(abs(centavos), 100)
    return f"{reais:,}".replace(",", ".") + f",{cents:02d}"
