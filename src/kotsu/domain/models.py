"""Domain types. Amounts are always in integer cents (BRL)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum


class Kind(StrEnum):
    INCOME = "income"
    EXPENSE = "expense"


class Scope(StrEnum):
    """Answer to "only this one or all?" when changing an installment (D12). Default: all."""

    ONLY_THIS = "only_this"
    ALL = "all"
    UPCOMING = "upcoming"  # recurring: this month and the following ones (D36)


@dataclass(frozen=True, slots=True)
class Account:
    """Colored tag (D9): does not carry a balance across months."""

    id: int
    name: str
    color: str


@dataclass(frozen=True, slots=True)
class Category:
    id: int
    name: str
    recurring: bool = False  # entries in it repeat every month (D36)


@dataclass(frozen=True, slots=True)
class Installment:
    """Position of an entry inside an installment purchase (D2, D8)."""

    group: str
    number: int
    total: int

    def __post_init__(self) -> None:
        if not 1 <= self.number <= self.total:
            raise ValueError(f"invalid installment {self.number}/{self.total}")

    @property
    def label(self) -> str:
        return f"{self.number}/{self.total}"


@dataclass(frozen=True, slots=True)
class NewEntry:
    """Entry not saved yet. `amount` is positive; the sign comes from `kind`.

    Every entry has an account (D21); the category is optional.
    """

    date: dt.date
    description: str
    amount: int
    kind: Kind
    account_id: int
    category_id: int | None = None
    installment: Installment | None = None
    recurrence_group: str | None = None  # endless monthly series (D36)

    def __post_init__(self) -> None:
        if not isinstance(self.amount, int) or isinstance(self.amount, bool):
            raise TypeError("amount must be an int in cents")
        if self.amount <= 0:
            raise ValueError("amount must be positive; the kind says income or expense")
        if not isinstance(self.account_id, int) or isinstance(self.account_id, bool):
            raise ValueError("every entry needs an account")


@dataclass(frozen=True, slots=True)
class Entry:
    id: int
    date: dt.date
    description: str
    amount: int
    kind: Kind
    account_id: int
    category_id: int | None
    installment: Installment | None
    recurrence_group: str | None = None

    @property
    def signed_amount(self) -> int:
        return self.amount if self.kind is Kind.INCOME else -self.amount
