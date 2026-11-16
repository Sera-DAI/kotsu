# Kotsu uses no reflection or serialization libraries (org.json is part of Android),
# so R8's defaults are enough. Keep line numbers so crash traces stay readable.
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile
