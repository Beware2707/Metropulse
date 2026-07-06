import 'package:dio/dio.dart';

import 'local_store.dart';

/// Dio wrapper: base URL, bearer auth, and transparent token recovery.
///
/// The backend rotates tokens on device re-registration, so a 401 is
/// recoverable: re-register once with the stored device id and retry.
///
/// A dropped connection is retried too, but only for GET requests: reads
/// are safe to repeat, while retrying a POST like starting a journey risks
/// creating a duplicate on the server if the original request actually
/// landed and only the response was lost. Two retries with a short
/// backoff (500ms, 1000ms) — enough to ride out a brief flicker, not so
/// much that a genuinely dead connection hangs for long before every
/// caller's own error handling (offline messaging, cached fallbacks) takes
/// over as it already does today.
class ApiClient {
  static const _maxGetRetries = 2;

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
          final options = error.requestOptions;
          final retryCount = (options.extra['mp_retry_count'] as int?) ?? 0;
          final isRetryableGet = options.method.toUpperCase() == 'GET' &&
              isConnectivityError(error) &&
              retryCount < _maxGetRetries;
          if (isRetryableGet) {
            await Future<void>.delayed(Duration(milliseconds: 500 * (retryCount + 1)));
            options.extra['mp_retry_count'] = retryCount + 1;
            try {
              handler.resolve(await _dio.fetch<dynamic>(options));
            } on DioException catch (retryError) {
              handler.next(retryError);
            }
            return;
          }

          final isAuthFailure = error.response?.statusCode == 401;
          final alreadyRetried = options.extra['mp_retried'] == true;
          if (!isAuthFailure || alreadyRetried) {
            handler.next(error);
            return;
          }
          try {
            await registerDevice();
            options
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

/// True for the connection-shaped [DioException] types (timed out, no route
/// to host) rather than a real server-side error — the distinction that
/// decides whether a screen can honestly say "you're offline" instead of a
/// generic failure message.
bool isConnectivityError(DioException error) => switch (error.type) {
      DioExceptionType.connectionError ||
      DioExceptionType.connectionTimeout ||
      DioExceptionType.receiveTimeout ||
      DioExceptionType.sendTimeout =>
        true,
      _ => false,
    };
