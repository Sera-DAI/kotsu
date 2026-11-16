package kotsu.core

import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import java.time.LocalDate

/** An exchange file that cannot be used. The message is shown to the person as is. */
class ExchangeError(message: String) : IllegalArgumentException(message)

/**
 * Reading, checking and writing the exchange file (D39), format 2 with English keys.
 * Mirrors kotsu.domain.merge.validate and kotsu.storage.exchange; checked by
 * vectors/invalid.json and vectors/merge.json. Format 1 files (Portuguese keys) are translated.
 */
object Exchange {
    private val STAMP = Regex("""\d{13}-\d{4}-[0-9a-f]{8}""")
    private val KINDS = setOf("income", "expense")
    val SECTIONS = listOf("accounts", "categories", "recurrences", "entries", "tombstones")

    /** A missing key, reported like Python's KeyError: `('date')`. */
    private class Missing(val key: String) : RuntimeException(key)

    // --- reading ----------------------------------------------------------------------

    /** Parses and validates the text of an exchange file. Raises [ExchangeError]. */
    fun read(text: String): State {
        val data = try {
            JSONObject(text)
        } catch (e: JSONException) {
            throw ExchangeError("this file is not a Kotsu export")
        }
        return validate(data)
    }

    /** Checks a decoded file (a JSONObject, or anything else) and returns its state. */
    fun validate(value: Any?): State {
        if (value !is JSONObject || value.opt("app") != "kotsu") throw ExchangeError("this file is not a Kotsu export")
        var obj: JSONObject = value
        val fmt = if (obj.has("format")) obj.opt("format") else obj.opt("formato")
        if (!(fmt is Int || fmt is Long) || (fmt as Number).toLong() < 1) throw ExchangeError("this file is not a Kotsu export")
        if (fmt.toLong() > Merge.FORMAT) {
            throw ExchangeError("file in format $fmt, newer than this Kotsu (format ${Merge.FORMAT}): update Kotsu on this device")
        }
        if (fmt.toLong() == 1L) obj = upgradeV1(obj)
        try {
            checkContent(obj)
            return toState(obj)
        } catch (e: Missing) {
            throw ExchangeError("exchange file incomplete or damaged ('${e.key}')")
        } catch (e: ExchangeError) {
            throw e
        } catch (e: RuntimeException) {
            throw ExchangeError("exchange file incomplete or damaged (${e.message})")
        }
    }

    private fun get(o: Any?, key: String): Any? {
        if (o !is JSONObject) throw IllegalStateException("record is not an object")
        if (!o.has(key)) throw Missing(key)
        val v = o.get(key)
        return if (v == JSONObject.NULL) null else v
    }

    private fun list(o: JSONObject, key: String): List<Any?> =
        (get(o, key) as JSONArray).let { a -> (0 until a.length()).map { a.get(it) } }

    private fun require(condition: Boolean, message: String) {
        if (!condition) throw ExchangeError("invalid exchange file: $message")
    }

    private fun integer(v: Any?) = v is Int || v is Long
    private fun nonBlank(v: Any?) = v is String && v.isNotBlank()
    private fun validStamp(v: Any?) = v is String && STAMP.matches(v)
    private fun date(v: Any?) = v is String && try {
        LocalDate.parse(v).toString() == v
    } catch (e: Exception) {
        false
    }

    private fun checkContent(s: JSONObject) {
        for (section in SECTIONS) require(get(s, section) is JSONArray, "missing the list of $section")

        for ((section, label) in listOf("accounts" to "account", "categories" to "category")) {
            val uids = HashSet<Any?>()
            val names = HashSet<String>()
            for (item in list(s, section)) {
                require(nonBlank(get(item, "uid")), "$label without uid")
                require(nonBlank(get(item, "name")), "$label without name")
                val name = get(item, "name") as String
                require(validStamp(get(item, "changed_at")), "stamp of $label $name")
                require(get(item, "uid") !in uids, "duplicate $label ($name)")
                require(Merge.nameKey(name) !in names, "duplicate $label ($name)")
                uids.add(get(item, "uid"))
                names.add(Merge.nameKey(name))
            }
        }
        for (a in list(s, "accounts")) require(get(a, "color") is String, "color of account ${get(a, "name")}")
        for (c in list(s, "categories")) require(get(c, "recurring") is Boolean, "category ${get(c, "name")}")
        val accounts = list(s, "accounts").map { get(it, "uid") }.toSet()
        val categories = list(s, "categories").map { get(it, "uid") }.toSet()

        fun movement(item: Any?, what: String) {
            require(get(item, "description") is String, "description of $what")
            val amount = get(item, "amount")
            require(integer(amount) && (amount as Number).toLong() > 0, "amount of $what")
            require(get(item, "kind") in KINDS, "kind of $what")
            require(get(item, "account") in accounts, "unknown account in $what")
            val category = get(item, "category")
            require(category == null || category in categories, "unknown category in $what")
            require(validStamp(get(item, "changed_at")), "stamp of $what")
        }

        val series = HashSet<Any?>()
        for (serie in list(s, "recurrences")) {
            require(nonBlank(get(serie, "group")), "series without group")
            val what = "series ${get(serie, "group")}"
            require(get(serie, "group") !in series, "duplicate $what")
            series.add(get(serie, "group"))
            val day = get(serie, "day")
            require(integer(day) && (day as Number).toLong() in 1..31, "day of $what")
            require(date(get(serie, "generated_until")), "generated_until of $what")
            require(get(serie, "ended") is Boolean, "ended of $what")
            movement(serie, what)
        }

        val uids = HashSet<Any?>()
        for (entry in list(s, "entries")) {
            require(nonBlank(get(entry, "uid")), "entry without uid")
            val what = "entry ${get(entry, "uid")}"
            require(get(entry, "uid") !in uids, "duplicate $what")
            uids.add(get(entry, "uid"))
            require(date(get(entry, "date")), "date of $what")
            require(get(entry, "generated") is Boolean, "generated of $what")
            val rec = get(entry, "recurrence")
            require(rec == null || rec in series, "unknown series in $what")
            val i = get(entry, "installment")
            if (i != null) {
                require(nonBlank(get(i, "group")), "installment of $what")
                val n = get(i, "number")
                val t = get(i, "total")
                require(
                    integer(n) && integer(t) && (n as Number).toLong() >= 1 && n.toLong() <= (t as Number).toLong(),
                    "installment of $what",
                )
            }
            movement(entry, what)
        }

        val tombstones = HashSet<Any?>()
        for (t in list(s, "tombstones")) {
            require(nonBlank(get(t, "uid")), "deletion without uid")
            require(get(t, "uid") !in tombstones, "duplicate deletion (${get(t, "uid")})")
            tombstones.add(get(t, "uid"))
            require(validStamp(get(t, "deleted_at")), "stamp of deletion ${get(t, "uid")}")
        }
    }

    private fun kind(v: Any?) = if (v == "income") Kind.INCOME else Kind.EXPENSE
    private fun str(o: Any?, k: String) = get(o, k) as String
    private fun optStr(o: Any?, k: String) = get(o, k) as String?
    private fun long(o: Any?, k: String) = (get(o, k) as Number).toLong()
    private fun int(o: Any?, k: String) = (get(o, k) as Number).toInt()

    /** Decodes a state that already passed [checkContent] (also used for the local file). */
    internal fun toState(s: JSONObject) = State(
        accounts = list(s, "accounts").map { Account(str(it, "uid"), str(it, "name"), str(it, "color"), str(it, "changed_at")) },
        categories = list(s, "categories").map {
            Category(str(it, "uid"), str(it, "name"), get(it, "recurring") as Boolean, str(it, "changed_at"))
        },
        recurrences = list(s, "recurrences").map {
            Series(
                str(it, "group"), int(it, "day"), str(it, "description"), long(it, "amount"), kind(get(it, "kind")),
                str(it, "account"), optStr(it, "category"), LocalDate.parse(str(it, "generated_until")),
                get(it, "ended") as Boolean, str(it, "changed_at"),
            )
        },
        entries = list(s, "entries").map {
            val i = get(it, "installment")
            Entry(
                uid = str(it, "uid"), date = LocalDate.parse(str(it, "date")), description = str(it, "description"),
                amount = long(it, "amount"), kind = kind(get(it, "kind")), account = str(it, "account"),
                category = optStr(it, "category"),
                installment = i?.let { x -> Installment(str(x, "group"), int(x, "number"), int(x, "total")) },
                recurrence = optStr(it, "recurrence"), generated = get(it, "generated") as Boolean,
                changedAt = str(it, "changed_at"),
            )
        },
        tombstones = list(s, "tombstones").map { Tombstone(str(it, "uid"), str(it, "deleted_at")) },
    )

    // --- format 1 ---------------------------------------------------------------------

    private val V1_SECTIONS = mapOf(
        "contas" to "accounts", "categorias" to "categories", "recorrencias" to "recurrences",
        "lancamentos" to "entries", "lapides" to "tombstones",
    )
    private val V1_FIELDS = mapOf(
        "nome" to "name", "cor" to "color", "recorrente" to "recurring", "alterado_em" to "changed_at",
        "grupo" to "group", "dia" to "day", "descricao" to "description", "valor" to "amount", "tipo" to "kind",
        "conta" to "account", "categoria" to "category", "gerada_ate" to "generated_until", "encerrada" to "ended",
        "data" to "date", "recorrencia" to "recurrence", "gerado" to "generated", "parcela" to "installment",
        "numero" to "number", "excluido_em" to "deleted_at",
    )
    private val V1_KINDS = mapOf("receita" to "income", "despesa" to "expense")

    private fun upgradeRecord(record: Any?): Any? {
        if (record !is JSONObject) return record
        val new = JSONObject()
        for (k in record.keys()) {
            val key = V1_FIELDS[k] ?: k
            var value = record.get(k)
            if (key == "installment") value = upgradeRecord(value)
            else if (key == "kind") value = V1_KINDS[value as? String] ?: value
            new.put(key, value)
        }
        return new
    }

    /** Translates a format-1 file (Portuguese keys) to format 2. */
    fun upgradeV1(state: JSONObject): JSONObject {
        val new = JSONObject()
        for (k in state.keys()) if (k !in V1_SECTIONS) new.put(k, state.get(k))
        for ((old, section) in V1_SECTIONS) {
            if (!state.has(old)) continue
            val records = state.get(old)
            new.put(section, if (records is JSONArray) JSONArray((0 until records.length()).map { upgradeRecord(records.get(it)) }) else records)
        }
        new.put("format", Merge.FORMAT)
        return new
    }

    // --- writing ----------------------------------------------------------------------

    private fun nul(v: Any?): Any = v ?: JSONObject.NULL

    /** The data sections as JSON (keys as in the Python exchange file). */
    fun sections(s: State, into: JSONObject = JSONObject()): JSONObject {
        into.put("accounts", JSONArray(s.accounts.sortedBy { it.uid }.map {
            JSONObject().put("uid", it.uid).put("name", it.name).put("color", it.color).put("changed_at", it.changedAt)
        }))
        into.put("categories", JSONArray(s.categories.sortedBy { it.uid }.map {
            JSONObject().put("uid", it.uid).put("name", it.name).put("recurring", it.recurring).put("changed_at", it.changedAt)
        }))
        into.put("recurrences", JSONArray(s.recurrences.sortedBy { it.group }.map {
            JSONObject().put("group", it.group).put("day", it.day).put("description", it.description)
                .put("amount", it.amount).put("kind", it.kind.text).put("account", it.account)
                .put("category", nul(it.category)).put("generated_until", it.generatedUntil.toString())
                .put("ended", it.ended).put("changed_at", it.changedAt)
        }))
        into.put("entries", JSONArray(s.entries.sortedBy { it.uid }.map {
            JSONObject().put("uid", it.uid).put("date", it.date.toString()).put("description", it.description)
                .put("amount", it.amount).put("kind", it.kind.text).put("account", it.account)
                .put("category", nul(it.category)).put("recurrence", nul(it.recurrence))
                .put("generated", it.generated).put("changed_at", it.changedAt)
                .put("installment", it.installment?.let { i ->
                    JSONObject().put("group", i.group).put("number", i.number).put("total", i.total)
                } ?: JSONObject.NULL)
        }))
        into.put("tombstones", JSONArray(s.tombstones.sortedBy { it.uid }.map {
            JSONObject().put("uid", it.uid).put("deleted_at", it.deletedAt)
        }))
        return into
    }

    /** The whole exchange file, ready to save. `exportedAt` like `2026-11-15T10:20:30`. */
    fun write(s: State, replica: String, exportedAt: String): String {
        val file = JSONObject()
            .put("app", "kotsu").put("format", Merge.FORMAT).put("replica", replica)
            .put("exported_at", exportedAt).put("check_code", Merge.checkCode(s))
        return sections(s, file).toString()
    }
}
