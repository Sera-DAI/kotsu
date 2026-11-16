package kotsu.core

import java.time.LocalDate
import java.time.YearMonth

/** Installment dates (mirrors kotsu.domain.installments.installment_date). */
object Dates {
    /** Same day, `index` months later; a missing day becomes the month's last day. */
    fun installmentDate(first: LocalDate, index: Int): LocalDate {
        val month = YearMonth.from(first).plusMonths(index.toLong())
        return month.atDay(minOf(first.dayOfMonth, month.lengthOfMonth()))
    }
}
