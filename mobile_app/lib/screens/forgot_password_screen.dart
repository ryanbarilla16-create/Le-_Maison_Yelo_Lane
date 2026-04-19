import 'package:flutter/material.dart';
import 'dart:async';
import '../theme.dart';
import '../services/api_service.dart';

class ForgotPasswordScreen extends StatefulWidget {
  const ForgotPasswordScreen({super.key});

  @override
  State<ForgotPasswordScreen> createState() => _ForgotPasswordScreenState();
}

class _ForgotPasswordScreenState extends State<ForgotPasswordScreen> with TickerProviderStateMixin {
  int _step = 0;
  bool _loading = false;
  int? _userId;
  String? _otpCode;
  
  final _emailCtrl = TextEditingController();
  final _otpCtrl = TextEditingController();
  final _newPassCtrl = TextEditingController();
  final _confirmPassCtrl = TextEditingController();
  
  int _resendCountdown = 0;
  Timer? _countdownTimer;

  late AnimationController _animController;
  late Animation<double> _fade;
  late Animation<Offset> _slide;
  late AnimationController _driftController;

  @override
  void initState() {
    super.initState();
    _animController = AnimationController(vsync: this, duration: const Duration(milliseconds: 1500));
    _fade = Tween<double>(begin: 0, end: 1).animate(CurvedAnimation(parent: _animController, curve: Curves.easeIn));
    _slide = Tween<Offset>(begin: const Offset(0, 0.1), end: Offset.zero).animate(CurvedAnimation(parent: _animController, curve: Curves.easeOutBack));
    _driftController = AnimationController(vsync: this, duration: const Duration(seconds: 40))..repeat();
    _animController.forward();
  }

  @override
  void dispose() {
    _countdownTimer?.cancel();
    _animController.dispose();
    _driftController.dispose();
    super.dispose();
  }

  void _startResendCountdown() {
    _resendCountdown = 60;
    _countdownTimer?.cancel();
    _countdownTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted) { timer.cancel(); return; }
      setState(() {
        _resendCountdown--;
        if (_resendCountdown <= 0) timer.cancel();
      });
    });
  }

  Future<void> _sendOtp() async {
    final email = _emailCtrl.text.trim();
    if (email.isEmpty) { _showMsg('Enter email.'); return; }
    setState(() => _loading = true);
    final res = await ApiService.post('/api/auth/forgot-password', {'email': email});
    setState(() => _loading = false);
    if (res['success'] == true) {
      setState(() { _userId = res['user_id']; _step = 1; });
      _startResendCountdown();
      _showSuccess('OTP sent!');
    } else { _showMsg(res['message'] ?? 'Failed.'); }
  }

  Future<void> _verifyOtp() async {
    final otp = _otpCtrl.text.trim();
    if (otp.length != 6) return;
    setState(() => _loading = true);
    final res = await ApiService.post('/api/auth/forgot-password/verify-otp', {'user_id': _userId, 'otp': otp});
    setState(() => _loading = false);
    if (res['success'] == true) {
      setState(() { _otpCode = otp; _step = 2; });
    } else { _showMsg(res['message'] ?? 'Invalid.'); }
  }

  Future<void> _resetPassword() async {
    if (_newPassCtrl.text != _confirmPassCtrl.text) { _showMsg('Mismatch.'); return; }
    setState(() => _loading = true);
    final res = await ApiService.post('/api/auth/forgot-password/reset', {
      'user_id': _userId, 'otp': _otpCode, 'new_password': _newPassCtrl.text, 'confirm_password': _confirmPassCtrl.text,
    });
    setState(() => _loading = false);
    if (res['success'] == true) { Navigator.pop(context); _showSuccess('Password reset!'); }
    else { _showMsg(res['message'] ?? 'Failed.'); }
  }

  void _showMsg(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg), backgroundColor: AppColors.danger, behavior: SnackBarBehavior.floating));
  }
  void _showSuccess(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg), backgroundColor: AppColors.success, behavior: SnackBarBehavior.floating));
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.of(context).size;
    return Scaffold(
      backgroundColor: Colors.white,
      body: Stack(
        children: [
          _buildDriftingBg(size),
          FadeTransition(
            opacity: _fade,
            child: CustomPaint(size: Size(size.width, 350), painter: _ForgotWavePainter()),
          ),

          SafeArea(
            child: SizedBox(
               width: double.infinity, height: size.height * 0.32,
               child: FadeTransition(
                 opacity: _fade,
                 child: Column(
                   mainAxisAlignment: MainAxisAlignment.center,
                   children: [
                     Container(
                       width: 90, height: 90, padding: const EdgeInsets.all(3),
                       decoration: BoxDecoration(color: Colors.white, shape: BoxShape.circle, boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.1), blurRadius: 20)]),
                       child: ClipOval(child: Image.asset('brand/logo.jpg', fit: BoxFit.cover)),
                     ),
                     const SizedBox(height: 10),
                     const Text('Account Recovery', style: TextStyle(fontSize: 28, fontWeight: FontWeight.w900, color: Colors.white, letterSpacing: 2)),
                     Text(_step == 0 ? 'Verified identity needed' : 'Final security steps', style: const TextStyle(color: Colors.white70, fontSize: 13, fontWeight: FontWeight.bold)),
                   ],
                 ),
               ),
            ),
          ),

          SingleChildScrollView(
            child: Column(
              children: [
                SizedBox(height: size.height * 0.28),
                FadeTransition(
                  opacity: _fade,
                  child: SlideTransition(
                    position: _slide,
                    child: Container(
                      margin: const EdgeInsets.symmetric(horizontal: 24), padding: const EdgeInsets.all(35),
                      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(40), boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.06), blurRadius: 40, offset: const Offset(0, 10))]),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          if (_step == 0) ...[
                             const Text('Recovery', style: TextStyle(fontSize: 28, fontWeight: FontWeight.w900, color: AppColors.textMain)),
                             const SizedBox(height: 30),
                            _buildInput(_emailCtrl, 'Email Address', Icons.email_outlined),
                            const SizedBox(height: 30),
                            GradientButton(label: 'SEND CODE', onPressed: _loading ? null : _sendOtp, isLoading: _loading, radius: 30, height: 60),
                          ] else if (_step == 1) ...[
                             const Text('Verification', style: TextStyle(fontSize: 28, fontWeight: FontWeight.w900, color: AppColors.textMain)),
                             const SizedBox(height: 30),
                             _buildInput(_otpCtrl, '6-Digit Code', Icons.pin_rounded, kb: TextInputType.number),
                             const SizedBox(height: 10),
                             Center(child: TextButton(onPressed: _resendCountdown > 0 ? null : _sendOtp, 
                               child: Text(_resendCountdown > 0 ? 'Resend in ${_resendCountdown}s' : 'Resend Code'))),
                             const SizedBox(height: 20),
                             GradientButton(label: 'VERIFY CODE', onPressed: _loading ? null : _verifyOtp, isLoading: _loading, radius: 30, height: 60),
                          ] else ...[
                             const Text('New Password', style: TextStyle(fontSize: 28, fontWeight: FontWeight.w900, color: AppColors.textMain)),
                             const SizedBox(height: 30),
                            _buildInput(_newPassCtrl, 'New Password', Icons.lock_outline, obscure: true, isPass: true),
                            const SizedBox(height: 16),
                            _buildInput(_confirmPassCtrl, 'Confirm Password', Icons.lock_outline, obscure: true, isPass: true),
                            const SizedBox(height: 30),
                            GradientButton(label: 'RESET PASSWORD', onPressed: _loading ? null : _resetPassword, isLoading: _loading, radius: 30, height: 60),
                          ],
                        ],
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 40),
                TextButton(onPressed: () => Navigator.pop(context), 
                  child: const Text('Back to Login', style: TextStyle(color: AppColors.primary, fontWeight: FontWeight.bold))),
                const SizedBox(height: 50),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDriftingBg(Size size) {
    return AnimatedBuilder(
      animation: _driftController, builder: (context, child) {
        return Stack(children: List.generate(12, (index) {
          double left = (index * 97.0) % size.width;
          return Positioned(left: left + (25 * _driftController.value), top: (index * 133.0) % size.height, child: Opacity(opacity: 0.03, child: Icon(Icons.security, size: 50, color: AppColors.primary)));
        }));
      },
    );
  }

  Widget _buildInput(TextEditingController ctrl, String hint, IconData icon, {bool obscure = false, bool isPass = false, VoidCallback? onToggle, TextInputType kb = TextInputType.text}) {
    return Container(decoration: BoxDecoration(color: const Color(0xFFF1F3F5), borderRadius: BorderRadius.circular(20)), padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 4), child: TextFormField(controller: ctrl, obscureText: obscure, keyboardType: kb, style: const TextStyle(fontWeight: FontWeight.bold, color: AppColors.textMain), decoration: InputDecoration(border: InputBorder.none, hintText: hint, icon: Icon(icon, color: AppColors.primary, size: 22))));
  }
}

class _ForgotWavePainter extends CustomPainter {
  @override void paint(Canvas canvas, Size size) {
    final paint = Paint()..color = AppColors.primary..style = PaintingStyle.fill;
    final path = Path();
    path.lineTo(0, size.height - 70); path.quadraticBezierTo(size.width * 0.5, size.height + 30, size.width, size.height - 70);
    path.lineTo(size.width, 0); path.close();
    canvas.drawShadow(path, Colors.black, 10, true);
    canvas.drawPath(path, paint);
  }
  @override bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
