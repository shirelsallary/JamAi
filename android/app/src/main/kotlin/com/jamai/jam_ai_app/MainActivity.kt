package com.jamai.jam_ai_app

import android.content.Intent
import com.spotify.sdk.android.auth.AuthorizationClient
import com.spotify.sdk.android.auth.AuthorizationRequest
import com.spotify.sdk.android.auth.AuthorizationResponse
import com.spotify.sdk.android.auth.app.SpotifyNativeAuthUtil
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

private const val SPOTIFY_AUTH_CHANNEL = "jamai/spotify_app_auth"

// Distinct from com.spotify.sdk.android.auth.LoginActivity.REQUEST_CODE (1138)
// so this doesn't collide if the SDK's own request code ever changes.
private const val SPOTIFY_AUTH_REQUEST_CODE = 4381

class MainActivity : FlutterActivity() {
    private var pendingAuthResult: MethodChannel.Result? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, SPOTIFY_AUTH_CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "isSpotifyInstalled" -> {
                        // SpotifyNativeAuthUtil's own check (not a bare PackageManager
                        // package-name query) — it also validates the installed app's
                        // signing certificate against Spotify's known signature
                        // hashes, so a malicious app can't spoof com.spotify.music.
                        result.success(SpotifyNativeAuthUtil.isSpotifyInstalled(this))
                    }
                    "authorize" -> handleAuthorize(call, result)
                    else -> result.notImplemented()
                }
            }
    }

    private fun handleAuthorize(call: io.flutter.plugin.common.MethodCall, result: MethodChannel.Result) {
        val clientId = call.argument<String>("clientId")
        val redirectUri = call.argument<String>("redirectUri")
        val scopes = call.argument<List<String>>("scopes")
        val state = call.argument<String>("state")

        if (clientId == null || redirectUri == null || scopes == null || state == null) {
            result.error("INVALID_ARGS", "Missing required Spotify authorization parameters", null)
            return
        }
        if (pendingAuthResult != null) {
            result.error("AUTH_IN_PROGRESS", "A Spotify authorization request is already in progress", null)
            return
        }

        pendingAuthResult = result

        // Type.CODE (not TOKEN) — same authorization-code flow as the browser
        // path, exchanged server-side via the existing
        // POST /auth/oauth/spotify/exchange endpoint, unmodified.
        val request = AuthorizationRequest.Builder(
            clientId,
            AuthorizationResponse.Type.CODE,
            redirectUri,
        )
            .setScopes(scopes.toTypedArray())
            .setState(state)
            .build()

        AuthorizationClient.openLoginActivity(this, SPOTIFY_AUTH_REQUEST_CODE, request)
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != SPOTIFY_AUTH_REQUEST_CODE) return

        val result = pendingAuthResult ?: return
        pendingAuthResult = null

        val response = AuthorizationClient.getResponse(resultCode, data)
        when (response.type) {
            AuthorizationResponse.Type.CODE -> result.success(
                mapOf("type" to "code", "code" to response.code, "state" to response.state)
            )
            AuthorizationResponse.Type.EMPTY -> result.success(mapOf("type" to "cancelled"))
            AuthorizationResponse.Type.ERROR -> result.success(
                mapOf("type" to "error", "error" to (response.error ?: "Unknown error"))
            )
            else -> result.success(mapOf("type" to "error", "error" to "Unexpected Spotify auth response"))
        }
    }
}
