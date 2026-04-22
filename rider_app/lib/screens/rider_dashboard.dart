import 'dart:async';
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:url_launcher/url_launcher.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';
import '../theme.dart';
import 'login_screen.dart';
import 'notifications_screen.dart';
import 'chat_screen.dart';
import 'order_chat_screen.dart';
import 'change_password_screen.dart';

class RiderDashboard extends StatefulWidget {
  const RiderDashboard({super.key});

  @override
  State<RiderDashboard> createState() => _RiderDashboardState();
}

class _RiderDashboardState extends State<RiderDashboard>
    with SingleTickerProviderStateMixin {
  late TabController _tabCtrl;
  dynamic _summary;
  Timer? _dashboardTimer;
  Timer? _locationTimer;
  final ScrollController _scrollCtrl = ScrollController();

  List<Map<String, dynamic>> _available = [];
  List<Map<String, dynamic>> _active = [];
  List<Map<String, dynamic>> _myWaiting =
      []; // Accepted but waiting for kitchen
  List<Map<String, dynamic>> _completed = [];
  int? _riderId;
  bool _loading = true;
  int _totalToday = 0;
  int _activeCount = 0;
  bool _locationEnabled = false;
  int _unreadNotifCount = 0;

  @override
  void initState() {
    super.initState();
    _tabCtrl = TabController(length: 3, vsync: this);
    _initLocationTracking();
    _loadData();

    // Auto-refresh orders and dashboard data every 10 seconds
    _dashboardTimer = Timer.periodic(const Duration(seconds: 10), (_) {
      _loadData(silent: true);
    });
  }

  @override
  void dispose() {
    _dashboardTimer?.cancel();
    _locationTimer?.cancel();
    _scrollCtrl.dispose();
    _tabCtrl.dispose();
    super.dispose();
  }

  // ═══ GPS LOCATION TRACKING ═══
  Future<void> _initLocationTracking() async {
    bool serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) return;

    LocationPermission permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
      if (permission == LocationPermission.denied) return;
    }
    if (permission == LocationPermission.deniedForever) return;

    setState(() => _locationEnabled = true);

    // Send location every 10 seconds
    _sendLocation(); // send once immediately
    _locationTimer = Timer.periodic(const Duration(seconds: 10), (_) {
      _sendLocation();
    });
  }

  Future<void> _sendLocation() async {
    if (!_locationEnabled || _riderId == null) return;
    // Only send if rider has active deliveries
    if (_active.isEmpty && _myWaiting.isEmpty) return;

    try {
      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          distanceFilter: 5,
        ),
      );
      await ApiService.post('/api/rider/location', {
        'rider_id': _riderId,
        'latitude': position.latitude,
        'longitude': position.longitude,
      });
    } catch (e) {
      // Silently fail - GPS not critical for core function
      debugPrint('Location update failed: $e');
    }
  }

  Future<void> _loadData({bool silent = false}) async {
    final user = await AuthService.getUser();
    if (user == null) return;
    _riderId = user['id'];

    if (!silent && mounted) setState(() => _loading = true);

    final res = await ApiService.get(
      '/api/rider/deliveries?rider_id=$_riderId',
    );
    final summary = await ApiService.get('/api/rider/summary/$_riderId');

    if (mounted) {
      if (res == null && !_loading) {
        // Show error only if not silently auto-refreshing
        // to avoid spamming the user when internet drops briefly
      }

      if (res == null && !silent) {
        _showSnack(
          'Could not sync data. Check internet connection or tunnel.',
          Colors.red,
        );
      }

      setState(() {
        if (res != null && res['success'] == true) {
          final allAvailable = List<Map<String, dynamic>>.from(
            res['available'] ?? [],
          );
          // Separate: orders assigned to this rider with WAITING status go to myWaiting
          _myWaiting = allAvailable
              .where(
                (o) =>
                    o['rider_id'] == _riderId &&
                    (o['delivery_status'] == 'WAITING' ||
                        o['delivery_status'] == null),
              )
              .toList();
          // Available = orders NOT yet assigned to any rider
          _available = allAvailable
              .where((o) => o['rider_id'] == null || o['rider_id'] != _riderId)
              .toList();
          _active = List<Map<String, dynamic>>.from(res['active'] ?? []);
          _completed = List<Map<String, dynamic>>.from(res['completed'] ?? []);
        }
        if (summary != null && summary['success'] == true) {
          _summary = summary;
          _totalToday = summary['total_deliveries_today'] ?? 0;
          _activeCount = summary['active_deliveries'] ?? 0;
        }
        _loading = false;
      });
    }
  }

  Future<void> _acceptOrder(int orderId) async {
    final res = await ApiService.post('/api/rider/accept/$orderId', {
      'rider_id': _riderId,
    });
    if (res['success'] == true) {
      _showSnack(res['message'] ?? 'Order reserved!', Colors.green);
      _loadData();
      // Go to Active tab to see the waiting order
      _tabCtrl.animateTo(1);
    } else {
      _showSnack(res['message'] ?? 'Failed to accept.', Colors.red);
    }
  }

  Future<void> _updateStatus(
    int orderId,
    String newStatus, {
    double? amountTendered,
  }) async {
    final body = <String, dynamic>{
      'rider_id': _riderId,
      'delivery_status': newStatus,
    };
    if (amountTendered != null) {
      body['amount_tendered'] = amountTendered;
    }

    final res = await ApiService.post('/api/rider/update/$orderId', body);
    if (res['success'] == true) {
      _showSnack('Status updated to $newStatus!', Colors.green);
      _loadData();
    } else {
      _showSnack(res['message'] ?? 'Failed to update.', Colors.red);
    }
  }

  void _showSnack(String msg, Color color) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(msg, style: const TextStyle(fontWeight: FontWeight.w600)),
        backgroundColor: color,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
    );
  }

  void _showCollectPaymentDialog(Map<String, dynamic> order) {
    final totalAmount = order['total_amount'] as double;
    final amountCtrl = TextEditingController();
    double change = 0;

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          title: Row(
            children: [
              Icon(Icons.payments, color: AppColors.primary),
              const SizedBox(width: 8),
              const Text(
                'Collect Payment',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 18),
              ),
            ],
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: AppColors.primary.withOpacity(0.08),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text(
                      'Total',
                      style: TextStyle(
                        fontWeight: FontWeight.w600,
                        fontSize: 16,
                      ),
                    ),
                    Text(
                      '₱${totalAmount.toStringAsFixed(2)}',
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 20,
                        color: AppColors.primary,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: amountCtrl,
                keyboardType: TextInputType.number,
                decoration: InputDecoration(
                  labelText: 'Amount Received (₱)',
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                  prefixIcon: Icon(Icons.money, color: AppColors.primary),
                ),
                onChanged: (val) {
                  final amt = double.tryParse(val) ?? 0;
                  setDialogState(() {
                    change = amt - totalAmount;
                  });
                },
              ),
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: change >= 0
                      ? Colors.green.withOpacity(0.08)
                      : Colors.red.withOpacity(0.08),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: change >= 0
                        ? Colors.green.withOpacity(0.3)
                        : Colors.red.withOpacity(0.3),
                  ),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text(
                      'Change',
                      style: TextStyle(
                        fontWeight: FontWeight.w600,
                        fontSize: 16,
                      ),
                    ),
                    Text(
                      '₱${change >= 0 ? change.toStringAsFixed(2) : '0.00'}',
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 20,
                        color: change >= 0 ? Colors.green : Colors.red,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Cancel'),
            ),
            ElevatedButton(
              onPressed: change >= 0 && amountCtrl.text.isNotEmpty
                  ? () {
                      Navigator.pop(ctx);
                      _updateStatus(
                        order['id'],
                        'DELIVERED',
                        amountTendered: double.tryParse(amountCtrl.text),
                      );
                    }
                  : null,
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.green,
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(10),
                ),
              ),
              child: const Text('Confirm Delivered'),
            ),
          ],
        ),
      ),
    );
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

  Future<void> _loadUnreadCount() async {
    if (_riderId == null) return;
    final res = await ApiService.get(
      '/api/user/$_riderId/notifications/unread-count',
    );
    if (!mounted) return;
    if (res != null && res['success'] == true) {
      setState(() => _unreadNotifCount = res['count'] ?? 0);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        backgroundColor: Colors.white,
        elevation: 0,
        iconTheme: IconThemeData(color: AppColors.textMain),
        title: Row(
          children: [
            Icon(Icons.delivery_dining, color: AppColors.primary, size: 28),
            const SizedBox(width: 10),
            Text(
              'Rider Dashboard',
              style: TextStyle(
                fontFamily: 'Georgia',
                fontWeight: FontWeight.bold,
                color: AppColors.textMain,
              ),
            ),
          ],
        ),
        actions: [
          // Notification Bell
          IconButton(
            onPressed: () async {
              await Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const NotificationsScreen()),
              );
              _loadUnreadCount();
            },
            icon: Badge(
              label: Text(
                '$_unreadNotifCount',
                style: const TextStyle(fontSize: 10),
              ),
              isLabelVisible: _unreadNotifCount > 0,
              backgroundColor: AppColors.danger,
              child: Icon(
                Icons.notifications_rounded,
                color: AppColors.textMain,
              ),
            ),
          ),
          PopupMenuButton<String>(
            onSelected: (val) {
              if (val == 'password') {
                Navigator.push(context, MaterialPageRoute(builder: (_) => const ChangePasswordScreen()));
              } else if (val == 'logout') {
                _logout();
              }
            },
            icon: Icon(Icons.more_vert, color: AppColors.textMain),
            itemBuilder: (ctx) => [
              const PopupMenuItem(value: 'password', child: Row(children: [Icon(Icons.lock_reset, size: 20), SizedBox(width: 10), Text('Change Password')])),
              const PopupMenuItem(value: 'logout', child: Row(children: [Icon(Icons.logout, size: 20), SizedBox(width: 10), Text('Logout')])),
            ],
          ),
        ],
        bottom: TabBar(
          controller: _tabCtrl,
          indicatorColor: AppColors.primary,
          labelColor: AppColors.primary,
          unselectedLabelColor: AppColors.textMuted,
          tabs: [
            Tab(
              icon: Badge(
                label: Text('${_available.length}'),
                isLabelVisible: _available.isNotEmpty,
                child: const Icon(Icons.local_shipping),
              ),
              text: 'Available',
            ),
            Tab(
              icon: Badge(
                label: Text('${_myWaiting.length + _active.length}'),
                isLabelVisible: (_myWaiting.length + _active.length) > 0,
                backgroundColor: Colors.orange,
                child: const Icon(Icons.directions_bike),
              ),
              text: 'Active',
            ),
            Tab(
              icon: Badge(
                label: Text('$_totalToday'),
                isLabelVisible: _totalToday > 0,
                backgroundColor: Colors.green,
                child: const Icon(Icons.check_circle),
              ),
              text: 'Done',
            ),
          ],
        ),
      ),
      body: Column(
        children: [
          // Earnings Card
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
            child: _buildEarningsCard(),
          ),
          // Stats bar
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            color: Colors.white,
            child: Row(
              children: [
                _statBadge(
                  Icons.pending_actions,
                  '${_available.length}',
                  'Waiting',
                  AppColors.primary,
                ),
                const SizedBox(width: 12),
                _statBadge(
                  Icons.directions_bike,
                  '$_activeCount',
                  'Active',
                  Colors.orange,
                ),
                const SizedBox(width: 12),
                _statBadge(
                  Icons.check_circle,
                  '$_totalToday',
                  'History',
                  Colors.green,
                ),
              ],
            ),
          ),
          // Tab content
          Expanded(
            child: _loading
                ? Center(
                    child: CircularProgressIndicator(color: AppColors.primary),
                  )
                : TabBarView(
                    controller: _tabCtrl,
                    children: [
                      _buildOrderList(_available, 'available'),
                      _buildOrderList([..._myWaiting, ..._active], 'active'),
                      _buildOrderList(_completed, 'completed'),
                    ],
                  ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () {
          Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => const ChatScreen()),
          );
        },
        backgroundColor: AppColors.primary,
        child: const Icon(Icons.support_agent_rounded, color: Colors.white),
        tooltip: 'Admin Support',
      ),
    );
  }

  Widget _buildEarningsCard() {
    final balance = _summary?['wallet_balance'] ?? 0;
    final todayEarn = _summary?['today_earnings'] ?? 0;
    final todayTrips = _summary?['today_deliveries'] ?? 0;

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [AppColors.primary, Color(0xFF6D4C41)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: AppColors.primary.withOpacity(0.3),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'Wallet Balance',
                style: TextStyle(
                  color: Colors.white70,
                  fontSize: 13,
                  fontWeight: FontWeight.bold,
                ),
              ),
              Icon(
                Icons.account_balance_wallet,
                color: Colors.white.withOpacity(0.8),
                size: 20,
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            '₱${(balance as num).toStringAsFixed(2)}',
            style: const TextStyle(
              color: Colors.white,
              fontSize: 32,
              fontWeight: FontWeight.bold,
              letterSpacing: 0.5,
            ),
          ),
          const SizedBox(height: 20),
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Today\'s Earnings',
                      style: TextStyle(color: Colors.white70, fontSize: 11),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '₱${(todayEarn as num).toStringAsFixed(2)}',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ),
              Container(width: 1, height: 30, color: Colors.white24),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.only(left: 16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Today\'s Trips',
                        style: TextStyle(color: Colors.white70, fontSize: 11),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        '$todayTrips',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _statBadge(IconData icon, String count, String label, Color color) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 8),
        decoration: BoxDecoration(
          color: color.withOpacity(0.1),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: color.withOpacity(0.3)),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, color: color, size: 20),
            const SizedBox(width: 6),
            Text(
              count,
              style: TextStyle(
                color: color,
                fontWeight: FontWeight.bold,
                fontSize: 18,
              ),
            ),
            const SizedBox(width: 4),
            Text(
              label,
              style: TextStyle(color: color.withOpacity(0.8), fontSize: 11),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildOrderList(List<Map<String, dynamic>> orders, String type) {
    if (orders.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              type == 'available'
                  ? Icons.local_shipping_outlined
                  : type == 'active'
                  ? Icons.directions_bike_outlined
                  : Icons.check_circle_outline,
              size: 60,
              color: AppColors.textMuted.withOpacity(0.3),
            ),
            const SizedBox(height: 12),
            Text(
              type == 'available'
                  ? 'No delivery orders right now'
                  : type == 'active'
                  ? 'No active deliveries'
                  : 'No completed deliveries yet',
              style: TextStyle(color: AppColors.textMuted, fontSize: 15),
            ),
          ],
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: () => _loadData(),
      child: ListView.builder(
        padding: const EdgeInsets.all(12),
        itemCount: orders.length,
        itemBuilder: (ctx, i) => _orderCard(orders[i], type),
      ),
    );
  }

  Widget _orderCard(Map<String, dynamic> order, String type) {
    final items = List<Map<String, dynamic>>.from(order['items'] ?? []);
    final deliveryStatus = order['delivery_status'] ?? 'WAITING';
    final paymentMethod = order['payment_method'] ?? 'COUNTER';
    final paymentStatus = order['payment_status'] ?? 'UNPAID';
    final isCOD = paymentMethod == 'COUNTER' && paymentStatus == 'UNPAID';

    Color statusColor;
    IconData statusIcon;
    String statusLabel;
    switch (deliveryStatus) {
      case 'WAITING':
        statusColor = Colors.orange;
        statusIcon = Icons.hourglass_top;
        statusLabel = 'WAITING';
        break;
      case 'PICKED_UP':
        statusColor = Colors.teal;
        statusIcon = Icons.inventory_2;
        statusLabel = 'PICKED UP';
        break;
      case 'ON_THE_WAY':
        statusColor = Colors.blue;
        statusIcon = Icons.directions_bike;
        statusLabel = 'ON THE WAY';
        break;
      case 'DELIVERED':
        statusColor = Colors.green;
        statusIcon = Icons.check_circle;
        statusLabel = 'DELIVERED';
        break;
      default:
        statusColor = AppColors.primary;
        statusIcon = Icons.schedule;
        statusLabel = deliveryStatus;
    }

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: statusColor.withOpacity(0.3)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.05),
            offset: const Offset(0, 4),
            blurRadius: 10,
          ),
        ],
      ),
      child: Column(
        children: [
          // Header
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: statusColor.withOpacity(0.08),
              borderRadius: const BorderRadius.vertical(
                top: Radius.circular(16),
              ),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  children: [
                    Icon(statusIcon, color: statusColor, size: 20),
                    const SizedBox(width: 8),
                    Text(
                      'Order #${order['id']}',
                      style: TextStyle(
                        color: AppColors.textMain,
                        fontWeight: FontWeight.bold,
                        fontSize: 16,
                      ),
                    ),
                  ],
                ),
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 10,
                    vertical: 4,
                  ),
                  decoration: BoxDecoration(
                    color: statusColor.withOpacity(0.2),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    statusLabel,
                    style: TextStyle(
                      color: statusColor,
                      fontWeight: FontWeight.bold,
                      fontSize: 11,
                    ),
                  ),
                ),
              ],
            ),
          ),
          // Body
          Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Customer info
                Row(
                  children: [
                    Icon(Icons.person, color: AppColors.textMuted, size: 18),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        order['customer_name'] ?? 'Customer',
                        style: TextStyle(
                          color: AppColors.textMain,
                          fontSize: 14,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(Icons.location_on, color: AppColors.primary, size: 18),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        order['delivery_address'] ?? 'No address',
                        style: TextStyle(
                          color: AppColors.textMuted,
                          fontSize: 13,
                        ),
                      ),
                    ),
                    if (type == 'active' && order['delivery_address'] != null)
                      IconButton(
                        onPressed: () async {
                          final address = Uri.encodeComponent(
                            order['delivery_address'],
                          );
                          final googleUrl = Uri.parse(
                            'https://www.google.com/maps/search/?api=1&query=$address',
                          );
                          try {
                            final launched = await launchUrl(
                              googleUrl,
                              mode: LaunchMode.externalApplication,
                            );
                            if (!launched && mounted) {
                              _showSnack(
                                'Could not open Google Maps.',
                                Colors.red,
                              );
                            }
                          } catch (e) {
                            if (mounted) {
                              _showSnack(
                                'Could not open Google Maps.',
                                Colors.red,
                              );
                            }
                          }
                        },
                        icon: const Icon(Icons.directions),
                        color: Colors.blue,
                        tooltip: 'Open in Maps',
                        padding: EdgeInsets.zero,
                        constraints: const BoxConstraints(),
                      ),
                  ],
                ),
                if (order['customer_phone'] != null) ...[
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      GestureDetector(
                        onTap: () async {
                          final phone = order['customer_phone'];
                          final uri = Uri.parse('tel:$phone');
                          try {
                            await launchUrl(uri);
                          } catch (_) {
                            if (mounted)
                              _showSnack('Could not open dialer.', Colors.red);
                          }
                        },
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Container(
                              padding: const EdgeInsets.all(4),
                              decoration: BoxDecoration(
                                color: Colors.green.withOpacity(0.1),
                                borderRadius: BorderRadius.circular(6),
                              ),
                              child: const Icon(
                                Icons.phone,
                                color: Colors.green,
                                size: 16,
                              ),
                            ),
                            const SizedBox(width: 8),
                            Text(
                              order['customer_phone'],
                              style: const TextStyle(
                                color: Colors.green,
                                fontSize: 13,
                                fontWeight: FontWeight.w600,
                                decoration: TextDecoration.underline,
                              ),
                            ),
                          ],
                        ),
                      ),
                      if (type == 'active') ...[
                        const Spacer(),
                        GestureDetector(
                          onTap: () {
                            Navigator.push(
                              context,
                              MaterialPageRoute(
                                builder: (_) => OrderChatScreen(
                                  orderId: order['id'],
                                  otherPartyName:
                                      order['customer_name'] ?? 'Customer',
                                  otherPartyRole: 'Customer',
                                ),
                              ),
                            );
                          },
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 10,
                              vertical: 6,
                            ),
                            decoration: BoxDecoration(
                              color: AppColors.primary.withOpacity(0.1),
                              borderRadius: BorderRadius.circular(20),
                              border: Border.all(
                                color: AppColors.primary.withOpacity(0.3),
                              ),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(
                                  Icons.chat_bubble_outline_rounded,
                                  color: AppColors.primary,
                                  size: 14,
                                ),
                                const SizedBox(width: 4),
                                Text(
                                  'Chat',
                                  style: TextStyle(
                                    color: AppColors.primary,
                                    fontSize: 11,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                ],
                // Kitchen Status Indicator (for active/waiting orders)
                if (type == 'active' && order['kitchen_status'] != null) ...[
                  const SizedBox(height: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 10,
                      vertical: 6,
                    ),
                    decoration: BoxDecoration(
                      color: order['kitchen_status'] == 'COMPLETED'
                          ? Colors.green.withOpacity(0.08)
                          : order['kitchen_status'] == 'PREPARING'
                          ? Colors.blue.withOpacity(0.08)
                          : Colors.orange.withOpacity(0.08),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(
                        color: order['kitchen_status'] == 'COMPLETED'
                            ? Colors.green.withOpacity(0.3)
                            : order['kitchen_status'] == 'PREPARING'
                            ? Colors.blue.withOpacity(0.3)
                            : Colors.orange.withOpacity(0.3),
                      ),
                    ),
                    child: Row(
                      children: [
                        Icon(
                          order['kitchen_status'] == 'COMPLETED'
                              ? Icons.check_circle
                              : order['kitchen_status'] == 'PREPARING'
                              ? Icons.local_fire_department
                              : Icons.hourglass_top,
                          size: 16,
                          color: order['kitchen_status'] == 'COMPLETED'
                              ? Colors.green
                              : order['kitchen_status'] == 'PREPARING'
                              ? Colors.blue
                              : Colors.orange,
                        ),
                        const SizedBox(width: 6),
                        Text(
                          'Kitchen: ${order['kitchen_status']}',
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.bold,
                            color: order['kitchen_status'] == 'COMPLETED'
                                ? Colors.green
                                : order['kitchen_status'] == 'PREPARING'
                                ? Colors.blue
                                : Colors.orange,
                          ),
                        ),
                        if (order['kitchen_status'] != 'COMPLETED' &&
                            deliveryStatus == 'WAITING') ...[
                          const Spacer(),
                          Text(
                            'Wait...',
                            style: TextStyle(
                              fontSize: 11,
                              fontStyle: FontStyle.italic,
                              color: Colors.grey[500],
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ],
                // Order timestamp
                if (order['created_at'] != null) ...[
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      Icon(
                        Icons.access_time,
                        color: AppColors.textMuted.withOpacity(0.6),
                        size: 14,
                      ),
                      const SizedBox(width: 6),
                      Text(
                        _formatOrderTime(order['created_at']),
                        style: TextStyle(
                          color: AppColors.textMuted.withOpacity(0.7),
                          fontSize: 11,
                          fontStyle: FontStyle.italic,
                        ),
                      ),
                    ],
                  ),
                ],
                Divider(color: Colors.grey.withOpacity(0.2), height: 20),
                // Items
                ...items.map(
                  (item) => Padding(
                    padding: const EdgeInsets.only(bottom: 4),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          '${item['quantity']}x ${item['name']}',
                          style: TextStyle(
                            color: AppColors.textMain.withOpacity(0.8),
                            fontSize: 13,
                          ),
                        ),
                        Text(
                          '₱${(item['price'] * item['quantity']).toStringAsFixed(2)}',
                          style: TextStyle(
                            color: AppColors.textMain.withOpacity(0.8),
                            fontSize: 13,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                Divider(color: Colors.grey.withOpacity(0.2), height: 20),
                // Total & Payment
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 8,
                            vertical: 3,
                          ),
                          decoration: BoxDecoration(
                            color: isCOD
                                ? Colors.orange.withOpacity(0.15)
                                : Colors.green.withOpacity(0.15),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Text(
                            isCOD ? 'COD' : 'PAID',
                            style: TextStyle(
                              color: isCOD ? Colors.orange : Colors.green,
                              fontWeight: FontWeight.bold,
                              fontSize: 11,
                            ),
                          ),
                        ),
                      ],
                    ),
                    Text(
                      '₱${(order['total_amount'] as num).toStringAsFixed(2)}',
                      style: TextStyle(
                        color: AppColors.textMain,
                        fontWeight: FontWeight.bold,
                        fontSize: 18,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          // Action buttons
          if (type != 'completed')
            Container(
              padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
              child: _buildActionButton(order, type),
            ),
        ],
      ),
    );
  }

  Widget _buildActionButton(Map<String, dynamic> order, String type) {
    final deliveryStatus = order['delivery_status'] ?? 'WAITING';
    final kitchenStatus = order['kitchen_status'] ?? 'PENDING';
    final isCOD =
        order['payment_method'] == 'COUNTER' &&
        order['payment_status'] == 'UNPAID';

    if (type == 'available') {
      final kitchenReady = kitchenStatus == 'COMPLETED';
      return SizedBox(
        width: double.infinity,
        child: ElevatedButton.icon(
          onPressed: kitchenReady ? () => _acceptOrder(order['id']) : null,
          icon: Icon(
            kitchenReady ? Icons.check : Icons.local_fire_department,
            size: 20,
          ),
          label: Text(
            kitchenReady ? 'ACCEPT DELIVERY' : 'KITCHEN IS PREPARING',
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
          style: ElevatedButton.styleFrom(
            backgroundColor: kitchenReady
                ? AppColors.primary
                : Colors.grey[400],
            foregroundColor: Colors.white,
            disabledBackgroundColor: Colors.grey[300],
            disabledForegroundColor: Colors.grey[500],
            padding: const EdgeInsets.symmetric(vertical: 14),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
          ),
        ),
      );
    }

    // WAITING state - rider has accepted but kitchen not done
    if (deliveryStatus == 'WAITING') {
      final kitchenReady = kitchenStatus == 'COMPLETED';
      return SizedBox(
        width: double.infinity,
        child: ElevatedButton.icon(
          onPressed: kitchenReady
              ? () => _updateStatus(order['id'], 'PICKED_UP')
              : null, // Disabled until kitchen is done
          icon: Icon(
            kitchenReady ? Icons.inventory_2 : Icons.hourglass_top,
            size: 20,
          ),
          label: Text(
            kitchenReady ? 'PICK UP ORDER' : 'WAITING FOR KITCHEN...',
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
          style: ElevatedButton.styleFrom(
            backgroundColor: kitchenReady ? Colors.teal : Colors.grey[400],
            foregroundColor: Colors.white,
            disabledBackgroundColor: Colors.grey[300],
            disabledForegroundColor: Colors.grey[500],
            padding: const EdgeInsets.symmetric(vertical: 14),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
          ),
        ),
      );
    }

    if (deliveryStatus == 'PICKED_UP') {
      return SizedBox(
        width: double.infinity,
        child: ElevatedButton.icon(
          onPressed: () => _updateStatus(order['id'], 'ON_THE_WAY'),
          icon: const Icon(Icons.directions_bike, size: 20),
          label: const Text(
            'ON THE WAY',
            style: TextStyle(fontWeight: FontWeight.bold),
          ),
          style: ElevatedButton.styleFrom(
            backgroundColor: Colors.blue,
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(vertical: 14),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
          ),
        ),
      );
    }

    if (deliveryStatus == 'ON_THE_WAY') {
      return SizedBox(
        width: double.infinity,
        child: ElevatedButton.icon(
          onPressed: () {
            if (isCOD) {
              _showCollectPaymentDialog(order);
            } else {
              _updateStatus(order['id'], 'DELIVERED');
            }
          },
          icon: const Icon(Icons.check_circle, size: 20),
          label: Text(
            isCOD ? 'COLLECT & DELIVER' : 'MARK AS DELIVERED',
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
          style: ElevatedButton.styleFrom(
            backgroundColor: Colors.green,
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(vertical: 14),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
          ),
        ),
      );
    }

    return const SizedBox.shrink();
  }

  String _formatOrderTime(String dateStr) {
    try {
      final dt = DateTime.parse(dateStr);
      final now = DateTime.now();
      final diff = now.difference(dt);

      if (diff.inMinutes < 1) return 'Just now';
      if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
      if (diff.inHours < 24) return '${diff.inHours}h ago';
      if (diff.inDays < 7) return '${diff.inDays}d ago';

      final months = [
        'Jan',
        'Feb',
        'Mar',
        'Apr',
        'May',
        'Jun',
        'Jul',
        'Aug',
        'Sep',
        'Oct',
        'Nov',
        'Dec',
      ];
      final hour = dt.hour > 12 ? dt.hour - 12 : (dt.hour == 0 ? 12 : dt.hour);
      final ampm = dt.hour >= 12 ? 'PM' : 'AM';
      return '${months[dt.month - 1]} ${dt.day}, $hour:${dt.minute.toString().padLeft(2, '0')} $ampm';
    } catch (_) {
      return '';
    }
  }
}


