package kotsu.core

import java.time.LocalDate
import java.time.YearMonth
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** The phone's database: same behavior as kotsu.storage.database on the PC. */
class BookTest {
    private val today = LocalDate.of(2026, 11, 15)
    private var ms = 1_762_850_000_000L
    private fun book(storage: Storage = MemoryStorage()) = Book.open(storage) { ms++ }
    private fun Book.line(text: String, account: String = "nubank", category: String? = null): List<Entry> {
        val a = accountByName(account) ?: createAccount(account, suggestedColor())
        val c = category?.let { categoryByName(it) ?: createCategory(it) }
        return add(Line.parse(text, today), a.uid, c?.uid)
    }

    @Test
    fun entriesPersistAcrossOpenings() {
        val storage = MemoryStorage()
        val b = book(storage)
        b.line("12,50 bakery")
        val again = book(storage)
        assertEquals(b.data, again.data)
        assertEquals(b.replica, again.replica)
        assertEquals(1, again.monthEntries(YearMonth.of(2026, 11)).size)
        // The clock goes on from where it was: a new stamp is larger.
        val e = again.line("3 coffee")
        assertTrue(e[0].changedAt > b.data.entries[0].changedAt)
    }

    @Test
    fun installmentsShareAGroup() {
        val b = book()
        val e = b.line("100 fridge 3x")
        assertEquals(listOf("2026-11-15", "2026-12-15", "2027-01-15"), e.map { it.date.toString() })
        assertEquals(1, e.map { it.installment!!.group }.toSet().size)
        assertEquals(listOf("1/3", "2/3", "3/3"), e.map { it.installment!!.label })
        assertEquals(10000, b.totals(YearMonth.of(2026, 12)).expenses)
        assertEquals(3, b.delete(e[1].uid, Scope.ALL))
        assertEquals(3, b.data.tombstones.size)
    }

    @Test
    fun onlyThisInstallment() {
        val b = book()
        val e = b.line("100 fridge 3x")
        assertEquals(1, b.rename(e[0].uid, "freezer", Scope.ONLY_THIS))
        assertEquals(3, b.edit(e[1].uid, Book.Change(today, "fridge!", 200, Kind.EXPENSE, e[1].account, null), Scope.ALL))
        val dates = b.data.entries.map { it.date }
        assertEquals(e.map { it.date }, dates, "ALL keeps the dates")
        assertEquals(listOf(200L, 200L, 200L), b.data.entries.map { it.amount })
    }

    @Test
    fun recurringCategoryMakesASeries() {
        val b = book()
        val rent = b.createCategory("rent", recurring = true)
        val a = b.createAccount("itaú", "#ff7a00")
        val first = b.add(Line.parse("1500 rent 31/01/2026", today), a.uid, rent.uid).single()
        assertFailsWith<LineError> { b.add(Line.parse("10 x 3x", today), a.uid, rent.uid) }
        assertEquals(3, b.extendRecurrences(YearMonth.of(2026, 4), today))
        val feb = b.monthEntries(YearMonth.of(2026, 2)).single()
        assertEquals("2026-02-28", feb.date.toString())
        assertEquals(Merge.monthUid(first.recurrence!!, 2026, 2), feb.uid)
        assertTrue(feb.generated)
        // Deleting only one month: it does not come back.
        b.delete(feb.uid, Scope.ONLY_THIS)
        b.extendRecurrences(YearMonth.of(2026, 6), today)
        assertTrue(b.monthEntries(YearMonth.of(2026, 2)).isEmpty())
        // Editing the upcoming ones changes the template too.
        val apr = b.monthEntries(YearMonth.of(2026, 4)).single()
        b.edit(apr.uid, Book.Change(apr.date, "rent", 1600_00, Kind.EXPENSE, a.uid, rent.uid), Scope.UPCOMING)
        assertEquals(1500_00, b.monthEntries(YearMonth.of(2026, 3)).single().amount)
        assertEquals(1600_00, b.monthEntries(YearMonth.of(2026, 6)).single().amount)
        b.extendRecurrences(YearMonth.of(2026, 7), today)
        assertEquals(1600_00, b.monthEntries(YearMonth.of(2026, 7)).single().amount)
        // Deleting the upcoming ones ends the series and keeps the past.
        b.delete(b.monthEntries(YearMonth.of(2026, 5)).single().uid, Scope.UPCOMING)
        b.extendRecurrences(YearMonth.of(2026, 12), today)
        assertTrue(b.monthEntries(YearMonth.of(2026, 9)).isEmpty())
        assertEquals(1, b.monthEntries(YearMonth.of(2026, 4)).size)
        assertTrue(b.data.recurrences.single().ended)
    }

    @Test
    fun neverPastTwoYearsAhead() {
        val b = book()
        val rent = b.createCategory("rent", recurring = true)
        b.add(Line.parse("10 rent", today), b.createAccount("nu", "#8a2be2").uid, rent.uid)
        b.extendRecurrences(YearMonth.of(2040, 1), today)
        assertEquals(LocalDate.of(2028, 11, 1), b.data.recurrences.single().generatedUntil)
    }

    @Test
    fun makeRecurring() {
        val b = book()
        val e = b.line("50 internet").single()
        assertTrue(b.makeRecurring(e.uid))
        assertFalse(b.makeRecurring(e.uid))
        assertFalse(b.makeRecurring(b.line("10 x 2x")[0].uid))
        assertEquals(1, b.extendRecurrences(YearMonth.of(2026, 12), today))
    }

    @Test
    fun namesAreCaseInsensitive() {
        val b = book()
        b.createAccount("Itaú", "#ff7a00")
        assertEquals("Itaú", b.accountByName("ITAÚ")?.name)
        assertFailsWith<IllegalArgumentException> { b.createAccount("itaú ", "#000000") }
        assertEquals("#8a2be2", b.suggestedColor())
    }

    @Test
    fun twoPhonesMergeToTheSameCode() {
        val a = book()
        val b = book()
        a.line("12,50 bakery", category = "food")
        b.line("20 uber", account = "NUBANK", category = "Food")
        val ae = a.line("5 gum").single()
        val sb = b.import(a.export("2026-11-15T10:00:00"))
        assertEquals(Merge.Summary(added = 2), sb)
        a.import(b.export("2026-11-15T10:01:00"))
        assertEquals(a.checkCode(), b.checkCode())
        assertEquals(1, a.data.accounts.size)
        assertEquals(1, a.data.categories.size)
        // A deletion on one side wins on the other.
        b.delete(ae.uid)
        a.import(b.export("2026-11-15T10:02:00"))
        assertTrue(a.entry(ae.uid) == null)
        assertEquals(a.checkCode(), b.checkCode())
        // Importing again changes nothing.
        assertTrue(a.import(b.export("2026-11-15T10:03:00")).nothing)
    }

    @Test
    fun aBadFileChangesNothing() {
        val b = book()
        b.line("1 x")
        val before = b.data
        assertFailsWith<ExchangeError> { b.import("{\"app\": \"other\"}") }
        assertFailsWith<ExchangeError> { b.import("not json") }
        assertEquals(before, b.data)
    }

    @Test
    fun buildIsTheReverseOfParse() {
        val text = buildLine(123456, Kind.INCOME, "salary", "itaú", "work", LocalDate.of(2026, 1, 5))
        assertEquals("+1.234,56 salary #work @itaú 05/01/2026", text)
        val p = Line.parse(text, today)
        assertEquals(123456, p.amount)
        assertEquals(LocalDate.of(2026, 1, 5), p.date)
    }

    @Test
    fun restoreBringsBackEntriesDeletedAfterTheBackup() {
        val b = book()
        val e = b.line("100 fridge 3x")
        b.line("12,50 bakery")
        val backup = b.export("2026-11-15T10:00:00")
        assertEquals(3, b.delete(e[0].uid, Scope.ALL))
        // A plain import keeps them deleted: the tombstones are newer.
        val other = book()
        other.import(b.export("2026-11-15T11:00:00"))
        assertTrue(b.import(backup).nothing)
        assertEquals(1, b.data.entries.size)
        assertEquals(3, b.deletedHere(backup))
        assertEquals(3, b.restore(backup))
        assertEquals(4, b.data.entries.size)
        assertTrue(b.data.tombstones.isEmpty())
        assertEquals(0, b.deletedHere(backup))
        // Another device that saw the deletion gets them back too.
        assertEquals(1, other.data.entries.size)
        other.import(b.export("2026-11-15T12:00:00"))
        assertEquals(4, other.data.entries.size)
    }

    @Test
    fun deletingAnAccountTakesItsEntriesAndReachesOtherDevices() {
        val b = book()
        b.line("100 fridge 3x")
        b.line("5 coffee", account = "inter")
        val other = book()
        val backup = b.export("2026-11-15T10:00:00")
        other.import(backup)
        val nubank = b.accountByName("nubank")!!.uid
        assertEquals(3, b.accountUse(nubank))
        assertEquals(3, b.deleteAccount(nubank))
        assertEquals(listOf("inter"), b.accounts.map { it.name })
        assertEquals(1, b.data.entries.size)
        // The other device still has it; the exchange removes it there and keeps it gone here.
        other.import(b.export("2026-11-15T11:00:00"))
        assertEquals(listOf("inter"), other.accounts.map { it.name })
        assertEquals(b.checkCode(), other.checkCode())
        assertTrue(b.import(other.export("2026-11-15T12:00:00")).nothing)
        // A backup from before brings everything back.
        assertEquals(3, b.restore(backup))
        assertEquals(listOf("inter", "nubank"), b.accounts.map { it.name })
    }
}
