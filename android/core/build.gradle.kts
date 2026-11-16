// Pure Kotlin core: the same rules as the Python domain, checked by the shared vectors.
plugins {
    kotlin("jvm")
}

kotlin { jvmToolchain(17) }

dependencies {
    // Android ships org.json; the JVM tests bring their own copy.
    compileOnly("org.json:json:20240303")
    testImplementation(kotlin("test"))
    testImplementation("org.json:json:20240303")
}

tasks.test {
    useJUnitPlatform()
    // The shared test cases live at the repository root (vectors/*.json).
    systemProperty("kotsu.vectors", rootProject.projectDir.resolve("../vectors").canonicalPath)
}
