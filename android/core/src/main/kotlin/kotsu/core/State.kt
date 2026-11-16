package kotsu.core

import java.time.LocalDate

/**
 * The whole content of a Kotsu database, as in the exchange file (D39). Records refer to
 * each other by `uid`, never by a local id. Mirrors the dictionaries of kotsu.domain.merge.
 */
data class Account(val uid: String, val name: String, val color: String, val changedAt: String)

data class Category(val uid: String, val name: String, val recurring: Boolean, val changedAt: String)

/** Template of an endless monthly series (D36). */
data class Series(
    val group: String,
    val day: Int,
    val description: String,
    val amount: Long,
    val kind: Kind,
    val account: String,
    val category: String?,
    val generatedUntil: LocalDate,
    val ended: Boolean,
    val changedAt: String,
)

/** Position of an entry inside an installment purchase (D2, D8, D17). */
data class Installment(val group: String, val number: Int, val total: Int) {
    val label: String get() = "$number/$total"
}

data class Entry(
    val uid: String,
    val date: LocalDate,
    val description: String,
    val amount: Long,
    val kind: Kind,
    val account: String,
    val category: String?,
    val installment: Installment? = null,
    val recurrence: String? = null,
    val generated: Boolean = false,
    val changedAt: String,
) {
    val signed: Long get() = if (kind == Kind.INCOME) amount else -amount
}

data class Tombstone(val uid: String, val deletedAt: String)

data class State(
    val accounts: List<Account> = emptyList(),
    val categories: List<Category> = emptyList(),
    val recurrences: List<Series> = emptyList(),
    val entries: List<Entry> = emptyList(),
    val tombstones: List<Tombstone> = emptyList(),
)

internal val Kind.text: String get() = name.lowercase()
