package kotsu.core

import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.time.LocalDate
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

/** Runs the cases generated from the Python domain (tools/generate_vectors.py). */
class VectorsTest {
    private val folder = File(System.getProperty("kotsu.vectors"))
    private fun read(name: String) = File(folder, name).readText()

    @Test
    fun currency() {
        val cases = JSONArray(read("currency.json"))
        for (i in 0 until cases.length()) {
            val c = cases.getJSONObject(i)
            assertEquals(c.getString("text"), Money.format(c.getLong("cents")), "cents=${c.getLong("cents")}")
        }
    }

    @Test
    fun installmentDates() {
        val cases = JSONObject(read("dates.json")).getJSONArray("installments")
        for (i in 0 until cases.length()) {
            val c = cases.getJSONObject(i)
            val got = Dates.installmentDate(LocalDate.parse(c.getString("first")), c.getInt("index"))
            assertEquals(c.getString("date"), got.toString(), c.toString())
        }
    }

    @Test
    fun line() {
        val cases = JSONArray(read("line.json"))
        for (i in 0 until cases.length()) {
            val c = cases.getJSONObject(i)
            val text = c.getString("line")
            val today = LocalDate.parse(c.getString("today"))
            if (c.has("error")) {
                val e = assertFailsWith<LineError>(text) { Line.parse(text, today) }
                assertEquals(c.getString("error"), e.message, text)
                continue
            }
            val x = c.getJSONObject("expected")
            val p = Line.parse(text, today)
            assertEquals(x.getLong("amount"), p.amount, text)
            assertEquals(x.getString("kind"), p.kind.name.lowercase(), text)
            assertEquals(x.getString("description"), p.description, text)
            assertEquals(x.getString("date"), p.date.toString(), text)
            assertEquals(x.optString("category").takeIf { !x.isNull("category") }, p.category, text)
            assertEquals(x.optString("account").takeIf { !x.isNull("account") }, p.account, text)
            assertEquals(x.getInt("installments"), p.installments, text)
            assertEquals(x.getBoolean("has_date"), p.hasDate, text)
        }
    }

    @Test
    fun monthUidAndRecurrence() {
        val d = JSONObject(read("dates.json"))
        val uids = d.getJSONArray("month_uid")
        for (i in 0 until uids.length()) {
            val c = uids.getJSONObject(i)
            assertEquals(c.getString("uid"), Merge.monthUid(c.getString("group"), c.getInt("year"), c.getInt("month")))
        }
        val rec = d.getJSONArray("recurrence")
        for (i in 0 until rec.length()) {
            val c = rec.getJSONObject(i)
            val got = Recurrence.dateInMonth(c.getInt("day"), java.time.YearMonth.of(c.getInt("year"), c.getInt("month")))
            assertEquals(c.getString("date"), got.toString(), c.toString())
        }
    }

    @Test
    fun stamps() {
        val cases = JSONArray(read("stamp.json"))
        for (i in 0 until cases.length()) {
            val c = cases.getJSONObject(i)
            assertEquals(c.getString("stamp"), Merge.stamp(c.getLong("now_ms"), c.getString("last"), c.getString("replica")), c.toString())
        }
    }

    @Test
    fun merges() {
        val cases = JSONArray(read("merge.json"))
        for (i in 0 until cases.length()) {
            val c = cases.getJSONObject(i)
            val name = c.getString("name")
            val a = Exchange.validate(c.getJSONObject("a"))
            val b = Exchange.validate(c.getJSONObject("b"))
            assertEquals(c.getString("code_a"), Merge.checkCode(a), name)
            assertEquals(c.getString("code_b"), Merge.checkCode(b), name)
            val expected = Exchange.validate(c.getJSONObject("expected").put("app", "kotsu").put("format", 2))
            val got = Merge.merge(a, b)
            assertEquals(expected, got, name)
            assertEquals(c.getString("expected_canonical_form"), Merge.canonicalForm(got), name)
            assertEquals(c.getString("expected_code"), Merge.checkCode(got), name)
            // Commutative and idempotent, and the written file reads back the same.
            assertEquals(Merge.checkCode(got), Merge.checkCode(Merge.merge(b, a)), "$name (b+a)")
            assertEquals(got, Merge.merge(got, b), "$name (twice)")
            assertEquals(got, Exchange.read(Exchange.write(got, "00000000", "2026-11-15T00:00:00")), "$name (file)")
        }
    }

    @Test
    fun invalidFiles() {
        val cases = JSONArray(read("invalid.json"))
        for (i in 0 until cases.length()) {
            val c = cases.getJSONObject(i)
            val e = assertFailsWith<ExchangeError>(c.getString("name")) { Exchange.validate(c.get("file")) }
            assertEquals(c.getString("error"), e.message, c.getString("name"))
        }
    }
}
