import 'package:flutter/material.dart';
import 'dart:async';
import '../theme.dart';
import '../services/api_service.dart';
import 'login_screen.dart';

class OtpScreen extends StatefulWidget {
  final int userId;
  const OtpScreen({super.key, required this.userId});

  @override
  State<OtpScreen> createState() => _OtpScreenState();
}

class _OtpScreenState extends State<OtpScreen> {
  final _otpCtrl = TextEditingController();
  bool _loading = false;
  int _cooldown = 0;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _cooldown = 300; // 5 minutes
    _startTimer();
  }

  void _startTimer() {
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 1), (t) {
      if (_cooldown > 0) {
        setState(() => _cooldown--);
      } else {
        t.cancel();
      }
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _verify() async {
    if (_otpCtrl.text.trim().isEmpty) {
      _showMsg('Please enter your OTP code.', false);
      return;
    }
    setState(() => _loading = true);
    final res = await ApiService.post('/api/auth/verify_otp', {
      'user_id': widget.userId,
      'otp': _otpCtrl.text.trim(),
    });
    setState(() => _loading = false);

    if (res['success'] == true) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(res['message'] ?? 'Verified!'),
          backgroundColor: AppColors.success,
        ),
      );
      Navigator.pushAndRemoveUntil(
        context,
        MaterialPageRoute(builder: (_) => const LoginScreen()),
        (_) => false,
      );
    } else {
      _showMsg(res['message'] ?? 'Invalid OTP.', false);
    }
  }

  Future<void> _resend() async {
    if (_cooldown > 0) {
      _showMsg(
        'Please wait ${_cooldown ~/ 60}m ${_cooldown % 60}s before requesting a new code.',
        false,
      );
      return;
    }
    final res = await ApiService.post('/api/auth/resend_otp', {
      'user_id': widget.userId,
    });
    if (res['success'] == true) {
      setState(() => _cooldown = 300);
      _startTimer();
      _showMsg(res['message'] ?? 'New OTP sent!', true);
    } else {
      _showMsg(res['message'] ?? 'Failed to resend.', false);
    }
  }

  void _showMsg(String msg, bool success) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(msg),
        backgroundColor: success ? AppColors.success : AppColors.danger,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Verify Email')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            const SizedBox(height: 30),
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [AppColors.primary, AppColors.primaryLight],
                ),
                borderRadius: BorderRadius.circular(20),
              ),
              child: const Icon(
                Icons.mark_email_read,
                color: Colors.white,
                size: 50,
              ),
            ),
            const SizedBox(height: 24),
            Text(
              'Enter OTP Code',
              style: AppTextStyles.heading.copyWith(fontSize: 22),
            ),
            const SizedBox(height: 8),
            const Text(
              'We sent a verification code to your email.\nPlease enter it below.',
              style: AppTextStyles.muted,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 32),

            TextField(
              controller: _otpCtrl,
              keyboardType: TextInputType.number,
              textAlign: TextAlign.center,
              maxLength: 6,
              style: const TextStyle(
                fontSize: 28,
                fontWeight: FontWeight.bold,
                letterSpacing: 10,
                color: AppColors.primary,
              ),
              decoration: InputDecoration(
                counterText: '',
                hintText: '------',
                hintStyle: TextStyle(
                  color: AppColors.textMuted.withOpacity(0.3),
                  letterSpacing: 10,
                ),
              ),
            ),
            const SizedBox(height: 28),

            SizedBox(
              width: double.infinity,
              height: 52,
              child: ElevatedButton(
                onPressed: _loading ? null : _verify,
                child: _loading
                    ? const SizedBox(
                        width: 22,
                        height: 22,
                        child: CircularProgressIndicator(
                          color: Colors.white,
                          strokeWidth: 2.5,
                        ),
                      )
                    : const Text('Verify'),
              ),
            ),
            const SizedBox(height: 20),

            TextButton(
              onPressed: _cooldown > 0 ? null : _resend,
              child: Text(
                _cooldown > 0
                    ? 'Resend code in ${_cooldown ~/ 60}:${(_cooldown % 60).toString().padLeft(2, '0')}'
                    : 'Resend Code',
                style: TextStyle(
                  color: _cooldown > 0
                      ? AppColors.textMuted
                      : AppColors.primary,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}


