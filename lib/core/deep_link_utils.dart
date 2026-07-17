// Pure parsing for jamai:// deep links, kept separate from any
// platform-channel/stream plumbing so it's testable without a running
// app_links plugin (no platform channels involved).

/// jamai://join/{code} -> the session code, uppercased; null if the URI
/// doesn't match that shape (wrong scheme/host, or no code segment).
String? parseJoinCode(Uri uri) {
  if (uri.scheme != 'jamai' || uri.host != 'join') return null;
  if (uri.pathSegments.isEmpty) return null;
  final code = uri.pathSegments.first.trim();
  return code.isEmpty ? null : code.toUpperCase();
}
