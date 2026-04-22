import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';
import '../theme.dart';

class ChangePasswordScreen extends StatefulWidget {
  const ChangePasswordScreen({super.key});

  @override
  State<ChangePasswordScreen> createState() => _ChangePasswordScreenState();
}

class _ChangePasswordScreenState extends State<ChangePasswordScreen> {
  final _currentCtrl = TextEditingController();
  final _newCtrl = TextEditingController();
  final _confirmCtrl = TextEditingController();
  bool _loading = false;
  bool _showCurr = false;
  bool _showNew = false;
  bool _showConf = false;

  Future<void> _submit() async {
    if (_currentCtrl.text.isEmpty || _newCtrl.text.isEmpty || _confirmCtrl.text.isEmpty) {
      _showMsg('Please fill in all fields.', Colors.orange);
      return;
    }
    if (_newCtrl.text != _confirmCtrl.text) {
      _showMsg('Passwords do not match.', Colors.red);
      return;
    }

    setState(() => _loading = true);
    final user = await AuthService.getUser();
    final res = await ApiService.put('/api/user/${user?['id']}/profile', {
      'current_password': _currentCtrl.text,
      'new_password': _newCtrl.text,
      'confirm_new_password': _confirmCtrl.text,
      // Pass existing data to avoid overwriting with nulls if API requires it
      'first_name': user?['first_name'],
      'last_name': user?['last_name'],
      'username': user?['username'],
      'email': user?['email'],
    });
    setState(() => _loading = false);

    if (res['success'] == true) {
      _showMsg('Password updated successfully!', Colors.green);
      if (mounted) Navigator.pop(context);
    } else {
      _showMsg(res['message'] ?? 'Error updating password.', Colors.red);
    }
  }

  void _showMsg(String msg, Color color) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(msg), backgroundColor: color, behavior: SnackBarBehavior.floating),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('CHANGE PASSWORD', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 18)),
        centerTitle: true,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            const Icon(Icons.security, size: 60, color: AppColors.primary),
            const SizedBox(height: 24),
            const Text('Secure your account by setting a new password.', textAlign: TextAlign.center, style: TextStyle(color: AppColors.textMuted)),
            const SizedBox(height: 32),
            _buildField('Current Password', _currentCtrl, _showCurr, () => setState(() => _showCurr = !_showCurr)),
            const SizedBox(height: 16),
            _buildField('New Password', _newCtrl, _showNew, () => setState(() => _showNew = !_showNew)),
            const SizedBox(height: 16),
            _buildField('Confirm New Password', _confirmCtrl, _showConf, () => setState(() => _showConf = !_showConf)),
            const SizedBox(height: 40),
            GradientButton(label: 'SAVE PASSWORD', onPressed: _loading ? null : _submit, isLoading: _loading),
          ],
        ),
      ),
    );
  }

  Widget _buildField(String label, TextEditingController ctrl, bool show, VoidCallback onToggle) {
    return TextField(
      controller: ctrl,
      obscureText: !show,
      decoration: InputDecoration(
        labelText: label,
        prefixIcon: const Icon(Icons.lock_outline),
        suffixIcon: IconButton(onPressed: onToggle, icon: Icon(show ? Icons.visibility_off : Icons.visibility)),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(16)),
      ),
    );
  }
}
