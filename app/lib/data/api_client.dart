import 'package:dio/dio.dart';

import 'local_store.dart';

/// Dio wrapper: base URL, bearer auth, and transparent token recovery.
///
/// The backend rotates tokens on device re-registration, so a 401 is
/// recoverable: re-register once with the stored device id and retry.
class ApiClient {
  ApiClient(this._store) {
    _dio = Dio(
      BaseOptions(
        baseUrl: _store.apiBase,
        connectTimeout: const Duration(seconds: 8),
        receiveTimeout: const Duration(seconds: 15),
      ),
    );
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) {
          final token = _store.token;
          if (token != null && options.headers['Authorization'] == null) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
        onError: (error, handler) async {
          final isAuthFailure = error.response?.statusCode == 401;
          final alreadyRetried = error.requestOptions.extra['mp_retried'] == true;
          if (!isAuthFailure || alreadyRetried) {
            handler.next(error);
            return;
          }
          try {
            await registerDevice();
            final options = error.requestOptions
              ..extra['mp_retried'] = true
              ..headers['Authorization'] = 'Bearer ${_store.token}';
            handler.resolve(await _dio.fetch<dynamic>(options));
          } on DioException {
            handler.next(error);
          }
        },
      ),
    );
  }

  final LocalStore _store;
  late final Dio _dio;

  Dio get dio => _dio;

  String get apiBase => _store.apiBase;

  /// Register (or re-key) this device and persist the bearer token.
  Future<void> registerDevice() async {
    final response = await _dio.post<Map<String, dynamic>>(
      '/api/v1/users',
      data: {'device_id': _store.deviceId, 'platform': 'flutter'},
      options: Options(headers: {'Authorization': null}),
    );
    final token = response.data?['token'] as String?;
    if (token == null) {
      throw StateError('registration response is missing the token');
    }
    await _store.saveToken(token);
  }

  /// Ensure a usable token exists (called once at startup).
  Future<void> ensureRegistered() async {
    if (_store.token == null) await registerDevice();
  }
}
