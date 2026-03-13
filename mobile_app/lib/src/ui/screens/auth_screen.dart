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

  _AuthMode _mode = _AuthMode.signIn;

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
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

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authControllerProvider);
    final theme = Theme.of(context);

    return Scaffold(
      body: AppBackdrop(
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(20),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 480),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text('Smart Bed', style: theme.textTheme.headlineLarge),
                    const SizedBox(height: 12),
                    Text(
                      'One surface. One wow. One revenue hook. Start with a calm mobile command center that can actually ship.',
                      style: theme.textTheme.bodyLarge,
                    ),
                    const SizedBox(height: 24),
                    PanelCard(
                      gradient: const LinearGradient(
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                        colors: <Color>[
                          SmartBedPalette.surfaceDark,
                          SmartBedPalette.surfaceLight,
                        ],
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: const <Widget>[
                              Chip(label: Text('Bearer auth')),
                              Chip(label: Text('Scene preview first')),
                              Chip(label: Text('Polling, not sockets')),
                            ],
                          ),
                          const SizedBox(height: 20),
                          SegmentedButton<_AuthMode>(
                            segments: const <ButtonSegment<_AuthMode>>[
                              ButtonSegment<_AuthMode>(
                                value: _AuthMode.signIn,
                                label: Text('Sign In'),
                                icon: Icon(Icons.lock_open_rounded),
                              ),
                              ButtonSegment<_AuthMode>(
                                value: _AuthMode.register,
                                label: Text('Create Account'),
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
                            const LinearProgressIndicator(minHeight: 6),
                            const SizedBox(height: 12),
                            Text(
                              'Restoring your previous mobile session...',
                              style: theme.textTheme.bodyMedium,
                            ),
                            const SizedBox(height: 20),
                          ],
                          if (authState.errorMessage != null) ...<Widget>[
                            Container(
                              width: double.infinity,
                              padding: const EdgeInsets.all(14),
                              decoration: BoxDecoration(
                                color: SmartBedPalette.danger.withValues(
                                  alpha: 0.22,
                                ),
                                borderRadius: BorderRadius.circular(18),
                                border: Border.all(
                                  color: SmartBedPalette.danger.withValues(
                                    alpha: 0.42,
                                  ),
                                ),
                              ),
                              child: Text(
                                authState.errorMessage!,
                                style: theme.textTheme.bodyMedium?.copyWith(
                                  color: const Color(0xFFFFC7C7),
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
                                      labelText: 'Name',
                                      hintText: 'Muneeb',
                                    ),
                                    textInputAction: TextInputAction.next,
                                    validator: (value) {
                                      if (_mode == _AuthMode.register &&
                                          (value == null ||
                                              value.trim().isEmpty)) {
                                        return 'Name helps personalize the dashboard.';
                                      }
                                      return null;
                                    },
                                  ),
                                  const SizedBox(height: 14),
                                ],
                                TextFormField(
                                  controller: _emailController,
                                  keyboardType: TextInputType.emailAddress,
                                  autofillHints: const <String>[
                                    AutofillHints.email,
                                  ],
                                  decoration: const InputDecoration(
                                    labelText: 'Email',
                                    hintText: 'you@example.com',
                                  ),
                                  textInputAction: TextInputAction.next,
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
                                  autofillHints: const <String>[
                                    AutofillHints.password,
                                  ],
                                  decoration: InputDecoration(
                                    labelText: _mode == _AuthMode.signIn
                                        ? 'Password'
                                        : 'Create Password',
                                  ),
                                  textInputAction: TextInputAction.done,
                                  onFieldSubmitted: (_) => _submit(),
                                  validator: (value) {
                                    final text = value ?? '';
                                    if (text.length < 6) {
                                      return 'Use at least 6 characters.';
                                    }
                                    return null;
                                  },
                                ),
                                const SizedBox(height: 24),
                                SizedBox(
                                  width: double.infinity,
                                  child: FilledButton.icon(
                                    onPressed: authState.isSubmitting
                                        ? null
                                        : _submit,
                                    icon: authState.isSubmitting
                                        ? const SizedBox(
                                            width: 18,
                                            height: 18,
                                            child: CircularProgressIndicator(
                                              strokeWidth: 2,
                                            ),
                                          )
                                        : Icon(
                                            _mode == _AuthMode.signIn
                                                ? Icons.arrow_forward_rounded
                                                : Icons.bolt_rounded,
                                          ),
                                    label: Text(
                                      _mode == _AuthMode.signIn
                                          ? 'Enter Command Center'
                                          : 'Create Mobile Access',
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 18),
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
