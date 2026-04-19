import 'dart:async';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:flutter/material.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:url_launcher/url_launcher.dart';
import '../theme.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';
import 'signup_screen.dart';
import 'home_screen.dart';
import 'rider_screen.dart';
import 'otp_screen.dart';
import 'forgot_password_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> with TickerProviderStateMixin {
  final _emailCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  bool _loading = false;
  bool _obscure = true;
  bool _socialLoading = false;

  late AnimationController _animController;
  late Animation<double> _fadeHeader;
  late Animation<double> _fadeForm;
  late Animation<Offset> _slideForm;
  
  late AnimationController _driftController;

  @override
  void initState() {
    super.initState();
    _animController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1800),
    );

    _fadeHeader = Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(parent: _animController, curve: const Interval(0.0, 0.5, curve: Curves.easeIn)),
    );

    _fadeForm = Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(parent: _animController, curve: const Interval(0.4, 1.0, curve: Curves.easeIn)),
    );

    _slideForm = Tween<Offset>(begin: const Offset(0, 0.15), end: Offset.zero).animate(
      CurvedAnimation(parent: _animController, curve: const Interval(0.4, 1.0, curve: Curves.easeOutBack)),
    );

    _driftController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 40),
    )..repeat();

    _animController.forward();
  }

  @override
  void dispose() {
    _animController.dispose();
    _driftController.dispose();
    _emailCtrl.dispose();
    _passCtrl.dispose();
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _login() async {
    final email = _emailCtrl.text.trim();
    final password = _passCtrl.text;
    if (email.isEmpty || password.isEmpty) { _showMsg('Please fill in all fields.'); return; }
    setState(() => _loading = true);
    try {
      final res = await ApiService.post('/api/auth/login', {'email': email, 'password': password});
      setState(() => _loading = false);
      if (res['success'] == true) {
        await AuthService.saveUser(res['user']);
        if (!mounted) return;
        final role = res['user']['role'] ?? 'USER';
        Navigator.pushAndRemoveUntil(context, MaterialPageRoute(builder: (_) => role == 'RIDER' ? const RiderScreen() : const HomeScreen()), (_) => false);
      } else if (res['needs_otp'] == true) {
        Navigator.push(context, MaterialPageRoute(builder: (_) => OtpScreen(userId: res['user_id'])));
      } else { _showMsg(res['message'] ?? 'Login failed.'); }
    } catch (e) { setState(() => _loading = false); _showMsg('Error logged.'); }
  }

  Future<void> _handleGoogleLogin() async {
    setState(() => _socialLoading = true);
    try {
      final googleSignIn = GoogleSignIn(scopes: ['email', 'profile']);
      final account = await googleSignIn.signIn();
      if (account == null) { setState(() => _socialLoading = false); return; }
      final res = await ApiService.post('/api/auth/social', {
        'email': account.email,
        'first_name': account.displayName?.split(' ').first ?? '',
        'last_name': account.displayName?.split(' ').skip(1).join(' ') ?? '',
        'provider': 'Google', 'picture_url': account.photoUrl,
      });
      await googleSignIn.signOut();
      if (!mounted) return;
      setState(() => _socialLoading = false);
      if (res['success'] == true) {
        await AuthService.saveUser(res['user']);
        Navigator.pushAndRemoveUntil(context, MaterialPageRoute(builder: (_) => const HomeScreen()), (_) => false);
      } else if (res['needs_otp'] == true) {
        Navigator.push(context, MaterialPageRoute(builder: (_) => OtpScreen(userId: res['user_id'])));
      } else { _showMsg(res['message'] ?? 'Login failed.'); }
    } catch (e) { setState(() => _socialLoading = false); _showMsg('Login error.'); }
  }

  Timer? _pollTimer;
  Future<void> _handleFacebookLogin() async {
    setState(() => _socialLoading = true);
    final sessionId = '${DateTime.now().millisecondsSinceEpoch}';
    final String oauthBase = dotenv.env['OAUTH_BASE_URL'] ?? 'http://192.168.0.1:5000';
    final url = Uri.parse('$oauthBase/mobile/social?provider=facebook&session_id=$sessionId');
    try {
      await launchUrl(url, mode: LaunchMode.externalApplication);
      _pollTimer?.cancel();
      _pollTimer = Timer.periodic(const Duration(seconds: 2), (t) async {
        final res = await ApiService.get('/api/auth/social/poll?session_id=$sessionId');
        if (res != null && res['success'] == true) {
          t.cancel(); setState(() => _socialLoading = false);
          await AuthService.saveUser(res['user']);
          Navigator.pushAndRemoveUntil(context, MaterialPageRoute(builder: (_) => const HomeScreen()), (_) => false);
        } else if (res != null && res['needs_otp'] == true) {
          t.cancel(); setState(() => _socialLoading = false);
          Navigator.push(context, MaterialPageRoute(builder: (_) => OtpScreen(userId: res['user_id'])));
        }
      });
    } catch (e) { setState(() => _socialLoading = false); }
  }

  void _showMsg(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg), backgroundColor: AppColors.danger, behavior: SnackBarBehavior.floating));
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.of(context).size;
    return Scaffold(
      backgroundColor: Colors.white,
      body: Stack(
        children: [
          _buildDriftingBg(size),
          Positioned(
            top: 0, left: 0, right: 0,
            child: FadeTransition(
              opacity: _fadeHeader,
              child: CustomPaint(size: Size(size.width, 380), painter: _LoginWavePainter()),
            ),
          ),
          SafeArea(
            child: SizedBox(
              width: double.infinity, height: size.height * 0.35,
              child: FadeTransition(
                opacity: _fadeHeader,
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Container(
                      width: 100,
                      height: 100,
                      padding: const EdgeInsets.all(4),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        shape: BoxShape.circle,
                        boxShadow: [
                          BoxShadow(
                            color: AppColors.primary.withOpacity(0.3),
                            blurRadius: 30,
                            offset: const Offset(0, 5),
                          ),
                        ],
                      ),
                      child: ClipOval(
                        child: Image.asset(
                          'brand/logo.jpg',
                          fit: BoxFit.cover,
                        ),
                      ),
                    ),
                    const SizedBox(height: 15),
                    const Text('LE MAISON', style: TextStyle(fontSize: 32, fontWeight: FontWeight.w900, color: Colors.white, letterSpacing: 2)),
                    const Text('YELO LANE', style: TextStyle(fontSize: 12, color: Colors.white70, letterSpacing: 8, fontWeight: FontWeight.bold)),
                  ],
                ),
              ),
            ),
          ),
          SingleChildScrollView(
            child: Column(
              children: [
                SizedBox(height: size.height * 0.32),
                FadeTransition(
                  opacity: _fadeForm,
                  child: SlideTransition(
                    position: _slideForm,
                    child: Container(
                      margin: const EdgeInsets.symmetric(horizontal: 24),
                      padding: const EdgeInsets.symmetric(horizontal: 30, vertical: 40),
                      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(40), boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.06), blurRadius: 40, offset: const Offset(0, 15))]),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text('Login', style: TextStyle(fontSize: 34, fontWeight: FontWeight.w900, color: AppColors.textMain)),
                          const SizedBox(height: 8),
                          const Text('Welcome back to the flavors of home', style: TextStyle(color: AppColors.textMuted, fontSize: 14, fontWeight: FontWeight.w500)),
                          const SizedBox(height: 40),
                          _buildInput(_emailCtrl, 'Email Address', Icons.alternate_email_rounded, kb: TextInputType.emailAddress),
                          const SizedBox(height: 20),
                          _buildInput(_passCtrl, 'Password', Icons.lock_outline_rounded, obscure: _obscure, isPass: true, onToggle: () => setState(() => _obscure = !_obscure)),
                          const SizedBox(height: 16),
                          Align(alignment: Alignment.centerRight, child: GestureDetector(onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const ForgotPasswordScreen())), child: const Text('Forgot Password?', style: TextStyle(color: AppColors.primary, fontWeight: FontWeight.w800, fontSize: 13)))),
                          const SizedBox(height: 40),
                          GradientButton(label: 'SIGN IN', onPressed: _loading ? null : _login, isLoading: _loading, radius: 35, height: 65, fontSize: 16),
                          const SizedBox(height: 40),
                          Row(children: [Expanded(child: Divider(color: Colors.grey.shade200, thickness: 1)), Padding(padding: const EdgeInsets.symmetric(horizontal: 16), child: Text('SOCIAL LOGIN', style: TextStyle(color: Colors.grey.shade400, fontSize: 11, fontWeight: FontWeight.w900, letterSpacing: 1.5))), Expanded(child: Divider(color: Colors.grey.shade200, thickness: 1))]),
                          const SizedBox(height: 30),
                          Row(mainAxisAlignment: MainAxisAlignment.center, children: [_socialBtn('https://cdn-icons-png.flaticon.com/512/300/300221.png', _handleGoogleLogin), const SizedBox(width: 30), _socialBtn('https://cdn-icons-png.flaticon.com/512/733/733547.png', _handleFacebookLogin)]),
                        ],
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 40),
                FadeTransition(opacity: _fadeForm, child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [const Text("New here? ", style: TextStyle(color: AppColors.textMain, fontWeight: FontWeight.w600)), GestureDetector(onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const SignupScreen())), child: const Text('Get Started', style: TextStyle(color: AppColors.primary, fontWeight: FontWeight.bold)))])),
                const SizedBox(height: 50),
              ],
            ),
          ),
          if (_socialLoading) Container(color: Colors.black.withOpacity(0.3), child: const Center(child: Column(mainAxisSize: MainAxisSize.min, children: [CircularProgressIndicator(color: Colors.white), SizedBox(height: 16), Text('Connecting...', style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600))]))),
        ],
      ),
    );
  }

  Widget _buildDriftingBg(Size size) {
    return AnimatedBuilder(
      animation: _driftController,
      builder: (context, child) {
        return Stack(children: List.generate(12, (index) {
          double left = (index * 97.0) % size.width;
          double top = (index * 133.0) % size.height;
          return Positioned(left: left + (20 * _driftController.value), top: top + (30 * (1 - _driftController.value)), child: Opacity(opacity: 0.03, child: Icon([Icons.local_pizza, Icons.coffee, Icons.icecream, Icons.fastfood, Icons.ramen_dining][index % 5], size: 50, color: AppColors.primary)));
        }));
      },
    );
  }

  Widget _buildInput(TextEditingController ctrl, String hint, IconData icon, {bool obscure = false, bool isPass = false, VoidCallback? onToggle, TextInputType kb = TextInputType.text}) {
    return Container(decoration: BoxDecoration(color: const Color(0xFFF1F3F5), borderRadius: BorderRadius.circular(20)), padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 5), child: TextField(controller: ctrl, obscureText: obscure, keyboardType: kb, style: const TextStyle(fontWeight: FontWeight.bold, color: AppColors.textMain), decoration: InputDecoration(icon: Icon(icon, color: AppColors.primary, size: 22), border: InputBorder.none, hintText: hint, hintStyle: const TextStyle(color: Colors.grey, fontWeight: FontWeight.w500), suffixIcon: isPass ? GestureDetector(onTap: onToggle, child: Icon(obscure ? Icons.visibility_off_rounded : Icons.visibility_rounded, color: Colors.grey, size: 20)) : null)));
  }

  Widget _socialBtn(String url, VoidCallback? onTap) {
    return GestureDetector(onTap: onTap, child: Container(height: 60, width: 60, padding: const EdgeInsets.all(15), decoration: BoxDecoration(color: Colors.white, shape: BoxShape.circle, boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.06), blurRadius: 15, offset: const Offset(0, 5))], border: Border.all(color: Colors.grey.shade100)), child: Image.network(url)));
  }
}

class _LoginWavePainter extends CustomPainter {
  @override void paint(Canvas canvas, Size size) {
    final paint = Paint()..color = AppColors.primary..style = PaintingStyle.fill;
    final path = Path();
    path.lineTo(0, size.height - 100);
    path.quadraticBezierTo(size.width * 0.25, size.height - 40, size.width * 0.5, size.height - 80);
    path.quadraticBezierTo(size.width * 0.75, size.height - 120, size.width, size.height - 50);
    path.lineTo(size.width, 0); path.close();
    canvas.drawShadow(path, Colors.black, 10, true);
    canvas.drawPath(path, paint);
  }
  @override bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
