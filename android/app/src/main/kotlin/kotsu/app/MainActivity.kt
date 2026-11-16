package kotsu.app

import android.os.Bundle
import android.util.AtomicFile
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import kotsu.core.Book
import kotsu.core.Storage
import java.io.File
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

/** The phone's database file (`kotsu.json` in the app's private folder), saved with an atomic swap. */
class FileStorage(file: File) : Storage {
    private val atomic = AtomicFile(file)

    override fun read(): String? = if (atomic.baseFile.exists()) atomic.readFully().toString(Charsets.UTF_8) else null

    override fun write(text: String) {
        val out = atomic.startWrite()
        try {
            out.write(text.toByteArray(Charsets.UTF_8))
            atomic.finishWrite(out)
        } catch (e: Exception) {
            atomic.failWrite(out)
            throw e
        }
    }
}

class MainActivity : ComponentActivity() {
    private lateinit var book: Book

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        book = Book.open(FileStorage(File(filesDir, "kotsu.json")))
        setContent {
            // The result of an export or import, shown by the screen as a message.
            val message = remember { mutableStateOf<String?>(null) }
            val changed = remember { mutableStateOf(0) }
            val export = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri ->
                if (uri == null) return@rememberLauncherForActivityResult
                message.value = try {
                    val now = LocalDateTime.now().withNano(0).format(DateTimeFormatter.ISO_LOCAL_DATE_TIME)
                    val text = book.export(now)
                    contentResolver.openOutputStream(uri, "wt")!!.use { it.write(text.toByteArray(Charsets.UTF_8)) }
                    "Data exported.\nCheck code: ${book.checkCode()}"
                } catch (e: Exception) {
                    "Could not export: ${e.message}"
                }
            }
            // Offer to bring back entries the file has but this phone deleted (restoring a backup).
            val offer = remember { mutableStateOf<Ask?>(null) }
            val import = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
                if (uri == null) return@rememberLauncherForActivityResult
                message.value = try {
                    val text = contentResolver.openInputStream(uri)!!.use { it.readBytes().toString(Charsets.UTF_8) }
                    val s = book.import(text)
                    changed.value++
                    val result = if (s.nothing) "Nothing new: this phone already had everything.\nCheck code: ${book.checkCode()}"
                    else "Merged: ${s.added} new, ${s.changed} changed, ${s.removed} removed.\nCheck code: ${book.checkCode()}"
                    val deleted = book.deletedHere(text)
                    if (deleted == 0) result else {
                        offer.value = Ask.Question(
                            "This file has $deleted ${if (deleted == 1) "entry" else "entries"} you deleted on this phone." +
                                "\nBring ${if (deleted == 1) "it" else "them"} back?",
                            listOf(
                                "restore" to {
                                    offer.value = null
                                    message.value = try {
                                        val n = book.restore(text)
                                        changed.value++
                                        "Restored $n ${if (n == 1) "entry" else "entries"}.\nCheck code: ${book.checkCode()}"
                                    } catch (e: Exception) {
                                        "Could not restore: ${e.message}"
                                    }
                                },
                                "keep deleted" to { offer.value = null; message.value = result },
                            ),
                        )
                        null
                    }
                } catch (e: Exception) {
                    "Could not import: ${e.message}"
                }
            }
            MainScreen(
                book = book,
                onExport = { export.launch("kotsu-${book.replica}.json") },
                onImport = { import.launch(arrayOf("application/json", "application/octet-stream", "text/plain", "*/*")) },
                outsideMessage = message.value,
                outsideAsk = offer.value,
                onOutsideMessageSeen = { message.value = null; offer.value = null },
                outsideChange = changed.value,
            )
        }
    }
}
