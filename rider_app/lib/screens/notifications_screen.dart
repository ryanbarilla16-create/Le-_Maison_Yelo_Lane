import 'package:flutter/material.dart';
import '../theme.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  List<Map<String, dynamic>> _notifications = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final userId = await AuthService.getUserId();
    if (userId == null) return;

    final res = await ApiService.get('/api/user/$userId/notifications');
    if (!mounted) return;

    setState(() {
      if (res != null && res['success'] == true) {
        _notifications = List<Map<String, dynamic>>.from(
          res['notifications'] ?? [],
        );
      }
      _loading = false;
    });
  }

  Future<void> _markAsRead(int notifId) async {
    await ApiService.post('/api/notification/$notifId/read', {});
    setState(() {
      final idx = _notifications.indexWhere((n) => n['id'] == notifId);
      if (idx >= 0) {
        _notifications[idx]['is_read'] = true;
      }
    });
  }

  Future<void> _markAllRead() async {
    final userId = await AuthService.getUserId();
    if (userId == null) return;
    await ApiService.post('/api/user/$userId/notifications/read-all', {});
    setState(() {
      for (var n in _notifications) {
        n['is_read'] = true;
      }
    });
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('All notifications marked as read.'),
        backgroundColor: AppColors.success,
      ),
    );
  }

  IconData _getIcon(String type) {
    switch (type) {
      case 'ORDER':
        return Icons.shopping_bag_rounded;
      case 'RESERVATION':
        return Icons.calendar_today_rounded;
      case 'DELIVERY':
        return Icons.delivery_dining_rounded;
      case 'SYSTEM':
        return Icons.info_rounded;
      default:
        return Icons.notifications_rounded;
    }
  }

  Color _getIconColor(String type) {
    switch (type) {
      case 'ORDER':
        return AppColors.primary;
      case 'RESERVATION':
        return AppColors.accent;
      case 'DELIVERY':
        return AppColors.info;
      case 'SYSTEM':
        return AppColors.warning;
      default:
        return AppColors.textMuted;
    }
  }

  @override
  Widget build(BuildContext context) {
    final unreadCount = _notifications.where((n) => n['is_read'] != true).length;

    return Scaffold(
      appBar: AppBar(
        title: Text(
          'Notifications',
          style: AppTextStyles.heading.copyWith(fontSize: 20),
        ),
        centerTitle: true,
        actions: [
          if (unreadCount > 0)
            TextButton(
              onPressed: _markAllRead,
              child: const Text(
                'Read All',
                style: TextStyle(
                  color: AppColors.primary,
                  fontWeight: FontWeight.w600,
                  fontSize: 13,
                ),
              ),
            ),
        ],
      ),
      body: _loading
          ? const Center(
              child: CircularProgressIndicator(color: AppColors.primary),
            )
          : _notifications.isEmpty
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        padding: const EdgeInsets.all(24),
                        decoration: BoxDecoration(
                          color: AppColors.primary.withOpacity(0.08),
                          shape: BoxShape.circle,
                        ),
                        child: Icon(
                          Icons.notifications_off_rounded,
                          color: AppColors.primary.withOpacity(0.3),
                          size: 48,
                        ),
                      ),
                      const SizedBox(height: 16),
                      Text(
                        'No Notifications Yet',
                        style: AppTextStyles.heading.copyWith(fontSize: 18),
                      ),
                      const SizedBox(height: 6),
                      const Text(
                        'You\'ll see order updates, reservation\nconfirmations, and more here.',
                        textAlign: TextAlign.center,
                        style: AppTextStyles.muted,
                      ),
                    ],
                  ),
                )
              : RefreshIndicator(
                  color: AppColors.primary,
                  onRefresh: _load,
                  child: ListView.builder(
                    physics: const AlwaysScrollableScrollPhysics(),
                    padding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 8,
                    ),
                    itemCount: _notifications.length,
                    itemBuilder: (ctx, i) {
                      final n = _notifications[i];
                      final isRead = n['is_read'] == true;
                      final type = n['type'] ?? 'SYSTEM';

                      return GestureDetector(
                        onTap: () {
                          if (!isRead) _markAsRead(n['id']);
                        },
                        child: AnimatedContainer(
                          duration: const Duration(milliseconds: 300),
                          margin: const EdgeInsets.only(bottom: 8),
                          padding: const EdgeInsets.all(14),
                          decoration: BoxDecoration(
                            color: isRead
                                ? Colors.white
                                : AppColors.primary.withOpacity(0.04),
                            borderRadius: BorderRadius.circular(14),
                            border: Border.all(
                              color: isRead
                                  ? Colors.grey.withOpacity(0.1)
                                  : AppColors.primary.withOpacity(0.15),
                            ),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withOpacity(0.03),
                                blurRadius: 8,
                                offset: const Offset(0, 2),
                              ),
                            ],
                          ),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              // Icon
                              Container(
                                padding: const EdgeInsets.all(10),
                                decoration: BoxDecoration(
                                  color: _getIconColor(type).withOpacity(0.1),
                                  borderRadius: BorderRadius.circular(12),
                                ),
                                child: Icon(
                                  _getIcon(type),
                                  color: _getIconColor(type),
                                  size: 22,
                                ),
                              ),
                              const SizedBox(width: 12),
                              // Content
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Row(
                                      children: [
                                        Expanded(
                                          child: Text(
                                            n['title'] ?? '',
                                            style: TextStyle(
                                              fontWeight: isRead
                                                  ? FontWeight.w600
                                                  : FontWeight.w800,
                                              fontSize: 14,
                                              color: AppColors.textMain,
                                            ),
                                          ),
                                        ),
                                        if (!isRead)
                                          Container(
                                            width: 8,
                                            height: 8,
                                            decoration: const BoxDecoration(
                                              color: AppColors.primary,
                                              shape: BoxShape.circle,
                                            ),
                                          ),
                                      ],
                                    ),
                                    const SizedBox(height: 4),
                                    Text(
                                      n['message'] ?? '',
                                      style: TextStyle(
                                        fontSize: 12.5,
                                        color: AppColors.textMuted,
                                        height: 1.4,
                                      ),
                                    ),
                                    const SizedBox(height: 6),
                                    Text(
                                      n['created_at'] ?? '',
                                      style: TextStyle(
                                        fontSize: 11,
                                        color:
                                            AppColors.textMuted.withOpacity(0.6),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
                ),
    );
  }
}


