package kotsu.core

/** Formatting of amounts in integer cents (mirrors kotsu.domain.money). */
object Money {
    /** 123456 -> "1.234,56". The sign never shows: the UI uses color for negatives. */
    fun format(cents: Long): String {
        val abs = kotlin.math.abs(cents)
        val reais = (abs / 100).toString().reversed().chunked(3).joinToString(".").reversed()
        return reais + "," + (abs % 100).toString().padStart(2, '0')
    }
}
