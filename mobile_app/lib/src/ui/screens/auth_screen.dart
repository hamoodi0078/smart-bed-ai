import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../config/app_config.dart';
import '../../state/auth_controller.dart';
import '../theme.dart';
import '../widgets/app_backdrop.dart';
import '../widgets/panel_card.dart';

enum _AuthMode { signIn, register }

class AuthScreen extends ConsumerStatefulWidget {
  const AuthScreen({super.key});

  @override
  ConsumerState<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends ConsumerState<AuthScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _phoneController = TextEditingController();
  final _otpController = TextEditingController();
  final _socialTokenController = TextEditingController();
  final _socialAuthCodeController = TextEditingController();

  _AuthMode _mode = _AuthMode.signIn;
  String _otpRequestId = '';
  String _otpMaskedPhone = '';
  String _otpDebugCode = '';

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    _phoneController.dispose();
    _otpController.dispose();
    _socialTokenController.dispose();
    _socialAuthCodeController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final valid = _formKey.currentState?.validate() ?? false;
    if (!valid) {
      return;
    }

    final auth = ref.read(authControllerProvider.notifier);
    try {
      if (_mode == _AuthMode.signIn) {
        await auth.signIn(
          email: _emailController.text.trim(),
          password: _passwordController.text,
        );
      } else {
        await auth.register(
          email: _emailController.text.trim(),
          password: _passwordController.text,
          name: _nameController.text.trim(),
        );
      }
      if (mounted) {
        context.go('/dashboard');
      }
    } catch (_) {}
  }

  Future<void> _requestOtp() async {
    final phone = _phoneController.text.trim();
    if (phone.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter a phone number first.')),
      );
      return;
    }
    final auth = ref.read(authControllerProvider.notifier);
    try {
      final result = await auth.requestOtp(phoneNumber: phone);
      if (!mounted) {
        return;
      }
      setState(() {
        _otpRequestId = result.requestId;
        _otpMaskedPhone = result.phoneNumberMasked;
        _otpDebugCode = result.debugCode;
      });
      final debug = result.debugCode.isEmpty ? '' : ' OTP: ${result.debugCode}';
      final delivery =
          result.delivery.isEmpty ? '' : ' via ${result.delivery}';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'OTP sent to ${result.phoneNumberMasked}$delivery.$debug',
          ),
        ),
      );
    } catch (_) {}
  }

  Future<void> _verifyOtp() async {
    final requestId = _otpRequestId;
    final phone = _phoneController.text.trim();
    final code = _otpController.text.trim();
    if (requestId.isEmpty || phone.isEmpty || code.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Request and enter OTP first.')),
      );
      return;
    }
    final auth = ref.read(authControllerProvider.notifier);
    try {
      await auth.verifyOtp(
        requestId: requestId,
        phoneNumber: phone,
        otpCode: code,
        name: _nameController.text.trim(),
      );
      if (mounted) {
        context.go('/dashboard');
      }
    } catch (_) {}
  }

  Future<void> _socialLogin(String provider) async {
    final auth = ref.read(authControllerProvider.notifier);
    final email = _emailController.text.trim();
    final rawSocialToken = _socialTokenController.text.trim();
    final rawAuthCode = _socialAuthCodeController.text.trim();
    final providerUserId = email.isNotEmpty
        ? email.toLowerCase()
        : _phoneController.text.trim();
    if (providerUserId.isEmpty &&
        rawSocialToken.isEmpty &&
        rawAuthCode.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Provide a social token/auth code or email/phone fallback.'),
        ),
      );
      return;
    }
    String providerAccessToken = '';
    String providerIdToken = '';
    if (rawSocialToken.isNotEmpty) {
      if (provider == 'facebook') {
        providerAccessToken = rawSocialToken;
      } else if (rawSocialToken.split('.').length >= 3) {
        providerIdToken = rawSocialToken;
      } else {
        providerAccessToken = rawSocialToken;
      }
    }
    try {
      await auth.signInWithSocial(
        provider: provider,
        providerUserId: providerUserId,
        providerAccessToken: providerAccessToken,
        providerIdToken: providerIdToken,
        providerAuthCode: rawAuthCode,
        email: email,
        name: _nameController.text.trim(),
      );
      if (mounted) {
        context.go('/dashboard');
      }
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authControllerProvider);
    final theme = Theme.of(context);

    return Scaffold(
      body: AppBackdrop(
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 520),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text('Danah Smart Bed', style: theme.textTheme.headlineLarge),
                    const SizedBox(height: 10),
                    Text(
                      _mode == _AuthMode.signIn
                          ? 'Welcome back. Sign in to restore Dana, your routines, and live prayer timings.'
                          : 'Create your account to personalize Dana, prayer timings, and nightly automation.',
                      style: theme.textTheme.bodyLarge,
                    ),
                    const SizedBox(height: 24),
                    PanelCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Text(
                            _mode == _AuthMode.signIn ? 'Sign in' : 'Create account',
                            style: theme.textTheme.titleLarge,
                          ),
                          const SizedBox(height: 8),
                          Text(
                            'Built by Dana Abuhalifa',
                            style: theme.textTheme.bodyMedium,
                          ),
                          const SizedBox(height: 18),
                          SegmentedButton<_AuthMode>(
                            segments: const <ButtonSegment<_AuthMode>>[
                              ButtonSegment<_AuthMode>(
                                value: _AuthMode.signIn,
                                label: Text('Sign In'),
                                icon: Icon(Icons.lock_open_rounded),
                              ),
                              ButtonSegment<_AuthMode>(
                                value: _AuthMode.register,
                                label: Text('Register'),
                                icon: Icon(Icons.person_add_alt_1_rounded),
                              ),
                            ],
                            selected: <_AuthMode>{_mode},
                            onSelectionChanged: (selection) {
                              setState(() {
                                _mode = selection.first;
                              });
                            },
                          ),
                          const SizedBox(height: 20),
                          if (!authState.initialized) ...<Widget>[
                            const LinearProgressIndicator(minHeight: 5),
                            const SizedBox(height: 12),
                            Text(
                              'Restoring the last authenticated session...',
                              style: theme.textTheme.bodyMedium,
                            ),
                            const SizedBox(height: 16),
                          ],
                          if (authState.errorMessage != null) ...<Widget>[
                            Container(
                              width: double.infinity,
                              padding: const EdgeInsets.all(14),
                              decoration: BoxDecoration(
                                color: SmartBedPalette.danger.withValues(alpha: 0.14),
                                borderRadius: BorderRadius.circular(18),
                                border: Border.all(
                                  color: SmartBedPalette.danger.withValues(alpha: 0.25),
                                ),
                              ),
                              child: Text(
                                authState.errorMessage!,
                                style: theme.textTheme.bodyMedium?.copyWith(
                                  color: Theme.of(context).colorScheme.error,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                            const SizedBox(height: 16),
                          ],
                          Form(
                            key: _formKey,
                            child: Column(
                              children: <Widget>[
                                if (_mode == _AuthMode.register) ...<Widget>[
                                  TextFormField(
                                    controller: _nameController,
                                    decoration: const InputDecoration(
                                      labelText: 'Full name',
                                      hintText: 'Hamoud Khan',
                                      prefixIcon: Icon(Icons.person_outline_rounded),
                                    ),
                                    validator: (value) {
                                      if (_mode == _AuthMode.register &&
                                          (value == null || value.trim().isEmpty)) {
                                        return 'Enter your name so Dana can greet you properly.';
                                      }
                                      return null;
                                    },
                                  ),
                                  const SizedBox(height: 14),
                                ],
                                TextFormField(
                                  controller: _emailController,
                                  keyboardType: TextInputType.emailAddress,
                                  decoration: const InputDecoration(
                                    labelText: 'Email address',
                                    hintText: 'you@example.com',
                                    prefixIcon: Icon(Icons.email_outlined),
                                  ),
                                  validator: (value) {
                                    final text = value?.trim() ?? '';
                                    if (text.isEmpty || !text.contains('@')) {
                                      return 'Enter a valid email address.';
                                    }
                                    return null;
                                  },
                                ),
                                const SizedBox(height: 14),
                                TextFormField(
                                  controller: _passwordController,
                                  obscureText: true,
                                  decoration: const InputDecoration(
                                    labelText: 'Password',
                                    prefixIcon: Icon(Icons.lock_outline_rounded),
                                  ),
                                  onFieldSubmitted: (_) => _submit(),
                                  validator: (value) {
                                    if ((value ?? '').length < 8) {
                                      return 'Use at least 8 characters.';
                                    }
                                    return null;
                                  },
                                ),
                                const SizedBox(height: 22),
                                SizedBox(
                                  width: double.infinity,
                                  child: FilledButton.icon(
                                    onPressed: authState.isSubmitting ? null : _submit,
                                    icon: authState.isSubmitting
                                        ? const SizedBox(
                                            width: 18,
                                            height: 18,
                                            child: CircularProgressIndicator(strokeWidth: 2),
                                          )
                                        : Icon(
                                            _mode == _AuthMode.signIn
                                                ? Icons.arrow_forward_rounded
                                                : Icons.auto_awesome_rounded,
                                          ),
                                    label: Text(
                                      _mode == _AuthMode.signIn
                                          ? 'Continue to Danah'
                                          : 'Create Danah account',
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 20),
                          const Divider(height: 1),
                          const SizedBox(height: 18),
                          Text(
                            'Phone verification',
                            style: theme.textTheme.titleMedium,
                          ),
                          const SizedBox(height: 10),
                          TextFormField(
                            controller: _phoneController,
                            keyboardType: TextInputType.phone,
                            decoration: const InputDecoration(
                              labelText: 'Phone number',
                              hintText: '+96550000000',
                              prefixIcon: Icon(Icons.phone_rounded),
                            ),
                          ),
                          if (_otpRequestId.isNotEmpty) ...<Widget>[
                            const SizedBox(height: 10),
                            TextFormField(
                              controller: _otpController,
                              keyboardType: TextInputType.number,
                              decoration: InputDecoration(
                                labelText: 'OTP code',
                                hintText: _otpDebugCode.isNotEmpty
                                    ? _otpDebugCode
                                    : '6-digit code',
                                prefixIcon: const Icon(Icons.verified_user_rounded),
                              ),
                            ),
                            const SizedBox(height: 6),
                            Text(
                              _otpMaskedPhone.isEmpty
                                  ? 'Enter the code you received.'
                                  : 'Code sent to $_otpMaskedPhone.',
                              style: theme.textTheme.bodySmall,
                            ),
                          ],
                          const SizedBox(height: 12),
                          Wrap(
                            spacing: 10,
                            runSpacing: 10,
                            children: <Widget>[
                              FilledButton.tonalIcon(
                                onPressed: authState.isSubmitting ? null : _requestOtp,
                                icon: const Icon(Icons.sms_outlined),
                                label: Text(
                                  _otpRequestId.isEmpty ? 'Send OTP' : 'Resend OTP',
                                ),
                              ),
                              FilledButton.tonalIcon(
                                onPressed: authState.isSubmitting || _otpRequestId.isEmpty
                                    ? null
                                    : _verifyOtp,
                                icon: const Icon(Icons.login_rounded),
                                label: const Text('Verify & Continue'),
                              ),
                            ],
                          ),
                          const SizedBox(height: 18),
                          Text('Social sign-in', style: theme.textTheme.titleMedium),
                          const SizedBox(height: 10),
                          TextFormField(
                            controller: _socialTokenController,
                            decoration: const InputDecoration(
                              labelText: 'Provider token (id/access)',
                              hintText: 'Paste Google/Facebook/Apple token',
                              prefixIcon: Icon(Icons.key_rounded),
                            ),
                          ),
                          const SizedBox(height: 10),
                          TextFormField(
                            controller: _socialAuthCodeController,
                            decoration: const InputDecoration(
                              labelText: 'Apple auth code (optional)',
                              hintText: 'Use when Apple returns authorization code',
                              prefixIcon: Icon(Icons.code_rounded),
                            ),
                          ),
                          const SizedBox(height: 10),
                          Wrap(
                            spacing: 10,
                            runSpacing: 10,
                            children: <Widget>[
                              OutlinedButton.icon(
                                onPressed: authState.isSubmitting
                                    ? null
                                    : () => _socialLogin('google'),
                                icon: const Icon(Icons.g_mobiledata_rounded),
                                label: const Text('Google'),
                              ),
                              OutlinedButton.icon(
                                onPressed: authState.isSubmitting
                                    ? null
                                    : () => _socialLogin('apple'),
                                icon: const Icon(Icons.apple_rounded),
                                label: const Text('Apple'),
                              ),
                            ],
                          ),
                          const SizedBox(height: 16),
                          Text(
                            'API base: ${AppConfig.apiBaseUrl}',
                            style: theme.textTheme.bodySmall,
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

