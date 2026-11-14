"""Formatting of amounts in integer cents."""


def format_cents(cents: int) -> str:
    """Formats cents as BRL without a sign: 123456 -> '1.234,56'.

    The sign never shows in the text: negatives are shown only in red by the UI.
    """
    reais, rest = divmod(abs(cents), 100)
    return f"{reais:,}".replace(",", ".") + f",{rest:02d}"
