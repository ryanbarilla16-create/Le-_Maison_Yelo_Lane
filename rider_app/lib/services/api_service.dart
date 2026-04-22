import 'dart:convert';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:http/http.dart' as http;

class ApiService {
  static const Duration _timeout = Duration(seconds: 30);
  static const int _maxRetries = 3;

  static final Map<String, String> _defaultHeaders = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'Bypass-Tunnel-Reminder': 'true',
  };

  static final Map<String, String> _getHeaders = {
    'Accept': 'application/json',
    'Bypass-Tunnel-Reminder': 'true',
  };

  static String getBaseUrl() {
    return dotenv.env['BASE_URL'] ?? 'http://localhost:5000';
  }

  /// Checks if a response body is HTML (LocalTunnel warning page) instead of JSON
  static bool _isHtmlResponse(String body) {
    final trimmed = body.trimLeft().toLowerCase();
    return trimmed.startsWith('<!doctype') || trimmed.startsWith('<html');
  }

  /// Retry helper: executes an HTTP call up to [_maxRetries] times if LocalTunnel returns HTML
  static Future<http.Response?> _retryRequest(
    Future<http.Response> Function() request,
  ) async {
    for (int attempt = 0; attempt < _maxRetries; attempt++) {
      try {
        final response = await request().timeout(_timeout);
        if (!_isHtmlResponse(response.body)) return response;
        // Wait before retry
        if (attempt < _maxRetries - 1) {
          await Future.delayed(Duration(seconds: 1 + attempt));
        }
      } catch (e) {
        if (attempt == _maxRetries - 1) rethrow;
        await Future.delayed(Duration(seconds: 1 + attempt));
      }
    }
    return null; // All retries returned HTML
  }

  // ── POST ──────────────────────────────────────────────────────────────
  static Future<Map<String, dynamic>> post(
    String endpoint,
    Map<String, dynamic> body,
  ) async {
    final url = '${getBaseUrl()}$endpoint';
    try {
      final response = await _retryRequest(
        () => http.post(
          Uri.parse(url),
          headers: _defaultHeaders,
          body: json.encode(body),
        ),
      );

      if (response == null) {
        return {
          'success': false,
          'message': 'Server returned an unexpected page. Please try again.',
        };
      }
      return json.decode(response.body);
    } catch (e) {
      return {
        'success': false,
        'message':
            'Could not connect to server. Make sure Flask is running.\nError: $e',
      };
    }
  }

  // ── PUT ───────────────────────────────────────────────────────────────
  static Future<Map<String, dynamic>> put(
    String endpoint,
    Map<String, dynamic> body,
  ) async {
    final url = '${getBaseUrl()}$endpoint';
    try {
      final response = await _retryRequest(
        () => http.put(
          Uri.parse(url),
          headers: _defaultHeaders,
          body: json.encode(body),
        ),
      );

      if (response == null) {
        return {
          'success': false,
          'message': 'Server returned an unexpected page. Please try again.',
        };
      }
      return json.decode(response.body);
    } catch (e) {
      return {'success': false, 'message': 'Connection error: $e'};
    }
  }

  // ── GET ───────────────────────────────────────────────────────────────
  static Future<dynamic> get(String endpoint) async {
    final url = '${getBaseUrl()}$endpoint';
    try {
      final response = await _retryRequest(
        () => http.get(Uri.parse(url), headers: _getHeaders),
      );

      if (response == null) return null;
      return json.decode(response.body);
    } catch (e) {
      return null;
    }
  }

  // ── DELETE ────────────────────────────────────────────────────────────
  static Future<Map<String, dynamic>> delete(String endpoint) async {
    final url = '${getBaseUrl()}$endpoint';
    try {
      final response = await _retryRequest(
        () => http.delete(Uri.parse(url), headers: _defaultHeaders),
      );

      if (response == null) {
        return {
          'success': false,
          'message': 'Server returned an unexpected page. Please try again.',
        };
      }
      return json.decode(response.body);
    } catch (e) {
      return {'success': false, 'message': 'Connection error: $e'};
    }
  }
}


