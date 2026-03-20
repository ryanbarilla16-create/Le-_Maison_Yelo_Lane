import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../theme.dart';

// Conditional imports for WebView (only works on mobile)
import 'xendit_webview_stub.dart'
    if (dart.library.io) 'xendit_webview_mobile.dart';

class XenditSandboxScreen extends StatefulWidget {
  final String url;
  const XenditSandboxScreen({super.key, required this.url});

  @override
  State<XenditSandboxScreen> createState() => _XenditSandboxScreenState();
}

class _XenditSandboxScreenState extends State<XenditSandboxScreen> {
  bool _loading = true;
  bool _paymentOpened = false;

  @override
  void initState() {
    super.initState();

    // On Web/Desktop, open in browser and show waiting screen
    if (kIsWeb) {
      _openInBrowser();
    }
  }

  Future<void> _openInBrowser() async {
    final url = Uri.parse(widget.url);
    if (await canLaunchUrl(url)) {
      await launchUrl(url, mode: LaunchMode.platformDefault);
    }
    setState(() {
      _loading = false;
      _paymentOpened = true;
    });
  }

  @override
  Widget build(BuildContext context) {
    // For Web: Show a waiting/instructions screen
    if (kIsWeb || _paymentOpened) {
      return Scaffold(
        appBar: AppBar(
          title: const Text('Secure Payment'),
          backgroundColor: Colors.white,
          foregroundColor: AppColors.textMain,
          elevation: 0,
          leading: IconButton(
            icon: const Icon(Icons.close),
            onPressed: () => Navigator.pop(context, true),
          ),
        ),
        body: Center(
          child: Container(
            padding: const EdgeInsets.all(40),
            constraints: const BoxConstraints(maxWidth: 420),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      colors: [AppColors.primary, Color(0xFF6D4C41)],
                    ),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(
                    Icons.payment_rounded,
                    color: Colors.white,
                    size: 48,
                  ),
                ),
                const SizedBox(height: 28),
                Text(
                  'Payment Page Opened',
                  style: AppTextStyles.heading.copyWith(fontSize: 22),
                ),
                const SizedBox(height: 12),
                const Text(
                  'A payment window has been opened. Please complete your payment there.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: AppColors.textMuted,
                    fontSize: 15,
                    height: 1.5,
                  ),
                ),
                const SizedBox(height: 32),
                SizedBox(
                  width: double.infinity,
                  height: 48,
                  child: ElevatedButton.icon(
                    onPressed: _openInBrowser,
                    icon: const Icon(Icons.open_in_new),
                    label: const Text('Reopen Payment Page'),
                  ),
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  height: 48,
                  child: OutlinedButton.icon(
                    onPressed: () => Navigator.pop(context, true),
                    icon: const Icon(Icons.check_circle_outline),
                    label: const Text('I\'ve Completed Payment'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppColors.success,
                      side: const BorderSide(color: AppColors.success),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      );
    }

    // For Mobile: Use WebView
    return Scaffold(
      appBar: AppBar(
        title: const Text('Secure Payment'),
        backgroundColor: Colors.white,
        foregroundColor: AppColors.textMain,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.close),
          onPressed: () => Navigator.pop(context, true),
        ),
      ),
      body: Stack(
        children: [
          buildWebView(
            url: widget.url,
            onLoadingChanged: (loading) {
              if (mounted) setState(() => _loading = loading);
            },
          ),
          if (_loading)
            const Center(
              child: CircularProgressIndicator(color: AppColors.primary),
            ),
        ],
      ),
    );
  }
}
