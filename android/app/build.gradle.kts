plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.jamai.jam_ai_app"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.jamai.jam_ai_app"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName

        // Required by com.spotify.android:auth's bundled RedirectUriReceiverActivity
        // manifest placeholders, even though that activity is removed from our
        // merged manifest (AndroidManifest.xml, tools:node="remove") — the Gradle
        // manifest merger resolves placeholders before node-removal is guaranteed
        // to apply, so an unresolved placeholder would fail the build regardless.
        // Kept matching the app's real jamai://spotify-callback deep link so that,
        // if a future library version changes what gets merged, this stays correct
        // rather than silently wrong.
        manifestPlaceholders["redirectSchemeName"] = "jamai"
        manifestPlaceholders["redirectHostName"] = "spotify-callback"
    }

    buildTypes {
        release {
            // TODO: Add your own signing config for the release build.
            // Signing with the debug keys for now, so `flutter run --release` works.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}

dependencies {
    // App-to-App Spotify auth (AuthorizationClient). Verified against the
    // actual published artifact on Maven Central — 2.1.2 is newer than the
    // 1.2.5 shown on Spotify's docs page.
    implementation("com.spotify.android:auth:2.1.2")
}
