import 'package:flutter/material.dart';
import '../theme.dart';
import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';

import 'xendit_sandbox_screen.dart';

class CartScreen extends StatefulWidget {
  const CartScreen({super.key});

  // ═══ STATIC CART (in-memory, shared across screens) ═══
  static final List<Map<String, dynamic>> _cartItems = [];

  static Future<void> loadCart() async {
    final prefs = await SharedPreferences.getInstance();
    final String? cartStr = prefs.getString('cart_items');
    if (cartStr != null) {
      final List<dynamic> decoded = jsonDecode(cartStr);
      _cartItems.clear();
      _cartItems.addAll(decoded.map((e) => e as Map<String, dynamic>));
    }
  }

  static Future<void> saveCart() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('cart_items', jsonEncode(_cartItems));
  }

  static void addItem(dynamic menuItem) {
    final existing = _cartItems.indexWhere((ci) => ci['id'] == menuItem['id']);
    if (existing >= 0) {
      _cartItems[existing]['quantity']++;
    } else {
      _cartItems.add({
        'id': menuItem['id'],
        'name': menuItem['name'],
        'price': menuItem['price'],
        'image_url': menuItem['image_url'],
        'category': menuItem['category'],
        'quantity': 1,
      });
    }
    saveCart();
  }

  static List<Map<String, dynamic>> get items => _cartItems;
  static int get count =>
      _cartItems.fold(0, (sum, i) => sum + (i['quantity'] as int));
  static double get total => _cartItems.fold(
    0.0,
    (sum, i) => sum + (i['price'] as num) * (i['quantity'] as int),
  );
  static void clear() {
    _cartItems.clear();
    saveCart();
  }

  @override
  State<CartScreen> createState() => _CartScreenState();
}

class _CartScreenState extends State<CartScreen> {
  String _diningOption = 'DINE_IN';
  String _paymentMethod = 'COUNTER';
  final _notesCtrl = TextEditingController();
  final _addressCtrl = TextEditingController();
  bool _loading = false;

  Future<void> _checkout() async {
    if (CartScreen._cartItems.isEmpty) {
      _showMsg('Your cart is empty.', false);
      return;
    }

    if (_diningOption == 'DELIVERY' && _addressCtrl.text.trim().isEmpty) {
      _showMsg('Delivery address is required.', false);
      return;
    }

    final userId = await AuthService.getUserId();
    if (userId == null) return;

    setState(() => _loading = true);

    final res = await ApiService.post('/api/order/checkout', {
      'user_id': userId,
      'items': CartScreen._cartItems
          .map((ci) => {'menu_item_id': ci['id'], 'quantity': ci['quantity']})
          .toList(),
      'notes': _notesCtrl.text.trim(),
      'dining_option': _diningOption,
      'payment_method': _paymentMethod,
      if (_diningOption == 'DELIVERY')
        'delivery_address': _addressCtrl.text.trim(),
    });

    setState(() => _loading = false);

    if (res['success'] == true) {
      CartScreen.clear();
      
      // Handle Xendit Payment Redirection (In-App WebView)
      if (res['invoice_url'] != null) {
        if (!mounted) return;
        await Navigator.push(
          context,
          MaterialPageRoute(
            builder: (_) => XenditSandboxScreen(url: res['invoice_url']),
          ),
        );
      }

      if (!mounted) return;
      
      // Show success dialog
      showDialog(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => AlertDialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          title: Row(
            children: [
              Icon(Icons.check_circle, color: AppColors.success, size: 28),
              const SizedBox(width: 10),
              const Text('Order Success!'),
            ],
          ),
          content: Text(res['message'] ?? 'Your order has been placed successfully!'),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.pop(ctx); // pop dialog
                Navigator.pop(context, 1); // pop cart and return index 1
              },
              child: const Text('OK'),
            ),
          ],
        ),
      );
    } else {
      _showMsg(res['message'] ?? 'Checkout failed.', false);
    }
  }

  void _showMsg(String msg, bool success) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(msg),
        backgroundColor: success ? AppColors.success : AppColors.danger,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(
          'My Cart (${CartScreen.count})',
          style: AppTextStyles.heading.copyWith(fontSize: 18),
        ),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: CartScreen._cartItems.isEmpty
          ? Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    Icons.shopping_cart_outlined,
                    size: 60,
                    color: AppColors.primary.withOpacity(0.2),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    'Your cart is empty',
                    style: AppTextStyles.heading.copyWith(fontSize: 18),
                  ),
                  const SizedBox(height: 4),
                  const Text(
                    'Browse the menu to add items',
                    style: AppTextStyles.muted,
                  ),
                  const SizedBox(height: 20),
                  ElevatedButton(
                    onPressed: () => Navigator.pop(context, 1),
                    child: const Text('Browse Menu'),
                  ),
                ],
              ),
            )
          : Column(
              children: [
                Expanded(
                  child: ListView(
                    padding: const EdgeInsets.all(16),
                    children: [
                      ...CartScreen._cartItems.asMap().entries.map((entry) {
                        final i = entry.key;
                        final item = entry.value;
                        return _cartItemCard(item, i);
                      }),
                      const SizedBox(height: 16),

                      // Dining option
                      Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(14),
                          boxShadow: [
                            BoxShadow(
                              color: Colors.black.withOpacity(0.04),
                              blurRadius: 10,
                            ),
                          ],
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Dining Option',
                              style: AppTextStyles.heading.copyWith(
                                fontSize: 14,
                              ),
                            ),
                            const SizedBox(height: 8),
                            Wrap(
                              spacing: 8,
                              runSpacing: 8,
                              children: [
                                _optionChip(
                                  'Dine In',
                                  'DINE_IN',
                                  _diningOption,
                                  (v) => setState(() => _diningOption = v),
                                ),
                                _optionChip(
                                  'Take Out',
                                  'TAKE_OUT',
                                  _diningOption,
                                  (v) => setState(() => _diningOption = v),
                                ),
                                _optionChip(
                                  'Delivery',
                                  'DELIVERY',
                                  _diningOption,
                                  (v) => setState(() => _diningOption = v),
                                ),
                              ],
                            ),
                            if (_diningOption == 'DELIVERY') ...[
                              const SizedBox(height: 12),
                              TextField(
                                controller: _addressCtrl,
                                decoration: const InputDecoration(
                                  hintText: 'Enter complete delivery address',
                                  prefixIcon: Icon(Icons.location_on_outlined),
                                ),
                              ),
                            ],
                          ],
                        ),
                      ),
                      const SizedBox(height: 12),

                      // Payment method
                      Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(14),
                          boxShadow: [
                            BoxShadow(
                              color: Colors.black.withOpacity(0.04),
                              blurRadius: 10,
                            ),
                          ],
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Payment Method',
                              style: AppTextStyles.heading.copyWith(
                                fontSize: 14,
                              ),
                            ),
                            const SizedBox(height: 8),
                            Row(
                              children: [
                                _optionChip(
                                  _diningOption == 'DELIVERY'
                                      ? 'Cash on Delivery'
                                      : 'Pay at Counter',
                                  'COUNTER',
                                  _paymentMethod,
                                  (v) => setState(() => _paymentMethod = v),
                                ),
                                const SizedBox(width: 8),
                                _optionChip(
                                  'GCash',
                                  'GCASH',
                                  _paymentMethod,
                                  (v) => setState(() => _paymentMethod = v),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 12),

                      // Notes
                      Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(14),
                          boxShadow: [
                            BoxShadow(
                              color: Colors.black.withOpacity(0.04),
                              blurRadius: 10,
                            ),
                          ],
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Order Notes',
                              style: AppTextStyles.heading.copyWith(
                                fontSize: 14,
                              ),
                            ),
                            const SizedBox(height: 8),
                            TextField(
                              controller: _notesCtrl,
                              maxLines: 3,
                              decoration: const InputDecoration(
                                hintText: 'Special instructions (optional)',
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 20),
                    ],
                  ),
                ),

                // Bottom total & checkout
                Container(
                  padding: const EdgeInsets.all(20),
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
                  child: Row(
                    children: [
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text('Total', style: AppTextStyles.muted),
                          Text(
                            '₱${CartScreen.total.toStringAsFixed(2)}',
                            style: TextStyle(
                              fontFamily: 'Georgia',
                              fontWeight: FontWeight.bold,
                              fontSize: 22,
                              color: AppColors.primary,
                            ),
                          ),
                        ],
                      ),
                      const Spacer(),
                      SizedBox(
                        height: 48,
                        child: ElevatedButton(
                          onPressed: _loading ? null : _checkout,
                          style: ElevatedButton.styleFrom(
                            padding: const EdgeInsets.symmetric(horizontal: 32),
                          ),
                          child: _loading
                              ? const SizedBox(
                                  width: 22,
                                  height: 22,
                                  child: CircularProgressIndicator(
                                    color: Colors.white,
                                    strokeWidth: 2.5,
                                  ),
                                )
                              : const Text('Place Order'),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
    );
  }

  Widget _cartItemCard(Map<String, dynamic> item, int index) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        boxShadow: [
          BoxShadow(color: Colors.black.withOpacity(0.04), blurRadius: 8),
        ],
      ),
      child: Row(
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(10),
            child: item['image_url'] != null
                ? Image.network(
                    item['image_url'],
                    width: 60,
                    height: 60,
                    fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) => Container(
                      width: 60,
                      height: 60,
                      color: AppColors.primary.withOpacity(0.1),
                      child: const Icon(
                        Icons.restaurant,
                        size: 20,
                        color: AppColors.primary,
                      ),
                    ),
                  )
                : Container(
                    width: 60,
                    height: 60,
                    color: AppColors.primary.withOpacity(0.1),
                    child: const Icon(
                      Icons.restaurant,
                      size: 20,
                      color: AppColors.primary,
                    ),
                  ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item['name'],
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 14,
                  ),
                ),
                Text(
                  '₱${(item['price'] as num).toStringAsFixed(2)}',
                  style: TextStyle(
                    color: AppColors.primary,
                    fontWeight: FontWeight.w600,
                    fontSize: 13,
                  ),
                ),
              ],
            ),
          ),
          Row(
            children: [
              _qtyBtn(Icons.remove, () {
                setState(() {
                  if (item['quantity'] > 1) {
                    item['quantity']--;
                  } else {
                    CartScreen._cartItems.removeAt(index);
                  }
                  CartScreen.saveCart();
                });
              }),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 10),
                child: Text(
                  '${item['quantity']}',
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 16,
                  ),
                ),
              ),
              _qtyBtn(Icons.add, () {
                setState(() {
                  item['quantity']++;
                  CartScreen.saveCart();
                });
              }),
            ],
          ),
        ],
      ),
    );
  }

  Widget _qtyBtn(IconData icon, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(6),
        decoration: BoxDecoration(
          color: AppColors.primary.withOpacity(0.08),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Icon(icon, size: 16, color: AppColors.primary),
      ),
    );
  }

  Widget _optionChip(
    String label,
    String value,
    String current,
    Function(String) onTap,
  ) {
    final selected = value == current;
    return GestureDetector(
      onTap: () => onTap(value),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        decoration: BoxDecoration(
          color: selected ? AppColors.primary : Colors.transparent,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: selected
                ? AppColors.primary
                : AppColors.textMuted.withOpacity(0.3),
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: selected ? Colors.white : AppColors.textMain,
            fontWeight: FontWeight.w600,
            fontSize: 13,
          ),
        ),
      ),
    );
  }
}
