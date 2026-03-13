import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mobile_app/src/state/auth_controller.dart';
import 'package:mobile_app/src/ui/screens/auth_screen.dart';
import 'package:mobile_app/src/ui/widgets/status_pill.dart';

void main() {
  testWidgets('status pill renders the supplied label', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: Center(
            child: StatusPill(label: 'ONLINE', tone: StatusTone.success),
          ),
        ),
      ),
    );

    expect(find.text('ONLINE'), findsOneWidget);
    expect(find.byType(StatusPill), findsOneWidget);
  });

  testWidgets('auth screen renders the mobile sign-in shell', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          authControllerProvider.overrideWith(_FakeAuthController.new),
        ],
        child: const MaterialApp(home: AuthScreen()),
      ),
    );

    await tester.pump();

    expect(find.text('Smart Bed'), findsOneWidget);
    expect(find.text('Enter Command Center'), findsOneWidget);
    expect(find.text('Bearer auth'), findsOneWidget);
  });
}

class _FakeAuthController extends AuthController {
  @override
  AuthViewState build() {
    return const AuthViewState.ready(session: null);
  }
}
