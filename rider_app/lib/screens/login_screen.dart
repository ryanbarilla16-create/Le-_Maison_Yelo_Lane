import 'package:flutter/material.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import '../theme.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';
import 'rider_dashboard.dart';
import 'forgot_password_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _emailCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  bool _loading = false;
  bool _obscure = true;

  Future<void> _login() async {
    final email = _emailCtrl.text.trim();
    final password = _passCtrl.text;
    if (email.isEmpty || password.isEmpty) {
      _showMsg('Please fill in all fields.');
      return;
    }

    setState(() => _loading = true);
    try {
      final res = await ApiService.post('/api/auth/login', {
        'email': email,
        'password': password,
      });

      setState(() => _loading = false);
      
      if (res['success'] == true) {
        final role = res['user']['role'];
        if (role != 'RIDER') {
          _showMsg('This account is not registered as a Rider.');
          return;
        }
        await AuthService.saveUser(res['user']);
        if (!mounted) return;
        Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => const RiderDashboard()));
      } else {
        _showMsg(res['message'] ?? 'Invalid email or password.');
      }
    } catch (e) {
      setState(() => _loading = false);
      _showMsg('Could not connect to server.');
    }
  }

  void _showMsg(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(msg), backgroundColor: AppColors.danger, behavior: SnackBarBehavior.floating),
    );
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.of(context).size;
    return Scaffold(
      body: SingleChildScrollView(
        child: Column(
          children: [
            Container(
              height: size.height * 0.4,
              width: double.infinity,
              decoration: const BoxDecoration(
                gradient: LinearGradient(
                  colors: [AppColors.primary, Color(0xFF4E342E)],
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                ),
                borderRadius: BorderRadius.only(bottomLeft: Radius.circular(80)),
              ),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(Icons.delivery_dining, size: 80, color: Colors.white),
                  const SizedBox(height: 15),
                  const Text('LE MAISON', style: TextStyle(color: Colors.white, fontSize: 32, fontWeight: FontWeight.w900, letterSpacing: 2)),
                  const Text('RIDER PORTAL', style: TextStyle(color: Colors.white70, fontSize: 12, letterSpacing: 4, fontWeight: FontWeight.bold)),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(30),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Rider Login', style: TextStyle(fontSize: 28, fontWeight: FontWeight.w900, color: AppColors.textMain)),
                  const SizedBox(height: 8),
                  const Text('Login to access your delivery dashboard.', style: TextStyle(color: AppColors.textMuted)),
                  const SizedBox(height: 40),
                  TextField(
                    controller: _emailCtrl,
                    decoration: InputDecoration(
                      labelText: 'Email Address',
                      prefixIcon: const Icon(Icons.email_outlined),
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(16)),
                    ),
                  ),
                  const SizedBox(height: 20),
                  TextField(
                    controller: _passCtrl,
                    obscureText: _obscure,
                    decoration: InputDecoration(
                      labelText: 'Password',
                      prefixIcon: const Icon(Icons.lock_outline),
                      suffixIcon: IconButton(onPressed: () => setState(() => _obscure = !_obscure), icon: Icon(_obscure ? Icons.visibility_off : Icons.visibility)),
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(16)),
                    ),
                  ),
                  Align(
                    alignment: Alignment.centerRight,
                    child: TextButton(
                      onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const ForgotPasswordScreen())),
                      child: const Text('Forgot Password?', style: TextStyle(color: AppColors.primary, fontWeight: FontWeight.bold)),
                    ),
                  ),
                  const SizedBox(height: 20),
                  GradientButton(label: 'LOGIN', onPressed: _loading ? null : _login, isLoading: _loading),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
