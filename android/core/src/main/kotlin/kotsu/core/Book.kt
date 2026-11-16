package kotsu.core

import org.json.JSONObject
import java.time.LocalDate
import java.time.YearMonth
import java.util.UUID

/** Where the book's file lives. The app saves to a file with an atomic swap; tests keep it in memory. */
interface Storage {
    fun read(): String?
    fun write(text: String)
}

class MemoryStorage(var text: String? = null) : Storage {
    override fun read() = text
    override fun write(text: String) { this.text = text }
}

/** Answer to "only this one or all?" (D12) and "only this month or the upcoming ones?" (D36). */
enum class Scope { ONLY_THIS, ALL, UPCOMING }

/** Main-screen filter (D26): account and category by uid, plus a description search. */
data class Filter(val account: String? = null, val category: String? = null, val text: String = "") {
    val active get() = account != null || category != null || text.isNotBlank()
    fun matches(e: Entry) = (account == null || e.account == account) &&
        (category == null || e.category == category) &&
        (text.isBlank() || e.description.contains(text.trim(), ignoreCase = true))
}

data class Totals(val income: Long = 0, val expenses: Long = 0, val count: Int = 0) {
    val balance get() = income - expenses
}

/**
 * The phone's database: the same records and rules as the PC's SQLite database
 * (kotsu.storage.database), kept as a state (D39) and saved whole after every change, so a
 * change is all or nothing. Every write gets one stamp; deleting leaves tombstones.
 */
class Book private constructor(
    private val storage: Storage,
    val replica: String,
    private var clock: String,
    private var state: State,
    private val nowMs: () -> Long,
) {
    companion object {
        /** Account colors offered to a new account, in order (same as the PC, ui/colors.py). */
        val ACCOUNT_COLORS = listOf("#8a2be2", "#ff7a00", "#1f8fff", "#e8c547", "#2ec4b6", "#ff5fa2", "#9bd34a", "#c0c0c0")
        const val MONTHS_AHEAD = 24L

        fun open(storage: Storage, nowMs: () -> Long = System::currentTimeMillis): Book {
            val text = storage.read()
            if (text.isNullOrBlank()) {
                val replica = UUID.randomUUID().toString().replace("-", "").take(8)
                return Book(storage, replica, Merge.ZERO_STAMP, State(), nowMs).also { it.save() }
            }
            val o = JSONObject(text)
            return Book(storage, o.getString("replica"), o.getString("clock"), Exchange.toState(o), nowMs)
        }

        fun newUid(): String = UUID.randomUUID().toString().replace("-", "")
    }

    val data: State get() = state

    private fun save() {
        val o = JSONObject().put("app", "kotsu").put("format", Merge.FORMAT).put("replica", replica).put("clock", clock)
        storage.write(Exchange.sections(state, o).toString())
    }

    /** Runs one change: one stamp, and the file saved once at the end (or nothing on error). */
    private fun <T> change(block: (now: String) -> T): T {
        val before = state to clock
        try {
            clock = Merge.stamp(nowMs(), clock, replica)
            val result = block(clock)
            save()
            return result
        } catch (e: Throwable) {
            state = before.first; clock = before.second
            throw e
        }
    }

    // --- accounts and categories ------------------------------------------------------

    val accounts: List<Account> get() = state.accounts.sortedBy { Merge.nameKey(it.name) }
    val categories: List<Category> get() = state.categories.sortedBy { Merge.nameKey(it.name) }

    fun account(uid: String) = state.accounts.firstOrNull { it.uid == uid }
    fun category(uid: String?) = uid?.let { u -> state.categories.firstOrNull { it.uid == u } }
    fun accountByName(name: String) = state.accounts.firstOrNull { Merge.nameKey(it.name) == Merge.nameKey(name) }
    fun categoryByName(name: String) = state.categories.firstOrNull { Merge.nameKey(it.name) == Merge.nameKey(name) }

    fun suggestedColor(): String {
        val used = state.accounts.map { it.color }.toSet()
        return ACCOUNT_COLORS.firstOrNull { it !in used } ?: ACCOUNT_COLORS[used.size % ACCOUNT_COLORS.size]
    }

    fun createAccount(name: String, color: String): Account {
        require(name.isNotBlank()) { "the account needs a name" }
        require(accountByName(name) == null) { "the account ${name.trim()} already exists" }
        return change { now ->
            Account(newUid(), name.trim(), color, now).also { state = state.copy(accounts = state.accounts + it) }
        }
    }

    fun createCategory(name: String, recurring: Boolean = false): Category {
        require(name.isNotBlank()) { "the category needs a name" }
        require(categoryByName(name) == null) { "the category ${name.trim()} already exists" }
        return change { now ->
            Category(newUid(), name.trim(), recurring, now).also { state = state.copy(categories = state.categories + it) }
        }
    }

    /** Entries (all months) and series of an account. */
    fun accountUse(uid: String): Int =
        state.entries.count { it.account == uid } + state.recurrences.count { it.account == uid && !it.ended }

    /**
     * Deletes an account with all its entries and series (D44). The account and each entry
     * leave tombstones, so the deletion reaches the PC on the next exchange.
     */
    fun deleteAccount(uid: String): Int {
        requireNotNull(account(uid)) { "no such account" }
        return change { now ->
            val gone = state.entries.filter { it.account == uid }
            val uids = gone.map { it.uid }.toSet() + uid
            state = state.copy(
                accounts = state.accounts.filterNot { it.uid == uid },
                recurrences = state.recurrences.filterNot { it.account == uid },
                entries = state.entries.filterNot { it.account == uid },
                tombstones = state.tombstones.filterNot { it.uid in uids } + uids.map { Tombstone(it, now) },
            )
            gone.size
        }
    }

    /** Marks or unmarks "every month" (D36). Series already running do not change. */
    fun setRecurring(uid: String, recurring: Boolean) = change { now ->
        state = state.copy(categories = state.categories.map { if (it.uid == uid) it.copy(recurring = recurring, changedAt = now) else it })
    }

    // --- entries ----------------------------------------------------------------------

    fun entry(uid: String) = state.entries.firstOrNull { it.uid == uid }

    /**
     * Saves a parsed quick line (D11): one entry, one per installment, or the first month of
     * a series when the category repeats every month (D36). Returns the saved entries.
     */
    fun add(line: ParsedLine, accountUid: String, categoryUid: String?): List<Entry> {
        requireNotNull(account(accountUid)) { "every entry needs an account" }
        val category = category(categoryUid)
        val recurring = category?.recurring == true
        if (recurring && line.installments > 1) {
            throw LineError("#${category!!.name} already repeats every month: remove the ${line.installments}x")
        }
        return change { now ->
            val group = if (line.installments > 1) newUid() else null
            val series = if (recurring) newUid() else null
            val new = (0 until line.installments).map { i ->
                Entry(
                    uid = newUid(), date = Dates.installmentDate(line.date, i), description = line.description,
                    amount = line.amount, kind = line.kind, account = accountUid, category = categoryUid,
                    installment = group?.let { Installment(it, i + 1, line.installments) },
                    recurrence = series, changedAt = now,
                )
            }
            if (series != null) state = state.copy(recurrences = state.recurrences + seriesOf(series, new[0], now))
            state = state.copy(entries = state.entries + new)
            new
        }
    }

    private fun seriesOf(group: String, e: Entry, now: String) = Series(
        group, e.date.dayOfMonth, e.description, e.amount, e.kind, e.account, e.category,
        YearMonth.from(e.date).atDay(1), false, now,
    )

    /** Makes the entry the start of a monthly series (D36). False for installments or one already recurring. */
    fun makeRecurring(uid: String): Boolean {
        val e = entry(uid) ?: return false
        if (e.installment != null || e.recurrence != null) return false
        change { now ->
            val group = newUid()
            state = state.copy(
                recurrences = state.recurrences + seriesOf(group, e, now),
                entries = state.entries.map { if (it.uid == uid) it.copy(recurrence = group, changedAt = now) else it },
            )
        }
        return true
    }

    /**
     * Generates the missing months of the active series up to `until` (D36), never past
     * today + 24 months. Only moves forward; a generated month has a fixed uid and the
     * template's stamp (D39), and does not stamp.
     */
    fun extendRecurrences(until: YearMonth, today: LocalDate = LocalDate.now()): Int {
        val limit = minOf(until, YearMonth.from(today).plusMonths(MONTHS_AHEAD))
        val start = limit.atDay(1)
        val pending = state.recurrences.filter { !it.ended && it.generatedUntil < start }
        if (pending.isEmpty()) return 0
        val taken = (state.entries.map { it.uid } + state.tombstones.map { it.uid }).toHashSet()
        val created = mutableListOf<Entry>()
        val series = state.recurrences.map { r ->
            if (r !in pending) return@map r
            var m = YearMonth.from(r.generatedUntil).plusMonths(1)
            while (m <= limit) {
                val uid = Merge.monthUid(r.group, m.year, m.monthValue)
                if (uid !in taken) {
                    created += Entry(
                        uid = uid, date = Recurrence.dateInMonth(r.day, m), description = r.description,
                        amount = r.amount, kind = r.kind, account = r.account, category = r.category,
                        recurrence = r.group, generated = true, changedAt = r.changedAt,
                    )
                }
                m = m.plusMonths(1)
            }
            r.copy(generatedUntil = start)
        }
        val before = state
        state = state.copy(recurrences = series, entries = state.entries + created)
        try {
            save()
        } catch (e: Throwable) {
            state = before; throw e
        }
        return created.size
    }

    /** The month's entries, newest first (same day: the last saved first). */
    fun monthEntries(month: YearMonth, filter: Filter = Filter()): List<Entry> =
        state.entries.withIndex()
            .filter { YearMonth.from(it.value.date) == month && filter.matches(it.value) }
            .sortedWith(compareByDescending<IndexedValue<Entry>> { it.value.date }.thenByDescending { it.index })
            .map { it.value }

    fun totals(month: YearMonth, filter: Filter = Filter()): Totals = sum(monthEntries(month, filter))

    /** Income and expenses of each account that had an entry in the month (D9, D29). */
    fun totalsByAccount(month: YearMonth, filter: Filter = Filter()): Map<String, Totals> =
        monthEntries(month, filter).groupBy { it.account }.mapValues { sum(it.value) }

    private fun sum(list: List<Entry>) = Totals(
        list.filter { it.kind == Kind.INCOME }.sumOf { it.amount },
        list.filter { it.kind == Kind.EXPENSE }.sumOf { it.amount },
        list.size,
    )

    /** The entries a change reaches: the whole purchase, this month and the next ones, or just it. */
    private fun target(uid: String, scope: Scope): (Entry) -> Boolean {
        val e = entry(uid) ?: return { false }
        val group = e.installment?.group
        if (group != null && scope == Scope.ALL) return { it.installment?.group == group }
        if (e.recurrence != null && scope == Scope.UPCOMING) return { it.recurrence == e.recurrence && it.date >= e.date }
        return { it.uid == uid }
    }

    private fun single(uid: String, scope: Scope): Boolean {
        val e = entry(uid) ?: return true
        return !((e.installment != null && scope == Scope.ALL) || (e.recurrence != null && scope == Scope.UPCOMING))
    }

    /** Deletes; with ALL the whole purchase (D12), with UPCOMING it also ends the series (D36). */
    fun delete(uid: String, scope: Scope = Scope.ALL): Int {
        val hit = target(uid, scope)
        val series = entry(uid)?.recurrence
        return change { now ->
            val gone = state.entries.filter(hit)
            val tombs = state.tombstones.filter { t -> gone.none { it.uid == t.uid } } + gone.map { Tombstone(it.uid, now) }
            state = state.copy(
                entries = state.entries.filterNot(hit),
                tombstones = tombs,
                recurrences = if (scope == Scope.UPCOMING && series != null) {
                    state.recurrences.map { if (it.group == series) it.copy(ended = true, changedAt = now) else it }
                } else state.recurrences,
            )
            gone.size
        }
    }

    /** New fields for [edit]. The date only counts on a single entry. */
    data class Change(
        val date: LocalDate, val description: String, val amount: Long, val kind: Kind,
        val account: String, val category: String?,
    )

    /**
     * Changes amount, kind, description, account and category (D28). The date changes only
     * on a single entry; ALL and UPCOMING keep the dates (UPCOMING also changes the series
     * template). Installment number and group never change. Returns how many changed.
     */
    fun edit(uid: String, new: Change, scope: Scope = Scope.ALL): Int {
        requireNotNull(account(new.account)) { "every entry needs an account" }
        val hit = target(uid, scope)
        val one = single(uid, scope)
        val series = entry(uid)?.recurrence
        return change { now ->
            var n = 0
            state = state.copy(
                entries = state.entries.map {
                    if (!hit(it)) return@map it
                    n++
                    it.copy(
                        date = if (one) new.date else it.date, description = new.description.trim(), amount = new.amount,
                        kind = new.kind, account = new.account, category = new.category, generated = false, changedAt = now,
                    )
                },
                recurrences = if (scope == Scope.UPCOMING && series != null) state.recurrences.map {
                    if (it.group != series) it else it.copy(
                        description = new.description.trim(), amount = new.amount, kind = new.kind,
                        account = new.account, category = new.category, changedAt = now,
                    )
                } else state.recurrences,
            )
            n
        }
    }

    /** Changes only the description, with the same scopes as [edit]. */
    fun rename(uid: String, description: String, scope: Scope = Scope.ALL): Int {
        val e = entry(uid) ?: return 0
        return edit(uid, Change(e.date, description, e.amount, e.kind, e.account, e.category), scope)
    }

    // --- exchange (D39) ---------------------------------------------------------------

    fun checkCode(): String = Merge.checkCode(state)

    /** The exchange file with everything this phone has. */
    fun export(exportedAt: String): String = Exchange.write(state, replica, exportedAt)

    /**
     * Merges another device's exchange file. Raises [ExchangeError] for a bad file; nothing
     * changes then. The local clock moves past every stamp the file brought.
     */
    fun import(text: String): Merge.Summary {
        val remote = Exchange.read(text)
        val local = state
        val merged = Merge.merge(local, remote)
        val seen = Merge.highestStamp(remote)
        val before = state to clock
        // Keep the screen's order: local entries first, new ones after.
        val order = local.entries.withIndex().associate { it.value.uid to it.index }
        state = merged.copy(entries = merged.entries.sortedBy { order[it.uid] ?: Int.MAX_VALUE })
        if (seen > clock) clock = seen
        try {
            save()
        } catch (e: Throwable) {
            state = before.first; clock = before.second; throw e
        }
        return Merge.summarize(local, merged)
    }

    /** Entries in an exchange file (or backup) that were deleted on this phone. */
    fun deletedHere(text: String): Int {
        val remote = Exchange.read(text)
        val gone = state.tombstones.map { it.uid }.toSet()
        return remote.entries.count { it.uid in gone && entry(it.uid) == null }
    }

    /**
     * Restores from a backup: like [import], but entries deleted here come back. Merging alone
     * keeps them deleted, because the tombstone is newer than the copy in the backup (D39).
     * The restored entries get a new stamp, so they also come back on the other devices.
     * Returns how many came back.
     */
    fun restore(text: String): Int {
        val remote = Exchange.read(text)
        val gone = state.tombstones.map { it.uid }.toSet()
        val back = remote.entries.filter { it.uid in gone && entry(it.uid) == null }.map { it.uid }.toSet()
        val seen = Merge.highestStamp(remote)
        if (seen > clock) clock = seen
        return change { now ->
            val fresh = remote.copy(
                entries = remote.entries.map { if (it.uid in back) it.copy(generated = false, changedAt = now) else it },
                tombstones = remote.tombstones.filterNot { it.uid in back },
            )
            val local = state.copy(tombstones = state.tombstones.filterNot { it.uid in back })
            val merged = Merge.merge(local, fresh)
            val order = state.entries.withIndex().associate { it.value.uid to it.index }
            state = merged.copy(entries = merged.entries.sortedBy { order[it.uid] ?: Int.MAX_VALUE })
            merged.entries.count { it.uid in back }
        }
    }
}

/** Dates of recurring entries (mirrors kotsu.domain.recurrence). */
object Recurrence {
    /** `day` in the month; a day the month lacks becomes the last day (31 -> 28/02). */
    fun dateInMonth(day: Int, month: YearMonth): LocalDate = month.atDay(minOf(day, month.lengthOfMonth()))
}
