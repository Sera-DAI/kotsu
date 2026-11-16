package kotsu.app

import androidx.compose.ui.graphics.Color

/** Cotton Candy colors (D37), copied from src/kotsu/ui/themes.py. */
data class Palette(
    val background: Color, val surface: Color, val panel: Color, val text: Color,
    val highlight: Color, val secondary: Color, val warning: Color,
    val income: Color, val expense: Color, val neutral: Color,
)

val CottonCandyNight = Palette(
    background = Color(0xFF1D1424), surface = Color(0xFF291B33), panel = Color(0xFF41274F),
    text = Color(0xFFFFE9F4), highlight = Color(0xFFFF7FB8), secondary = Color(0xFF8FB3FF),
    warning = Color(0xFFFFD27A), income = Color(0xFF86EFC0), expense = Color(0xFFFF7A9E),
    neutral = Color(0xFF9A7FA8),
)

val CottonCandyLight = Palette(
    background = Color(0xFFFFF5FA), surface = Color(0xFFFFEAF4), panel = Color(0xFFFFD6E8),
    text = Color(0xFF5A3A5E), highlight = Color(0xFFE0509A), secondary = Color(0xFF4F74C7),
    warning = Color(0xFFB87400), income = Color(0xFF1F9D6B), expense = Color(0xFFD6336C),
    neutral = Color(0xFF8F6F8C),
)
