import 'dart:convert';
import 'package:flutter_dotenv/flutter_dotenv.dart';

import 'package:http/http.dart' as http;

class ApiService {
  static const Duration _timeout = Duration(seconds: 30);

  static String getBaseUrl() {
    // Dynamic access from .env
    return dotenv.env['BASE_URL'] ?? 'http://localhost:5000';
  }

  static Future<Map<String, dynamic>> post(
    String endpoint,
    Map<String, dynamic> body,
  ) async {
    final url = '${getBaseUrl()}$endpoint';
    try {
      final response = await http
          .post(
            Uri.parse(url),
            headers: {
              'Content-Type': 'application/json',
              'Bypass-Tunnel-Reminder': 'true',
            },
            body: json.encode(body),
          )
          .timeout(_timeout);
      return json.decode(response.body);
    } catch (e) {
      return {
        'success': false,
        'message':
            'Could not connect to server. Make sure Flask is running.\nError: $e',
      };
    }
  }

  static Future<Map<String, dynamic>> put(
    String endpoint,
    Map<String, dynamic> body,
  ) async {
    final url = '${getBaseUrl()}$endpoint';
    try {
      final response = await http
          .put(
            Uri.parse(url),
            headers: {
              'Content-Type': 'application/json',
              'Bypass-Tunnel-Reminder': 'true',
            },
            body: json.encode(body),
          )
          .timeout(_timeout);
      return json.decode(response.body);
    } catch (e) {
      return {'success': false, 'message': 'Connection error: $e'};
    }
  }

  static Future<dynamic> get(String endpoint) async {
    final url = '${getBaseUrl()}$endpoint';
    try {
      final response = await http
          .get(Uri.parse(url), headers: {'Bypass-Tunnel-Reminder': 'true'})
          .timeout(_timeout);
      return json.decode(response.body);
    } catch (e) {
      return null;
    }
  }

  static Future<Map<String, dynamic>> delete(String endpoint) async {
    final url = '${getBaseUrl()}$endpoint';
    try {
      final response = await http
          .delete(
            Uri.parse(url),
            headers: {
              'Content-Type': 'application/json',
              'Bypass-Tunnel-Reminder': 'true',
            },
          )
          .timeout(_timeout);
      return json.decode(response.body);
    } catch (e) {
      return {'success': false, 'message': 'Connection error: $e'};
    }
  }
}
