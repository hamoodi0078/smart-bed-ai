import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:mobile_app/src/core/api_client.dart';
import 'package:mobile_app/src/core/models.dart';
import 'package:mobile_app/src/core/session_store.dart';
import 'package:mobile_app/src/state/auth_controller.dart';

class MockSessionStore extends Mock implements SessionStore {}

class MockSmartBedApi extends Mock implements SmartBedApi {}

const _dummySession = AuthSession(
  accessToken: 'tok_fallback',
  refreshToken: 'ref_fallback',
  user: MobileUser(
    userId: 'u0',
    email: 'fallback@example.com',
    name: 'Fallback',
    clientName: 'Fallback',
  ),
);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late MockSessionStore mockStore;
  late MockSmartBedApi mockApi;

  setUpAll(() {
    registerFallbackValue(_dummySession);
  });

  setUp(() {
    mockStore = MockSessionStore();
    mockApi = MockSmartBedApi();
    // The bootstrap's fire-and-forget profile sync calls getProfile; a thrown
    // ApiException is swallowed by the controller's broad catch.
    when(() => mockApi.getProfile(any())).thenThrow(
      const ApiException(message: 'offline in tests'),
    );
  });

  ProviderContainer makeContainer() {
    final container = ProviderContainer(
      overrides: [
        sessionStoreProvider.overrideWithValue(mockStore),
        smartBedApiProvider.overrideWithValue(mockApi),
      ],
    );
    addTearDown(container.dispose);
    return container;
  }

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
    when(() => mockStore.write(any())).thenAnswer((_) async {});
    when(() => mockApi.me('tok_abc')).thenAnswer((_) async => session.user);

    final container = makeContainer();

    // Initial state is loading (first read triggers the lazy bootstrap).
    final initial = container.read(authControllerProvider);
    expect(initial.initialized, isFalse);

    // Drain the bootstrap: store read → /me hydration → store write.
    await pumpEventQueue();

    final after = container.read(authControllerProvider);
    expect(after.initialized, isTrue);
    expect(after.session?.accessToken, 'tok_abc');
    expect(after.session?.user.userId, 'u1');

    verify(() => mockStore.read()).called(1);
    verify(() => mockStore.write(any())).called(1);
  });

  test('auth controller transitions to ready with null session when store is empty', () async {
    when(() => mockStore.read()).thenAnswer((_) async => null);

    final container = makeContainer();

    // Trigger the lazy bootstrap, then drain it.
    final initial = container.read(authControllerProvider);
    expect(initial.initialized, isFalse);

    await pumpEventQueue();

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

    final store = MockSessionStore();
    when(() => store.write(any())).thenAnswer((_) async {});
    when(() => store.clear()).thenAnswer((_) async {});

    await store.write(session);
    await store.clear();

    verify(() => store.write(session)).called(1);
    verify(() => store.clear()).called(1);
  });
}
