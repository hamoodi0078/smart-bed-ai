import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:mobile_app/src/core/models.dart';
import 'package:mobile_app/src/core/session_store.dart';
import 'package:mobile_app/src/state/auth_controller.dart';

class MockSessionStore extends Mock implements SessionStore {}

void main() {
  late MockSessionStore mockStore;

  setUp(() {
    mockStore = MockSessionStore();
  });

  test('auth controller initialises as loading then transitions to ready with session', () async {
    const session = AuthSession(
      accessToken: 'tok_abc',
      refreshToken: 'ref_abc',
      user: MobileUser(
        userId: 'u1',
        email: 'user@example.com',
        name: 'Test User',
        clientName: 'Test',
      ),
    );

    when(() => mockStore.read()).thenAnswer((_) async => session);

    final container = ProviderContainer(
      overrides: [
        sessionStoreProvider.overrideWithValue(mockStore),
      ],
    );
    addTearDown(container.dispose);

    // Initial state is loading.
    final initial = container.read(authControllerProvider);
    expect(initial.initialized, isFalse);

    // Wait for the bootstrap microtask.
    await Future<void>.delayed(Duration.zero);

    final after = container.read(authControllerProvider);
    expect(after.initialized, isTrue);
    expect(after.session, equals(session));

    verify(() => mockStore.read()).called(1);
  });

  test('auth controller transitions to ready with null session when store is empty', () async {
    when(() => mockStore.read()).thenAnswer((_) async => null);

    final container = ProviderContainer(
      overrides: [
        sessionStoreProvider.overrideWithValue(mockStore),
      ],
    );
    addTearDown(container.dispose);

    await Future<void>.delayed(Duration.zero);

    final state = container.read(authControllerProvider);
    expect(state.initialized, isTrue);
    expect(state.session, isNull);
  });

  test('write and clear delegate to the underlying store', () async {
    const session = AuthSession(
      accessToken: 'tok_xyz',
      refreshToken: 'ref_xyz',
      user: MobileUser(
        userId: 'u2',
        email: 'other@example.com',
        name: 'Other',
        clientName: 'Other',
      ),
    );

    when(() => mockStore.read()).thenAnswer((_) async => null);
    when(() => mockStore.write(any())).thenAnswer((_) async {});
    when(() => mockStore.clear()).thenAnswer((_) async {});

    final store = MockSessionStore();
    when(() => store.write(session)).thenAnswer((_) async {});
    when(() => store.clear()).thenAnswer((_) async {});

    await store.write(session);
    await store.clear();

    verify(() => store.write(session)).called(1);
    verify(() => store.clear()).called(1);
  });
}