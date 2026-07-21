import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:webview_flutter/webview_flutter.dart';
import '../../../core/auth_service.dart';
import '../../../core/constants.dart';
import '../../../core/theme.dart';

class YouTubeWebViewScreen extends StatefulWidget {
  const YouTubeWebViewScreen({super.key});

  @override
  State<YouTubeWebViewScreen> createState() => _YouTubeWebViewScreenState();
}

class _YouTubeWebViewScreenState extends State<YouTubeWebViewScreen> {
  late final WebViewController _controller;
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(NavigationDelegate(
        onPageStarted: (_) => setState(() => _isLoading = true),
        onPageFinished: (url) async {
          setState(() => _isLoading = false);
          if (url.contains('music.youtube.com')) {
            await _extractAndSaveCookies();
          }
        },
      ))
      // music.youtube.com itself redirects to Google Sign-in with a valid
      // continue= param back to music.youtube.com — unlike the generic
      // accounts.google.com/signin (no continue param), which lands on
      // myaccount.google.com after login and never triggers onPageFinished's
      // music.youtube.com check below.
      ..loadRequest(Uri.parse('https://music.youtube.com'));
  }

  Future<void> _extractAndSaveCookies() async {
    try {
      final cookies = await _controller.runJavaScriptReturningResult(
        'document.cookie',
      );

      final token = await AuthService.getToken();
      if (token == null) {
        if (mounted) context.go('/');
        return;
      }

      final response = await http.post(
        Uri.parse('$kBaseUrl/auth/youtube/connect'),
        headers: {
          'Authorization': 'Bearer $token',
          'Content-Type': 'application/json',
        },
        body: jsonEncode({'cookies': cookies.toString()}),
      );

      if (!mounted) return;

      if (response.statusCode == 200) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('YouTube Music connected!'),
            backgroundColor: kGreen,
          ),
        );
        context.go('/home');
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Could not save connection. Try again.'),
            backgroundColor: kRed,
          ),
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Connection failed. Please try again.'),
            backgroundColor: kRed,
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Connect YouTube Music'),
        // Was hardcoded to kRed, overriding every other screen's AppBar
        // treatment — fixed to inherit jamAiTheme's appBarTheme like
        // everywhere else. Everything below (WebView, cookie-scrape logic)
        // is untouched.
        leading: IconButton(
          icon: const Icon(Icons.close),
          // pop (not go) — this screen is only ever reached by pushing from
          // ConnectPlatformScreen, so it's already on the stack.
          onPressed: () => context.pop(),
        ),
      ),
      body: Stack(
        children: [
          WebViewWidget(controller: _controller),
          if (_isLoading)
            const Center(
              child: CircularProgressIndicator(color: kRed),
            ),
        ],
      ),
    );
  }
}
