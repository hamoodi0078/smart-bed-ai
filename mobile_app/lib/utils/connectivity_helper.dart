import 'dart:async';
import 'dart:io';

class ConnectivityHelper {
  static Future<bool> hasConnection() async {
    try {
      final result = await InternetAddress.lookup('google.com')
          .timeout(const Duration(seconds: 5));
      return result.isNotEmpty && result[0].rawAddress.isNotEmpty;
    } on SocketException catch (_) {
      return false;
    } on TimeoutException catch (_) {
      return false;
    } catch (_) {
      return false;
    }
  }

  static Future<bool> canReachBackend(String baseUrl) async {
    try {
      final uri = Uri.parse(baseUrl);
      final socket = await Socket.connect(
        uri.host,
        uri.port,
        timeout: const Duration(seconds: 3),
      );
      socket.destroy();
      return true;
    } catch (_) {
      return false;
    }
  }
}
