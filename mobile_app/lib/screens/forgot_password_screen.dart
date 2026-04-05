import 'dart:async';
import 'package:flutter/material.dart';
import '../theme.dart';
import '../services/api_service.dart';

class ForgotPasswordScreen extends StatefulWidget {
  const ForgotPasswordScreen({super.key});

  @override
  State<ForgotPasswordScreen> createState() => _ForgotPasswordScreenState();
}

class _ForgotPasswordScreenState extends State<ForgotPasswordScreen> {
  // Steps: 0 = Enter Email, 1 = Enter OTP, 2 = New Password
  int _step = 0;
  bool _loading = false;
  int? _userId;
  String _otpCode = '';

  final _emailCtrl = TextEditingController();
  final _otpCtrl = TextEditingController();
  final _newPassCtrl = TextEditingController();
  final _confirmPassCtrl = TextEditingController();
  bool _obscureNew = true;
  bool _obscureConfirm = true;

  // Countdown timer for resend
  int _resendCountdown = 0;
  Timer? _countdownTimer;

  @override
  void dispose() {
    _countdownTimer?.cancel();
    super.dispose();
  }

  void _startResendCountdown() {
    _resendCountdown = 60;
    _countdownTimer?.cancel();
    _countdownTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      setState(() {
        _resendCountdown--;
        if (_resendCountdown <= 0) {
          timer.cancel();
        }
      });
    });
  }

  // STEP 1: Send OTP to email
  Future<void> _sendOtp() async {
    final email = _emailCtrl.text.trim();
    if (email.isEmpty) {
      _showMsg('Please enter your email address.');
      return;
    }

    setState(() => _loading = true);

    final res = await ApiService.post('/api/auth/forgot-password', {
      'email': email,
    });

    setState(() => _loading = false);

    if (res['success'] == true) {
      setState(() {
        _userId = res['user_id'];
        _step = 1;
      });
      _startResendCountdown();
      _showSuccess(res['message'] ?? 'OTP sent!');
    } else {
      _showMsg(res['message'] ?? 'Failed to send OTP.');
    }
  }

  // Resend OTP
  Future<void> _resendOtp() async {
    if (_resendCountdown > 0) return;

    setState(() => _loading = true);

    final res = await ApiService.post('/api/auth/forgot-password', {
      'email': _emailCtrl.text.trim(),
    });

    setState(() => _loading = false);

    if (res['success'] == true) {
      _startResendCountdown();
      _showSuccess('New OTP sent!');
    } else {
      _showMsg(res['message'] ?? 'Failed to resend OTP.');
    }
  }

  // STEP 2: Verify OTP
  Future<void> _verifyOtp() async {
    final otp = _otpCtrl.text.trim();
    if (otp.isEmpty || otp.length != 6) {
      _showMsg('Please enter the 6-digit OTP code.');
      return;
    }

    setState(() => _loading = true);

    final res = await ApiService.post('/api/auth/forgot-password/verify-otp', {
      'user_id': _userId,
      'otp': otp,
    });

    setState(() => _loading = false);

    if (res['success'] == true) {
      setState(() {
        _otpCode = otp;
        _step = 2;
      });
      _showSuccess('OTP verified!');
    } else {
      _showMsg(res['message'] ?? 'Invalid OTP.');
    }
  }

  // STEP 3: Reset Password
  Future<void> _resetPassword() async {
    final newPass = _newPassCtrl.text;
    final confirmPass = _confirmPassCtrl.text;

    if (newPass.isEmpty || confirmPass.isEmpty) {
      _showMsg('Please fill in both password fields.');
      return;
    }

    if (newPass != confirmPass) {
      _showMsg('Passwords do not match.');
      return;
    }

    setState(() => _loading = true);

    final res = await ApiService.post('/api/auth/forgot-password/reset', {
      'user_id': _userId,
      'otp': _otpCode,
      'new_password': newPass,
      'confirm_password': confirmPass,
    });

    setState(() => _loading = false);

    if (res['success'] == true) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('Password reset successfully! You can now log in.'),
          backgroundColor: AppColors.success,
          duration: const Duration(seconds: 3),
        ),
      );
      Navigator.pop(context); // Go back to login
    } else {
      _showMsg(res['message'] ?? 'Failed to reset password.');
    }
  }

  void _showMsg(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(msg), backgroundColor: AppColors.danger),
    );
  }

  void _showSuccess(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(msg), backgroundColor: AppColors.success),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SingleChildScrollView(
        child: Column(
          children: [
            // Hero header
            Container(
              width: double.infinity,
              padding: const EdgeInsets.fromLTRB(24, 70, 24, 35),
              decoration: const BoxDecoration(
                gradient: LinearGradient(
                  colors: [AppColors.primary, AppColors.primaryLight],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.only(
                  bottomLeft: Radius.circular(30),
                  bottomRight: Radius.circular(30),
                ),
              ),
              child: Column(
                children: [
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: Colors.white.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Icon(
                      _step == 0
                          ? Icons.lock_reset
                          : _step == 1
                              ? Icons.mark_email_read
                              : Icons.vpn_key,
                      color: Colors.white,
                      size: 40,
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    _step == 0
                        ? 'Forgot Password'
                        : _step == 1
                            ? 'Verify OTP'
                            : 'New Password',
                    style: const TextStyle(
                      fontFamily: 'Georgia',
                      fontSize: 24,
                      fontWeight: FontWeight.bold,
                      color: Colors.white,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    _step == 0
                        ? 'Enter your email to receive a reset code'
                        : _step == 1
                            ? 'Check your Gmail for the 6-digit code'
                            : 'Create a strong new password',
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.8),
                      fontSize: 13,
                    ),
                  ),
                  // Step indicator
                  const SizedBox(height: 20),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      _stepDot(0, 'Email'),
                      _stepLine(0),
                      _stepDot(1, 'OTP'),
                      _stepLine(1),
                      _stepDot(2, 'Reset'),
                    ],
                  ),
                ],
              ),
            ),

            // Form content
            Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SizedBox(height: 8),
                  if (_step == 0) _buildEmailStep(),
                  if (_step == 1) _buildOtpStep(),
                  if (_step == 2) _buildResetStep(),
                  const SizedBox(height: 16),
                  // Back to login
                  Center(
                    child: TextButton.icon(
                      onPressed: () => Navigator.pop(context),
                      icon: const Icon(Icons.arrow_back, size: 18),
                      label: const Text('Back to Login'),
                      style: TextButton.styleFrom(
                        foregroundColor: AppColors.primary,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _stepDot(int step, String label) {
    final isActive = _step >= step;
    return Column(
      children: [
        Container(
          width: 30,
          height: 30,
          decoration: BoxDecoration(
            color: isActive ? Colors.white : Colors.white.withOpacity(0.3),
            shape: BoxShape.circle,
          ),
          child: Center(
            child: isActive && _step > step
                ? Icon(Icons.check, color: AppColors.primary, size: 18)
                : Text(
                    '${step + 1}',
                    style: TextStyle(
                      color: isActive ? AppColors.primary : Colors.white70,
                      fontWeight: FontWeight.bold,
                      fontSize: 13,
                    ),
                  ),
          ),
        ),
        const SizedBox(height: 4),
        Text(
          label,
          style: TextStyle(
            color: isActive ? Colors.white : Colors.white54,
            fontSize: 10,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }

  Widget _stepLine(int afterStep) {
    return Container(
      width: 50,
      height: 2,
      margin: const EdgeInsets.only(bottom: 16),
      color: _step > afterStep ? Colors.white : Colors.white.withOpacity(0.3),
    );
  }

  // === STEP 0: Enter Email ===
  Widget _buildEmailStep() {
    return Column(
      children: [
        TextField(
          controller: _emailCtrl,
          keyboardType: TextInputType.emailAddress,
          decoration: const InputDecoration(
            labelText: 'Email Address',
            prefixIcon: Icon(Icons.email_outlined, color: AppColors.primary),
            hintText: 'example@gmail.com',
          ),
        ),
        const SizedBox(height: 24),
        GradientButton(
          label: 'Send OTP Code',
          icon: Icons.send_rounded,
          onPressed: _loading ? null : _sendOtp,
          isLoading: _loading,
        ),

      ],
    );
  }

  // === STEP 1: Enter OTP ===
  Widget _buildOtpStep() {
    return Column(
      children: [
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppColors.info.withOpacity(0.08),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: AppColors.info.withOpacity(0.2)),
          ),
          child: Row(
            children: [
              const Icon(Icons.info_outline, color: AppColors.info, size: 20),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  'A 6-digit code was sent to ${_emailCtrl.text.trim()}',
                  style: const TextStyle(fontSize: 13, color: AppColors.info),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),
        TextField(
          controller: _otpCtrl,
          keyboardType: TextInputType.number,
          maxLength: 6,
          textAlign: TextAlign.center,
          style: const TextStyle(
            fontSize: 24,
            fontWeight: FontWeight.bold,
            letterSpacing: 8,
          ),
          decoration: const InputDecoration(
            labelText: 'Enter OTP Code',
            prefixIcon: Icon(Icons.pin, color: AppColors.primary),
            counterText: '',
          ),
        ),
        const SizedBox(height: 12),
        // Resend OTP
        TextButton(
          onPressed: _resendCountdown > 0 ? null : _resendOtp,
          child: Text(
            _resendCountdown > 0
                ? 'Resend OTP in ${_resendCountdown}s'
                : 'Resend OTP',
            style: TextStyle(
              color: _resendCountdown > 0
                  ? AppColors.textMuted
                  : AppColors.primary,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        const SizedBox(height: 16),
        GradientButton(
          label: 'Verify OTP',
          icon: Icons.verified_rounded,
          onPressed: _loading ? null : _verifyOtp,
          isLoading: _loading,
        ),

      ],
    );
  }

  // === STEP 2: New Password ===
  Widget _buildResetStep() {
    return Column(
      children: [
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppColors.success.withOpacity(0.08),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: AppColors.success.withOpacity(0.2)),
          ),
          child: const Row(
            children: [
              Icon(Icons.check_circle, color: AppColors.success, size: 20),
              SizedBox(width: 12),
              Expanded(
                child: Text(
                  'OTP verified! Now set your new password.',
                  style: TextStyle(fontSize: 13, color: AppColors.success),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),
        TextField(
          controller: _newPassCtrl,
          keyboardType: TextInputType.visiblePassword,
          obscureText: _obscureNew,
          decoration: InputDecoration(
            labelText: 'New Password',
            prefixIcon:
                const Icon(Icons.lock_outline, color: AppColors.primary),
            suffixIcon: IconButton(
              icon: Icon(
                _obscureNew ? Icons.visibility_off : Icons.visibility,
                color: AppColors.textMuted,
              ),
              onPressed: () => setState(() => _obscureNew = !_obscureNew),
            ),
          ),
        ),
        const SizedBox(height: 16),
        TextField(
          controller: _confirmPassCtrl,
          keyboardType: TextInputType.visiblePassword,
          obscureText: _obscureConfirm,
          decoration: InputDecoration(
            labelText: 'Confirm New Password',
            prefixIcon:
                const Icon(Icons.lock_outline, color: AppColors.primary),
            suffixIcon: IconButton(
              icon: Icon(
                _obscureConfirm ? Icons.visibility_off : Icons.visibility,
                color: AppColors.textMuted,
              ),
              onPressed: () =>
                  setState(() => _obscureConfirm = !_obscureConfirm),
            ),
          ),
        ),
        const SizedBox(height: 12),
        // Password requirements
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: Colors.grey.withOpacity(0.05),
            borderRadius: BorderRadius.circular(10),
          ),
          child: const Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Password must contain:',
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  color: AppColors.textMuted,
                ),
              ),
              SizedBox(height: 4),
              Text('  • At least 6 characters',
                  style: TextStyle(fontSize: 11, color: AppColors.textMuted)),
              Text('  • An uppercase letter',
                  style: TextStyle(fontSize: 11, color: AppColors.textMuted)),
              Text('  • A number',
                  style: TextStyle(fontSize: 11, color: AppColors.textMuted)),
              Text('  • A special character',
                  style: TextStyle(fontSize: 11, color: AppColors.textMuted)),
            ],
          ),
        ),
        const SizedBox(height: 24),
        GradientButton(
          label: 'Reset Password',
          icon: Icons.lock_reset_rounded,
          onPressed: _loading ? null : _resetPassword,
          isLoading: _loading,
        ),

      ],
    );
  }
}


