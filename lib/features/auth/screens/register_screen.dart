import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../core/auth_service.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmController = TextEditingController();
  bool _loading = false;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    _confirmController.dispose();
    super.dispose();
  }

  String? _validateEmail(String email) {
    if (email.isEmpty) return 'Email is required';
    final emailRegex = RegExp(r'^[\w\.-]+@[\w\.-]+\.\w{2,}$');
    if (!emailRegex.hasMatch(email)) {
      return 'Email must be in format: example@gmail.com';
    }
    return null;
  }

  String? _validatePassword(String password) {
    if (password.isEmpty) return 'Password is required';
    if (password.length < 8) {
      return 'Password must be at least 8 characters';
    }
    if (!password.contains(RegExp(r'[A-Z]'))) {
      return 'Password must contain at least one uppercase letter (e.g. A)';
    }
    if (!password.contains(RegExp(r'[0-9]'))) {
      return 'Password must contain at least one number (e.g. 1)';
    }
    if (!password.contains(RegExp(r'[!@#\$%^&*]'))) {
      return 'Password must contain at least one symbol (e.g. !)';
    }
    return null;
  }

  Future<void> _register() async {
    final email = _emailController.text.trim();
    final password = _passwordController.text;
    final confirm = _confirmController.text;

    final emailError = _validateEmail(email);
    if (emailError != null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(emailError), backgroundColor: kRed),
      );
      return;
    }

    final passwordError = _validatePassword(password);
    if (passwordError != null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(passwordError), backgroundColor: kRed),
      );
      return;
    }

    if (password != confirm) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('Passwords do not match'),
          backgroundColor: kRed,
        ),
      );
      return;
    }

    setState(() => _loading = true);

    try {
      final registered = await AuthService.register(email, password);
      if (!mounted) return;

      if (registered) {
        final token = await AuthService.login(email, password);
        if (!mounted) return;

        if (token != null) {
          await AuthService.saveToken(token);
          if (!mounted) return;
          context.go('/connect-platform');
        } else {
          _showError('Registered! Please log in.');
          context.go('/');
        }
      } else {
        _showError('Registration failed. Email may already be in use.');
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
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: const Text('Create Account'),
        leading: Navigator.canPop(context)
            ? AppBackButton(onPressed: () => context.pop())
            : null,
      ),
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
                    'Create your account',
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
                    helperText: 'Format: example@gmail.com',
                  ),
                  const SizedBox(height: kSpaceMd),
                  AppTextField(
                    controller: _passwordController,
                    obscureText: true,
                    keyboardType: TextInputType.visiblePassword,
                    labelText: 'Password',
                    helperText: 'Min 8 chars, 1 uppercase, 1 number, 1 symbol (!@#\$)',
                  ),
                  const SizedBox(height: kSpaceMd),
                  AppTextField(
                    controller: _confirmController,
                    obscureText: true,
                    keyboardType: TextInputType.visiblePassword,
                    labelText: 'Confirm Password',
                    helperText: 'Must match password above',
                    onSubmitted: (_) => _register(),
                  ),
                  const SizedBox(height: kSpaceLg),
                  PrimaryButton(
                    label: 'Register',
                    onPressed: _loading ? null : _register,
                    isLoading: _loading,
                  ),
                  TextButton(
                    // pop (not go) — RegisterScreen is only ever reached by
                    // pushing from LoginScreen, so Login is already on the
                    // stack.
                    onPressed: () => context.pop(),
                    child: const Text('Already have an account? Login'),
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
