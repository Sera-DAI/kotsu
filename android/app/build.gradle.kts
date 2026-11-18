plugins {
    id("com.android.application")
    kotlin("android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("io.github.takahirom.roborazzi")
}

android {
    namespace = "kotsu.app"
    compileSdk = 35
    defaultConfig {
        // Unique id tied to the owner's GitHub namespace (D46). Google developer verification
        // registers this exact name together with the release key's SHA-256 fingerprint.
        applicationId = "io.github.seradai.kotsu"
        minSdk = 26
        targetSdk = 35
        versionCode = 3
        versionName = "0.3.0"
    }
    // Release key (D46): a fixed keystore kept by the owner, given to CI through GitHub
    // Secrets. Without it the release build is left unsigned and the workflow skips it.
    val releaseKeystore = System.getenv("KOTSU_KEYSTORE_PATH")?.let { file(it) }
    signingConfigs {
        if (releaseKeystore != null && releaseKeystore.exists()) {
            create("release") {
                storeFile = releaseKeystore
                storePassword = System.getenv("KOTSU_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("KOTSU_KEY_ALIAS")
                keyPassword = System.getenv("KOTSU_KEY_PASSWORD")
                enableV1Signing = false // minSdk 26: v2 + v3 are enough
                enableV2Signing = true
                enableV3Signing = true
            }
        }
    }
    buildTypes {
        debug {
            // Installs next to the release app, so data can be moved with export → import.
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfigs.findByName("release")?.let { signingConfig = it }
        }
    }
    buildFeatures { compose = true }
    testOptions { unitTests.isIncludeAndroidResources = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

kotlin { jvmToolchain(17) }

dependencies {
    implementation(project(":core"))
    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.9.3")

    // Screenshot tests: render the real Compose screen on the JVM (Robolectric + Roborazzi).
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.robolectric:robolectric:4.18")
    testImplementation("io.github.takahirom.roborazzi:roborazzi:1.32.2")
    testImplementation("io.github.takahirom.roborazzi:roborazzi-compose:1.32.2")
    testImplementation("androidx.compose.ui:ui-test-junit4")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}
