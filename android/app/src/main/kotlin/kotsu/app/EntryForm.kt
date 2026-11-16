package kotsu.app

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotsu.core.Book
import kotsu.core.Entry
import kotsu.core.Kind
import kotsu.core.Line
import kotsu.core.LineError
import kotsu.core.Money
import kotsu.core.Scope
import java.time.LocalDate

/** What the full-screen entry form is doing (D45): a new entry, or editing one with its scope. */
sealed class FormTarget {
    data object New : FormTarget()
    data class Edit(val entry: Entry, val scope: Scope) : FormTarget()
}

/** The fields of the form, ready to save. `installments` only counts on a new entry. */
data class FormValues(
    val amount: Long, val kind: Kind, val description: String, val date: LocalDate,
    val account: String, val category: String?, val installments: Int,
)

/** Cents from "89,90", "1.234,56" or "12": the quick line's own amount rule; null when unreadable. */
internal fun parseAmount(text: String): Long? =
    if (text.isBlank()) null else runCatching { Line.parse(text.trim().removePrefix("+").removePrefix("-"), LocalDate.now()).amount }.getOrNull()

/**
 * The full-screen form to create or edit an entry (D45, Android only; the PC stays on the
 * quick line). Saving goes through [onSave]; dates are locked when the edit changes several
 * entries ("all" installments or "this and upcoming"), as in D28.
 */
@Composable
fun EntryForm(
    target: FormTarget,
    book: Book,
    p: Palette,
    today: LocalDate,
    version: Int = 0,
    error: String? = null,
    onSave: (FormValues) -> Unit,
    onCancel: () -> Unit,
    onDelete: (Entry) -> Unit = {},
    onNewAccount: (String, (String) -> Unit) -> Unit = { _, _ -> },
    onNewCategory: (String, (String) -> Unit) -> Unit = { _, _ -> },
    onPickDay: (LocalDate, (LocalDate) -> Unit) -> Unit = { _, _ -> },
) {
    val e = (target as? FormTarget.Edit)?.entry
    val scope = (target as? FormTarget.Edit)?.scope
    val locked = e != null && ((e.installment != null && scope == Scope.ALL) || (e.recurrence != null && scope == Scope.UPCOMING))

    var amount by remember(target) { mutableStateOf(e?.let { Money.format(it.amount) } ?: "") }
    var kind by remember(target) { mutableStateOf(e?.kind ?: Kind.EXPENSE) }
    var description by remember(target) { mutableStateOf(e?.description ?: "") }
    var date by remember(target) { mutableStateOf(e?.date ?: today) }
    var account by remember(target) { mutableStateOf(e?.account ?: book.accounts.firstOrNull()?.uid) }
    var category by remember(target) { mutableStateOf(e?.category) }
    var installments by remember(target) { mutableStateOf(1) }
    var naming by remember(target) { mutableStateOf<String?>(null) } // "account" or "category" while typing a new name
    var newName by remember(target) { mutableStateOf("") }

    val cents = parseAmount(amount)
    val recurringCategory = book.category(category)?.recurring == true
    val problem = when {
        cents == null -> "type the amount, e.g. 89,90"
        cents <= 0 -> "the amount must be more than zero"
        account == null || book.account(account!!) == null -> "pick an account (or + new)"
        e == null && recurringCategory && installments > 1 -> "#${book.category(category)!!.name} already repeats every month: use 1×"
        else -> null
    }

    fun save() {
        if (problem != null) return
        onSave(FormValues(cents!!, kind, description.trim(), date, account!!, category, if (e == null) installments else 1))
    }

    val field = Modifier.fillMaxWidth().border(1.dp, p.highlight, RoundedCornerShape(10.dp)).padding(12.dp)

    version.let { _ ->
    Column(Modifier.fillMaxSize().background(p.background).systemBarsPadding().imePadding()) {
        // Title bar: cancel, title, save.
        Row(Modifier.fillMaxWidth().background(p.surface).padding(horizontal = 8.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically) {
            T("✕ cancel", p.neutral, 14, bold = true, modifier = Modifier.clickable(onClick = onCancel).padding(8.dp))
            T(if (e == null) "☁ new entry" else "✎ edit entry", p.highlight, 16, bold = true,
                modifier = Modifier.weight(1f).wrapContentWidth())
            val ready = problem == null
            T("✓ save", if (ready) p.background else p.neutral, 14, bold = true,
                modifier = Modifier.background(if (ready) p.highlight else Color.Transparent, RoundedCornerShape(8.dp))
                    .border(1.dp, if (ready) p.highlight else p.neutral, RoundedCornerShape(8.dp))
                    .clickable(enabled = ready) { save() }.padding(horizontal = 12.dp, vertical = 6.dp))
        }

        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)) {

            // Installment / recurrence info: shown, not editable (D28).
            if (e != null && (e.installment != null || e.recurrence != null)) {
                val info = buildList {
                    e.installment?.let { add("installment ${it.label}") }
                    if (e.recurrence != null) add("↻ every month")
                    add(when {
                        scope == Scope.ALL -> "changing all ${e.installment!!.total} installments"
                        scope == Scope.UPCOMING -> "changing this month and the upcoming ones"
                        else -> "changing only this one"
                    })
                }.joinToString(" · ")
                T(info, p.warning, 12, lines = 2,
                    modifier = Modifier.fillMaxWidth().background(p.surface, RoundedCornerShape(8.dp)).padding(10.dp))
            }

            // Kind and amount.
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Chip("✧ expense", p.expense, p, on = kind == Kind.EXPENSE) { kind = Kind.EXPENSE }
                Chip("♡ income", p.income, p, on = kind == Kind.INCOME) { kind = Kind.INCOME }
            }
            Label("amount", p)
            Row(field, verticalAlignment = Alignment.CenterVertically) {
                T(if (kind == Kind.INCOME) "+ R$ " else "- R$ ", if (kind == Kind.INCOME) p.income else p.expense, 20, bold = true)
                BasicTextField(
                    amount, { t -> amount = t.filter { it.isDigit() || it == ',' || it == '.' } }, singleLine = true,
                    textStyle = TextStyle(color = if (kind == Kind.INCOME) p.income else p.expense, fontFamily = mono,
                        fontSize = 22.sp),
                    cursorBrush = SolidColor(p.highlight),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    modifier = Modifier.weight(1f),
                    decorationBox = { inner -> if (amount.isEmpty()) T("0,00", p.neutral, 22); inner() },
                )
            }

            Label("description", p)
            Box(field) {
                BasicTextField(
                    description, { description = it }, singleLine = true,
                    textStyle = TextStyle(color = p.text, fontFamily = mono, fontSize = 15.sp),
                    cursorBrush = SolidColor(p.highlight), modifier = Modifier.fillMaxWidth(),
                    decorationBox = { inner -> if (description.isEmpty()) T("groceries, rent, salary...", p.neutral, 15); inner() },
                )
            }

            Label("date", p)
            Row(
                field.then(if (locked) Modifier else Modifier.clickable { onPickDay(date) { date = it } }),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                T("%02d/%02d/%04d".format(date.dayOfMonth, date.monthValue, date.year), if (locked) p.neutral else p.text, 15,
                    modifier = Modifier.weight(1f))
                T(if (locked) "kept on each entry" else "▦ pick", if (locked) p.neutral else p.highlight, 12, bold = !locked)
            }

            Label("account", p)
            Flow {
                for (a in book.accounts) Chip(a.name, hex(a.color, p.highlight), p, on = account == a.uid) { account = a.uid }
                Chip("+ new", p.neutral, p) { naming = "account"; newName = "" }
            }
            if (naming == "account") NewName("new account name", newName, { newName = it }, p,
                onOk = { val n = newName.trim(); naming = null; if (n.isNotEmpty()) onNewAccount(n) { account = it } },
                onCancel = { naming = null })

            Label("category", p)
            Flow {
                Chip("none", p.neutral, p, on = category == null) { category = null }
                for (c in book.categories) Chip(c.name + if (c.recurring) " ↻" else "", p.secondary, p, on = category == c.uid) { category = c.uid }
                Chip("+ new", p.neutral, p) { naming = "category"; newName = "" }
            }
            if (naming == "category") NewName("new category name", newName, { newName = it }, p,
                onOk = { val n = newName.trim(); naming = null; if (n.isNotEmpty()) onNewCategory(n) { category = it } },
                onCancel = { naming = null })

            // Installments: only when creating (the count never changes on edit, D28).
            if (e == null) {
                Label("installments", p)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    T("−", p.highlight, 20, bold = true, modifier = Modifier.clickable { if (installments > 1) installments-- }
                        .border(1.dp, p.highlight, RoundedCornerShape(8.dp)).padding(horizontal = 14.dp, vertical = 2.dp))
                    T(if (installments == 1) "  once  " else "  ${installments}×  ", p.text, 16, bold = true)
                    T("+", p.highlight, 20, bold = true,
                        modifier = Modifier.clickable { if (installments < Line.MAX_INSTALLMENTS) installments++ }
                            .border(1.dp, p.highlight, RoundedCornerShape(8.dp)).padding(horizontal = 14.dp, vertical = 2.dp))
                    if (installments > 1 && cents != null) T("  ${Money.format(cents)} each", p.neutral, 12)
                }
                if (recurringCategory && installments == 1) T("↻ repeats every month (category)", p.neutral, 12)
            }

            val msg = error ?: problem
            if (msg != null) T(msg, if (error != null || amount.isNotEmpty()) p.expense else p.neutral, 12, lines = 3)

            if (e != null) {
                Spacer(Modifier.height(10.dp))
                T("✕ delete entry", p.expense, 14, bold = true,
                    modifier = Modifier.fillMaxWidth().border(1.dp, p.expense, RoundedCornerShape(10.dp))
                        .clickable { onDelete(e) }.padding(12.dp).wrapContentWidth())
            }
        }
    }
    }
}

@Composable
private fun Label(text: String, p: Palette) = T(text, p.secondary, 12, bold = true)

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun Flow(content: @Composable () -> Unit) =
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) { content() }

@Composable
private fun NewName(hint: String, value: String, onChange: (String) -> Unit, p: Palette, onOk: () -> Unit, onCancel: () -> Unit) {
    Row(Modifier.fillMaxWidth().border(1.dp, p.secondary, RoundedCornerShape(10.dp)).padding(10.dp),
        verticalAlignment = Alignment.CenterVertically) {
        BasicTextField(
            value, { t -> onChange(t.replace(" ", "")) }, singleLine = true,
            textStyle = TextStyle(color = p.text, fontFamily = mono, fontSize = 14.sp),
            cursorBrush = SolidColor(p.secondary), modifier = Modifier.weight(1f),
            decorationBox = { inner -> if (value.isEmpty()) T(hint, p.neutral, 14); inner() },
        )
        T("ok", p.background, 13, bold = true, modifier = Modifier.background(p.secondary, RoundedCornerShape(6.dp))
            .clickable(onClick = onOk).padding(horizontal = 10.dp, vertical = 4.dp))
        Spacer(Modifier.width(6.dp))
        T("✕", p.neutral, 13, bold = true, modifier = Modifier.clickable(onClick = onCancel).padding(horizontal = 6.dp))
    }
}
