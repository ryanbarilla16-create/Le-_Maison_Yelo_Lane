import 'package:flutter/material.dart';
import '../theme.dart';
import '../services/api_service.dart';
import 'reserve_checkout_screen.dart';

class ReserveMenuScreen extends StatefulWidget {
  final Map<String, dynamic> reservationData;

  const ReserveMenuScreen({super.key, required this.reservationData});

  @override
  State<ReserveMenuScreen> createState() => _ReserveMenuScreenState();
}

class _ReserveMenuScreenState extends State<ReserveMenuScreen> {
  List<dynamic> _menuItems = [];
  Map<int, int> _cart = {}; // itemId -> quantity
  bool _loading = true;
  String _searchQuery = '';
  String? _selectedCategory;
  List<String> _categories = ['All'];

  @override
  void initState() {
    super.initState();
    _fetchMenu();
  }

  Future<void> _fetchMenu() async {
    final res = await ApiService.get('/api/menu');
    final catsRes = await ApiService.get('/api/menu/categories');
    if (res != null && res is List) {
      setState(() {
        _menuItems = res;
        _loading = false;
      });
    }
    if (catsRes != null && catsRes is List) {
      setState(() {
        _categories = ['All', ...catsRes.map((e) => e['category'].toString())];
      });
    }
  }

  double get _totalPrice {
    double total = 0;
    for (var entry in _cart.entries) {
      final item = _menuItems.firstWhere((element) => element['id'] == entry.key);
      total += (item['price'] as num).toDouble() * entry.value;
    }
    return total;
  }

  void _updateQty(int id, int delta) {
    setState(() {
      final current = _cart[id] ?? 0;
      final next = current + delta;
      if (next <= 0) {
        _cart.remove(id);
      } else {
        _cart[id] = next;
      }
    });
  }

  void _goToCheckout() {
    if (_cart.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please select at least one item or go back.')),
      );
      return;
    }

    // Format selected items for checkout
    final itemsList = _cart.entries.map((e) {
      final item = _menuItems.firstWhere((element) => element['id'] == e.key);
      return {
        'id': e.key,
        'qty': e.value,
        'name': item['name'],
        'price': (item['price'] as num).toDouble(),
        'image_url': item['image_url'],
      };
    }).toList();

    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => ReserveCheckoutScreen(
          reservationData: widget.reservationData,
          selectedItems: itemsList,
          totalPrice: _totalPrice,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final filtered = _menuItems.where((item) {
      final matchesSearch = item['name'].toString().toLowerCase().contains(_searchQuery.toLowerCase());
      final matchesCat = _selectedCategory == null || _selectedCategory == 'All' || item['category'] == _selectedCategory;
      return matchesSearch && matchesCat;
    }).toList();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Step 2: Pre-order Food'),
        centerTitle: true,
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: AppColors.primary))
          : Column(
              children: [
                // Header Policy
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(12),
                  color: AppColors.primary.withOpacity(0.05),
                  child: const Row(
                    children: [
                      Icon(Icons.info_outline, size: 18, color: AppColors.primary),
                      SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'Payment First Policy: Select your food to confirm your booking.',
                          style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: AppColors.primary),
                        ),
                      ),
                    ],
                  ),
                ),
                // Search & Filter
                Padding(
                  padding: const EdgeInsets.all(12),
                  child: Row(
                    children: [
                      Expanded(
                        child: TextField(
                          decoration: InputDecoration(
                            hintText: 'Search menu...',
                            prefixIcon: const Icon(Icons.search),
                            contentPadding: const EdgeInsets.symmetric(vertical: 0, horizontal: 16),
                            fillColor: Colors.grey.shade100,
                          ),
                          onChanged: (v) => setState(() => _searchQuery = v),
                        ),
                      ),
                      const SizedBox(width: 8),
                      DropdownButton<String>(
                        value: _selectedCategory ?? 'All',
                        onChanged: (v) => setState(() => _selectedCategory = v),
                        items: _categories.map((c) => DropdownMenuItem(value: c, child: Text(c, style: const TextStyle(fontSize: 12)))).toList(),
                      ),
                    ],
                  ),
                ),
                // Menu List
                Expanded(
                  child: ListView.builder(
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    itemCount: filtered.length,
                    itemBuilder: (context, index) {
                      final item = filtered[index];
                      final qty = _cart[item['id']] ?? 0;
                      return Card(
                        margin: const EdgeInsets.only(bottom: 10),
                        elevation: 0,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                          side: BorderSide(color: Colors.grey.shade200),
                        ),
                        child: Padding(
                          padding: const EdgeInsets.all(8),
                          child: Row(
                            children: [
                              ClipRRect(
                                borderRadius: BorderRadius.circular(8),
                                child: Image.network(
                                  item['image_url'] ?? 'https://via.placeholder.com/100',
                                  width: 60,
                                  height: 60,
                                  fit: BoxFit.cover,
                                  errorBuilder: (c, e, s) => Container(color: Colors.grey.shade200, width: 60, height: 60, child: const Icon(Icons.fastfood, color: Colors.grey)),
                                ),
                              ),
                              const SizedBox(width: 12),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(item['name'], style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                                    Text('₱${item['price']}', style: const TextStyle(color: AppColors.primary, fontWeight: FontWeight.bold)),
                                  ],
                                ),
                              ),
                              Row(
                                children: [
                                  IconButton(
                                    icon: const Icon(Icons.remove_circle_outline, color: AppColors.primary),
                                    onPressed: () => _updateQty(item['id'], -1),
                                  ),
                                  Text('$qty', style: const TextStyle(fontWeight: FontWeight.bold)),
                                  IconButton(
                                    icon: const Icon(Icons.add_circle, color: AppColors.primary),
                                    onPressed: () => _updateQty(item['id'], 1),
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
                ),
                // Bottom Summary
                Container(
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.05), blurRadius: 10, offset: const Offset(0, -5))],
                  ),
                  child: SafeArea(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            const Text('Selected Items Header', style: TextStyle(fontWeight: FontWeight.bold)),
                            Text('Total: ₱${_totalPrice.toStringAsFixed(2)}', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: AppColors.primary)),
                          ],
                        ),
                        const SizedBox(height: 12),
                        GradientButton(
                          label: 'Proceed to Summary',
                          icon: Icons.arrow_forward_rounded,
                          onPressed: _cart.isEmpty ? null : _goToCheckout,
                          height: 52,
                          radius: 14,
                        ),

                      ],
                    ),
                  ),
                ),
              ],
            ),
    );
  }
}
