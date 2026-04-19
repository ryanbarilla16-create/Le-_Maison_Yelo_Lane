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

class _OtpScreenState extends State<OtpScreen> with TickerProviderStateMixin {
  final _otpCtrl = TextEditingController();
  bool _loading = false;
  int _cooldown = 0;
  Timer? _timer;

  late AnimationController _animController;
  late Animation<double> _fade;
  late Animation<Offset> _slide;
  late AnimationController _driftController;

  @override
  void initState() {
    super.initState();
    _startTimer();
    _animController = AnimationController(vsync: this, duration: const Duration(milliseconds: 1500));
    _fade = Tween<double>(begin: 0, end: 1).animate(CurvedAnimation(parent: _animController, curve: Curves.easeIn));
    _slide = Tween<Offset>(begin: const Offset(0, 0.1), end: Offset.zero).animate(CurvedAnimation(parent: _animController, curve: Curves.easeOutBack));
    _driftController = AnimationController(vsync: this, duration: const Duration(seconds: 40))..repeat();
    _animController.forward();
  }

  void _startTimer() {
    _timer = Timer.periodic(const Duration(seconds: 1), (t) {
      if (!mounted) { t.cancel(); return; }
      if (_cooldown > 0) { setState(() => _cooldown--); } else { t.cancel(); }
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    _animController.dispose();
    _driftController.dispose();
    super.dispose();
  }

  Future<void> _verify() async {
    final otp = _otpCtrl.text.trim();
    if (otp.isEmpty) { _showMsg('Enter OTP.', false); return; }
    setState(() => _loading = true);
    final res = await ApiService.post('/api/auth/verify_otp', {'user_id': widget.userId, 'otp': otp});
    setState(() => _loading = false);
    if (res['success'] == true) {
      Navigator.pushAndRemoveUntil(context, MaterialPageRoute(builder: (_) => const LoginScreen()), (_) => false);
    } else { _showMsg(res['message'] ?? 'Invalid.', false); }
  }

  Future<void> _resend() async {
    if (_cooldown > 0) return;
    final res = await ApiService.post('/api/auth/resend_otp', {'user_id': widget.userId});
    if (res['success'] == true) {
      setState(() => _cooldown = 300);
      _startTimer();
      _showMsg('New OTP sent!', true);
    } else { _showMsg('Resend failed.', false); }
  }

  void _showMsg(String msg, bool success) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg), backgroundColor: success ? AppColors.success : AppColors.danger, behavior: SnackBarBehavior.floating));
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
            child: CustomPaint(size: Size(size.width, 350), painter: _OtpWavePainter()),
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
                     const Text('Verification', style: TextStyle(fontSize: 28, fontWeight: FontWeight.w900, color: Colors.white, letterSpacing: 2)),
                     const Text('Security code sent to your inbox', style: TextStyle(color: Colors.white70, fontSize: 13, fontWeight: FontWeight.bold)),
                   ],
                 ),
               ),
            ),
          ),

          SingleChildScrollView(
            child: Column(
              children: [
                SizedBox(height: size.height * 0.3),
                FadeTransition(
                  opacity: _fade,
                  child: SlideTransition(
                    position: _slide,
                    child: Container(
                      margin: const EdgeInsets.symmetric(horizontal: 24), padding: const EdgeInsets.all(40),
                      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(40), boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.06), blurRadius: 40, offset: const Offset(0, 10))]),
                      child: Column(
                        children: [
                          const Text('Enter Code', style: TextStyle(fontSize: 24, fontWeight: FontWeight.w900, color: AppColors.textMain)),
                          const SizedBox(height: 40),
                          Container(
                            decoration: BoxDecoration(color: const Color(0xFFF1F3F5), borderRadius: BorderRadius.circular(20)),
                            child: TextField(
                              controller: _otpCtrl, keyboardType: TextInputType.number, textAlign: TextAlign.center, maxLength: 6,
                              style: const TextStyle(fontSize: 28, fontWeight: FontWeight.bold, letterSpacing: 10, color: AppColors.primary),
                              decoration: const InputDecoration(border: InputBorder.none, counterText: '', hintText: '------'),
                            ),
                          ),
                          const SizedBox(height: 20),
                          TextButton(onPressed: _cooldown > 0 ? null : _resend, child: Text(_cooldown > 0 ? 'Resend in ${_cooldown ~/ 60}:${(_cooldown % 60).toString().padLeft(2, '0')}' : 'Resend Code', style: const TextStyle(fontWeight: FontWeight.bold))),
                          const SizedBox(height: 40),
                          GradientButton(label: 'VERIFY EMAIL', onPressed: _loading ? null : _verify, isLoading: _loading, radius: 30, height: 60),
                        ],
                      ),
                    ),
                  ),
                ),
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
          return Positioned(left: left + (25 * _driftController.value), top: (index * 133.0) % size.height, child: Opacity(opacity: 0.03, child: Icon(Icons.mark_email_unread_rounded, size: 50, color: AppColors.primary)));
        }));
      },
    );
  }
}

class _OtpWavePainter extends CustomPainter {
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
