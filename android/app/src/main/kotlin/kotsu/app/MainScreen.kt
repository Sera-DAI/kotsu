package kotsu.app

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicText
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.rememberSwipeToDismissBoxState
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotsu.core.Book
import kotsu.core.Entry
import kotsu.core.Filter
import kotsu.core.Kind
import kotsu.core.Line
import kotsu.core.LineError
import kotsu.core.Money
import kotsu.core.ParsedLine
import kotsu.core.Scope
import kotsu.core.buildLine
import java.time.LocalDate
import java.time.YearMonth

internal val mono = FontFamily.Monospace

@Composable
internal fun T(
    text: String, color: Color, size: Int = 14, bold: Boolean = false, modifier: Modifier = Modifier, lines: Int = 1,
) = BasicText(
    text, modifier, maxLines = lines, overflow = TextOverflow.Ellipsis,
    style = TextStyle(color = color, fontSize = size.sp, fontFamily = mono,
        fontWeight = if (bold) FontWeight.Bold else FontWeight.Normal),
)

/** `#8a2be2` to a Compose color; anything unreadable becomes the theme's highlight. */
internal fun hex(color: String, fallback: Color): Color =
    color.removePrefix("#").takeIf { it.length == 6 }?.toLongOrNull(16)?.let { Color(0xFF000000 or it) } ?: fallback

/** Replaces the `#…` or `@…` word in the line, or appends it. */
private fun putToken(line: String, token: String): String {
    val parts = line.trim().split(Regex("""\s+""")).filter { it.isNotEmpty() }
    val prefix = token.first()
    val i = parts.indexOfFirst { it.startsWith(prefix) }
    val out = parts.toMutableList()
    if (i >= 0) out[i] = token else out.add(token)
    return out.joinToString(" ") + " "
}

/** An installment with ALL, or a recurring entry with UPCOMING: several entries, dates kept. */
private fun many(e: Entry, scope: Scope) =
    (e.installment != null && scope == Scope.ALL) || (e.recurrence != null && scope == Scope.UPCOMING)

/**
 * The main screen (D4) with the quick line (D10), the touch menus and the exchange (D39).
 * Every change goes to [book], which saves it on the phone right away.
 */
@OptIn(ExperimentalFoundationApi::class, ExperimentalMaterial3Api::class)
@Composable
fun MainScreen(
    book: Book,
    today: LocalDate = LocalDate.now(),
    startDark: Boolean = true,
    initialLine: String = "",
    initialFilter: Filter = Filter(),
    initialMenuFor: String? = null,
    initialAsk: Ask? = null,
    initialForm: FormTarget? = null,
    onExport: () -> Unit = {},
    onImport: () -> Unit = {},
    outsideMessage: String? = null,
    outsideAsk: Ask? = null,
    onOutsideMessageSeen: () -> Unit = {},
    outsideChange: Int = 0,
) {
    var dark by remember { mutableStateOf(startDark) }
    val p = if (dark) CottonCandyNight else CottonCandyLight
    var month by remember { mutableStateOf(YearMonth.from(today)) }
    var version by remember { mutableStateOf(0) } // bumps after every change, to redraw
    var line by remember { mutableStateOf(initialLine) }
    var filter by remember { mutableStateOf(initialFilter) }
    var searching by remember { mutableStateOf(initialFilter.text.isNotEmpty()) }
    var menuFor by remember { mutableStateOf(initialMenuFor) }
    var topMenu by remember { mutableStateOf(false) }
    var categoryMenu by remember { mutableStateOf(false) }
    var form by remember { mutableStateOf(initialForm) }
    var formError by remember { mutableStateOf<String?>(null) }
    var notice by remember { mutableStateOf<String?>(null) }
    var ask by remember { mutableStateOf(initialAsk) }

    // Recurring entries are generated while browsing (D36), up to today + 24 months.
    remember(month, version, outsideChange) { book.extendRecurrences(month, today) }

    fun changed() { version++ }

    val shown = book.monthEntries(month, filter)
    val totals = book.totals(month, filter)
    val byAccount = book.totalsByAccount(month, filter)
    val accounts = book.accounts.filter { filter.account == null || it.uid == filter.account }
    val categories = book.categories
    fun accountName(uid: String) = book.account(uid)?.name ?: "?"
    fun accountColor(uid: String?) = uid?.let(book::account)?.let { hex(it.color, p.highlight) } ?: p.highlight

    val preview: Result<ParsedLine>? = if (line.isBlank()) null else runCatching {
        Line.parse(line, today)
    }

    // --- saving: asks for what is missing first (new account, new category) ------------

    fun resolve(l: ParsedLine, then: (String, String?) -> Unit) {
        val name = l.account ?: run { notice = "give the account with @name"; return }
        fun withCategory(accountUid: String) {
            val cat = l.category ?: return then(accountUid, null)
            book.categoryByName(cat)?.let { return then(accountUid, it.uid) }
            ask = Ask.Question("Create the category $cat?", listOf("create" to {
                ask = Ask.Question(
                    "Repeat the entries of $cat every month?\nRent, internet, salary...",
                    listOf("every month" to true, "no" to false).map { (label, repeat) ->
                        label to { ask = null; then(accountUid, book.createCategory(cat, repeat).uid); changed() }
                    },
                )
            }, "cancel" to { ask = null; notice = "cancelled: nothing was saved" }))
        }
        val existing = book.accountByName(name)
        if (existing != null) return withCategory(existing.uid)
        ask = Ask.NewAccount(name, book.suggestedColor()) { color ->
            ask = null
            if (color == null) { notice = "cancelled: nothing was saved"; return@NewAccount }
            withCategory(book.createAccount(name, color).uid)
            changed()
        }
    }

    fun save() {
        val l = preview?.getOrNull() ?: return
        resolve(l) { accountUid, categoryUid ->
            try {
                val saved = book.add(l, accountUid, categoryUid)
                val every = saved[0].recurrence != null
                notice = "saved: ${Money.format(l.amount)} ${l.description}" +
                    if (every) " · every month" else if (saved.size > 1) " · ${saved.size}×" else ""
                month = YearMonth.from(l.date)
                line = ""
            } catch (e: LineError) {
                notice = e.message
            }
            changed()
        }
    }

    /** "Only this one or all?" (D12) or "only this month or the upcoming ones?" (D36); a plain entry asks nothing. */
    fun withScope(e: Entry, action: String, plain: Scope, then: (Scope) -> Unit) {
        val choose = { s: Scope -> { ask = null; then(s) } }
        ask = when {
            e.installment != null -> Ask.Question(
                "$action installment ${e.installment!!.label}: only this one or all?",
                listOf("all" to choose(Scope.ALL), "only this" to choose(Scope.ONLY_THIS), "cancel" to { ask = null }),
            )
            e.recurrence != null -> Ask.Question(
                "$action the entry that repeats every month: only this month or the upcoming ones?",
                listOf("only this month" to choose(Scope.ONLY_THIS), "this and upcoming" to choose(Scope.UPCOMING), "cancel" to { ask = null }),
            )
            else -> { then(plain); null }
        }
    }

    fun delete(e: Entry) {
        val run = { s: Scope ->
            val n = book.delete(e.uid, s)
            notice = "deleted: ${e.description.ifEmpty { "(no description)" }}" + if (n > 1) " ($n entries)" else ""
            if ((form as? FormTarget.Edit)?.entry?.uid == e.uid) form = null
            changed()
        }
        if (e.installment == null && e.recurrence == null) {
            ask = Ask.Question("Delete ${e.description.ifEmpty { "this entry" }} (${Money.format(e.amount)})?",
                listOf("delete" to { ask = null; run(Scope.ONLY_THIS) }, "cancel" to { ask = null }))
        } else {
            withScope(e, "Delete", Scope.ONLY_THIS, run)
        }
    }

    fun edit(e: Entry) = withScope(e, "Edit", Scope.ONLY_THIS) { s -> formError = null; form = FormTarget.Edit(e, s) }

    /** Saves the full-screen form (D45): the same [Book.add] and [Book.edit] as the quick line. */
    fun saveForm(v: FormValues) {
        val target = form ?: return
        try {
            when (target) {
                is FormTarget.Edit -> {
                    val (e, s) = target
                    val n = book.edit(e.uid, Book.Change(v.date, v.description, v.amount, v.kind, v.account, v.category), s)
                    notice = "edited: ${v.description.ifEmpty { "(no description)" }}" + if (n > 1) " ($n entries)" else ""
                    if (!many(e, s)) month = YearMonth.from(v.date)
                }
                FormTarget.New -> {
                    val parsed = ParsedLine(v.amount, v.kind, v.description, v.date, installments = v.installments, hasDate = true)
                    val saved = book.add(parsed, v.account, v.category)
                    notice = "saved: ${Money.format(v.amount)} ${v.description}" +
                        if (saved[0].recurrence != null) " · every month" else if (saved.size > 1) " · ${saved.size}×" else ""
                    month = YearMonth.from(v.date)
                }
            }
            form = null
            formError = null
        } catch (e: IllegalArgumentException) {
            formError = e.message
        }
        changed()
    }

    fun formNewAccount(name: String, picked: (String) -> Unit) {
        book.accountByName(name)?.let { return picked(it.uid) }
        ask = Ask.NewAccount(name, book.suggestedColor()) { color ->
            ask = null
            if (color != null) { picked(book.createAccount(name, color).uid); changed() }
        }
    }

    fun formNewCategory(name: String, picked: (String) -> Unit) {
        book.categoryByName(name)?.let { return picked(it.uid) }
        ask = Ask.Question("Repeat the entries of $name every month?\nRent, internet, salary...",
            listOf("every month" to true, "no" to false).map { (label, repeat) ->
                label to { ask = null; picked(book.createCategory(name, repeat).uid); changed() }
            } + ("cancel" to { ask = null }))
    }

    /** Long-press on an account: delete it with everything in it (D44), after asking. */
    fun askDeleteAccount(uid: String) {
        val a = book.account(uid) ?: return
        val n = book.accountUse(uid)
        val what = if (n == 0) "It has no entries." else "Its $n ${if (n == 1) "entry goes" else "entries go"} with it, in every month."
        ask = Ask.Question("Delete the account ${a.name}?\n$what\nOn the PC it goes away on the next exchange.", listOf(
            "delete" to {
                ask = null
                val gone = book.deleteAccount(uid)
                if (filter.account == uid) filter = filter.copy(account = null)
                notice = "account ${a.name} deleted ($gone ${if (gone == 1) "entry" else "entries"})"
                changed()
            },
            "cancel" to { ask = null },
        ))
    }

    // --- pieces -------------------------------------------------------------------------

    val header: @Composable () -> Unit = {
        Row(verticalAlignment = Alignment.CenterVertically) {
            T("☁ Kotsu ☁", p.highlight, 16, bold = true)
            Spacer(Modifier.weight(1f))
            T("+", p.background, 18, bold = true, modifier = Modifier.background(p.highlight, RoundedCornerShape(8.dp))
                .clickable { formError = null; form = FormTarget.New }.padding(horizontal = 10.dp))
            T("‹", p.highlight, 20, modifier = Modifier.clickable { month = month.minusMonths(1) }.padding(8.dp))
            T(" %02d/%d ".format(month.monthValue, month.year), p.background, 14, bold = true,
                modifier = Modifier.background(p.highlight).clickable {
                    ask = Ask.MonthPicker(month, YearMonth.from(today)) { picked -> ask = null; if (picked != null) month = picked }
                }
                    .padding(horizontal = 6.dp, vertical = 2.dp))
            T("›", p.highlight, 20, modifier = Modifier.clickable { month = month.plusMonths(1) }.padding(8.dp))
            T("⌕", p.secondary, 20, modifier = Modifier.clickable {
                searching = !searching
                if (!searching) filter = filter.copy(text = "")
            }.padding(8.dp))
            Box {
                T("⋯", p.warning, 20, bold = true, modifier = Modifier.clickable { topMenu = true }.padding(8.dp))
                DropdownMenu(topMenu, { topMenu = false }, Modifier.background(p.surface)) {
                    DropdownMenuItem(text = { T(if (dark) "☀ light theme" else "☾ night theme", p.text) },
                        onClick = { dark = !dark; topMenu = false })
                    DropdownMenuItem(text = { T("# filter by category", p.text) },
                        onClick = { topMenu = false; categoryMenu = true })
                    DropdownMenuItem(text = { T("↻ every-month categories", p.text) },
                        onClick = { topMenu = false; ask = Ask.Categories })
                    DropdownMenuItem(text = { T("⇪ export exchange file", p.text) },
                        onClick = { topMenu = false; onExport() })
                    DropdownMenuItem(text = { T("⇩ import exchange file", p.text) },
                        onClick = { topMenu = false; onImport() })
                    DropdownMenuItem(text = { T("✓ check code", p.text) }, onClick = {
                        topMenu = false
                        ask = Ask.Message("Check code: ${book.checkCode()}\nThe same code on the PC (key v) = the same data.")
                    })
                }
            }
        }
    }

    val summary: @Composable () -> Unit = {
        Column {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Total("♡ income", Money.format(totals.income), p.secondary, p.income)
                Total("✧ expenses", Money.format(totals.expenses), p.secondary, p.expense)
                Total("☆ balance", (if (totals.balance < 0) "-" else "") + Money.format(totals.balance),
                    p.secondary, if (totals.balance >= 0) p.income else p.expense)
            }
            Spacer(Modifier.height(10.dp))
            if (accounts.isEmpty()) T("No accounts yet: type an entry with @account.", p.neutral, 12)
            val biggest = byAccount.values.maxOfOrNull { maxOf(it.income, it.expenses) }?.coerceAtLeast(1) ?: 1
            Column(Modifier.heightIn(max = 160.dp).verticalScroll(rememberScrollState())) {
                for (a in accounts) {
                    val color = hex(a.color, p.highlight)
                    val on = filter.account == a.uid
                    val t = byAccount[a.uid]
                    Row(
                        Modifier.fillMaxWidth()
                            .background(if (on) p.panel else Color.Transparent, RoundedCornerShape(6.dp))
                            .combinedClickable(
                                onClick = { filter = filter.copy(account = if (on) null else a.uid) },
                                onLongClick = { askDeleteAccount(a.uid) },
                            )
                            .padding(vertical = 5.dp, horizontal = 4.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        T(if (on) "♥ " else "♡ ", color); T(a.name, color, bold = true, modifier = Modifier.width(80.dp))
                        if (t == null) {
                            Spacer(Modifier.weight(1f)); T("zzz… zeroed", p.neutral)
                        } else {
                            val full = (t.expenses * 9 / biggest).toInt().coerceIn(if (t.expenses > 0) 1 else 0, 9)
                            T("♥".repeat(full) + "·".repeat(9 - full), color, 12, modifier = Modifier.weight(1f))
                            if (t.income > 0) T("+" + Money.format(t.income) + " ", p.income, 12)
                            if (t.expenses > 0) T(Money.format(t.expenses), p.expense, 12)
                        }
                    }
                }
            }
        }
    }

    val list: @Composable (Modifier) -> Unit = { mod ->
        Column(mod.fillMaxWidth().border(1.dp, p.highlight).background(p.surface)) {
            Row(Modifier.fillMaxWidth().padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
                T("entries", p.highlight, 13, bold = true)
                Spacer(Modifier.width(8.dp))
                T("← swipe month →", p.neutral, 11)
                Spacer(Modifier.weight(1f))
                Box {
                    val cat = book.category(filter.category)
                    Chip(if (cat == null) "# category ▾" else "#${cat.name} ▾", p.secondary, p, on = cat != null) {
                        categoryMenu = true
                    }
                    DropdownMenu(categoryMenu, { categoryMenu = false }, Modifier.background(p.surface)) {
                        if (book.categories.isEmpty()) {
                            DropdownMenuItem(text = { T("no categories yet: type #category in an entry", p.neutral, 12) },
                                onClick = { categoryMenu = false })
                        }
                        if (filter.category != null) {
                            DropdownMenuItem(text = { T("✕ all categories", p.warning) },
                                onClick = { categoryMenu = false; filter = filter.copy(category = null) })
                        }
                        for (c in book.categories) {
                            val on = filter.category == c.uid
                            DropdownMenuItem(text = { T((if (on) "♥ #" else "♡ #") + c.name, p.secondary, bold = on) },
                                onClick = { categoryMenu = false; filter = filter.copy(category = if (on) null else c.uid) })
                        }
                    }
                }
                Spacer(Modifier.width(8.dp))
                T(if (totals.balance >= 0) "(◕‿◕)♡" else "(；ω；)", p.warning, 13)
            }
            if (searching) {
                Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp)
                    .border(1.dp, p.secondary).padding(6.dp)) {
                    T("⌕ ", p.secondary)
                    BasicTextField(
                        filter.text, { filter = filter.copy(text = it) }, singleLine = true,
                        textStyle = TextStyle(color = p.text, fontFamily = mono, fontSize = 13.sp),
                        cursorBrush = SolidColor(p.secondary), modifier = Modifier.weight(1f),
                        decorationBox = { inner -> if (filter.text.isEmpty()) T("search description", p.neutral, 13); inner() },
                    )
                }
            }
            if (filter.account != null || filter.category != null) {
                Row(Modifier.padding(horizontal = 8.dp, vertical = 2.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    filter.account?.let { Chip("@${accountName(it)} ✕", accountColor(it), p, on = true) { filter = filter.copy(account = null) } }
                    filter.category?.let { c ->
                        Chip("#${book.category(c)?.name ?: "?"} ✕", p.secondary, p, on = true) { filter = filter.copy(category = null) }
                    }
                }
            }
            if (shown.isEmpty()) {
                T(if (filter.active) "  nothing matches the filter" else "  nothing this month yet", p.neutral, 13,
                    modifier = Modifier.padding(8.dp))
            }
            LazyColumn {
                itemsIndexed(shown, key = { _, e -> e.uid + version }) { i, e ->
                    val dismiss = rememberSwipeToDismissBoxState(confirmValueChange = {
                        if (it == SwipeToDismissBoxValue.EndToStart) delete(e)
                        false // the row comes back; the question decides
                    })
                    SwipeToDismissBox(
                        dismiss, enableDismissFromStartToEnd = false,
                        backgroundContent = {
                            Box(Modifier.fillMaxSize().background(p.expense).padding(horizontal = 12.dp),
                                contentAlignment = Alignment.CenterEnd) { T("delete ✕", p.background, bold = true) }
                        },
                    ) {
                        val open = menuFor == e.uid
                        val sel = open || (form as? FormTarget.Edit)?.entry?.uid == e.uid
                        val bg = when {
                            sel -> p.highlight
                            i % 2 == 0 -> p.background
                            else -> p.surface
                        }
                        val fg = if (sel) p.background else p.text
                        val dim = if (sel) p.background else p.neutral
                        Box {
                            Column(Modifier.fillMaxWidth().background(bg)
                                .combinedClickable(onClick = { menuFor = e.uid }, onLongClick = { menuFor = e.uid })
                                .padding(horizontal = 8.dp, vertical = 6.dp)) {
                                Row {
                                    T(e.description.ifEmpty { "—" }, fg, modifier = Modifier.weight(1f))
                                    e.installment?.let { T(" ${it.label} ", dim, 12) }
                                    if (e.recurrence != null) T(" ↻ ", dim, 12)
                                    T((if (e.kind == Kind.INCOME) "+" else "-") + Money.format(e.amount),
                                        if (sel) p.background else if (e.kind == Kind.INCOME) p.income else p.expense, bold = true)
                                }
                                Row {
                                    T("%02d/%02d · ".format(e.date.dayOfMonth, e.date.monthValue), dim, 11)
                                    val cat = book.category(e.category)
                                    T(cat?.name ?: "no category", dim, 11,
                                        modifier = Modifier.clickable(enabled = cat != null) { filter = filter.copy(category = e.category) })
                                    T(" · ", dim, 11)
                                    T(accountName(e.account), if (sel) p.background else accountColor(e.account), 11, bold = true,
                                        modifier = Modifier.clickable { filter = filter.copy(account = e.account) })
                                }
                            }
                            DropdownMenu(open, { menuFor = null }, Modifier.background(p.surface)) {
                                DropdownMenuItem(text = { T("✎ edit", p.text) }, onClick = { menuFor = null; edit(e) })
                                DropdownMenuItem(text = { T("⧉ copy to today", p.text) }, onClick = {
                                    menuFor = null
                                    line = buildLine(e.amount, e.kind, e.description, accountName(e.account), book.category(e.category)?.name)
                                })
                                if (e.installment == null && e.recurrence == null) {
                                    DropdownMenuItem(text = { T("↻ repeat every month", p.text) }, onClick = {
                                        menuFor = null
                                        if (book.makeRecurring(e.uid)) { notice = "repeats every month from ${"%02d/%d".format(e.date.monthValue, e.date.year)}"; changed() }
                                    })
                                }
                                DropdownMenuItem(text = { T("✕ delete", p.expense) }, onClick = { menuFor = null; delete(e) })
                            }
                        }
                    }
                }
            }
        }
    }

    val quick: @Composable () -> Unit = {
        Column {
            // Chips that complete the line: accounts, then categories.
            Row(Modifier.horizontalScroll(rememberScrollState()).padding(vertical = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                val current = preview?.getOrNull()
                for (a in book.accounts) Chip("@${a.name}", hex(a.color, p.highlight), p,
                    on = current?.account?.let { book.accountByName(it)?.uid } == a.uid) { line = putToken(line, "@${a.name}") }
                for (c in categories) Chip("#${c.name}" + if (c.recurring) " ↻" else "", p.secondary, p,
                    on = current?.category?.let { book.categoryByName(it)?.uid } == c.uid) { line = putToken(line, "#${c.name}") }
            }
            Column(Modifier.fillMaxWidth().border(1.dp, p.highlight).padding(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    T("› ", p.highlight)
                    BasicTextField(
                        value = line, onValueChange = { line = it; notice = null }, singleLine = true,
                        textStyle = TextStyle(color = p.text, fontFamily = mono, fontSize = 14.sp),
                        cursorBrush = SolidColor(p.highlight),
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                        keyboardActions = KeyboardActions(onDone = { save() }),
                        modifier = Modifier.weight(1f),
                        decorationBox = { inner ->
                            if (line.isEmpty()) T("89,90 groceries #food @nubank", p.neutral)
                            inner()
                        },
                    )
                    val ready = preview?.getOrNull()?.account != null
                    T(if (ready) "✓" else "", p.background, 14, bold = true,
                        modifier = Modifier.background(if (ready) p.highlight else Color.Transparent, RoundedCornerShape(6.dp))
                            .clickable(enabled = ready) { save() }.padding(horizontal = 10.dp, vertical = 2.dp))
                }
                val hint = when {
                    preview == null -> notice ?: "tap a chip or type; ✓ saves · + opens the full form"
                    preview.isFailure -> (preview.exceptionOrNull() as? LineError)?.message ?: "?"
                    preview.getOrNull()!!.account == null -> "missing the @account (tap one above)"
                    else -> preview.getOrNull()!!.let { l ->
                        val k = if (l.kind == Kind.INCOME) "income" else "expense"
                        val n = if (l.installments > 1) " ${l.installments}×" else ""
                        val acc = book.accountByName(l.account!!)?.name ?: "${l.account} (new)"
                        val catObj = l.category?.let(book::categoryByName)
                        val cat = l.category?.let { catObj?.name ?: "$it (new)" } ?: "no category"
                        val period = when {
                            catObj?.recurring == true && l.installments == 1 ->
                                "%02d/%02d, and every month".format(l.date.dayOfMonth, l.date.monthValue)
                            else -> "%02d/%02d".format(l.date.dayOfMonth, l.date.monthValue)
                        }
                        "preview: " + "$k$n ${Money.format(l.amount)} · $cat · $acc · $period"
                    }
                }
                val bad = preview != null && (preview.isFailure || preview.getOrNull()?.account == null)
                T(hint, if (bad) p.expense else p.neutral, 11, lines = 2)
            }
        }
    }

    // --- layout -------------------------------------------------------------------------

    val opened = form
    if (opened != null) {
        BackHandler { form = null }
        EntryForm(
            opened, book, p, today, version, formError,
            onSave = ::saveForm,
            onCancel = { form = null },
            onDelete = { delete(it) },
            onNewAccount = ::formNewAccount,
            onNewCategory = ::formNewCategory,
            onPickDay = { current, picked ->
                ask = Ask.DayPicker(current, today) { d -> ask = null; if (d != null) picked(d) }
            },
        )
    } else BoxWithConstraints(
        Modifier.fillMaxSize().background(p.background).systemBarsPadding().imePadding()
            // A hardware keyboard still has the PC keys when the line is empty.
            .onPreviewKeyEvent { ev ->
                if (ev.type != KeyEventType.KeyDown || line.isNotEmpty() || searching || ask != null) return@onPreviewKeyEvent false
                when (ev.key) {
                    Key.T -> { dark = !dark; true }
                    Key.V -> { ask = Ask.Message("Check code: ${book.checkCode()}"); true }
                    Key.DirectionLeft -> { month = month.minusMonths(1); true }
                    Key.DirectionRight -> { month = month.plusMonths(1); true }
                    Key.Slash -> { searching = true; true }
                    Key.Escape -> if (filter.active) { filter = Filter(); searching = false; true } else false
                    else -> false
                }
            }
            .pointerInput(Unit) {
                var total = 0f
                detectHorizontalDragGestures(
                    onDragStart = { total = 0f },
                    onDragEnd = {
                        if (total > 120) month = month.minusMonths(1)
                        if (total < -120) month = month.plusMonths(1)
                    },
                ) { _, amount -> total += amount }
            },
    ) {
        val wide = maxWidth > maxHeight
        if (wide) {
            Row(Modifier.fillMaxSize().padding(horizontal = 14.dp, vertical = 10.dp)) {
                Column(Modifier.weight(0.42f).fillMaxHeight()) {
                    header(); Spacer(Modifier.height(10.dp)); summary()
                    Spacer(Modifier.weight(1f)); quick()
                }
                Spacer(Modifier.width(14.dp))
                list(Modifier.weight(0.58f).fillMaxHeight())
            }
        } else {
            Column(Modifier.fillMaxSize().padding(horizontal = 14.dp, vertical = 10.dp)) {
                header(); Spacer(Modifier.height(10.dp)); summary()
                Spacer(Modifier.height(10.dp))
                list(Modifier.weight(1f))
                Spacer(Modifier.height(6.dp))
                quick()
            }
        }
    }

    val shownAsk = ask ?: outsideAsk ?: outsideMessage?.let { Ask.Message(it) }
    if (shownAsk != null) {
        AskDialog(shownAsk, p, book, onClose = {
            if (ask == null) onOutsideMessageSeen()
            ask = null
            changed()
        }, onChanged = ::changed)
    }
}

@Composable
internal fun Chip(text: String, color: Color, p: Palette, on: Boolean = false, onClick: () -> Unit) {
    T(text, if (on) p.background else color, 12, bold = true,
        modifier = Modifier
            .background(if (on) color else Color.Transparent, RoundedCornerShape(12.dp))
            .border(1.dp, color, RoundedCornerShape(12.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 10.dp, vertical = 3.dp))
}

@Composable
private fun Total(label: String, value: String, labelColor: Color, valueColor: Color) {
    Column {
        T(label, labelColor, 12)
        T(value, valueColor, 15, bold = true)
    }
}
