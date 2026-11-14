"""Main screen: month, accounts, entries and the footer line (add, filter, edit)."""

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

from kotsu.domain import currency, installments
from kotsu.domain.filter import NO_FILTER, Filter, parse_filter
from kotsu.domain.line import LineError, ParsedLine, build, parse
from kotsu.domain.models import Account, Category, Entry, Kind, NewEntry, Scope
from kotsu.domain.month import NAMES, Month
from kotsu.domain.totals import MonthTotals
from kotsu.storage import exchange, preferences
from kotsu.storage.database import Database
from kotsu.ui import colors
from kotsu.ui.dialogs import (
    AskText,
    OnlyThisOrAll,
    OnlyThisOrUpcoming,
    PickColor,
    YesOrNo,
)
from kotsu.ui.themes import Theme, next_theme, theme_by_name

HINT = "e.g. 89,90 groceries #food @nubank   +3500 salary @itau   120 fridge 10x"
FILTER_HINT = "filter: @account   #category   @account #category   or just the name"
PAGE_SIZE = 200  # entries per page of the list (AGENTS.md: paginated lists)
MONTHS_AHEAD = 24  # recurring entries are only generated up to today + 24 months (D36)


class Mode(Enum):
    """What the footer line does on Enter."""

    ADD = "add"
    FILTER = "filter"
    EDIT = "edit"


class KotsuApp(App[None]):
    TITLE = "Kotsu"
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    Screen { layout: vertical; }
    #top { height: auto; padding: 1 2 0 2; }
    #accounts { height: auto; max-height: 8; padding: 0 2; margin-top: 1; }
    #entries { height: 1fr; margin: 1 2 0 2; }
    #empty { height: 1fr; padding: 1 2; color: $text-muted; }
    #line { margin: 0 1; }
    #preview { height: auto; min-height: 1; padding: 0 2; }
    DataTable { border: round $primary; background: $background; }
    DataTable > .datatable--header { background: $panel; color: $primary; }
    DataTable > .datatable--even-row { background: $surface; }
    DataTable > .datatable--odd-row { background: $background; }
    DataTable > .datatable--cursor { background: $primary; color: $background; }
    Footer { background: $panel; }
    """
    BINDINGS = [
        Binding("left", "month(-1)", "Previous month"),
        Binding("right", "month(1)", "Next month"),
        Binding("l", "add", "Log entry"),
        Binding("slash", "filter", "Filter"),
        Binding("e", "edit", "Edit"),
        Binding("c", "copy", "Copy"),
        Binding("d", "delete", "Delete"),
        Binding("r", "rename", "Rename"),
        Binding("m", "monthly", "Every month"),
        Binding("b", "backup", "Backup"),
        Binding("t", "theme", "Theme"),
        Binding("v", "verify", "Verify"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self, database: Database, today: dt.date | None = None, theme_folder: Path | None = None
    ) -> None:
        super().__init__()
        self.database = database
        # `theme_folder`: where to read and save theme.toml; None (tests) neither reads nor
        # saves (D37).
        self._theme_folder = theme_folder
        saved = preferences.read_theme(theme_folder) if theme_folder else None
        self.kotsu_theme: Theme = theme_by_name(saved)
        self._use_colors(self.kotsu_theme)
        self.today = today or dt.date.today()
        self.month = Month.of(self.today)
        self.filter: Filter = NO_FILTER
        self._filter_text = ""  # how the filter was typed, to reopen with it
        self._mode = Mode.ADD
        self._editing: tuple[Entry, Scope] | None = None
        self._notice: Text | None = None
        # State of the month's paginated list.
        self._count = 0
        self._loaded = 0
        self._accounts: dict[int, Account] = {}
        self._categories: dict[int, str] = {}

    def compose(self) -> ComposeResult:
        yield Static(id="top")
        yield Static(id="accounts")
        yield DataTable(id="entries", cursor_type="row", zebra_stripes=True)
        yield Static(id="empty")
        # No select-all on focus: copy and edit open the line pre-filled.
        yield Input(placeholder=HINT, id="line", select_on_focus=False)
        yield Static(id="preview")
        yield Footer()

    def _use_colors(self, theme: Theme) -> None:
        colors.apply(theme.income, theme.expense, theme.neutral)

    def action_theme(self) -> None:
        """Cycles through the themes and remembers the choice in theme.toml (D37)."""
        self.kotsu_theme = next_theme(self.kotsu_theme)
        self._use_colors(self.kotsu_theme)
        self.theme = self.kotsu_theme.name
        self.refresh_all()
        saved = True
        if self._theme_folder is not None:
            saved = preferences.save_theme(self._theme_folder, self.kotsu_theme.name)
        if saved:
            self.notify(self.kotsu_theme.label, timeout=3)
        else:
            self.notify(
                f"{self.kotsu_theme.label} (could not remember the choice)",
                severity="warning",
            )

    def on_mount(self) -> None:
        for theme in (self.kotsu_theme, next_theme(self.kotsu_theme)):
            self.register_theme(theme.to_textual())
        self.theme = self.kotsu_theme.name
        table = self.query_one("#entries", DataTable)
        table.add_columns("Date", "Description", "Category", "Account", "Amount")
        self.query_one("#line", Input).display = False
        self.refresh_all()

    def action_backup(self) -> None:
        """Manual backup: a new copy on every request, in the `backups/` folder."""
        try:
            target = self.database.manual_backup()
        except OSError:
            self.notify(
                "Could not make the backup. Check the data folder.",
                severity="warning",
                timeout=10,
            )
            return
        if target is None:
            self.notify("In-memory database: there is no file to copy.", severity="warning")
        else:
            self.notify(f"Backup saved to {target}", timeout=8)

    def action_verify(self) -> None:
        """Shows the check code: equal to the other device's = same data (D39)."""
        self.notify(f"Check code: {exchange.check_code(self.database)}", timeout=15)

    # --- navigation and drawing ----------------------------------------------

    def action_month(self, step: int) -> None:
        self.month = self.month.add(step)
        self.refresh_all(top=True)

    def refresh_all(self, keep: int | None = None, top: bool = False) -> None:
        """Redraws everything from the database.

        The cursor goes back to entry `keep` (default: the one selected now); if it left the
        month or the filter, it stays on the neighbor. `top=True` (another month, another
        filter) starts from the first.
        """
        self.database.extend_recurrences(min(self.month, Month.of(self.today).add(MONTHS_AHEAD)))
        table = self.query_one("#entries", DataTable)
        row_before = 0 if top or not table.row_count else table.cursor_row
        loaded_before = 0 if top else self._loaded
        if keep is None and not top:
            keep = self.selected_id()

        accounts = self.database.list_accounts()
        self._accounts = {a.id: a for a in accounts}
        self._categories = {c.id: c.name for c in self.database.list_categories()}

        totals = self.database.month_totals(self.month, self.filter)
        self._count = totals.count
        self.query_one("#top", Static).update(self.top_text(totals))
        self.query_one("#accounts", Static).update(self.accounts_text(accounts))

        table.clear()
        self._loaded = 0
        self.load_more(table)
        # Reloads the pages that were already open, so the cursor does not jump to the top.
        while self._loaded < min(loaded_before, self._count):
            self.load_more(table)
        if table.row_count:
            target = min(row_before, table.row_count - 1)
            if keep is not None:
                try:
                    target = table.get_row_index(str(keep))
                except RowDoesNotExist:  # left the month or the filter: stays on the neighbor
                    pass
            table.move_cursor(row=target, animate=False)

        empty = self._count == 0
        table.display = not empty
        notice = self.query_one("#empty", Static)
        notice.display = empty
        if self.filter.active:
            notice.update("Nothing this month with that filter. Esc removes the filter.")
        else:
            notice.update("No entries this month. Press l to log one.")

    def top_text(self, totals: MonthTotals) -> Text:
        theme = self.kotsu_theme
        count = totals.count
        face = theme.happy if totals.balance >= 0 else theme.sad
        top = Text.assemble(
            (face, theme.warning),
            "  ",
            (f" {self.month.name} ", f"bold {theme.background} on {theme.highlight}"),
            (f"   {count} entr{'y' if count == 1 else 'ies'}", colors.NEUTRAL),
            ("\n", ""),
            ("♡ income ", theme.secondary),
            (currency.format_cents(totals.income), f"bold {colors.INCOME}"),
            ("   ✧ expenses ", theme.secondary),
            (currency.format_cents(totals.expenses), f"bold {colors.EXPENSE}"),
            ("   ☆ balance ", theme.secondary),
            (currency.format_cents(totals.balance), f"bold {colors.of_balance(totals.balance)}"),
        )
        if self.filter.active:  # second line of the top, so the first does not wrap
            top.append("\nfilter: ", style=colors.NEUTRAL)
            top.append_text(self.filter_label(self.filter))
            top.append("   (Esc removes)", style=colors.NEUTRAL)
        return top

    def accounts_text(self, accounts: list[Account]) -> Text:
        """One line per account, in its color; with no entry in the month, "zeroed" (D9, D29)."""
        if not accounts:
            return Text("No accounts yet.", style=colors.NEUTRAL)
        by_account = self.database.totals_by_account(self.month, self.filter)
        if self.filter.account_id is not None:  # account filter: only that one
            accounts = [a for a in accounts if a.id == self.filter.account_id]
        width = max(len(a.name) for a in accounts)
        largest = max((x.expenses for x in by_account.values()), default=0)
        lines = []
        for account in accounts:
            theme = self.kotsu_theme
            text = Text.assemble(
                (f"{theme.bullet} ", account.color),
                (account.name.ljust(width), f"bold {account.color}"),
            )
            t = by_account.get(account.id)
            if t is None:
                text.append(f"   {theme.zeroed}", style=colors.NEUTRAL)
            else:
                full = round(10 * t.expenses / largest) if largest else 0
                text.append("   " + theme.bar_full * full, style=account.color)
                text.append(theme.bar_empty * (10 - full), style=colors.NEUTRAL)
                text.append("   income ")
                text.append(currency.format_cents(t.income).rjust(12), style=colors.INCOME)
                text.append("   expenses ")
                text.append(currency.format_cents(t.expenses).rjust(12), style=colors.EXPENSE)
            lines.append(text)
        return Text("\n").join(lines)

    def load_more(self, table: DataTable) -> None:
        """Appends the month's next page to the list."""
        page = self.database.month_entries(self.month, PAGE_SIZE, self._loaded, self.filter)
        for item in page:
            account = self._accounts.get(item.account_id)
            description = item.description
            if item.installment:
                description = f"{description} {item.installment.label}"
            elif item.recurrence_group:
                description = f"{description} ↻"
            table.add_row(
                item.date.strftime("%d/%m"),
                description,
                self._categories.get(item.category_id, ""),
                Text(account.name, style=account.color) if account else "",
                Text(
                    currency.format_cents(item.amount),
                    style=colors.of_balance(item.signed_amount),
                    justify="right",
                ),
                key=str(item.id),
            )
        self._loaded += len(page)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        table = event.data_table
        if event.cursor_row >= table.row_count - 1 and self._loaded < self._count:
            self.load_more(table)

    # --- footer line ---------------------------------------------------------

    def open_line(self, mode: Mode, text: str = "") -> None:
        self._mode = mode
        self.refresh_bindings()
        field = self.query_one("#line", Input)
        field.placeholder = FILTER_HINT if mode is Mode.FILTER else HINT
        field.value = text
        field.cursor_position = len(text)
        field.display = True
        field.focus()
        self._notice = None
        self.show_preview(text)

    def close_line(self) -> None:
        field = self.query_one("#line", Input)
        field.value = ""
        field.display = False
        self._mode = Mode.ADD
        self._editing = None
        self._notice = None
        self.query_one("#preview", Static).update("")
        self.query_one("#entries", DataTable).focus()
        self.refresh_bindings()

    def action_add(self) -> None:
        self.open_line(Mode.ADD)

    def action_filter(self) -> None:
        self.open_line(Mode.FILTER, self._filter_text)

    def action_copy(self) -> None:
        """Line pre-filled with the selected entry, without date or installments (D27)."""
        item = self.selected()
        if item is not None:
            self.open_line(Mode.ADD, self.line_of(item, with_date=False))

    @work(exclusive=True)
    async def action_edit(self) -> None:
        """Line pre-filled with the whole entry; Enter changes that same entry (D28)."""
        item = self.selected()
        if item is None:
            return
        scope = await self.ask_scope(item, "Edit", Scope.ONLY_THIS)
        if scope is None:
            return
        self._editing = (item, scope)
        text = self.line_of(item, with_date=not _many(item, scope))
        self.open_line(Mode.EDIT, text)

    async def ask_scope(self, item: Entry, action: str, default: Scope) -> Scope | None:
        """ "Only this one or all?" for installments (D12); "only this month or the upcoming
        ones?" for recurring entries (D36). A plain entry does not ask and returns `default`."""
        if item.installment:
            return await self.push_screen_wait(OnlyThisOrAll(action, item.installment.label))
        if item.recurrence_group:
            return await self.push_screen_wait(OnlyThisOrUpcoming(action))
        return default

    def line_of(self, item: Entry, with_date: bool) -> str:
        return build(
            item.amount,
            item.kind,
            item.description,
            self._accounts[item.account_id].name,
            self._categories.get(item.category_id),
            item.date if with_date else None,
        )

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        # With the line open, "/" is text (dates like 15/10): hides "Filter" from the footer.
        if action == "filter" and self.focused is self.query_one("#line", Input):
            return False
        return True

    def on_key(self, event) -> None:
        if event.key != "escape":
            return
        if self.focused is self.query_one("#line", Input):
            event.stop()
            self.close_line()
        elif self.filter.active and len(self.screen_stack) == 1:
            event.stop()
            self.set_filter(NO_FILTER, "")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "line":
            self.show_preview(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "line":
            return
        if self._mode is Mode.FILTER:
            self.apply_filter(event.value)
        elif self._mode is Mode.EDIT:
            self.save_edit(event.value)
        else:
            self.save_line(event.value)

    def show_preview(self, text: str) -> None:
        if not self.query_one("#line", Input).display:
            return  # line closed: the preview keeps the last notice ("edited: ...")
        preview = self.query_one("#preview", Static)
        if self._mode is Mode.FILTER:
            preview.update(self.filter_preview(text))
            return
        if not text.strip():
            # After saving, the line is empty but the "saved: ..." notice stays.
            preview.update(self._notice or Text(HINT, style=colors.NEUTRAL))
            return
        self._notice = None
        try:
            line = parse(text, self.today)
            if self._mode is Mode.EDIT:
                self.check_edit(line)
        except LineError as error:
            preview.update(Text(str(error), style=colors.EXPENSE))
            return
        if self._mode is Mode.EDIT:
            preview.update(Text.assemble(("edit: ", colors.NEUTRAL), self.preview_text(line)))
        else:
            preview.update(self.preview_text(line))

    def preview_text(self, line: ParsedLine) -> Text:
        amount_color = colors.INCOME if line.kind is Kind.INCOME else colors.EXPENSE
        parts: list[Text] = [
            Text.assemble(
                (line.kind.value, amount_color), " ", (_amount(line), f"bold {amount_color}")
            )
        ]
        if line.description:
            parts.append(Text(line.description, style="bold"))
        if line.category:
            existing = self.database.category_by_name(line.category)
            name = existing.name if existing else line.category
            parts.append(Text(f"#{name}" + ("" if existing else " (new)")))
        account = self.database.account_by_name(line.account) if line.account else None
        if account:
            parts.append(Text(f"@{account.name}", style=f"bold {account.color}"))
        elif line.account:
            parts.append(Text(f"@{line.account} (new)", style="bold"))
        else:
            parts.append(Text("missing @account", style=colors.EXPENSE))
        parts.append(Text(self.period(line), style=colors.NEUTRAL))
        return Text(" · ").join(parts)

    def period(self, line: ParsedLine) -> str:
        if self._mode is Mode.EDIT and self._editing and _many(*self._editing):
            item, scope = self._editing
            if scope is Scope.UPCOMING:
                return "this month and the upcoming ones, dates kept"
            return f"all {item.installment.total} installments, dates kept"
        if (
            self._mode is Mode.ADD
            and line.installments == 1
            and self.is_recurring_category(line.category)
        ):
            return f"{line.date.strftime('%d/%m/%Y')}, and every month"
        return _period(line)

    def is_recurring_category(self, name: str | None) -> bool:
        category = self.database.category_by_name(name) if name else None
        return category is not None and category.recurring

    async def resolve_names(self, line: ParsedLine) -> tuple[Account, int | None] | None:
        """The line's account (required, D21/D22) and category; creates new ones by asking.

        Returns None if the account is missing or the person cancelled; the preview already
        says why.
        """
        preview = self.query_one("#preview", Static)
        if not line.account:
            preview.update(Text("give the account with @name", style=colors.EXPENSE))
            return None
        account = self.database.account_by_name(line.account)
        if account is None:
            color = await self.push_screen_wait(PickColor(line.account, self.suggested_color()))
            if color is None:
                preview.update(Text("cancelled: nothing was saved", style=colors.NEUTRAL))
                return None
            account = self.database.create_account(line.account, color)

        category: Category | None = None
        if line.category:
            category = self.database.category_by_name(line.category)
            if category is None:
                create = await self.push_screen_wait(
                    YesOrNo(f"Create the category {line.category}?")
                )
                if not create:
                    preview.update(Text("cancelled: nothing was saved", style=colors.NEUTRAL))
                    self.refresh_all()  # the account may have been created
                    return None
                repeat = await self.push_screen_wait(
                    YesOrNo(
                        f"Repeat the entries of {line.category} every month?",
                        "Rent, internet, salary... Enter = yes   Esc = no",
                    )
                )
                category = self.database.create_category(line.category, bool(repeat))
        return account, category.id if category else None

    @work(exclusive=True)
    async def save_line(self, text: str) -> None:
        preview = self.query_one("#preview", Static)
        try:
            line = parse(text, self.today)
        except LineError as error:
            preview.update(Text(str(error), style=colors.EXPENSE))
            return
        names = await self.resolve_names(line)
        if names is None:
            return
        account, category_id = names

        recurring = category_id is not None and any(
            c.id == category_id and c.recurring for c in self.database.list_categories()
        )
        if recurring and line.installments > 1:
            preview.update(
                Text(
                    f"#{line.category} already repeats every month: remove the"
                    f" {line.installments}x",
                    style=colors.EXPENSE,
                )
            )
            return
        group = self.database.new_installment_group() if line.installments > 1 else None
        new = installments.generate(line, account.id, category_id, group)
        if recurring:
            new = [replace(new[0], recurrence_group=self.database.new_installment_group())]
        ids = self.database.insert_entries(new)

        self._notice = Text.assemble(("saved: ", colors.NEUTRAL), self.saved_text(line, account))
        self.query_one("#line", Input).value = ""
        self.refresh_all(keep=ids[0])
        preview.update(self._notice)

    def saved_text(self, line: ParsedLine, account: Account) -> Text:
        amount_color = colors.INCOME if line.kind is Kind.INCOME else colors.EXPENSE
        return Text(" · ").join(
            [
                Text(_amount(line), style=f"bold {amount_color}"),
                Text(line.description or "(no description)"),
                Text(f"@{account.name}", style=f"bold {account.color}"),
                Text(self.period(line), style=colors.NEUTRAL),
            ]
        )

    def suggested_color(self) -> str:
        used = {a.color for a in self.database.list_accounts()}
        free = [c for c in colors.ACCOUNTS if c not in used]
        return free[0] if free else colors.ACCOUNTS[len(used) % len(colors.ACCOUNTS)]

    # --- edit (D28) ----------------------------------------------------------

    def check_edit(self, line: ParsedLine) -> None:
        if line.installments > 1:
            raise LineError("the number of installments does not change when editing")
        if self._editing and _many(*self._editing) and line.has_date:
            raise LineError("the date only changes on a single entry: edit with 'only this'")

    @work(exclusive=True)
    async def save_edit(self, text: str) -> None:
        if self._editing is None:
            return
        item, scope = self._editing
        preview = self.query_one("#preview", Static)
        try:
            line = parse(text, self.today)
            self.check_edit(line)
        except LineError as error:
            preview.update(Text(str(error), style=colors.EXPENSE))
            return
        names = await self.resolve_names(line)
        if names is None:
            return
        account, category_id = names
        new = NewEntry(line.date, line.description, line.amount, line.kind, account.id, category_id)
        notice = Text.assemble(("edited: ", colors.NEUTRAL), self.saved_text(line, account))
        count = self.database.edit(item.id, new, scope)
        self.close_line()
        self.refresh_all(keep=item.id)
        if count > 1:
            notice.append(f" ({count} installments)", style=colors.NEUTRAL)
        self.query_one("#preview", Static).update(notice)

    # --- filter (D12, D26) ---------------------------------------------------

    def resolve_filter(self, text: str) -> Filter:
        """The `/` text into ids. Raises `LineError` with the message for the preview."""
        typed = parse_filter(text)
        account = category = None
        if typed.either is not None:
            name = typed.either
            account = self.database.account_by_name(name)
            category = self.database.category_by_name(name)
            if account and category:
                raise LineError(
                    f"there is an account and a category {name}: use @{name} or #{name}"
                )
            if not account and not category:
                raise LineError(f"there is no account or category {name}")
        if typed.account is not None:
            account = self.database.account_by_name(typed.account)
            if account is None:
                raise LineError(f"there is no account {typed.account}")
        if typed.category is not None:
            category = self.database.category_by_name(typed.category)
            if category is None:
                raise LineError(f"there is no category {typed.category}")
        return Filter(account.id if account else None, category.id if category else None)

    def filter_label(self, filter: Filter) -> Text:
        parts = []
        if filter.account_id is not None:
            account = self._accounts[filter.account_id]
            parts.append(Text(f"@{account.name}", style=f"bold {account.color}"))
        if filter.category_id is not None:
            name = self._categories[filter.category_id]
            parts.append(Text(f"#{name}", style="bold"))
        return Text(" ").join(parts)

    def filter_preview(self, text: str) -> Text:
        if not text.strip():
            if self.filter.active:
                return Text("Enter removes the filter", style=colors.NEUTRAL)
            return Text(FILTER_HINT, style=colors.NEUTRAL)
        try:
            filter = self.resolve_filter(text)
        except LineError as error:
            return Text(str(error), style=colors.EXPENSE)
        return Text.assemble(("show only ", colors.NEUTRAL), self.filter_label(filter))

    def apply_filter(self, text: str) -> None:
        try:
            filter = self.resolve_filter(text) if text.strip() else NO_FILTER
        except LineError as error:
            self.query_one("#preview", Static).update(Text(str(error), style=colors.EXPENSE))
            return
        self.close_line()
        self.set_filter(filter, text.strip() if filter.active else "")

    def set_filter(self, filter: Filter, text: str) -> None:
        self.filter = filter
        self._filter_text = text
        self.refresh_all(top=True)

    # --- select, delete and rename (D12) -------------------------------------

    def selected_id(self) -> int | None:
        table = self.query_one("#entries", DataTable)
        if table.row_count == 0:
            return None
        key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        return int(key.value)

    def selected(self) -> Entry | None:
        table = self.query_one("#entries", DataTable)
        if not table.display:
            return None
        id_ = self.selected_id()
        return self.database.entry(id_) if id_ is not None else None

    @work(exclusive=True)
    async def action_delete(self) -> None:
        item = self.selected()
        if item is None:
            return
        if item.installment or item.recurrence_group:
            scope = await self.ask_scope(item, "Delete", Scope.ONLY_THIS)
        else:
            ok = await self.push_screen_wait(YesOrNo(f"Delete {item.description or 'the entry'}?"))
            scope = Scope.ONLY_THIS if ok else None
        if scope is None:
            return
        self.database.delete(item.id, scope)
        self.refresh_all()  # the deleted one disappears; the cursor stays on the neighbor

    @work(exclusive=True)
    async def action_monthly(self) -> None:
        """Turns "every month" on or off for the selected entry's category (D36).

        Turning it on applies to the category's next entries and already makes the selected
        one the start of the series. Turning it off does not touch running series.
        """
        item = self.selected()
        if item is None:
            return
        if item.category_id is None:
            self.notify("This entry has no category (#name).", severity="warning")
            return
        name = self._categories[item.category_id]
        category = self.database.category_by_name(name)
        if category.recurring:
            ok = await self.push_screen_wait(
                YesOrNo(
                    f"Stop marking #{name} as every month?",
                    "New entries do not repeat. The ones already repeating go on"
                    " until you delete them (d).",
                )
            )
            if ok:
                self.database.set_recurring(category.id, False)
                self.notify(f"#{name} no longer repeats for new entries.")
        else:
            ok = await self.push_screen_wait(
                YesOrNo(
                    f"Repeat the entries of #{name} every month?",
                    "This entry becomes the start of the repetition."
                    if not item.installment
                    else "",
                )
            )
            if ok:
                self.database.set_recurring(category.id, True)
                self.database.make_recurring(item.id)
        self.refresh_all(keep=item.id)

    @work(exclusive=True)
    async def action_rename(self) -> None:
        item = self.selected()
        if item is None:
            return
        scope = await self.ask_scope(item, "Rename", Scope.ONLY_THIS)
        if scope is None:
            return
        new = await self.push_screen_wait(AskText("New description", item.description))
        if new is None:
            return
        self.database.rename(item.id, new, scope)
        self.refresh_all(keep=item.id)


def _many(item: Entry, scope: Scope) -> bool:
    """Scope larger than one entry: all installments or the upcoming months."""
    if scope is Scope.UPCOMING:
        return item.recurrence_group is not None
    return item.installment is not None and scope is Scope.ALL


def _amount(line: ParsedLine) -> str:
    if line.installments == 1:
        return currency.format_cents(line.amount)
    return (
        f"{line.installments}x of {currency.format_cents(line.amount)}"
        f" = {currency.format_cents(line.total)}"
    )


def _short_month(date: dt.date) -> str:
    return f"{NAMES[date.month - 1][:3]}/{date.year}"


def _period(line: ParsedLine) -> str:
    if line.installments == 1:
        return line.date.strftime("%d/%m/%Y")
    last = installments.installment_date(line.date, line.installments - 1)
    return f"{_short_month(line.date)} to {_short_month(last)}"
