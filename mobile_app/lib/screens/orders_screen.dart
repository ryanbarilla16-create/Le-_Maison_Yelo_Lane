import 'package:flutter/material.dart';
import '../theme.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';
import 'delivery_tracking_screen.dart';
import 'order_chat_screen.dart';
import 'cart_screen.dart';

class OrdersScreen extends StatefulWidget {
  const OrdersScreen({super.key});

  @override
  State<OrdersScreen> createState() => _OrdersScreenState();
}

class _OrdersScreenState extends State<OrdersScreen>
    with SingleTickerProviderStateMixin {
  List<dynamic> _orders = [];
  bool _loading = true;
  late TabController _tabController;

  final _tabs = [
    {'label': 'All', 'value': 'ALL'},
    {'label': 'Pending', 'value': 'PENDING'},
    {'label': 'Preparing', 'value': 'PREPARING'},
    {'label': 'Completed', 'value': 'COMPLETED'},
    {'label': 'Cancelled', 'value': 'CANCELLED'},
  ];

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: _tabs.length, vsync: this);
    _loadOrders();
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  Future<void> _loadOrders() async {
    final userId = await AuthService.getUserId();
    if (userId == null) return;

    final res = await ApiService.get('/api/user/$userId/orders');
    if (res != null && res is Map) {
      setState(() {
        _orders = res['orders'] ?? [];
        _loading = false;
      });
    } else {
      setState(() => _loading = false);
    }
  }

  List<dynamic> _filteredOrders(String filter) {
    if (filter == 'ALL') return _orders;
    return _orders.where((o) => o['status'] == filter).toList();
  }

  String _statusLabel(String status) {
    switch (status) {
      case 'PENDING':
        return 'TO CONFIRM';
      case 'CONFIRMED':
        return 'CONFIRMED';
      case 'PREPARING':
        return 'PREPARING';
      case 'READY':
        return 'READY';
      case 'ON_THE_WAY':
        return 'ON THE WAY';
      case 'COMPLETED':
        return 'COMPLETED';
      case 'CANCELLED':
        return 'CANCELLED';
      default:
        return status;
    }
  }

  Color _statusColor(String status) {
    switch (status) {
      case 'PENDING':
        return const Color(0xFFE8740C);
      case 'CONFIRMED':
        return const Color(0xFF2E7D32);
      case 'PREPARING':
        return const Color(0xFF1565C0);
      case 'READY':
        return const Color(0xFF00838F);
      case 'ON_THE_WAY':
        return const Color(0xFF6A1B9A);
      case 'COMPLETED':
        return const Color(0xFF2E7D32);
      case 'CANCELLED':
        return const Color(0xFFC62828);
      default:
        return Colors.grey;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF5F5F5),
      appBar: AppBar(
        backgroundColor: AppColors.primary,
        elevation: 0.5,
        title: const Text(
          'My Orders',
          style: TextStyle(
            color: Colors.white,
            fontWeight: FontWeight.w700,
            fontSize: 18,
            letterSpacing: 0.3,
          ),
        ),
        centerTitle: true,
        iconTheme: const IconThemeData(color: Colors.white),
        bottom: TabBar(
          controller: _tabController,
          isScrollable: true,
          indicatorColor: Colors.white,
          indicatorWeight: 3,
          labelColor: Colors.white,
          unselectedLabelColor: Colors.white60,
          labelStyle: const TextStyle(
            fontWeight: FontWeight.w700,
            fontSize: 13,
          ),
          unselectedLabelStyle: const TextStyle(
            fontWeight: FontWeight.w500,
            fontSize: 13,
          ),
          tabAlignment: TabAlignment.start,
          tabs: _tabs.map((t) {
            final count = _filteredOrders(t['value']!).length;
            return Tab(
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(t['label']!),
                  if (count > 0 && t['value'] != 'ALL') ...[
                    const SizedBox(width: 4),
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 6,
                        vertical: 1,
                      ),
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.25),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Text(
                        '$count',
                        style: const TextStyle(fontSize: 10),
                      ),
                    ),
                  ],
                ],
              ),
            );
          }).toList(),
        ),
      ),
      body: _loading
          ? const Center(
              child: CircularProgressIndicator(color: AppColors.primary),
            )
          : TabBarView(
              controller: _tabController,
              children: _tabs.map((t) {
                final orders = _filteredOrders(t['value']!);
                if (orders.isEmpty) return _emptyState(t['label']!);
                return RefreshIndicator(
                  color: AppColors.primary,
                  onRefresh: _loadOrders,
                  child: ListView.builder(
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    itemCount: orders.length,
                    physics: const AlwaysScrollableScrollPhysics(),
                    itemBuilder: (_, i) => _orderCard(orders[i]),
                  ),
                );
              }).toList(),
            ),
    );
  }

  Widget _orderCard(dynamic o) {
    final items = o['items'] as List? ?? [];
    final status = o['status'] ?? 'PENDING';
    final statusColor = _statusColor(status);
    final diningOption = o['dining_option'] ?? '';
    final paymentMethod = o['payment_method'] ?? '';

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        boxShadow: [
          BoxShadow(
            color: AppColors.primary.withOpacity(0.06),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Stack(
        children: [
          Positioned(
            left: -8,
            top: 50,
            child: CircleAvatar(radius: 8, backgroundColor: const Color(0xFFF5F5F5)),
          ),
          Positioned(
            right: -8,
            top: 50,
            child: CircleAvatar(radius: 8, backgroundColor: const Color(0xFFF5F5F5)),
          ),
          Column(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                decoration: BoxDecoration(
                  border: Border(bottom: BorderSide(color: Colors.grey.shade100, width: 1)),
                ),
                child: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(4),
                      decoration: BoxDecoration(
                        color: AppColors.primary.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: const Icon(Icons.store_rounded, size: 14, color: AppColors.primary),
                    ),
                    const SizedBox(width: 8),
                    const Expanded(
                      child: Text(
                        'Le Maison Yelo Lane',
                        style: TextStyle(fontWeight: FontWeight.w700, fontSize: 13, letterSpacing: 0.2),
                      ),
                    ),
                    Text(
                      _statusLabel(status),
                      style: TextStyle(color: statusColor, fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 0.5),
                    ),
                  ],
                ),
              ),
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 14),
                child: _DashedDivider(),
              ),
              ...items.map((item) => _orderItemRow(item)),
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 14),
                child: _DashedDivider(),
              ),
              if (diningOption == 'DELIVERY' && o['delivery_address'] != null && o['delivery_address'] != '')
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  decoration: BoxDecoration(
                    color: const Color(0xFFFFF8E1),
                    border: Border(top: BorderSide(color: Colors.amber.shade100)),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.delivery_dining_rounded, size: 16, color: Colors.amber.shade800),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(
                          o['delivery_address'],
                          style: TextStyle(fontSize: 11, color: Colors.amber.shade900),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                decoration: BoxDecoration(
                  border: Border(top: BorderSide(color: Colors.grey.shade100, width: 1)),
                ),
                child: Row(
                  children: [
                    _miniTag(diningOption == 'DINE_IN' ? 'Dine In' : diningOption == 'DELIVERY' ? 'Delivery' : 'Pick-up', diningOption == 'DELIVERY' ? Icons.delivery_dining : diningOption == 'DINE_IN' ? Icons.restaurant : Icons.takeout_dining),
                    const SizedBox(width: 6),
                    _miniTag(paymentMethod == 'ONLINE' || paymentMethod == 'GCASH' ? 'GCash' : 'Counter', Icons.payment_rounded),
                    const Spacer(),
                    Text('${items.length} item${items.length > 1 ? 's' : ''}', style: TextStyle(color: Colors.grey.shade600, fontSize: 12)),
                    const SizedBox(width: 6),
                    const Text('Total:', style: TextStyle(fontSize: 13, color: Colors.black54)),
                    const SizedBox(width: 4),
                    Text(
                      '₱${(o['total_amount'] as num).toStringAsFixed(2)}',
                      style: TextStyle(fontSize: 17, fontWeight: FontWeight.w800, color: AppColors.accent, fontFamily: 'Georgia'),
                    ),
                  ],
                ),
              ),
              if (o['notes'] != null && o['notes'] != '')
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  decoration: BoxDecoration(color: Colors.grey.shade50, border: Border(top: BorderSide(color: Colors.grey.shade100))),
                  child: Row(
                    children: [
                      Icon(Icons.sticky_note_2_outlined, size: 14, color: Colors.grey.shade500),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(
                          o['notes'],
                          style: TextStyle(fontSize: 12, color: Colors.grey.shade600, fontStyle: FontStyle.italic),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                ),
              if (o['review_rating'] != null)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  decoration: BoxDecoration(color: Colors.grey.shade50, border: Border(top: BorderSide(color: Colors.grey.shade100))),
                  child: Row(
                    children: [
                      ...List.generate(5, (i) => Icon(i < (o['review_rating'] as int) ? Icons.star_rounded : Icons.star_border_rounded, color: const Color(0xFFF9A825), size: 18)),
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                        decoration: BoxDecoration(color: const Color(0xFF2E7D32).withOpacity(0.08), borderRadius: BorderRadius.circular(10)),
                        child: const Text('Reviewed', style: TextStyle(color: Color(0xFF2E7D32), fontSize: 10, fontWeight: FontWeight.w700)),
                      ),
                    ],
                  ),
                ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                decoration: BoxDecoration(border: Border(top: BorderSide(color: Colors.grey.shade100))),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        'Order #${o['id']} · ${o['created_at'] ?? ''}',
                        style: TextStyle(fontSize: 11, color: Colors.grey.shade500),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    const SizedBox(width: 8),
                    if (diningOption == 'DELIVERY' && status != 'CANCELLED' && status != 'COMPLETED')
                      _actionButton('Track', Icons.location_on_rounded, const Color(0xFF1565C0), () {
                        Navigator.push(context, MaterialPageRoute(builder: (_) => DeliveryTrackingScreen(orderId: o['id'], deliveryAddress: o['delivery_address'])));
                      }),
                    if (diningOption == 'DELIVERY' && status != 'CANCELLED' && status != 'COMPLETED') ...[
                      const SizedBox(width: 8),
                      _actionButton('Chat', Icons.chat_bubble_rounded, AppColors.primary, () => Navigator.push(context, MaterialPageRoute(builder: (_) => OrderChatScreen(orderId: o['id'], otherPartyName: 'Delivery Rider', otherPartyRole: 'Rider')))),
                    ],
                    if (status == 'COMPLETED' && o['review_rating'] == null) ...[
                      const SizedBox(width: 8),
                      _actionButton('Rate', Icons.star_rounded, const Color(0xFFF9A825), () => _showReviewDialog(o['id'])),
                    ],
                    if (status == 'COMPLETED') ...[
                      const SizedBox(width: 8),
                      _primaryActionButton('Buy Again', () {
                        for (final item in items) {
                          final qty = item['quantity'] is int ? item['quantity'] : 1;
                          for (int i = 0; i < qty; i++) {
                            CartScreen.addItem({'id': item['menu_item_id'] ?? item['id'] ?? 0, 'name': item['name'], 'price': item['price'], 'image_url': item['image_url'], 'category': item['category'] ?? ''});
                          }
                        }
                        Navigator.push(context, MaterialPageRoute(builder: (_) => const CartScreen())).then((_) => setState(() {}));
                      }),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _orderItemRow(dynamic item) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          // Simple quantity indicator
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: AppColors.primary.withOpacity(0.05),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(
              '${item['quantity']}x',
              style: const TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.bold,
                color: AppColors.primary,
              ),
            ),
          ),
          const SizedBox(width: 12),
          // Product details
          Expanded(
            child: Text(
              item['name'] ?? '',
              style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w500,
                color: Color(0xFF444444),
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          const SizedBox(width: 8),
          Text(
            '₱${(item['price'] * item['quantity']).toStringAsFixed(2)}',
            style: const TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: Color(0xFF666666),
              fontFamily: 'monospace',
            ),
          ),
        ],
      ),
    );
  }

  Widget _imagePlaceholder() {
    return Container(
      width: 72,
      height: 72,
      decoration: BoxDecoration(
        color: AppColors.primary.withOpacity(0.08),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Icon(
        Icons.restaurant_rounded,
        color: AppColors.primary.withOpacity(0.4),
        size: 28,
      ),
    );
  }

  Widget _miniTag(String label, IconData icon) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
      decoration: BoxDecoration(
        color: Colors.grey.shade100,
        borderRadius: BorderRadius.circular(4),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 11, color: Colors.grey.shade600),
          const SizedBox(width: 3),
          Text(
            label,
            style: TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w600,
              color: Colors.grey.shade700,
            ),
          ),
        ],
      ),
    );
  }

  Widget _actionButton(
    String label,
    IconData icon,
    Color color,
    VoidCallback onTap,
  ) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(6),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
          decoration: BoxDecoration(
            border: Border.all(color: color.withOpacity(0.4)),
            borderRadius: BorderRadius.circular(6),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 14, color: color),
              const SizedBox(width: 4),
              Text(
                label,
                style: TextStyle(
                  color: color,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _primaryActionButton(String label, VoidCallback onTap) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(6),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
          decoration: BoxDecoration(
            color: AppColors.primary,
            borderRadius: BorderRadius.circular(6),
          ),
          child: Text(
            label,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 12,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
      ),
    );
  }

  // ═══ EMPTY STATE ═══
  Widget _emptyState(String tabLabel) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: Colors.grey.shade100,
              shape: BoxShape.circle,
            ),
            child: Icon(
              Icons.receipt_long_rounded,
              size: 48,
              color: Colors.grey.shade400,
            ),
          ),
          const SizedBox(height: 16),
          Text(
            'No ${tabLabel.toLowerCase()} orders',
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w600,
              color: Colors.grey.shade700,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            'Your orders will appear here',
            style: TextStyle(
              fontSize: 13,
              color: Colors.grey.shade500,
            ),
          ),
        ],
      ),
    );
  }

  // ═══ REVIEW DIALOG ═══
  void _showReviewDialog(int orderId) {
    int rating = 5;
    final commentCtrl = TextEditingController();

    showDialog(
      context: context,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setDialogState) {
            return AlertDialog(
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
              ),
              title: Row(
                children: [
                  Icon(Icons.star_rounded, color: const Color(0xFFF9A825)),
                  const SizedBox(width: 8),
                  const Text(
                    'Rate Your Order',
                    style: TextStyle(
                      fontFamily: 'Georgia',
                      fontWeight: FontWeight.bold,
                      fontSize: 18,
                    ),
                  ),
                ],
              ),
              content: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Text(
                    'How was your experience?',
                    style: TextStyle(
                      color: Colors.black54,
                      fontSize: 13,
                    ),
                  ),
                  const SizedBox(height: 16),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: List.generate(
                      5,
                      (i) => GestureDetector(
                        onTap: () =>
                            setDialogState(() => rating = i + 1),
                        child: Padding(
                          padding:
                              const EdgeInsets.symmetric(horizontal: 4),
                          child: Icon(
                            i < rating
                                ? Icons.star_rounded
                                : Icons.star_border_rounded,
                            color: const Color(0xFFF9A825),
                            size: 40,
                          ),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    rating == 5
                        ? 'Amazing!'
                        : rating == 4
                            ? 'Great!'
                            : rating == 3
                                ? 'Good'
                                : rating == 2
                                    ? 'Fair'
                                    : 'Poor',
                    style: TextStyle(
                      color: const Color(0xFFF9A825),
                      fontWeight: FontWeight.w700,
                      fontSize: 14,
                    ),
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: commentCtrl,
                    maxLines: 3,
                    decoration: InputDecoration(
                      hintText: 'Share your experience (optional)',
                      hintStyle: TextStyle(
                        color: Colors.grey.shade400,
                        fontSize: 13,
                      ),
                      filled: true,
                      fillColor: Colors.grey.shade50,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: BorderSide(color: Colors.grey.shade200),
                      ),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: BorderSide(color: Colors.grey.shade200),
                      ),
                    ),
                  ),
                ],
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(ctx),
                  child: Text(
                    'Cancel',
                    style: TextStyle(color: Colors.grey.shade600),
                  ),
                ),
                DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: AppColors.buttonGradient,
                    borderRadius: BorderRadius.circular(10),
                    boxShadow: [
                      BoxShadow(
                        color: AppColors.primary.withOpacity(0.25),
                        blurRadius: 6,
                        offset: const Offset(0, 3),
                      ),
                    ],
                  ),
                  child: ElevatedButton(
                    onPressed: () async {
                      final userId = await AuthService.getUserId();
                      final res = await ApiService.post(
                          '/api/order/$orderId/review', {
                        'user_id': userId,
                        'rating': rating,
                        'comment': commentCtrl.text.trim(),
                      });
                      if (!ctx.mounted) return;
                      Navigator.pop(ctx);
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content:
                              Text(res['message'] ?? 'Review submitted!'),
                          backgroundColor: res['success'] == true
                              ? const Color(0xFF2E7D32)
                              : const Color(0xFFC62828),
                          behavior: SnackBarBehavior.floating,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(10),
                          ),
                        ),
                      );
                      _loadOrders();
                    },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.transparent,
                      shadowColor: Colors.transparent,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(10),
                      ),
                    ),
                    child: const Text('Submit Review', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                  ),
                ),

              ],
            );
          },
        );
      },
    );
  }
}


class _DashedDivider extends StatelessWidget {
  const _DashedDivider();

  @override
  Widget build(BuildContext context) {
    return Row(
      children: List.generate(
        150,
        (i) => Expanded(
          child: Container(
            color: i % 2 == 0 ? Colors.transparent : Colors.grey.shade300,
            height: 1,
          ),
        ),
      ),
    );
  }
}
