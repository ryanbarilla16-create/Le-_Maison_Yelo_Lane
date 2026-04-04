import 'dart:async';
import 'package:flutter/material.dart';
import '../theme.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';
import 'login_screen.dart';
import 'menu_screen.dart';
import 'orders_screen.dart';
import 'reserve_screen.dart';
import 'profile_screen.dart';
import 'cart_screen.dart';
import 'notifications_screen.dart';
import 'chat_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  Map<String, dynamic>? _user;
  Map<String, dynamic>? _dashboard;
  List<dynamic> _bestsellers = [];
  List<dynamic> _featured = [];
  bool _loading = true;
  int _currentIndex = 0;
  int _unreadNotifCount = 0;
  Timer? _notifTimer;

  @override
  void initState() {
    super.initState();
    _loadData();
    _loadUnreadCount();
    // Poll for new notifications every 15 seconds
    _notifTimer = Timer.periodic(const Duration(seconds: 15), (_) {
      _loadUnreadCount();
    });
  }

  @override
  void dispose() {
    _notifTimer?.cancel();
    super.dispose();
  }

  Future<void> _loadUnreadCount() async {
    final userId = await AuthService.getUserId();
    if (userId == null) return;
    final res = await ApiService.get('/api/user/$userId/notifications/unread-count');
    if (!mounted) return;
    if (res != null && res['success'] == true) {
      setState(() => _unreadNotifCount = res['count'] ?? 0);
    }
  }

  Future<void> _loadData() async {
    _user = await AuthService.getUser();
    if (_user == null) {
      if (!mounted) return;
      Navigator.pushAndRemoveUntil(
        context,
        MaterialPageRoute(builder: (_) => const LoginScreen()),
        (_) => false,
      );
      return;
    }

    try {
      final userId = _user!['id'];
      final results = await Future.wait([
        ApiService.get('/api/user/$userId/dashboard'),
        ApiService.get('/api/menu/bestsellers'),
        ApiService.get('/api/menu/featured'),
      ]);

      if (!mounted) return;
      setState(() {
        _dashboard = results[0] is Map ? results[0] : null;
        _bestsellers = results[1] is List ? results[1] : [];
        _featured = results[2] is List ? results[2] : [];
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _dashboard = null;
        _bestsellers = [];
        _featured = [];
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final screens = [
      _buildDashboard(),
      const MenuScreen(),
      const OrdersScreen(),
      const ReserveScreen(),
      const ProfileScreen(),
    ];

    return Scaffold(
      body: screens[_currentIndex],
      bottomNavigationBar: Container(
        decoration: BoxDecoration(
          color: Colors.white,
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.06),
              blurRadius: 10,
              offset: const Offset(0, -2),
            ),
          ],
        ),
        child: BottomNavigationBar(
          currentIndex: _currentIndex,
          onTap: (i) => setState(() => _currentIndex = i),
          type: BottomNavigationBarType.fixed,
          backgroundColor: Colors.white,
          selectedItemColor: AppColors.primary,
          unselectedItemColor: AppColors.textMuted,
          selectedFontSize: 11,
          unselectedFontSize: 11,
          items: const [
            BottomNavigationBarItem(
              icon: Icon(Icons.home_rounded),
              label: 'Home',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.restaurant_menu),
              label: 'Menu',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.shopping_bag_rounded),
              label: 'Orders',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.calendar_today_rounded),
              label: 'Reserve',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.person_rounded),
              label: 'Profile',
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildDashboard() {
    if (_loading) {
      return const Center(
        child: CircularProgressIndicator(color: AppColors.primary),
      );
    }

    return RefreshIndicator(
      color: AppColors.primary,
      onRefresh: _loadData,
      child: SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // ═══ PREMIUM HOME HEADER ═══
            Container(
              width: double.infinity,
              padding: const EdgeInsets.fromLTRB(26, 65, 26, 35),
              decoration: const BoxDecoration(
                gradient: LinearGradient(
                  colors: [AppColors.primary, Color(0xFF6D4C41)],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.only(
                  bottomLeft: Radius.circular(35),
                  bottomRight: Radius.circular(35),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Good Day,',
                              style: TextStyle(
                                color: AppColors.accent.withOpacity(0.8),
                                fontSize: 13,
                                letterSpacing: 1.2,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              '${_user?['first_name'] ?? 'Guest'}',
                              style: const TextStyle(
                                fontSize: 28,
                                fontWeight: FontWeight.w900,
                                color: Colors.white,
                                letterSpacing: -0.5,
                              ),
                            ),
                          ],
                        ),
                      ),
                      _headerIcon(
                        Icons.notifications_outlined,
                        badgeCount: _unreadNotifCount,
                        onTap: () async {
                          await Navigator.push(
                            context,
                            MaterialPageRoute(builder: (_) => const NotificationsScreen()),
                          );
                          _loadUnreadCount();
                        },
                      ),
                      const SizedBox(width: 12),
                      _headerIcon(
                        Icons.shopping_cart_outlined,
                        onTap: () async {
                          final result = await Navigator.push(
                            context,
                            MaterialPageRoute(builder: (_) => const CartScreen()),
                          );
                          if (result == 1) {
                            setState(() => _currentIndex = 1);
                          } else if (result == true) {
                            _loadData();
                          }
                        },
                      ),
                    ],
                  ),
                  const SizedBox(height: 15),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                    decoration: BoxDecoration(
                      color: Colors.white.withOpacity(0.12),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Text(
                      'LE MAISON YELO LANE',
                      style: TextStyle(
                        color: Colors.white.withOpacity(0.9),
                        fontSize: 10,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 4,
                      ),
                    ),
                  ),
                ],
              ),
            ),

            // ═══ QUICK ACTIONS ═══
            Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  _quickAction(
                    Icons.calendar_today,
                    'Reserve',
                    AppColors.primary,
                    () => setState(() => _currentIndex = 3),
                  ),
                  const SizedBox(width: 10),
                  _quickAction(
                    Icons.restaurant_menu,
                    'Menu',
                    AppColors.accent,
                    () => setState(() => _currentIndex = 1),
                  ),
                  const SizedBox(width: 10),
                  _quickAction(
                    Icons.shopping_bag,
                    'Orders',
                    const Color(0xFF5D4037),
                    () => setState(() => _currentIndex = 2),
                  ),
                  const SizedBox(width: 10),
                  _quickAction(Icons.chat_rounded, 'Chat', AppColors.gold, () {
                    Navigator.push(
                      context,
                      MaterialPageRoute(builder: (_) => const ChatScreen()),
                    );
                  }),
                ],
              ),
            ),

            // ═══ STATS ═══
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Row(
                children: [
                  _statCard(
                    Icons.event_available,
                    '${_dashboard?['upcoming_reservations']?.length ?? 0}',
                    'Upcoming',
                    AppColors.primary,
                  ),
                  const SizedBox(width: 10),
                  _statCard(
                    Icons.check_circle,
                    '${_dashboard?['total_visits'] ?? 0}',
                    'Visits',
                    AppColors.success,
                  ),
                  const SizedBox(width: 10),
                  _statCard(
                    Icons.emoji_events,
                    _dashboard?['loyalty_status'] ?? 'New',
                    'Loyalty',
                    AppColors.accent,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 20),

            // ═══ UPCOMING RESERVATIONS (compact) ═══
            _sectionCompact(
              'Upcoming Reservations',
              Icons.schedule,
              _dashboard?['upcoming_reservations'] ?? [],
              emptyText: 'No upcoming reservations',
              emptyCta: 'Book a Table',
              onCta: () => setState(() => _currentIndex = 3),
              itemBuilder: (r) => _reservationTile(r),
            ),
            const SizedBox(height: 12),

            // ═══ RECENT ORDERS (compact) ═══
            _sectionCompact(
              'Recent Orders',
              Icons.shopping_bag,
              _dashboard?['recent_orders'] ?? [],
              emptyText: 'No orders yet',
              emptyCta: 'Browse Menu',
              onCta: () => setState(() => _currentIndex = 1),
              trailing: TextButton(
                onPressed: () => setState(() => _currentIndex = 2),
                child: const Text(
                  'View All',
                  style: TextStyle(
                    color: AppColors.primary,
                    fontWeight: FontWeight.bold,
                    fontSize: 13,
                  ),
                ),
              ),
              itemBuilder: (o) => _orderTile(o),
            ),
            const SizedBox(height: 20),

            // ═══ BESTSELLERS ═══
            if (_bestsellers.isNotEmpty) ...[
              _sectionHeader('🔥 Bestsellers', "Today's Specials"),
              SizedBox(
                height: 230,
                child: ListView.builder(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  itemCount: _bestsellers.length,
                  itemBuilder: (ctx, i) =>
                      _menuCard(_bestsellers[i], badge: 'Popular'),
                ),
              ),
              const SizedBox(height: 20),
            ],

            // ═══ FEATURED ═══
            if (_featured.isNotEmpty) ...[
              _sectionHeader('Curated For You', "Today's Featured Picks"),
              SizedBox(
                height: 230,
                child: ListView.builder(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  itemCount: _featured.length,
                  itemBuilder: (ctx, i) => _menuCard(_featured[i]),
                ),
              ),
              const SizedBox(height: 20),
            ],

            // ═══ VISIT US ═══
            Padding(
              padding: const EdgeInsets.all(16),
              child: Container(
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(14),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withOpacity(0.04),
                      blurRadius: 15,
                    ),
                  ],
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Visit Us',
                      style: AppTextStyles.heading.copyWith(fontSize: 18),
                    ),
                    const SizedBox(height: 12),
                    _infoRow(
                      Icons.location_on,
                      'Yelo Lane, General Taino Street\nPagsanjan, Laguna, Philippines',
                    ),
                    _infoRow(
                      Icons.access_time,
                      'Mon - Sun · 8:00 AM - 10:00 PM',
                    ),
                    _infoRow(Icons.phone, '+63 (912) 345-6789'),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 30),
          ],
        ),
      ),
    );
  }

  // ═══ HELPER WIDGETS ═══

  Widget _quickAction(
    IconData icon,
    String label,
    Color color,
    VoidCallback onTap,
  ) {
    return Expanded(
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 16),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(12),
            boxShadow: [
              BoxShadow(color: Colors.black.withOpacity(0.04), blurRadius: 10),
            ],
          ),
          child: Column(
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [color, color.withOpacity(0.7)],
                  ),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(icon, color: Colors.white, size: 20),
              ),
              const SizedBox(height: 8),
              Text(
                label,
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  color: AppColors.textMain,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _statCard(IconData icon, String value, String label, Color color) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(12),
          boxShadow: [
            BoxShadow(color: Colors.black.withOpacity(0.04), blurRadius: 10),
          ],
        ),
        child: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: color.withOpacity(0.1),
                shape: BoxShape.circle,
              ),
              child: Icon(icon, color: color, size: 18),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    value,
                    style: TextStyle(
                      fontWeight: FontWeight.w800,
                      color: AppColors.textMain,
                      fontSize: 16,
                    ),
                  ),
                  Text(
                    label,
                    style: TextStyle(color: AppColors.textMuted, fontSize: 10),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _sectionCompact(
    String title,
    IconData icon,
    List items, {
    required String emptyText,
    required String emptyCta,
    required VoidCallback onCta,
    Widget? trailing,
    required Widget Function(dynamic) itemBuilder,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(14),
          boxShadow: [
            BoxShadow(color: Colors.black.withOpacity(0.04), blurRadius: 15),
          ],
        ),
        child: Column(
          children: [
            Row(
              children: [
                Icon(icon, color: AppColors.primary, size: 18),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    title,
                    style: AppTextStyles.heading.copyWith(fontSize: 15),
                  ),
                ),
                if (trailing != null) trailing,
              ],
            ),
            const SizedBox(height: 10),
            if (items.isEmpty) ...[
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 12),
                child: Column(
                  children: [
                    Icon(
                      icon,
                      color: AppColors.primary.withOpacity(0.15),
                      size: 32,
                    ),
                    const SizedBox(height: 8),
                    Text(emptyText, style: AppTextStyles.muted),
                    const SizedBox(height: 8),
                    ElevatedButton(
                      onPressed: onCta,
                      style: ElevatedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 20,
                          vertical: 10,
                        ),
                        textStyle: const TextStyle(fontSize: 13),
                      ),
                      child: Text(emptyCta),
                    ),
                  ],
                ),
              ),
            ] else
              ...items.map((item) => itemBuilder(item)),
          ],
        ),
      ),
    );
  }

  Widget _reservationTile(dynamic r) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: AppColors.primary.withOpacity(0.03),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.primary.withOpacity(0.06)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${r['date']} · ${r['time']}',
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 13,
                  ),
                ),
                Text(
                  '${r['guest_count']} guests${r['occasion'] != null && r['occasion'] != '' ? ' · ${r['occasion']}' : ''}',
                  style: AppTextStyles.muted.copyWith(fontSize: 12),
                ),
              ],
            ),
          ),
          _statusBadge(r['status']),
        ],
      ),
    );
  }

  Widget _orderTile(dynamic o) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: AppColors.primary.withOpacity(0.03),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.primary.withOpacity(0.06)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Order #${o['id']} · ${o['created_at']}',
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 13,
                  ),
                ),
                Text(
                  '${o['item_count']} item${o['item_count'] > 1 ? 's' : ''}${o['first_item'] != '' ? ' — ${o['first_item']}' : ''}',
                  style: AppTextStyles.muted.copyWith(fontSize: 12),
                ),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                '₱${o['total_amount'].toStringAsFixed(2)}',
                style: TextStyle(
                  fontWeight: FontWeight.w800,
                  color: AppColors.primary,
                  fontSize: 14,
                ),
              ),
              const SizedBox(height: 2),
              _statusBadge(o['status']),
            ],
          ),
        ],
      ),
    );
  }

  Widget _statusBadge(String status) {
    Color bg, fg;
    switch (status) {
      case 'CONFIRMED':
        bg = AppColors.success.withOpacity(0.1);
        fg = AppColors.success;
        break;
      case 'COMPLETED':
        bg = AppColors.success.withOpacity(0.1);
        fg = AppColors.success;
        break;
      case 'PENDING':
        bg = AppColors.warning.withOpacity(0.1);
        fg = AppColors.warning;
        break;
      case 'PREPARING':
        bg = AppColors.info.withOpacity(0.1);
        fg = AppColors.info;
        break;
      case 'CANCELLED':
        bg = AppColors.danger.withOpacity(0.1);
        fg = AppColors.danger;
        break;
      default:
        bg = Colors.grey.withOpacity(0.1);
        fg = Colors.grey;
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        status[0] + status.substring(1).toLowerCase(),
        style: TextStyle(color: fg, fontSize: 11, fontWeight: FontWeight.w600),
      ),
    );
  }

  Widget _sectionHeader(String subtitle, String title) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            subtitle.toUpperCase(),
            style: TextStyle(
              color: AppColors.primary,
              fontSize: 11,
              fontWeight: FontWeight.w700,
              letterSpacing: 2,
            ),
          ),
          Text(title, style: AppTextStyles.heading.copyWith(fontSize: 18)),
        ],
      ),
    );
  }

  Widget _menuCard(dynamic item, {String? badge}) {
    return Container(
      width: 170,
      margin: const EdgeInsets.only(right: 12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        boxShadow: [
          BoxShadow(color: Colors.black.withOpacity(0.04), blurRadius: 10),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Stack(
            children: [
              ClipRRect(
                borderRadius: const BorderRadius.vertical(
                  top: Radius.circular(14),
                ),
                child: ColorFiltered(
                  colorFilter: ColorFilter.mode(
                    item['is_out_of_stock'] == true ? Colors.grey : Colors.transparent,
                    BlendMode.saturation,
                  ),
                  child: item['image_url'] != null
                      ? Image.network(
                          item['image_url'],
                          height: 120,
                          width: 170,
                          fit: BoxFit.cover,
                          errorBuilder: (_, __, ___) => Container(
                            height: 120,
                            width: 170,
                            color: AppColors.primary.withOpacity(0.1),
                            child: const Icon(
                              Icons.restaurant,
                              color: AppColors.primary,
                            ),
                          ),
                        )
                      : Container(
                          height: 120,
                          width: 170,
                          decoration: BoxDecoration(
                            gradient: LinearGradient(
                              colors: [AppColors.primary, AppColors.primaryLight],
                            ),
                          ),
                          child: const Icon(
                            Icons.restaurant,
                            color: Colors.white54,
                            size: 35,
                          ),
                        ),
                ),
              ),
              if (item['is_out_of_stock'] == true)
                Positioned.fill(
                  child: Container(
                    decoration: BoxDecoration(
                      color: Colors.black.withOpacity(0.2),
                      borderRadius: const BorderRadius.vertical(
                        top: Radius.circular(14),
                      ),
                    ),
                    child: Center(
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
                        decoration: BoxDecoration(
                          color: AppColors.danger,
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: const Text(
                          'OUT OF STOCK',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 7,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              if (badge != null)
                Positioned(
                  top: 6,
                  left: 6,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 3,
                    ),
                    decoration: BoxDecoration(
                      gradient: const LinearGradient(
                        colors: [AppColors.accent, Color(0xFFC49652)],
                      ),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(
                          Icons.local_fire_department,
                          color: Colors.white,
                          size: 11,
                        ),
                        const SizedBox(width: 3),
                        Text(
                          badge,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 10,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
            ],
          ),
          Padding(
            padding: const EdgeInsets.all(10),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item['name'] ?? '',
                  style: TextStyle(
                    fontFamily: 'Georgia',
                    fontWeight: FontWeight.w700,
                    fontSize: 13,
                    color: AppColors.textMain,
                  ),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 4),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 6,
                        vertical: 2,
                      ),
                      decoration: BoxDecoration(
                        color: AppColors.primary.withOpacity(0.06),
                        borderRadius: BorderRadius.circular(20),
                      ),
                      child: Text(
                        item['category'] ?? '',
                        style: TextStyle(
                          fontSize: 9,
                          fontWeight: FontWeight.w600,
                          color: AppColors.textMuted,
                        ),
                      ),
                    ),
                    Row(
                      children: [
                        Text(
                          '₱${item['price']?.toStringAsFixed(0) ?? ''}',
                          style: TextStyle(
                            fontWeight: FontWeight.w800,
                            color: AppColors.primary,
                            fontSize: 14,
                          ),
                        ),
                        if (item['is_out_of_stock'] != true) ...[
                          const SizedBox(width: 4),
                          _addIcon(() => _addToCart(item)),
                        ],
                      ],
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _headerIcon(IconData icon, {int badgeCount = 0, required VoidCallback onTap}) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.15),
          shape: BoxShape.circle,
        ),
        child: badgeCount > 0
            ? Badge(
                label: Text('$badgeCount', style: const TextStyle(fontSize: 8)),
                backgroundColor: AppColors.danger,
                child: Icon(icon, color: Colors.white, size: 20),
              )
            : Icon(icon, color: Colors.white, size: 20),
      ),
    );
  }

  Widget _infoRow(IconData icon, String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: AppColors.primary, size: 18),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              text,
              style: AppTextStyles.muted.copyWith(fontSize: 13),
            ),
          ),
        ],
      ),
    );
  }

  Widget _addIcon(VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(4),
        decoration: const BoxDecoration(
          color: AppColors.primary,
          shape: BoxShape.circle,
        ),
        child: const Icon(Icons.add, color: Colors.white, size: 16),
      ),
    );
  }

  void _addToCart(dynamic item) {
    setState(() {
      CartScreen.addItem(item);
    });
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('${item['name']} added to cart!'),
        backgroundColor: AppColors.success,
        duration: const Duration(seconds: 1),
      ),
    );
  }
}


