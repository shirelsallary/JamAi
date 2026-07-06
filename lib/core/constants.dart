import 'package:flutter/foundation.dart' show kDebugMode;

const String _prodBaseUrl = 'https://jamai-lpjq.onrender.com';
const String _prodWsUrl = 'wss://jamai-lpjq.onrender.com';

// Port your local FastAPI backend listens on (uvicorn app.main:app --reload).
// Adjust if your backend runs on a different port.
const int kLocalBackendPort = 8000;

// Frontend and backend both run inside the same WSL instance, so the backend
// is always reachable via loopback. In release builds, always uses the
// deployed Render backend.
const String _localHost = '127.0.0.1';

String get kBaseUrl =>
    kDebugMode ? 'http://$_localHost:$kLocalBackendPort' : _prodBaseUrl;

String get kWsUrl =>
    kDebugMode ? 'ws://$_localHost:$kLocalBackendPort' : _prodWsUrl;
