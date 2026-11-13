"""Modal questions on the screen. Each returns the answer, or None on Esc.

The single-letter keys from the Portuguese versions (s, t, p) still work next to the English
ones, so old habits are not broken.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from kotsu.domain.models import Scope
from kotsu.ui import colors

_CSS = """
Question { align: center middle; }
Question > Vertical {
    width: 64; height: auto; padding: 1 2;
    border: round $accent; background: $surface;
}
Question .hint { color: $text-muted; margin-top: 1; }
"""


class Question(ModalScreen):
    DEFAULT_CSS = _CSS
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str | Text, body: str | Text = "", hint: str = "") -> None:
        super().__init__()
        self.title_text, self.body, self.hint = title, body, hint

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self.title_text, classes="title")
            if self.body:
                yield Static(self.body, classes="body")
            yield from self.extras()
            if self.hint:
                yield Static(self.hint, classes="hint")

    def extras(self) -> ComposeResult:
        yield from ()

    def action_cancel(self) -> None:
        self.dismiss(None)


class YesOrNo(Question):
    """Enter or y = yes; Esc or n = no (returns None)."""

    BINDINGS = [
        Binding("enter,y,s", "yes", "Yes"),
        Binding("n", "cancel", "No"),
    ]

    def __init__(self, title: str | Text, body: str | Text = "") -> None:
        super().__init__(title, body, "Enter = yes   Esc = no")

    def action_yes(self) -> None:
        self.dismiss(True)


class PickColor(Question):
    """Create an account (D3, D11): 1 to 8 pick the color; Enter uses the suggested one."""

    BINDINGS = [
        Binding("enter", "color(-1)", "Suggested"),
        *(Binding(str(i + 1), f"color({i})", show=False) for i in range(len(colors.ACCOUNTS))),
    ]

    def __init__(self, name: str, suggested: str) -> None:
        swatches = Text()
        for i, color in enumerate(colors.ACCOUNTS):
            mark = "▸" if color == suggested else " "
            swatches.append(f"{mark}{i + 1} ", style="bold" if color == suggested else "")
            swatches.append("██ ", style=color)
        title = Text.assemble("Create the account ", (name, f"bold {suggested}"), "?")
        super().__init__(title, swatches, "1–8 = color   Enter = marked color   Esc = don't create")
        self.suggested = suggested

    def action_color(self, index: int) -> None:
        self.dismiss(self.suggested if index < 0 else colors.ACCOUNTS[index])


class OnlyThisOrAll(Question):
    """The installment question (D12). Enter = all (default)."""

    BINDINGS = [
        Binding("enter,a,t", "all", "All"),
        Binding("o,s", "only_this", "Only this"),
    ]

    def __init__(self, action: str, label: str) -> None:
        super().__init__(
            f"{action} installment {label}: only this one or all?",
            hint="Enter or a = all   o = only this   Esc = cancel",
        )

    def action_all(self) -> None:
        self.dismiss(Scope.ALL)

    def action_only_this(self) -> None:
        self.dismiss(Scope.ONLY_THIS)


class OnlyThisOrUpcoming(Question):
    """The recurring-entry question (D36). Enter = only this month (the safest)."""

    BINDINGS = [
        Binding("enter,o,s", "only_this", "Only this month"),
        Binding("u,p", "upcoming", "This and upcoming"),
    ]

    def __init__(self, action: str) -> None:
        super().__init__(
            f"{action} the entry that repeats every month: only this month or the upcoming ones?",
            hint="Enter or o = only this month   u = this and upcoming   Esc = cancel",
        )

    def action_only_this(self) -> None:
        self.dismiss(Scope.ONLY_THIS)

    def action_upcoming(self) -> None:
        self.dismiss(Scope.UPCOMING)


class AskText(Question):
    """Pre-filled text field. Enter confirms; Esc cancels."""

    def __init__(self, title: str, value: str) -> None:
        super().__init__(title, hint="Enter = save   Esc = cancel")
        self.value = value

    def extras(self) -> ComposeResult:
        yield Input(self.value, id="text")

    def on_mount(self) -> None:
        self.query_one("#text", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        text = event.value.strip()
        self.dismiss(text or None)
