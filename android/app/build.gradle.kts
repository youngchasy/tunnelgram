import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val keystoreFile = System.getenv("TUNNELGRAM_KEYSTORE_FILE")?.takeIf { it.isNotBlank() }
val keystorePassword = System.getenv("TUNNELGRAM_KEYSTORE_PASSWORD")?.takeIf { it.isNotBlank() }
val keyAliasName = System.getenv("TUNNELGRAM_KEY_ALIAS")?.takeIf { it.isNotBlank() }
val keyPasswordValue = System.getenv("TUNNELGRAM_KEY_PASSWORD")?.takeIf { it.isNotBlank() }
val hasReleaseSigning = listOf(keystoreFile, keystorePassword, keyAliasName, keyPasswordValue).all { it != null }

android {
    namespace = "org.tunnelgram.android"
    compileSdk = 35

    buildFeatures {
        buildConfig = true
    }

    defaultConfig {
        applicationId = "org.tunnelgram.android"
        minSdk = 24
        targetSdk = 35
        versionCode = 20005
        versionName = "2.0.0-android-alpha3.2"

        testInstrumentationRunner = "android.app.Instrumentation"
    }

    signingConfigs {
        if (hasReleaseSigning) {
            create("release") {
                storeFile = file(keystoreFile!!)
                storePassword = keystorePassword
                keyAlias = keyAliasName
                keyPassword = keyPasswordValue
            }
        }
    }

    buildTypes {
        getByName("debug") {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
        getByName("release") {
            isMinifyEnabled = false
            isShrinkResources = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
            signingConfig = if (hasReleaseSigning) {
                signingConfigs.getByName("release")
            } else {
                // Installable test APK. For public updates configure GitHub signing secrets.
                signingConfigs.getByName("debug")
            }
        }
    }

    splits {
        abi {
            isEnable = true
            reset()
            include("armeabi-v7a", "arm64-v8a")
            isUniversalApk = true
        }
    }

    packaging {
        jniLibs {
            useLegacyPackaging = true
            keepDebugSymbols += setOf("**/libsingbox.so")
        }
        resources {
            excludes += setOf("META-INF/DEPENDENCIES", "META-INF/LICENSE*", "META-INF/NOTICE*")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    testOptions {
        unitTests.isIncludeAndroidResources = false
    }
}

dependencies {
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
