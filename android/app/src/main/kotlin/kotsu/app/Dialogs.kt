package kotsu.app

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import kotsu.core.Book
import java.time.LocalDate
import java.time.YearMonth

/** A question on top of the main screen. The answers run the next step of the action. */
sealed class Ask {
    /** A question with answers; the first is the default (like Enter on the PC). */
    class Question(val text: String, val options: List<Pair<String, () -> Unit>>) : Ask()

    /** A new account: confirm and pick its color (D3, D22). `done(null)` cancels. */
    class NewAccount(val name: String, val suggested: String, val done: (String?) -> Unit) : Ask()

    class Message(val text: String) : Ask()

    /** Picks a month and year to jump to; `done(null)` cancels. */
    class MonthPicker(val current: YearMonth, val today: YearMonth, val done: (YearMonth?) -> Unit) : Ask()

    /** Picks a day, in the style of [MonthPicker] (D45); `done(null)` cancels. */
    class DayPicker(val current: LocalDate, val today: LocalDate, val done: (LocalDate?) -> Unit) : Ask()

    /** Marks or unmarks "every month" on each category (D36, key `m` on the PC). */
    data object Categories : Ask()
}

@Composable
fun AskDialog(ask: Ask, p: Palette, book: Book, onClose: () -> Unit, onChanged: () -> Unit) {
    val dismiss = when (ask) {
        is Ask.NewAccount -> { { ask.done(null) } }
        is Ask.MonthPicker -> { { ask.done(null) } }
        is Ask.DayPicker -> { { ask.done(null) } }
        else -> onClose
    }
    Dialog(onDismissRequest = dismiss) { AskCard(ask, p, book, onClose, onChanged) }
}

/** The dialog's content, drawn by itself so screenshots can show it. */
@Composable
fun AskCard(ask: Ask, p: Palette, book: Book, onClose: () -> Unit = {}, onChanged: () -> Unit = {}) {
    Column(
        Modifier.fillMaxWidth().background(p.surface, RoundedCornerShape(14.dp))
            .border(1.dp, p.highlight, RoundedCornerShape(14.dp)).padding(16.dp),
    ) {
        when (ask) {
            is Ask.Question -> {
                T(ask.text, p.text, 14, lines = 6)
                Spacer(Modifier.height(14.dp))
                Answers(p, ask.options)
            }
            is Ask.Message -> {
                T(ask.text, p.text, 14, lines = 8)
                Spacer(Modifier.height(14.dp))
                Answers(p, listOf("ok" to onClose))
            }
            is Ask.NewAccount -> {
                var color by remember { mutableStateOf(ask.suggested) }
                T("Create the account ${ask.name}?", p.text, 14, bold = true, lines = 2)
                Spacer(Modifier.height(4.dp))
                T("Its color on every screen:", p.neutral, 12)
                Spacer(Modifier.height(10.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    for (c in Book.ACCOUNT_COLORS) {
                        val col = hex(c, p.highlight)
                        Box(
                            Modifier.size(28.dp).background(col, RoundedCornerShape(14.dp))
                                .border(if (c == color) 3.dp else 0.dp, p.text, RoundedCornerShape(14.dp))
                                .clickable { color = c },
                        )
                    }
                }
                Spacer(Modifier.height(10.dp))
                T("♡ ${ask.name}", hex(color, p.highlight), 15, bold = true)
                Spacer(Modifier.height(14.dp))
                Answers(p, listOf("create" to { ask.done(color) }, "cancel" to { ask.done(null) }))
            }
            is Ask.MonthPicker -> {
                var year by remember { mutableStateOf(ask.current.year) }
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    T("‹", p.highlight, 22, modifier = Modifier.clickable { year-- }.padding(horizontal = 14.dp, vertical = 4.dp))
                    T("$year", p.highlight, 18, bold = true, modifier = Modifier.weight(1f).wrapContentWidth())
                    T("›", p.highlight, 22, modifier = Modifier.clickable { year++ }.padding(horizontal = 14.dp, vertical = 4.dp))
                }
                Spacer(Modifier.height(10.dp))
                val names = listOf("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
                for (row in 0 until 4) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        for (col in 0 until 3) {
                            val m = YearMonth.of(year, row * 3 + col + 1)
                            val on = m == ask.current
                            val now = m == ask.today
                            Box(
                                Modifier.weight(1f).padding(vertical = 4.dp)
                                    .background(if (on) p.highlight else p.surface, RoundedCornerShape(8.dp))
                                    .border(1.dp, if (on || now) p.highlight else p.neutral, RoundedCornerShape(8.dp))
                                    .clickable { ask.done(m) }.padding(vertical = 10.dp),
                                contentAlignment = Alignment.Center,
                            ) {
                                T(names[row * 3 + col], if (on) p.background else if (now) p.highlight else p.text, 14, bold = on || now)
                            }
                        }
                    }
                }
                Spacer(Modifier.height(14.dp))
                Answers(p, listOf("today" to { ask.done(ask.today) }, "cancel" to { ask.done(null) }))
            }
            is Ask.DayPicker -> {
                var shown by remember { mutableStateOf(YearMonth.from(ask.current)) }
                val names = listOf("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    T("‹", p.highlight, 22, modifier = Modifier.clickable { shown = shown.minusMonths(1) }.padding(horizontal = 14.dp, vertical = 4.dp))
                    T("${names[shown.monthValue - 1]} ${shown.year}", p.highlight, 18, bold = true, modifier = Modifier.weight(1f).wrapContentWidth())
                    T("›", p.highlight, 22, modifier = Modifier.clickable { shown = shown.plusMonths(1) }.padding(horizontal = 14.dp, vertical = 4.dp))
                }
                Spacer(Modifier.height(8.dp))
                Row(Modifier.fillMaxWidth()) {
                    for (d in listOf("mo", "tu", "we", "th", "fr", "sa", "su"))
                        T(d, p.neutral, 12, modifier = Modifier.weight(1f).wrapContentWidth())
                }
                val lead = shown.atDay(1).dayOfWeek.value - 1 // Monday first
                val cells = lead + shown.lengthOfMonth()
                for (row in 0 until (cells + 6) / 7) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        for (col in 0 until 7) {
                            val day = row * 7 + col - lead + 1
                            if (day < 1 || day > shown.lengthOfMonth()) { Spacer(Modifier.weight(1f)); continue }
                            val d = shown.atDay(day)
                            val on = d == ask.current
                            val now = d == ask.today
                            Box(
                                Modifier.weight(1f).padding(vertical = 3.dp)
                                    .background(if (on) p.highlight else p.surface, RoundedCornerShape(8.dp))
                                    .border(1.dp, if (on || now) p.highlight else p.neutral, RoundedCornerShape(8.dp))
                                    .clickable { ask.done(d) }.padding(vertical = 8.dp),
                                contentAlignment = Alignment.Center,
                            ) {
                                T("$day", if (on) p.background else if (now) p.highlight else p.text, 13, bold = on || now)
                            }
                        }
                    }
                }
                Spacer(Modifier.height(14.dp))
                Answers(p, listOf("today" to { ask.done(ask.today) }, "cancel" to { ask.done(null) }))
            }
            Ask.Categories -> {
                T("Every-month categories", p.highlight, 14, bold = true)
                T("A new entry in one of them repeats every month (rent, internet, salary...).", p.neutral, 12, lines = 3)
                Spacer(Modifier.height(10.dp))
                var tick by remember { mutableStateOf(0) }
                Column(Modifier.heightIn(max = 320.dp).verticalScroll(rememberScrollState())) {
                    tick.let { _ ->
                        if (book.categories.isEmpty()) T("No categories yet: type #name in an entry.", p.neutral, 13, lines = 2)
                        for (c in book.categories) {
                            Row(
                                Modifier.fillMaxWidth().clickable {
                                    book.setRecurring(c.uid, !c.recurring); tick++; onChanged()
                                }.padding(vertical = 8.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                T("#${c.name}", p.secondary, 14, bold = true, modifier = Modifier.weight(1f))
                                T(if (c.recurring) "↻ every month" else "once", if (c.recurring) p.highlight else p.neutral, 13)
                            }
                        }
                    }
                }
                T("Turning it off does not end series already running.", p.neutral, 11, lines = 2)
                Spacer(Modifier.height(10.dp))
                Answers(p, listOf("done" to onClose))
            }
        }
    }
}

@Composable
private fun Answers(p: Palette, options: List<Pair<String, () -> Unit>>) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.End)) {
        options.forEachIndexed { i, (label, run) ->
            val main = i == 0
            T(label, if (main) p.background else p.highlight, 14, bold = true,
                modifier = Modifier.background(if (main) p.highlight else p.surface, RoundedCornerShape(8.dp))
                    .border(1.dp, p.highlight, RoundedCornerShape(8.dp))
                    .clickable(onClick = run).padding(horizontal = 12.dp, vertical = 6.dp))
        }
    }
}
