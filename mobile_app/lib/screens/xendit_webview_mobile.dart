import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

/// Mobile implementation using WebView.
Widget buildWebView({
  required String url,
  required Function(bool) onLoadingChanged,
}) {
  final controller = WebViewController()
    ..setJavaScriptMode(JavaScriptMode.unrestricted)
    ..setBackgroundColor(const Color(0x00000000))
    ..setNavigationDelegate(
      NavigationDelegate(
        onPageStarted: (_) => onLoadingChanged(true),
        onPageFinished: (_) => onLoadingChanged(false),
        onWebResourceError: (_) => onLoadingChanged(false),
        onNavigationRequest: (request) => NavigationDecision.navigate,
      ),
    )
    ..loadRequest(Uri.parse(url));

  return WebViewWidget(controller: controller);
}


