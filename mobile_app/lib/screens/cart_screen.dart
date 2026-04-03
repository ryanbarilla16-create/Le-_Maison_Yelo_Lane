import 'package:flutter/material.dart';
import '../theme.dart';
import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
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
  Set<int> _selectedIds = {};
  bool _selectAll = true;

  @override
  void initState() {
    super.initState();
    _selectedIds = CartScreen._cartItems.map((i) => i['id'] as int).toSet();
  }

  double get _selectedTotal => CartScreen._cartItems
      .where((i) => _selectedIds.contains(i['id']))
      .fold(0.0, (sum, i) => sum + (i['price'] as num) * (i['quantity'] as int));
  
  final Map<String, List<String>> _locationData = {
    'Santa Cruz': ['Alipit', 'Bagong Bayan', 'Bubukal', 'Calios', 'Duhat', 'Gatid', 'Giling-Giling', 'Labuin', 'Malinao', 'Matalatala', 'Oogong', 'Pagsawitan', 'Palanas', 'Poblacion I', 'Poblacion II', 'Poblacion III', 'Poblacion IV', 'Poblacion V', 'San Jose', 'San Juan', 'San Nicolas', 'San Pablo Norte', 'San Pablo Sur', 'Santisima Cruz', 'Santo Angel Central', 'Santo Angel Norte', 'Santo Angel Sur'],
    'Pila': ['Aplaya', 'Bagong Pook', 'Bukal', 'Bulilan Sur', 'Concepcion', 'Labuin', 'Linga', 'Masico', 'Mojon', 'Pansol', 'Pinagbayanan', 'Poblacion', 'San Antonio', 'San Miguel', 'Santa Clara Norte', 'Santa Clara Sur', 'Tubuan'],
    'Victoria': ['Banca-banca', 'Daniw', 'Masapang', 'Nanhaya', 'Pagalangan', 'San Francisco', 'San Roque', 'San Nicolas', 'Santa Cruz'],
    'Lumban': ['Bagong Silang', 'Balimbingan', 'Balubad', 'Caliraya', 'Concepcion', 'Luwac', 'Maracta', 'Maytalang I', 'Maytalang II', 'Primeiro Distrito', 'Salac', 'Santo Niño', 'Segundo Distrito', 'Talahib', 'Talongue', 'Wawa'],
    'Magdalena': ['Alipit', 'Baanan', 'Balanac', 'Bucal', 'Buenavista', 'Bungkol', 'Burol', 'Capayapaan', 'Cigaras', 'Halayhayin', 'Ibabang Atingay', 'Ibabang Butnong', 'Ilayang Atingay', 'Ilayang Butnong', 'Ilog', 'Malaking Ambling', 'Mali-mali', 'Mamatid', 'Poblacion', 'Sabang', 'Salaking', 'San Antonio', 'San Francisco', 'Tipunan']
  };

  final Map<String, LatLng> _townCoordinates = {
    'Santa Cruz': const LatLng(14.2833, 121.4167),
    'Pila': const LatLng(14.2333, 121.3667),
    'Victoria': const LatLng(14.2250, 121.3283),
    'Lumban': const LatLng(14.2981, 121.4608),
    'Magdalena': const LatLng(14.2000, 121.4333)
  };

  LatLng? _pinnedLocation = const LatLng(14.2833, 121.4167); // Santa Cruz
  final MapController _mapController = MapController();
  
  String? _selectedMunicipality;
  String? _selectedBarangay;

  Future<void> _checkLocation(LatLng pos) async {
    setState(() {
      _pinnedLocation = pos;
    });
  }

  Future<void> _checkout() async {
    final selectedItems = CartScreen._cartItems
        .where((ci) => _selectedIds.contains(ci['id']))
        .toList();

    if (selectedItems.isEmpty) {
      _showMsg('Please select at least one item to checkout.', false);
      return;
    }

    if (_diningOption == 'DELIVERY') {
      if (_selectedMunicipality == null || _selectedBarangay == null || _addressCtrl.text.trim().isEmpty) {
        _showMsg('Please complete your delivery location details.', false);
        return;
      }
    }

    final userId = await AuthService.getUserId();
    if (userId == null) return;

    setState(() => _loading = true);

    final res = await ApiService.post('/api/order/checkout', {
      'user_id': userId,
      'items': selectedItems
          .map((ci) => {'menu_item_id': ci['id'], 'quantity': ci['quantity']})
          .toList(),
      'notes': _notesCtrl.text.trim(),
      'dining_option': _diningOption,
      'payment_method': _paymentMethod,
      if (_diningOption == 'DELIVERY')
        'delivery_address': '${_addressCtrl.text.trim()}, Brgy. $_selectedBarangay, $_selectedMunicipality, Laguna. (Map Pin: ${_pinnedLocation!.latitude.toStringAsFixed(5)}, ${_pinnedLocation!.longitude.toStringAsFixed(5)})',
    });

    setState(() => _loading = false);

    if (res['success'] == true) {
      // Remove only the checked-out items, keep the rest
      CartScreen._cartItems.removeWhere((ci) => _selectedIds.contains(ci['id']));
      _selectedIds.clear();
      CartScreen.saveCart();
      
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
                      // Select All & Delete Selected Bar
                      Container(
                        margin: const EdgeInsets.only(bottom: 12),
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(12),
                          boxShadow: [
                            BoxShadow(color: Colors.black.withOpacity(0.04), blurRadius: 8),
                          ],
                        ),
                        child: Row(
                          children: [
                            SizedBox(
                              width: 24, height: 24,
                              child: Checkbox(
                                value: _selectAll,
                                activeColor: AppColors.primary,
                                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
                                onChanged: (v) {
                                  setState(() {
                                    _selectAll = v ?? false;
                                    if (_selectAll) {
                                      _selectedIds = CartScreen._cartItems.map((i) => i['id'] as int).toSet();
                                    } else {
                                      _selectedIds.clear();
                                    }
                                  });
                                },
                              ),
                            ),
                            const SizedBox(width: 8),
                            Text(
                              'Select All',
                              style: TextStyle(
                                fontWeight: FontWeight.w600,
                                fontSize: 14,
                                color: AppColors.primary,
                              ),
                            ),
                            const Spacer(),
                            if (_selectedIds.isNotEmpty)
                              TextButton.icon(
                                onPressed: () {
                                  showDialog(
                                    context: context,
                                    builder: (ctx) => AlertDialog(
                                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                                      title: const Text('Delete Selected'),
                                      content: Text('Remove ${_selectedIds.length} selected item(s) from cart?'),
                                      actions: [
                                        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
                                        TextButton(
                                          onPressed: () {
                                            setState(() {
                                              CartScreen._cartItems.removeWhere((i) => _selectedIds.contains(i['id']));
                                              _selectedIds.clear();
                                              _selectAll = false;
                                              CartScreen.saveCart();
                                            });
                                            Navigator.pop(ctx);
                                          },
                                          child: const Text('Delete', style: TextStyle(color: Colors.red)),
                                        ),
                                      ],
                                    ),
                                  );
                                },
                                icon: const Icon(Icons.delete_outline, size: 18, color: Colors.red),
                                label: const Text('Delete', style: TextStyle(color: Colors.red, fontWeight: FontWeight.w600, fontSize: 13)),
                              ),
                          ],
                        ),
                      ),
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
                                  'Pick-up',
                                  'TAKE_OUT',
                                  _diningOption,
                                  (v) => setState(() => _diningOption = v),
                                ),
                                _optionChip(
                                  'Delivery',
                                  'DELIVERY',
                                  _diningOption,
                                  (v) {
                                    setState(() => _diningOption = v);
                                    if (v == 'DELIVERY' && _pinnedLocation != null && _addressCtrl.text.isEmpty) {
                                      _checkLocation(_pinnedLocation!);
                                    }
                                  },
                                ),
                              ],
                            ),
                            if (_diningOption == 'DELIVERY') ...[
                              const SizedBox(height: 12),
                              const Text('Select Delivery Area', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                              const SizedBox(height: 8),
                              Row(
                                children: [
                                  Expanded(
                                    child: DropdownButtonFormField<String>(
                                      decoration: InputDecoration(
                                        labelText: 'Municipality',
                                        labelStyle: const TextStyle(fontSize: 12),
                                        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
                                      ),
                                      value: _selectedMunicipality,
                                      items: _locationData.keys.map((String value) {
                                        return DropdownMenuItem<String>(
                                          value: value,
                                          child: Text(value, style: const TextStyle(fontSize: 13)),
                                        );
                                      }).toList(),
                                      onChanged: (String? newValue) {
                                        setState(() {
                                          _selectedMunicipality = newValue;
                                          _selectedBarangay = null;
                                          if (newValue != null) {
                                            final latLng = _townCoordinates[newValue];
                                            if (latLng != null) {
                                              _pinnedLocation = latLng;
                                              _mapController.move(latLng, 14.0);
                                            }
                                          }
                                        });
                                      },
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: DropdownButtonFormField<String>(
                                      decoration: InputDecoration(
                                        labelText: 'Barangay',
                                        labelStyle: const TextStyle(fontSize: 12),
                                        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
                                      ),
                                      value: _selectedBarangay,
                                      items: _selectedMunicipality == null
                                          ? []
                                          : _locationData[_selectedMunicipality!]!.map((String value) {
                                              return DropdownMenuItem<String>(
                                                value: value,
                                                child: Text(value, style: const TextStyle(fontSize: 13)),
                                              );
                                            }).toList(),
                                      onChanged: _selectedMunicipality == null ? null : (String? newValue) {
                                        setState(() {
                                          _selectedBarangay = newValue;
                                        });
                                      },
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 12),
                              TextField(
                                controller: _addressCtrl,
                                maxLines: 2,
                                decoration: const InputDecoration(
                                  hintText: 'House No. / Street / Landmark',
                                  prefixIcon: Icon(Icons.location_on_outlined),
                                ),
                              ),
                              const SizedBox(height: 12),
                              const Text('Pin Exact Location on Map (Optional)', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                              const SizedBox(height: 8),
                              Container(
                                height: 200,
                                decoration: BoxDecoration(
                                  borderRadius: BorderRadius.circular(12),
                                  border: Border.all(color: Colors.grey.withOpacity(0.3)),
                                ),
                                child: ClipRRect(
                                  borderRadius: BorderRadius.circular(12),
                                  child: FlutterMap(
                                    mapController: _mapController,
                                    options: MapOptions(
                                      initialCenter: _pinnedLocation ?? const LatLng(14.2833, 121.4167),
                                      initialZoom: 13.0,
                                      onTap: (tapPosition, point) => _checkLocation(point),
                                    ),
                                    children: [
                                      TileLayer(
                                        urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                                        userAgentPackageName: 'com.lemaisonyelolane.app',
                                      ),
                                      if (_pinnedLocation != null)
                                        MarkerLayer(
                                          markers: [
                                            Marker(
                                              point: _pinnedLocation!,
                                              width: 40,
                                              height: 40,
                                              child: const Icon(Icons.location_on, color: Colors.blueAccent, size: 40),
                                            ),
                                          ],
                                        ),
                                    ],
                                  ),
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
                            '₱${_selectedTotal.toStringAsFixed(2)}',
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
          SizedBox(
            width: 24, height: 24,
            child: Checkbox(
              value: _selectedIds.contains(item['id']),
              activeColor: AppColors.primary,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
              onChanged: (v) {
                setState(() {
                  if (v == true) {
                    _selectedIds.add(item['id'] as int);
                  } else {
                    _selectedIds.remove(item['id'] as int);
                  }
                  _selectAll = _selectedIds.length == CartScreen._cartItems.length;
                });
              },
            ),
          ),
          const SizedBox(width: 8),
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
                    _selectedIds.remove(item['id'] as int);
                    _selectAll = _selectedIds.length == CartScreen._cartItems.length && CartScreen._cartItems.isNotEmpty;
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
