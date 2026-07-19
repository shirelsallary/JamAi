import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../core/auth_service.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _loading = false;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    final email = _emailController.text.trim();
    final password = _passwordController.text;

    if (email.isEmpty || password.isEmpty) {
      _showError('Please fill in all fields');
      return;
    }

    setState(() => _loading = true);

    try {
      final token = await AuthService.login(email, password);
      if (!mounted) return;

      if (token != null) {
        await AuthService.saveToken(token);
        if (!mounted) return;
        final me = await AuthService.getMe(token);
        if (!mounted) return;
        final platformToken = me?['platform_token'];
        final hasPlatform =
            platformToken != null && platformToken.toString().isNotEmpty;
        context.go(hasPlatform ? '/home' : '/connect-platform');
      } else {
        _showError('Invalid email or password');
      }
    } catch (_) {
      if (mounted) _showError('Connection failed. Please try again.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _showError(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: kRed,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: GradientBackground(
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(kSpaceLg),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const SizedBox(height: 60),
                  Text(
                    'JAM AI',
                    textAlign: TextAlign.center,
                    style: kDuskTextTheme.displayLarge,
                  ),
                  const SizedBox(height: kSpaceSm),
                  const Text(
                    'Shared listening, reimagined',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: kTextSecondary),
                  ),
                  const SizedBox(height: kSpaceXxl),
                  AppTextField(
                    controller: _emailController,
                    keyboardType: TextInputType.emailAddress,
                    enableSuggestions: false,
                    autocorrect: false,
                    labelText: 'Email',
                  ),
                  const SizedBox(height: kSpaceMd),
                  AppTextField(
                    controller: _passwordController,
                    obscureText: true,
                    keyboardType: TextInputType.visiblePassword,
                    labelText: 'Password',
                    onSubmitted: (_) => _login(),
                  ),
                  const SizedBox(height: kSpaceLg),
                  PrimaryButton(
                    label: 'Login',
                    onPressed: _loading ? null : _login,
                    isLoading: _loading,
                  ),
                  const SizedBox(height: kSpaceSm),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Text('New here?', style: TextStyle(color: kTextSecondary)),
                      TextButton(
                        // push (not go) — Register should have a working back
                        // button to return here, per the navigation audit.
                        onPressed: () => context.push('/register'),
                        child: const Text('Create account →'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
