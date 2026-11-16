package kotsu.app

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.github.takahirom.roborazzi.captureRoboImage
import kotsu.core.Book
import kotsu.core.Filter
import kotsu.core.Line
import kotsu.core.MemoryStorage
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.time.LocalDate

/** Renders the real screen, with a real database in memory, to PNG files (build/screenshots/). */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34])
class ScreenshotTest {
    private val today = LocalDate.of(2026, 11, 15)

    /** The same kind of month as on the PC: accounts, categories, an installment and a series. */
    private fun demo(): Book {
        val b = Book.open(MemoryStorage())
        val nubank = b.createAccount("nubank", "#8a2be2").uid
        val itau = b.createAccount("itaú", "#ff7a00").uid
        b.createAccount("inter", "#1f8fff")
        val food = b.createCategory("food").uid
        val home = b.createCategory("home").uid
        val rent = b.createCategory("rent", recurring = true).uid
        fun add(text: String, account: String, category: String?) = b.add(Line.parse(text, today), account, category)
        add("+3500 salary 05/11", itau, null)
        add("1200 rent 10/10", itau, rent)
        add("120 fridge 10x 02/10", nubank, home)
        add("210,50 power 06/11", itau, home)
        add("89,90 groceries 07/11", nubank, food)
        add("12,50 bakery 08/11", nubank, food)
        return b
    }

    private fun screen(name: String, block: @androidx.compose.runtime.Composable () -> Unit) =
        captureRoboImage("build/screenshots/$name.png") { block() }

    @Test
    @Config(qualifiers = "w411dp-h891dp-port-xxhdpi")
    fun portraitNight() = screen("portrait-night") { MainScreen(remember { demo() }, today, startDark = true) }

    @Test
    @Config(qualifiers = "w411dp-h891dp-port-xxhdpi")
    fun portraitLight() = screen("portrait-light") { MainScreen(remember { demo() }, today, startDark = false) }

    @Test
    @Config(qualifiers = "w891dp-h411dp-land-xxhdpi")
    fun landscapeNight() = screen("landscape-night") { MainScreen(remember { demo() }, today, startDark = true) }

    @Test
    @Config(qualifiers = "w411dp-h891dp-port-xxhdpi")
    fun portraitTyping() = screen("portrait-typing") {
        MainScreen(remember { demo() }, today, initialLine = "-89,90 market #food @nubank 3x")
    }

    @Test
    @Config(qualifiers = "w411dp-h891dp-port-xxhdpi")
    fun portraitFiltered() = screen("portrait-filtered") {
        val b = remember { demo() }
        MainScreen(b, today, initialFilter = Filter(account = b.accountByName("nubank")!!.uid, text = "gro"))
    }

    private fun card(name: String, ask: (Book) -> Ask) = screen(name) {
        val b = remember { demo() }
        Box(Modifier.fillMaxSize().background(CottonCandyNight.background).padding(24.dp), contentAlignment = Alignment.Center) {
            AskCard(ask(b), CottonCandyNight, b)
        }
    }

    @Test
    @Config(qualifiers = "w411dp-h891dp-port-xxhdpi")
    fun dialogScope() = card("dialog-scope") {
        Ask.Question("Delete installment 2/10: only this one or all?", listOf("all" to {}, "only this" to {}, "cancel" to {}))
    }

    @Test
    @Config(qualifiers = "w411dp-h891dp-port-xxhdpi")
    fun dialogNewAccount() = card("dialog-new-account") { b -> Ask.NewAccount("picpay", b.suggestedColor()) {} }

    @Test
    @Config(qualifiers = "w411dp-h891dp-port-xxhdpi")
    fun dialogCategories() = card("dialog-categories") { Ask.Categories }

    @Test
    @Config(qualifiers = "w411dp-h891dp-port-xxhdpi")
    fun formNew() = screen("form-new") {
        val b = remember { demo() }
        EntryForm(FormTarget.New, b, CottonCandyNight, today, onSave = {}, onCancel = {})
    }

    @Test
    @Config(qualifiers = "w411dp-h891dp-port-xxhdpi")
    fun formEditInstallment() = screen("form-edit-installment") {
        val b = remember { demo() }
        val e = b.monthEntries(java.time.YearMonth.from(today)).first { it.installment != null }
        EntryForm(FormTarget.Edit(e, kotsu.core.Scope.ALL), b, CottonCandyLight, today, onSave = {}, onCancel = {})
    }

    @Test
    @Config(qualifiers = "w411dp-h891dp-port-xxhdpi")
    fun dialogDay() = card("dialog-day") { Ask.DayPicker(today.minusDays(3), today) {} }
}
