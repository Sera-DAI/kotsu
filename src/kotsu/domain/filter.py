"""Main-screen filter (D12, D26). Pure: reads the text; the UI resolves the names."""

from __future__ import annotations

from dataclasses import dataclass

from kotsu.domain.line import LineError


@dataclass(frozen=True, slots=True)
class TypedFilter:
    """What was typed after `/`, before becoming ids."""

    account: str | None = None  # @name
    category: str | None = None  # #name
    either: str | None = None  # name without prefix: account or category

    @property
    def empty(self) -> bool:
        return self.account is None and self.category is None and self.either is None


@dataclass(frozen=True, slots=True)
class Filter:
    """Filter already resolved into ids. Account and category combine with "and"."""

    account_id: int | None = None
    category_id: int | None = None

    @property
    def active(self) -> bool:
        return self.account_id is not None or self.category_id is not None


NO_FILTER = Filter()


def parse_filter(text: str) -> TypedFilter:
    """`@nubank`, `#home`, `@nubank #home` or `nubank`. Raises `LineError`."""
    account = category = either = None
    loose: list[str] = []
    for part in text.split():
        if part.startswith("@"):
            if account is not None:
                raise LineError("only one @account in the filter")
            account = _name(part, "account")
        elif part.startswith("#"):
            if category is not None:
                raise LineError("only one #category in the filter")
            category = _name(part, "category")
        else:
            loose.append(part)
    if loose:
        if account is not None or category is not None:
            raise LineError("use @account and #category together, or just a name")
        either = " ".join(loose)
    return TypedFilter(account, category, either)


def _name(part: str, what: str) -> str:
    if len(part) == 1:
        raise LineError(f"missing the {what} name after {part}")
    return part[1:]
