import 'dart:async';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:flutter/material.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:url_launcher/url_launcher.dart';
import '../theme.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';
import 'otp_screen.dart';
import 'home_screen.dart';

class SignupScreen extends StatefulWidget {
  const SignupScreen({super.key});

  @override
  State<SignupScreen> createState() => _SignupScreenState();
}

class _SignupScreenState extends State<SignupScreen> with TickerProviderStateMixin {
  final _formKey = GlobalKey<FormState>();
  final _firstNameCtrl = TextEditingController();
  final _middleNameCtrl = TextEditingController();
  final _lastNameCtrl = TextEditingController();
  final _usernameCtrl = TextEditingController();
  final _emailCtrl = TextEditingController();
  final _phoneCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  final _confirmPassCtrl = TextEditingController();
  DateTime? _birthday;
  bool _loading = false;
  bool _obscurePass = true;
  bool _termsAccepted = false;
  bool _socialLoading = false;

  late AnimationController _animController;
  late Animation<double> _fadeHeader;
  late Animation<double> _fadeForm;
  late Animation<Offset> _slideForm;
  late AnimationController _driftController;

  @override
  void initState() {
    super.initState();
    _animController = AnimationController(vsync: this, duration: const Duration(milliseconds: 1800));
    _fadeHeader = Tween<double>(begin: 0, end: 1).animate(CurvedAnimation(parent: _animController, curve: const Interval(0.0, 0.5, curve: Curves.easeIn)));
    _fadeForm = Tween<double>(begin: 0, end: 1).animate(CurvedAnimation(parent: _animController, curve: const Interval(0.4, 1.0, curve: Curves.easeIn)));
    _slideForm = Tween<Offset>(begin: const Offset(0, 0.1), end: Offset.zero).animate(CurvedAnimation(parent: _animController, curve: const Interval(0.4, 1.0, curve: Curves.easeOutBack)));
    _driftController = AnimationController(vsync: this, duration: const Duration(seconds: 45))..repeat();
    _animController.forward();
  }

  @override
  void dispose() { _animController.dispose(); _driftController.dispose(); super.dispose(); }

  void _showMsg(String msg) { ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg), backgroundColor: AppColors.danger, behavior: SnackBarBehavior.floating)); }

  Future<void> _pickBirthday() async {
    final picked = await showDatePicker(context: context, initialDate: DateTime(2000, 1, 1), firstDate: DateTime(1920), lastDate: DateTime.now());
    if (picked != null) setState(() => _birthday = picked);
  }

  Future<void> _signup() async {
    if (!_formKey.currentState!.validate()) return;
    if (_birthday == null) { _showMsg('Birth date required.'); return; }
    if (!_termsAccepted) { _showMsg('Accept terms first.'); return; }
    setState(() => _loading = true);
    final res = await ApiService.post('/api/auth/signup', {
      'first_name': _firstNameCtrl.text.trim(), 'middle_name': _middleNameCtrl.text.trim(), 'last_name': _lastNameCtrl.text.trim(), 'username': _usernameCtrl.text.trim(),
      'email': _emailCtrl.text.trim(), 'phone_number': _phoneCtrl.text.trim(), 'birthday': '${_birthday!.year}-${_birthday!.month}-${_birthday!.day}',
      'password': _passCtrl.text, 'confirm_password': _confirmPassCtrl.text,
    });
    setState(() => _loading = false);
    if (res['success'] == true) { Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => OtpScreen(userId: res['user_id']))); }
    else { _showMsg(res['message'] ?? 'Signup failed.'); }
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.of(context).size;
    return Scaffold(
      backgroundColor: Colors.white,
      body: Stack(
        children: [
          _buildDriftingBg(size),
          Positioned(top: 0, left: 0, right: 0, child: FadeTransition(opacity: _fadeHeader, child: CustomPaint(size: Size(size.width, 320), painter: _SignupWavePainter()))),
          SafeArea(
            child: SizedBox(
               width: double.infinity, height: size.height * 0.28,
               child: FadeTransition(
                 opacity: _fadeHeader,
                 child: Column(
                   mainAxisAlignment: MainAxisAlignment.center,
                   children: [
                     Container(
                       width: 80, height: 80, padding: const EdgeInsets.all(3),
                       decoration: BoxDecoration(color: Colors.white, shape: BoxShape.circle, boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.1), blurRadius: 20)]),
                       child: ClipOval(child: Image.asset('brand/logo.jpg', fit: BoxFit.cover)),
                     ),
                     const SizedBox(height: 8),
                     const Text('Join Us', style: TextStyle(fontSize: 30, fontWeight: FontWeight.w900, color: Colors.white, letterSpacing: 2)),
                     const Text('Create an account to begin', style: TextStyle(color: Colors.white70, fontSize: 13, fontWeight: FontWeight.bold)),
                   ],
                 ),
               ),
            ),
          ),
          SingleChildScrollView(
            child: Column(
              children: [
                SizedBox(height: size.height * 0.22),
                FadeTransition(
                  opacity: _fadeForm,
                  child: SlideTransition(
                    position: _slideForm,
                    child: Container(
                      margin: const EdgeInsets.symmetric(horizontal: 24), padding: const EdgeInsets.symmetric(horizontal: 30, vertical: 40),
                      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(40), boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.06), blurRadius: 40, offset: const Offset(0, 10))]),
                      child: Form(
                        key: _formKey,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('Sign Up', style: TextStyle(fontSize: 32, fontWeight: FontWeight.w900, color: AppColors.textMain)),
                            const SizedBox(height: 30),
                            _buildInput(_firstNameCtrl, 'First Name', Icons.person_outline),
                            const SizedBox(height: 16),
                            _buildInput(_middleNameCtrl, 'Middle Name', Icons.person_outline),
                            const SizedBox(height: 16),
                            _buildInput(_lastNameCtrl, 'Last Name', Icons.person_outline),
                            const SizedBox(height: 16),
                            _buildInput(_usernameCtrl, 'Username', Icons.alternate_email),
                            const SizedBox(height: 16),
                            _buildInput(_emailCtrl, 'Email Address', Icons.email_outlined, kb: TextInputType.emailAddress),
                            const SizedBox(height: 16),
                            _buildInput(_phoneCtrl, 'Phone Number', Icons.phone_android_rounded, kb: TextInputType.phone),
                            const SizedBox(height: 16),
                            GestureDetector(
                               onTap: _pickBirthday,
                               child: Container(
                                 padding: const EdgeInsets.all(18), decoration: BoxDecoration(color: const Color(0xFFF1F3F5), borderRadius: BorderRadius.circular(20)),
                                 child: Row(children: [
                                   const Icon(Icons.cake_outlined, color: AppColors.primary, size: 22), const SizedBox(width: 15),
                                   Text(_birthday == null ? 'Birthday' : '${_birthday!.month}/${_birthday!.day}/${_birthday!.year}', style: TextStyle(color: _birthday == null ? Colors.grey : AppColors.textMain, fontWeight: FontWeight.bold)),
                                 ]),
                               ),
                            ),
                            const SizedBox(height: 16),
                            _buildInput(_passCtrl, 'Password', Icons.lock_outline, obscure: _obscurePass, isPass: true, onToggle: () => setState(() => _obscurePass = !_obscurePass)),
                            const SizedBox(height: 16),
                            Row(children: [Checkbox(value: _termsAccepted, activeColor: AppColors.primary, onChanged: (v) => setState(() => _termsAccepted = v!)), const Expanded(child: Text('Accept Terms & Conditions', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w500)))]),
                            const SizedBox(height: 30),
                            GradientButton(label: 'REGISTER', onPressed: _loading ? null : _signup, isLoading: _loading, radius: 30, height: 60),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 30),
                FadeTransition(opacity: _fadeForm, child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [const Text("Member already? ", style: TextStyle(color: AppColors.textMain, fontWeight: FontWeight.w600)), GestureDetector(onTap: () => Navigator.pop(context), child: const Text('Login', style: TextStyle(color: AppColors.primary, fontWeight: FontWeight.bold)))])) ,
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
          double top = (index * 133.0) % size.height;
          return Positioned(left: left + (25 * _driftController.value), top: top + (20 * (1 - _driftController.value)), child: Opacity(opacity: 0.03, child: Icon([Icons.local_pizza, Icons.coffee, Icons.icecream][index % 3], size: 50, color: AppColors.primary)));
        }));
      },
    );
  }

  Widget _buildInput(TextEditingController ctrl, String hint, IconData icon, {bool obscure = false, bool isPass = false, VoidCallback? onToggle, TextInputType kb = TextInputType.text}) {
    return Container(decoration: BoxDecoration(color: const Color(0xFFF1F3F5), borderRadius: BorderRadius.circular(20)), padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 4), child: TextFormField(controller: ctrl, obscureText: obscure, keyboardType: kb, style: const TextStyle(fontWeight: FontWeight.bold, color: AppColors.textMain), decoration: InputDecoration(border: InputBorder.none, hintText: hint, icon: Icon(icon, color: AppColors.primary, size: 22), suffixIcon: isPass ? GestureDetector(onTap: onToggle, child: Icon(obscure ? Icons.visibility_off : Icons.visibility, color: Colors.grey, size: 20)) : null)));
  }
}

class _SignupWavePainter extends CustomPainter {
  @override void paint(Canvas canvas, Size size) {
    final paint = Paint()..color = AppColors.primary..style = PaintingStyle.fill;
    final path = Path();
    path.lineTo(0, size.height - 80); path.quadraticBezierTo(size.width * 0.5, size.height + 40, size.width, size.height - 80);
    path.lineTo(size.width, 0); path.close();
    canvas.drawShadow(path, Colors.black, 10, true);
    canvas.drawPath(path, paint);
  }
  @override bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
