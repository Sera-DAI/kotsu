package kotsu.core

import java.time.DateTimeException
import java.time.LocalDate

/** Quick-line parser (D10, D11). Mirrors kotsu.domain.line; checked by vectors/line.json. */
enum class Kind { INCOME, EXPENSE }

class LineError(message: String) : IllegalArgumentException(message)

data class ParsedLine(
    val amount: Long, // cents, positive; per installment
    val kind: Kind,
    val description: String,
    val date: LocalDate,
    val category: String? = null,
    val account: String? = null,
    val installments: Int = 1,
    val hasDate: Boolean = false,
) {
    val total: Long get() = amount * installments
}

object Line {
    const val MAX_INSTALLMENTS = 120

    private val TODAY = setOf("today", "hoje")
    private val YESTERDAY = setOf("yesterday", "ontem")
    private val INSTALLMENTS = Regex("""(\d+)[xX]""")
    private val DATE = Regex("""(\d{1,2})/(\d{1,2})(?:/(\d{2}|\d{4}))?""")
    private val AMOUNT = Regex("""([+-]?)(.+)""")
    private val DIGITS = Regex("""\d+""")
    private val THOUSANDS = Regex("""\d{1,3}(\.\d{3})+""")
    private val DOT_DECIMAL = Regex("""\d+\.\d{1,2}""")

    fun parse(line: String, today: LocalDate): ParsedLine {
        val parts = line.split(Regex("""\s+""")).filter { it.isNotEmpty() }
        if (parts.isEmpty()) throw LineError("type the amount first, e.g. 89,90 groceries @nubank")

        val (kind, amount) = readAmount(parts[0])
        val description = mutableListOf<String>()
        var category: String? = null
        var account: String? = null
        var date: LocalDate? = null
        var installments: Int? = null

        for (part in parts.drop(1)) {
            val inst = INSTALLMENTS.matchEntire(part)
            when {
                part.startsWith("#") -> {
                    if (category != null) throw LineError("only one #category per entry")
                    category = name(part, "category")
                }
                part.startsWith("@") -> {
                    if (account != null) throw LineError("only one @account per entry")
                    account = name(part, "account")
                }
                inst != null -> {
                    if (installments != null) throw LineError("only one installment count (e.g. 10x)")
                    val n = inst.groupValues[1].toBigInteger()
                    if (n < 2.toBigInteger() || n > MAX_INSTALLMENTS.toBigInteger()) {
                        throw LineError("installments go from 2x to ${MAX_INSTALLMENTS}x")
                    }
                    installments = n.toInt()
                }
                else -> {
                    val d = readDate(part, today)
                    if (d != null) {
                        if (date != null) throw LineError("only one date per entry")
                        date = d
                    } else {
                        description.add(part)
                    }
                }
            }
        }
        return ParsedLine(
            amount = amount,
            kind = kind,
            description = description.joinToString(" "),
            date = date ?: today,
            category = category,
            account = account,
            installments = installments ?: 1,
            hasDate = date != null,
        )
    }

    private fun name(part: String, what: String): String {
        val n = part.substring(1)
        if (n.isEmpty()) throw LineError("missing the $what name after ${part[0]}")
        return n
    }

    private fun readAmount(text: String): Pair<Kind, Long> {
        val unreadable = LineError("unreadable amount: $text (use 89,90 or 1.234,56)")
        val m = AMOUNT.matchEntire(text) ?: throw unreadable
        val kind = if (m.groupValues[1] == "+") Kind.INCOME else Kind.EXPENSE
        val cents = cents(m.groupValues[2]) ?: throw unreadable
        if (cents == 0L) throw LineError("the amount must be greater than zero")
        return kind to cents
    }

    /** Same rules as Python `_cents`: comma is decimal, dot is thousands unless 1-2 digits end it. */
    internal fun cents(number: String): Long? {
        var whole: String
        val fraction: String
        if ("," in number) {
            whole = number.substringBefore(","); fraction = number.substringAfter(",")
        } else if (DOT_DECIMAL.matches(number)) {
            whole = number.substringBefore("."); fraction = number.substringAfter(".")
        } else {
            whole = number; fraction = ""
        }
        if ("." in whole) {
            if (!THOUSANDS.matches(whole)) return null
            whole = whole.replace(".", "")
        }
        if (!DIGITS.matches(whole) || (fraction.isNotEmpty() && !DIGITS.matches(fraction))) return null
        if (fraction.length > 2) return null
        return whole.toLong() * 100 + (fraction.padEnd(2, '0').toLongOrNull() ?: 0)
    }

    private fun readDate(text: String, today: LocalDate): LocalDate? {
        val lower = text.lowercase()
        if (lower in TODAY) return today
        if (lower in YESTERDAY) return today.minusDays(1)
        val m = DATE.matchEntire(text) ?: return null
        val (day, month, year) = m.destructured
        val y = when {
            year.isEmpty() -> today.year
            year.length == 2 -> 2000 + year.toInt()
            else -> year.toInt()
        }
        return try {
            LocalDate.of(y, month.toInt(), day.toInt())
        } catch (e: DateTimeException) {
            throw LineError("impossible date: $text")
        }
    }
}

/** The reverse of [Line.parse]: the line that copy and edit show (D27, D28; mirrors `line.build`). */
fun buildLine(
    amount: Long, kind: Kind, description: String, account: String, category: String? = null, date: LocalDate? = null,
): String = buildList {
    add((if (kind == Kind.INCOME) "+" else "") + Money.format(amount))
    if (description.isNotEmpty()) add(description)
    category?.let { add("#$it") }
    add("@$account")
    date?.let { add("%02d/%02d/%04d".format(it.dayOfMonth, it.monthValue, it.year)) }
}.joinToString(" ")
