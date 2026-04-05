import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import '../theme.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';
import 'login_screen.dart';
import 'settings_screen.dart';
import 'info_hub_screen.dart';
import 'my_reviews_screen.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});
  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  Map<String, dynamic>? _user;
  bool _loading = true;
  bool _saving = false;
  bool _uploadingPic = false;
  String? _error;
  final _firstCtrl = TextEditingController();
  final _middleCtrl = TextEditingController();
  final _lastCtrl = TextEditingController();
  final _usernameCtrl = TextEditingController();
  final _emailCtrl = TextEditingController();
  final _phoneCtrl = TextEditingController();
  final _currentPwdCtrl = TextEditingController();
  final _newPwdCtrl = TextEditingController();
  final _confirmPwdCtrl = TextEditingController();
  bool _isEditing = false; // Track edit mode
  bool _showCurrentPwd = false;
  bool _showNewPwd = false;
  bool _showConfirmPwd = false;

  void _toggleEdit() {
    setState(() => _isEditing = !_isEditing);
  }

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final userId = await AuthService.getUserId();
      if (userId == null) {
        if (!mounted) return;
        setState(() {
          _error = 'Not logged in. Please log in again.';
          _loading = false;
        });
        return;
      }

      final res = await ApiService.get('/api/user/$userId/profile');

      if (!mounted) return;

      if (res != null && res is Map<String, dynamic>) {
        setState(() {
          _user = res;
          _firstCtrl.text = res['first_name'] ?? '';
          _middleCtrl.text = res['middle_name'] ?? '';
          _lastCtrl.text = res['last_name'] ?? '';
          _usernameCtrl.text = res['username'] ?? '';
          _emailCtrl.text = res['email'] ?? '';
          _phoneCtrl.text = res['phone_number'] ?? '';
          _loading = false;
        });
      } else {
        // API call failed or returned unexpected data — use local cached user data as fallback
        final cachedUser = await AuthService.getUser();
        if (!mounted) return;

        if (cachedUser != null) {
          setState(() {
            _user = cachedUser;
            _firstCtrl.text = cachedUser['first_name'] ?? '';
            _middleCtrl.text = cachedUser['middle_name'] ?? '';
            _lastCtrl.text = cachedUser['last_name'] ?? '';
            _usernameCtrl.text = cachedUser['username'] ?? '';
            _emailCtrl.text = cachedUser['email'] ?? '';
            _phoneCtrl.text = cachedUser['phone_number'] ?? '';
            _loading = false;
          });
        } else {
          setState(() {
            _error =
                'Could not load profile.\nMake sure Flask is running and your device is on the same network.';
            _loading = false;
          });
        }
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = 'Connection error: $e';
        _loading = false;
      });
    }
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    final userId = await AuthService.getUserId();
    final res = await ApiService.put('/api/user/$userId/profile', {
      'first_name': _firstCtrl.text.trim(),
      'middle_name': _middleCtrl.text.trim(),
      'last_name': _lastCtrl.text.trim(),
      'username': _usernameCtrl.text.trim(),
      'email': _emailCtrl.text.trim(),
      'phone_number': _phoneCtrl.text.trim(),
      'current_password': _currentPwdCtrl.text,
      'new_password': _newPwdCtrl.text,
      'confirm_new_password': _confirmPwdCtrl.text,
    });
    setState(() => _saving = false);
    final ok = res['success'] == true;
    if (ok) {
      final u = await AuthService.getUser();
      if (u != null) {
        u['first_name'] = _firstCtrl.text.trim();
        u['last_name'] = _lastCtrl.text.trim();
        u['username'] = _usernameCtrl.text.trim();
        u['email'] = _emailCtrl.text.trim();
        u['phone_number'] = _phoneCtrl.text.trim();
        await AuthService.saveUser(u);
      }
    }
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(res['message'] ?? ''),
        backgroundColor: ok ? AppColors.success : AppColors.danger,
      ),
    );
  }

  Future<void> _pickAndUploadImage() async {
    final ImagePicker picker = ImagePicker();

    // Show a dialog to choose camera or gallery
    final source = await showModalBottomSheet<ImageSource>(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: Colors.grey.shade300,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              const SizedBox(height: 20),
              Text(
                'Change Profile Picture',
                style: AppTextStyles.heading.copyWith(fontSize: 18),
              ),
              const SizedBox(height: 20),
              ListTile(
                leading: Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: AppColors.primary.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(Icons.camera_alt, color: AppColors.primary),
                ),
                title: const Text(
                  'Take a Photo',
                  style: TextStyle(fontWeight: FontWeight.w600),
                ),
                subtitle: const Text('Use your camera'),
                onTap: () => Navigator.pop(ctx, ImageSource.camera),
              ),
              const SizedBox(height: 8),
              ListTile(
                leading: Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: AppColors.accent.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(Icons.photo_library, color: AppColors.accent),
                ),
                title: const Text(
                  'Choose from Gallery',
                  style: TextStyle(fontWeight: FontWeight.w600),
                ),
                subtitle: const Text('Pick an existing photo'),
                onTap: () => Navigator.pop(ctx, ImageSource.gallery),
              ),
              const SizedBox(height: 12),
            ],
          ),
        ),
      ),
    );

    if (source == null) return;

    try {
      final XFile? pickedFile = await picker.pickImage(
        source: source,
        maxWidth: 500,
        maxHeight: 500,
        imageQuality: 80,
      );

      if (pickedFile == null) return;

      setState(() => _uploadingPic = true);

      // Convert to base64
      final bytes = await File(pickedFile.path).readAsBytes();
      final base64Image = base64Encode(bytes);

      final userId = await AuthService.getUserId();
      if (userId == null) return;

      final res = await ApiService.post('/api/user/$userId/profile-picture', {
        'image': base64Image,
      });

      if (!mounted) return;
      setState(() => _uploadingPic = false);

      if (res['success'] == true) {
        final newUrl = res['profile_picture_url'];
        setState(() {
          _user?['profile_picture_url'] = newUrl;
        });

        // Update cached user
        final u = await AuthService.getUser();
        if (u != null) {
          u['profile_picture_url'] = newUrl;
          await AuthService.saveUser(u);
        }

        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Profile picture updated!'),
            backgroundColor: AppColors.success,
          ),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(res['message'] ?? 'Upload failed.'),
            backgroundColor: AppColors.danger,
          ),
        );
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _uploadingPic = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Error picking image: $e'),
          backgroundColor: AppColors.danger,
        ),
      );
    }
  }

  Future<void> _logout() async {
    await AuthService.logout();
    if (!mounted) return;
    Navigator.pushAndRemoveUntil(
      context,
      MaterialPageRoute(builder: (_) => const LoginScreen()),
      (_) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Center(
        child: CircularProgressIndicator(color: AppColors.primary),
      );
    }

    // Show error state with retry button
    if (_error != null) {
      return Scaffold(
        appBar: AppBar(
          title: Text(
            'Profile',
            style: AppTextStyles.heading.copyWith(fontSize: 20),
          ),
          centerTitle: true,
        ),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    color: AppColors.danger.withOpacity(0.1),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(
                    Icons.person_off_rounded,
                    color: AppColors.danger,
                    size: 48,
                  ),
                ),
                const SizedBox(height: 20),
                Text(
                  'Profile Unavailable',
                  style: AppTextStyles.heading.copyWith(fontSize: 20),
                ),
                const SizedBox(height: 8),
                Text(
                  _error!,
                  textAlign: TextAlign.center,
                  style: AppTextStyles.muted.copyWith(fontSize: 13),
                ),
                const SizedBox(height: 24),
                ElevatedButton.icon(
                  onPressed: _load,
                  icon: const Icon(Icons.refresh),
                  label: const Text('Try Again'),
                  style: ElevatedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 28,
                      vertical: 14,
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  onPressed: _logout,
                  icon: const Icon(Icons.logout),
                  label: const Text('Sign Out'),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: AppColors.danger,
                    side: const BorderSide(color: AppColors.danger),
                  ),
                ),
              ],
            ),
          ),
        ),
      );
    }

    final profileUrl = _user?['profile_picture_url'];
    // Build full image URL from relative path
    String? fullImageUrl;
    if (profileUrl != null && profileUrl.toString().isNotEmpty) {
      if (profileUrl.toString().startsWith('http')) {
        fullImageUrl = profileUrl;
      } else {
        fullImageUrl = '${ApiService.getBaseUrl()}$profileUrl';
      }
    }

    return Scaffold(
      appBar: AppBar(
        title: Text(
          'Profile',
          style: AppTextStyles.heading.copyWith(fontSize: 20, color: AppColors.textMain),
        ),
        centerTitle: true,
        backgroundColor: Colors.transparent,
        elevation: 0,
        actions: [
          IconButton(
            icon: Icon(_isEditing ? Icons.close : Icons.edit_note_rounded, color: AppColors.primary),
            onPressed: _toggleEdit,
          ),
          IconButton(
            icon: const Icon(Icons.settings_outlined, color: AppColors.primary),
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const SettingsScreen()),
              );
            },
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: RefreshIndicator(
        color: AppColors.primary,
        onRefresh: _load,
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              // Avatar with camera edit button
              Stack(
                children: [
                  CircleAvatar(
                    radius: 55,
                    backgroundColor: AppColors.primary.withOpacity(0.1),
                    backgroundImage:
                        fullImageUrl != null ? NetworkImage(fullImageUrl) : null,
                    child: _uploadingPic
                        ? const CircularProgressIndicator(
                            color: AppColors.primary,
                            strokeWidth: 2.5,
                          )
                        : fullImageUrl == null
                            ? Text(
                                '${(_user?['first_name'] ?? 'U')[0]}',
                                style: const TextStyle(
                                  fontSize: 38,
                                  fontWeight: FontWeight.bold,
                                  color: AppColors.primary,
                                ),
                              )
                            : null,
                  ),
                  Positioned(
                    bottom: 0,
                    right: 0,
                    child: GestureDetector(
                      onTap: _uploadingPic ? null : _pickAndUploadImage,
                      child: Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          gradient: const LinearGradient(
                            colors: [AppColors.primary, AppColors.primaryLight],
                          ),
                          shape: BoxShape.circle,
                          border: Border.all(color: Colors.white, width: 2.5),
                          boxShadow: [
                            BoxShadow(
                              color: AppColors.primary.withOpacity(0.3),
                              blurRadius: 6,
                              offset: const Offset(0, 2),
                            ),
                          ],
                        ),
                        child: const Icon(
                          Icons.camera_alt,
                          color: Colors.white,
                          size: 18,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Text(
                '${_user?['first_name'] ?? ''} ${_user?['last_name'] ?? ''}',
                style: AppTextStyles.heading.copyWith(fontSize: 20),
              ),
              Text('@${_user?['username'] ?? ''}', style: AppTextStyles.muted),
              const SizedBox(height: 24),
              _field('First Name', _firstCtrl, Icons.person_outline, enabled: _isEditing),
              _field('Middle Name', _middleCtrl, Icons.person_outline, enabled: _isEditing),
              _field('Last Name', _lastCtrl, Icons.person_outline, enabled: _isEditing),
              _field('Username', _usernameCtrl, Icons.alternate_email, enabled: _isEditing),
              _field('Email', _emailCtrl, Icons.email_outlined, enabled: false), // Email NOT editable
              _field('Phone', _phoneCtrl, Icons.phone_outlined, enabled: _isEditing),
              
              if (_isEditing) ...[
                const SizedBox(height: 16),
                const Divider(),
                const SizedBox(height: 16),
                Text('Change Password', style: AppTextStyles.heading.copyWith(fontSize: 16)),
                const SizedBox(height: 8),
                Text('Leave blank if you don\'t want to change password', style: AppTextStyles.muted.copyWith(fontSize: 12)),
                const SizedBox(height: 16),
                _field('Current Password', _currentPwdCtrl, Icons.lock_outline, enabled: true, isPassword: true, showPassword: _showCurrentPwd, onToggle: () => setState(() => _showCurrentPwd = !_showCurrentPwd)),
                _field('New Password', _newPwdCtrl, Icons.lock_reset, enabled: true, isPassword: true, showPassword: _showNewPwd, onToggle: () => setState(() => _showNewPwd = !_showNewPwd)),
                _field('Confirm New Password', _confirmPwdCtrl, Icons.lock_reset, enabled: true, isPassword: true, showPassword: _showConfirmPwd, onToggle: () => setState(() => _showConfirmPwd = !_showConfirmPwd)),
              ],
              const SizedBox(height: 24),
              if (_isEditing)
                GradientButton(
                  label: 'Update Profile',
                  icon: Icons.save_rounded,
                  onPressed: _saving ? null : _save,
                  isLoading: _saving,
                  height: 56,
                ),

              if (!_isEditing) ...[
                const SizedBox(height: 16),
                const Divider(),
                const SizedBox(height: 16),
                const Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    'My Activity',
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                      fontSize: 16,
                      color: AppColors.primary,
                      letterSpacing: 0.5,
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                _infoTile(
                  Icons.rate_review_outlined,
                  'My Reviews',
                  'Track and view your feedback history',
                  () => Navigator.push(context, MaterialPageRoute(builder: (_) => const MyReviewsScreen())),
                ),
                const SizedBox(height: 16),
                const Divider(),
                const SizedBox(height: 16),
                const Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    'Information & Support',
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                      fontSize: 16,
                      color: AppColors.primary,
                      letterSpacing: 0.5,
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                _infoTile(
                  Icons.info_outline_rounded,
                  'About & FAQs',
                  'Our story, delivery info, and more',
                  () => Navigator.push(context, MaterialPageRoute(builder: (_) => const InfoHubScreen())),
                ),
                const SizedBox(height: 24),
              ],

              if (!_isEditing)
                SizedBox(
                  width: double.infinity,
                  height: 52,
                  child: OutlinedButton.icon(
                    onPressed: _logout,
                    icon: const Icon(Icons.logout_rounded),
                    label: const Text('Sign Out'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppColors.danger,
                      side: BorderSide(color: AppColors.danger.withOpacity(0.5)),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                    ),
                  ),
                ),
              const SizedBox(height: 40),
            ],
          ),
        ),
      ),
    );
  }

  Widget _infoTile(IconData icon, String title, String subtitle, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: AppColors.primary.withOpacity(0.1)),
        ),
        child: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: AppColors.primary.withOpacity(0.08),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(icon, color: AppColors.primary, size: 22),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                  Text(subtitle, style: AppTextStyles.muted.copyWith(fontSize: 12)),
                ],
              ),
            ),
            const Icon(Icons.arrow_forward_ios_rounded, color: Colors.grey, size: 14),
          ],
        ),
      ),
    );
  }

  Widget _field(String label, TextEditingController ctrl, IconData icon, {bool enabled = true, bool isPassword = false, bool showPassword = false, VoidCallback? onToggle}) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(left: 4, bottom: 6),
            child: Text(
              label,
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: AppColors.textMain.withOpacity(0.6),
                letterSpacing: 0.5,
              ),
            ),
          ),
          TextField(
            controller: ctrl,
            readOnly: !enabled,
            obscureText: isPassword && !showPassword,
            style: TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w500,
              color: enabled ? AppColors.textMain : AppColors.textMain.withOpacity(0.5),
            ),
            decoration: InputDecoration(
              prefixIcon: Icon(icon, color: AppColors.primary, size: 20),
              suffixIcon: isPassword ? IconButton(
                icon: Icon(showPassword ? Icons.visibility_off : Icons.visibility, color: AppColors.primary, size: 20),
                onPressed: onToggle,
              ) : null,
              filled: true,
              fillColor: enabled ? Colors.white : AppColors.cardBg.withOpacity(0.5),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(16),
                borderSide: BorderSide(color: AppColors.primary.withOpacity(0.1)),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(16),
                borderSide: BorderSide(color: AppColors.primary.withOpacity(0.08)),
              ),
              hintText: 'Enter your $label',
              contentPadding: const EdgeInsets.symmetric(vertical: 16),
            ),
          ),
        ],
      ),
    );
  }
}


