import 'package:flutter/material.dart';

/// Stub implementation for platforms that don't support WebView (Web, Desktop).
/// This widget will never actually be shown because the XenditSandboxScreen
/// detects kIsWeb and shows a fallback UI instead.
Widget buildWebView({
  required String url,
  required Function(bool) onLoadingChanged,
}) {
  return const Center(
    child: Text('WebView is not supported on this platform.'),
  );
}
