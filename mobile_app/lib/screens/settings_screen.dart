import 'package:flutter/material.dart';
import '../theme.dart';
import '../services/auth_service.dart';
import 'login_screen.dart';
import 'forgot_password_screen.dart';
import '../services/api_service.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  bool _notificationsEnabled = true;
  bool _darkMode = false;
  String _language = 'English';
  bool _isDeleting = false;

  void _changePassword() async {
    final user = await AuthService.getUser();
    if (user == null || user['email'] == null) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Error: User email not found.')),
      );
      return;
    }

    // Reuse ForgotPasswordScreen but we can pre-navigate or just let them enter email
    // To make it smoother, we'll navigate to ForgotPasswordScreen
    if (!mounted) return;
    Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => const ForgotPasswordScreen()),
    );
  }

  void _deleteAccount() async {
    bool? confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete Account?'),
        content: const Text(
          'This action is permanent and cannot be undone. All your orders and reservations will be removed.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: TextButton.styleFrom(foregroundColor: AppColors.danger),
            child: const Text('Delete Permanently'),
          ),
        ],
      ),
    );

    if (confirm != true) return;

    setState(() => _isDeleting = true);
    final userId = await AuthService.getUserId();
    final res = await ApiService.delete('/api/user/$userId');
    setState(() => _isDeleting = false);

    if (res != null && res['success'] == true) {
      await AuthService.logout();
      if (!mounted) return;
      Navigator.pushAndRemoveUntil(
        context,
        MaterialPageRoute(builder: (_) => const LoginScreen()),
        (_) => false,
      );
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Account deleted successfully.')),
      );
    } else {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(res['message'] ?? 'Failed to delete account.'),
          backgroundColor: AppColors.danger,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(
          'Settings',
          style: AppTextStyles.heading.copyWith(fontSize: 20),
        ),
        centerTitle: true,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 20),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          _sectionHeader('Preferences'),
          _settingItem(
            title: 'Push Notifications',
            subtitle: 'Receive updates about your orders',
            icon: Icons.notifications_none_rounded,
            trailing: Switch.adaptive(
              value: _notificationsEnabled,
              activeColor: AppColors.primary,
              onChanged: (val) => setState(() => _notificationsEnabled = val),
            ),
          ),
          _settingItem(
            title: 'Dark Mode',
            subtitle: 'Toggle dark interface for night use',
            icon: Icons.dark_mode_outlined,
            trailing: Switch.adaptive(
              value: _darkMode,
              activeColor: AppColors.primary,
              onChanged: (val) => setState(() => _darkMode = val),
            ),
          ),
          const SizedBox(height: 24),
          _sectionHeader('Account & Security'),
          _settingItem(
            title: 'Language',
            subtitle: _language,
            icon: Icons.language_rounded,
            onTap: () {
              // TODO: Show language picker
            },
          ),
          _settingItem(
            title: 'Change Password',
            subtitle: 'Secure your account',
            icon: Icons.lock_outline_rounded,
            onTap: _changePassword,
          ),
          _settingItem(
            title: 'Delete Account',
            subtitle: 'Permanently remove your data',
            icon: Icons.delete_outline_rounded,
            titleColor: AppColors.danger,
            trailing: _isDeleting 
              ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
              : null,
            onTap: _isDeleting ? null : _deleteAccount,
          ),
          const SizedBox(height: 24),
          _sectionHeader('About'),
          _settingItem(
            title: 'Help Center',
            subtitle: 'FAQs and support chat',
            icon: Icons.help_outline_rounded,
            onTap: () {},
          ),
          _settingItem(
            title: 'Terms & Conditions',
            subtitle: 'Read our legal guidelines',
            icon: Icons.description_outlined,
            onTap: () {},
          ),
          _settingItem(
            title: 'App Version',
            subtitle: '1.0.4 (Stable)',
            icon: Icons.info_outline_rounded,
          ),
          const SizedBox(height: 32),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: () async {
                await AuthService.logout();
                if (!mounted) return;
                Navigator.pushAndRemoveUntil(
                  context,
                  MaterialPageRoute(builder: (_) => const LoginScreen()),
                  (_) => false,
                );
              },
              icon: const Icon(Icons.logout_rounded),
              label: const Text('Sign Out'),
              style: OutlinedButton.styleFrom(
                foregroundColor: AppColors.danger,
                side: BorderSide(color: AppColors.danger.withOpacity(0.4)),
                padding: const EdgeInsets.symmetric(vertical: 16),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
              ),
            ),
          ),
          const SizedBox(height: 40),
        ],
      ),
    );
  }

  Widget _sectionHeader(String title) {
    return Padding(
      padding: const EdgeInsets.only(left: 4, bottom: 12),
      child: Text(
        title.toUpperCase(),
        style: TextStyle(
          color: AppColors.primary.withOpacity(0.7),
          fontSize: 11,
          fontWeight: FontWeight.w800,
          letterSpacing: 2,
        ),
      ),
    );
  }

  Widget _settingItem({
    required String title,
    required String subtitle,
    required IconData icon,
    Widget? trailing,
    Color? titleColor,
    VoidCallback? onTap,
  }) {
    return Card(
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 12),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: AppColors.primary.withOpacity(0.05)),
      ),
      child: ListTile(
        onTap: onTap,
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
        leading: Container(
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: (titleColor ?? AppColors.primary).withOpacity(0.08),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Icon(icon, color: titleColor ?? AppColors.primary, size: 20),
        ),
        title: Text(
          title,
          style: TextStyle(
            color: titleColor ?? AppColors.textMain,
            fontWeight: FontWeight.bold,
            fontSize: 15,
          ),
        ),
        subtitle: Text(
          subtitle,
          style: AppTextStyles.muted.copyWith(fontSize: 12),
        ),
        trailing: trailing ?? const Icon(Icons.chevron_right_rounded, size: 20, color: AppColors.textMuted),
      ),
    );
  }
}
