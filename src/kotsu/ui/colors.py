"""The app's fixed palette. Changes here are few and deliberate (best practices)."""

# Amount colors and muted text; they change with the theme (`apply`, D37).
INCOME = "#4ec27a"
EXPENSE = "#e5534b"
NEUTRAL = "#8b949e"


def apply(income: str, expense: str, neutral: str) -> None:
    """Switches the amount colors to the current theme's."""
    global INCOME, EXPENSE, NEUTRAL
    INCOME, EXPENSE, NEUTRAL = income, expense, neutral


# Colors offered when creating an account (D3). Readable on a dark background
# in Windows Terminal and in Linux terminals with truecolor.
ACCOUNTS = (
    "#8a2be2",  # purple
    "#ff7a00",  # orange
    "#1f8fff",  # blue
    "#e8c547",  # yellow
    "#2ec4b6",  # cyan
    "#ff5fa2",  # pink
    "#9bd34a",  # lime green
    "#c0c0c0",  # silver
)


def of_balance(cents: int) -> str:
    """A negative shows only in red, without the sign."""
    return EXPENSE if cents < 0 else INCOME
