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

class _SignupScreenState extends State<SignupScreen> {
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
  bool _obscureConfirm = true;
  bool _termsAccepted = false;
  bool _socialLoading = false;

  // ═══ SAME VALIDATIONS AS WEB ═══
  String? _validateName(String? value, String field) {
    if (value == null || value.trim().isEmpty) return '$field is required.';
    final v = value.trim();
    if (v.length > 50) return '$field must be 50 characters or less.';
    if (!RegExp(r'^[A-Za-z\s\-]+$').hasMatch(v))
      return '$field can only contain letters, spaces, and dashes.';
    if (RegExp(r'(.)\1{4,}').hasMatch(v))
      return '$field contains too many repeated characters.';
    final words = v.toLowerCase().split(' ');
    if (words.length != words.toSet().length)
      return '$field cannot contain repeated words.';
    return null;
  }

  String? _validateEmail(String? value) {
    if (value == null || value.trim().isEmpty) return 'Email is required.';
    final email = value.trim();
    if (!RegExp(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$').hasMatch(email))
      return 'Please enter a valid email address.';
    return null;
  }

  String? _validateUsername(String? value) {
    if (value == null || value.trim().isEmpty) return 'Username is required.';
    final u = value.trim();
    if (u.length < 5 || u.length > 20)
      return 'Username must be 5-20 characters.';
    if (!RegExp(r'^[A-Za-z0-9_]+$').hasMatch(u))
      return 'Username can only contain letters, numbers, and underscores.';
    if (RegExp(r'(.)\1{4,}').hasMatch(u))
      return 'Username contains too many repeated characters.';
    if (u.toLowerCase() == _firstNameCtrl.text.trim().toLowerCase() ||
        u.toLowerCase() == _lastNameCtrl.text.trim().toLowerCase()) {
      return 'Username cannot be identical to your first or last name.';
    }
    final fullIdentity =
        '${_firstNameCtrl.text.trim()} ${_lastNameCtrl.text.trim()}'
            .toLowerCase();
    if (u.toLowerCase() == fullIdentity)
      return 'Username cannot be identical to Full Name.';
    return null;
  }

  String? _validatePassword(String? value) {
    if (value == null || value.isEmpty) return 'Password is required.';
    if (value.startsWith(' ') || value.endsWith(' ')) return 'Password cannot start or end with spaces.';
    if (value.contains('   ')) return 'Password cannot contain too many consecutive spaces.';
    if (value.length < 6) return 'Password must be at least 6 characters.';
    if (!RegExp(r'[A-Z]').hasMatch(value))
      return 'Password must contain an uppercase letter.';
    if (!RegExp(r'[0-9]').hasMatch(value))
      return 'Password must contain a number.';
    if (!RegExp(r'[^A-Za-z0-9\s]').hasMatch(value))
      return 'Password must contain a special character.';
    return null;
  }

  String? _validateConfirmPassword(String? value) {
    if (value != _passCtrl.text) return 'Passwords do not match.';
    return null;
  }

  Future<void> _pickBirthday() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: DateTime(2000, 1, 1),
      firstDate: DateTime(1920),
      lastDate: DateTime.now(),
      builder: (context, child) {
        return Theme(
          data: Theme.of(context).copyWith(
            colorScheme: const ColorScheme.light(
              primary: AppColors.primary,
              onPrimary: Colors.white,
            ),
          ),
          child: child!,
        );
      },
    );
    if (picked != null) setState(() => _birthday = picked);
  }

  int _calcAge(DateTime born) {
    final now = DateTime.now();
    int age = now.year - born.year;
    if (now.month < born.month ||
        (now.month == born.month && now.day < born.day))
      age--;
    return age;
  }

  // ═══ GOOGLE SIGNUP (Native SDK) ═══
  Future<void> _handleGoogleSignup() async {
    setState(() => _socialLoading = true);
    try {
      final googleSignIn = GoogleSignIn(scopes: ['email', 'profile']);
      final account = await googleSignIn.signIn();
      if (account == null) {
        setState(() => _socialLoading = false);
        return;
      }

      final res = await ApiService.post('/api/auth/social', {
        'email': account.email,
        'first_name': account.displayName?.split(' ').first ?? '',
        'last_name': account.displayName?.split(' ').skip(1).join(' ') ?? '',
        'provider': 'Google',
        'picture_url': account.photoUrl,
      });

      await googleSignIn.signOut();

      if (!mounted) return;
      setState(() => _socialLoading = false);

      if (res['success'] == true) {
        await AuthService.saveUser(res['user']);
        if (!mounted) return;
        Navigator.pushAndRemoveUntil(
          context,
          MaterialPageRoute(builder: (_) => const HomeScreen()),
          (_) => false,
        );
      } else {
        _showMsg(res['message'] ?? 'Google signup failed.');
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _socialLoading = false);
      _showMsg(
        'Google Sign-In failed. Make sure Google Play Services is available.',
      );
    }
  }

  // ═══ FACEBOOK SIGNUP (In-App Browser) ═══
  Timer? _pollTimer;

  Future<void> _handleFacebookSignup() async {
    setState(() => _socialLoading = true);
    final sessionId =
        '${DateTime.now().millisecondsSinceEpoch}_${(1000 + (DateTime.now().microsecond % 9000))}';
    // Use local machine IP instead of localtunnel for Facebook redirect flow
    final String oauthBase = dotenv.env['OAUTH_BASE_URL'] ?? 'http://192.168.0.1:5000';
    final url = Uri.parse(
      '$oauthBase/mobile/social?provider=facebook&session_id=$sessionId',
    );

    try {
      await launchUrl(url, mode: LaunchMode.externalApplication);

      _pollTimer?.cancel();
      _pollTimer = Timer.periodic(const Duration(seconds: 2), (timer) async {
        try {
          final res = await ApiService.get(
            '/api/auth/social/poll?session_id=$sessionId',
          );
          if (res != null && res['success'] == true) {
            timer.cancel();
            if (!mounted) return;
            setState(() => _socialLoading = false);
            await AuthService.saveUser(res['user']);
            if (mounted) {
              Navigator.pushAndRemoveUntil(
                context,
                MaterialPageRoute(builder: (_) => const HomeScreen()),
                (_) => false,
              );
            }
          } else if (res != null && res['status'] == 'failed') {
            timer.cancel();
            if (!mounted) return;
            setState(() => _socialLoading = false);
            _showMsg(res['message'] ?? 'Facebook signup failed.');
          }
        } catch (e) {
          // ignore polling errors
        }
      });

      Future.delayed(const Duration(minutes: 3), () {
        if (_pollTimer != null && _pollTimer!.isActive) {
          _pollTimer!.cancel();
          if (mounted) setState(() => _socialLoading = false);
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _socialLoading = false);
      _showMsg('Could not open Facebook login.');
    }
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _signup() async {
    if (!_formKey.currentState!.validate()) return;

    if (_birthday == null) {
      _showMsg('Please select your birthday.');
      return;
    }

    final age = _calcAge(_birthday!);
    if (age < 18) {
      _showMsg('You must be at least 18 years old to register.');
      return;
    }
    if (age > 70) {
      _showMsg('Maximum age limit is 70 years old.');
      return;
    }

    if (!_termsAccepted) {
      _showMsg('Please accept the Terms & Conditions.');
      return;
    }

    setState(() => _loading = true);

    final res = await ApiService.post('/api/auth/signup', {
      'first_name': _firstNameCtrl.text.trim(),
      'middle_name': _middleNameCtrl.text.trim(),
      'last_name': _lastNameCtrl.text.trim(),
      'username': _usernameCtrl.text.trim(),
      'email': _emailCtrl.text.trim(),
      'phone_number': _phoneCtrl.text.trim(),
      'birthday':
          '${_birthday!.year}-${_birthday!.month.toString().padLeft(2, '0')}-${_birthday!.day.toString().padLeft(2, '0')}',
      'password': _passCtrl.text,
      'confirm_password': _confirmPassCtrl.text,
    });

    setState(() => _loading = false);

    if (res['success'] == true) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(res['message'] ?? 'OTP sent!'),
          backgroundColor: AppColors.success,
        ),
      );
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (_) => OtpScreen(userId: res['user_id'])),
      );
    } else {
      _showMsg(res['message'] ?? 'Signup failed.');
    }
  }

  void _showMsg(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(msg), backgroundColor: AppColors.danger),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Create Account'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: Stack(
        children: [
          SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Form(
              key: _formKey,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Center(
                    child: Column(
                      children: [
                        Container(
                          padding: const EdgeInsets.all(14),
                          decoration: BoxDecoration(
                            gradient: const LinearGradient(
                              colors: [
                                AppColors.primary,
                                AppColors.primaryLight,
                              ],
                            ),
                            borderRadius: BorderRadius.circular(16),
                          ),
                          child: const Icon(
                            Icons.person_add,
                            color: Colors.white,
                            size: 30,
                          ),
                        ),
                        const SizedBox(height: 12),
                        Text(
                          'Join Le Maison',
                          style: AppTextStyles.heading.copyWith(fontSize: 22),
                        ),
                        const Text(
                          'Create your account to get started',
                          style: AppTextStyles.muted,
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 24),

                  // ═══ SOCIAL LOGIN BUTTONS ═══
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: _socialLoading
                              ? null
                              : _handleGoogleSignup,
                          icon: Image.network(
                            'https://cdn-icons-png.flaticon.com/512/300/300221.png',
                            width: 20,
                            height: 20,
                            errorBuilder: (_, __, ___) =>
                                const Icon(Icons.g_mobiledata, size: 20),
                          ),
                          label: const Text(
                            'Google',
                            style: TextStyle(
                              fontWeight: FontWeight.w600,
                              fontSize: 13,
                            ),
                          ),
                          style: OutlinedButton.styleFrom(
                            foregroundColor: AppColors.textMain,
                            side: BorderSide(color: Colors.grey.shade300),
                            padding: const EdgeInsets.symmetric(vertical: 12),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(25),
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: _socialLoading
                              ? null
                              : _handleFacebookSignup,
                          icon: const Icon(
                            Icons.facebook,
                            color: Color(0xFF1877F2),
                            size: 20,
                          ),
                          label: const Text(
                            'Facebook',
                            style: TextStyle(
                              fontWeight: FontWeight.w600,
                              fontSize: 13,
                            ),
                          ),
                          style: OutlinedButton.styleFrom(
                            foregroundColor: AppColors.textMain,
                            side: BorderSide(color: Colors.grey.shade300),
                            padding: const EdgeInsets.symmetric(vertical: 12),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(25),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 20),

                  // Divider
                  Row(
                    children: [
                      Expanded(child: Divider(color: Colors.grey.shade300)),
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 16),
                        child: Text(
                          'OR SIGN UP WITH EMAIL',
                          style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.w700,
                            color: AppColors.textMuted,
                            letterSpacing: 1,
                          ),
                        ),
                      ),
                      Expanded(child: Divider(color: Colors.grey.shade300)),
                    ],
                  ),
                  const SizedBox(height: 20),

                  _buildField(
                    'First Name *',
                    _firstNameCtrl,
                    Icons.person_outline,
                    validator: (v) => _validateName(v, 'First Name'),
                  ),
                  _buildField(
                    'Middle Name',
                    _middleNameCtrl,
                    Icons.person_outline,
                  ),
                  _buildField(
                    'Last Name *',
                    _lastNameCtrl,
                    Icons.person_outline,
                    validator: (v) => _validateName(v, 'Last Name'),
                  ),
                  _buildField(
                    'Username *',
                    _usernameCtrl,
                    Icons.alternate_email,
                    validator: _validateUsername,
                  ),
                  _buildField(
                    'Email *',
                    _emailCtrl,
                    Icons.email_outlined,
                    validator: _validateEmail,
                    keyboardType: TextInputType.emailAddress,
                  ),
                  _buildField(
                    'Phone Number *',
                    _phoneCtrl,
                    Icons.phone_outlined,
                    keyboardType: TextInputType.phone,
                  ),

                  // Birthday picker
                  const SizedBox(height: 4),
                  GestureDetector(
                    onTap: _pickBirthday,
                    child: AbsorbPointer(
                      child: TextFormField(
                        decoration: InputDecoration(
                          labelText: 'Birthday *',
                          prefixIcon: const Icon(
                            Icons.cake_outlined,
                            color: AppColors.primary,
                          ),
                          hintText: _birthday != null
                              ? '${_birthday!.month}/${_birthday!.day}/${_birthday!.year}'
                              : 'Select your birthday',
                        ),
                        controller: TextEditingController(
                          text: _birthday != null
                              ? '${_birthday!.month}/${_birthday!.day}/${_birthday!.year}'
                              : '',
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),

                  // Password
                  TextFormField(
                    controller: _passCtrl,
                    obscureText: _obscurePass,
                    validator: _validatePassword,
                    decoration: InputDecoration(
                      labelText: 'Password *',
                      prefixIcon: const Icon(
                        Icons.lock_outline,
                        color: AppColors.primary,
                      ),
                      suffixIcon: IconButton(
                        icon: Icon(
                          _obscurePass
                              ? Icons.visibility_off
                              : Icons.visibility,
                          color: AppColors.textMuted,
                        ),
                        onPressed: () =>
                            setState(() => _obscurePass = !_obscurePass),
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _confirmPassCtrl,
                    obscureText: _obscureConfirm,
                    validator: _validateConfirmPassword,
                    decoration: InputDecoration(
                      labelText: 'Confirm Password *',
                      prefixIcon: const Icon(
                        Icons.lock_outline,
                        color: AppColors.primary,
                      ),
                      suffixIcon: IconButton(
                        icon: Icon(
                          _obscureConfirm
                              ? Icons.visibility_off
                              : Icons.visibility,
                          color: AppColors.textMuted,
                        ),
                        onPressed: () =>
                            setState(() => _obscureConfirm = !_obscureConfirm),
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),

                  // Terms
                  Row(
                    children: [
                      Checkbox(
                        value: _termsAccepted,
                        onChanged: (v) =>
                            setState(() => _termsAccepted = v ?? false),
                        activeColor: AppColors.primary,
                      ),
                      const Expanded(
                        child: Text(
                          'I accept the Terms & Conditions',
                          style: TextStyle(fontSize: 13),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 20),

                  SizedBox(
                    width: double.infinity,
                    height: 52,
                    child: ElevatedButton(
                      onPressed: _loading ? null : _signup,
                      child: _loading
                          ? const SizedBox(
                              width: 22,
                              height: 22,
                              child: CircularProgressIndicator(
                                color: Colors.white,
                                strokeWidth: 2.5,
                              ),
                            )
                          : const Text('Create Account'),
                    ),
                  ),
                  const SizedBox(height: 20),
                ],
              ),
            ),
          ),
          // Social loading overlay
          if (_socialLoading)
            Container(
              color: Colors.black.withOpacity(0.3),
              child: const Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    CircularProgressIndicator(color: Colors.white),
                    SizedBox(height: 16),
                    Text(
                      'Connecting...',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildField(
    String label,
    TextEditingController ctrl,
    IconData icon, {
    String? Function(String?)? validator,
    TextInputType? keyboardType,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: TextFormField(
        controller: ctrl,
        keyboardType: keyboardType,
        validator:
            validator ??
            (label.contains('*')
                ? (v) => (v == null || v.trim().isEmpty)
                      ? '$label is required.'
                      : null
                : null),
        decoration: InputDecoration(
          labelText: label,
          prefixIcon: Icon(icon, color: AppColors.primary),
        ),
      ),
    );
  }
}


