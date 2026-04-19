import 'package:flutter/material.dart';
import '../theme.dart';
import 'cart_screen.dart';

class MenuItemDetailScreen extends StatefulWidget {
  final dynamic item;

  const MenuItemDetailScreen({super.key, required this.item});

  @override
  State<MenuItemDetailScreen> createState() => _MenuItemDetailScreenState();
}

class _MenuItemDetailScreenState extends State<MenuItemDetailScreen> {
  int _quantity = 1;
  String _selectedSize = '380g';
  final Set<String> _selectedAddons = {'cheese', 'tomato', 'coriander'};

  void _toggleAddon(String addon) {
    setState(() {
      if (_selectedAddons.contains(addon)) {
        _selectedAddons.remove(addon);
      } else {
        _selectedAddons.add(addon);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        backgroundColor: Colors.white,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios, color: AppColors.textMain, size: 18),
          onPressed: () => Navigator.pop(context),
        ),
        title: Text(
          widget.item['category'] ?? 'Meal Category',
          style: const TextStyle(
            fontFamily: 'Inter',
            color: AppColors.textMain,
            fontWeight: FontWeight.bold,
            fontSize: 16,
          ),
        ),
        centerTitle: true,
        actions: [
          IconButton(
            icon: const Icon(Icons.sort, color: AppColors.primary),
            onPressed: () {},
          ),
        ],
      ),
      body: Stack(
        children: [
          SingleChildScrollView(
            padding: const EdgeInsets.only(bottom: 100),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Category Pills
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 20),
                  child: Row(
                    children: [
                      _buildCatPill('Pasta', true),
                      const SizedBox(width: 10),
                      _buildCatPill('Salad', false),
                      const SizedBox(width: 10),
                      _buildCatPill('Seafood', false),
                      const SizedBox(width: 10),
                      _buildCatPill('Soups', false),
                    ],
                  ),
                ),
                const SizedBox(height: 30),

                // Hero Image with Favorite button
                Center(
                  child: Stack(
                    alignment: Alignment.center,
                    clipBehavior: Clip.none,
                    children: [
                      Container(
                        width: 250,
                        height: 250,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          boxShadow: [
                            BoxShadow(
                              color: Colors.black.withOpacity(0.1),
                              blurRadius: 40,
                              spreadRadius: 10,
                              offset: const Offset(0, 20),
                            ),
                          ],
                        ),
                        child: ClipOval(
                          child: widget.item['image_url'] != null
                              ? Image.network(
                                  widget.item['image_url'],
                                  fit: BoxFit.cover,
                                  errorBuilder: (_, __, ___) => _fallbackImage(),
                                )
                              : _fallbackImage(),
                        ),
                      ),
                      Positioned(
                        top: -10,
                        right: -40,
                        child: IconButton(
                          icon: const Icon(Icons.favorite_outline, color: Colors.red, size: 28),
                          onPressed: () {},
                        ),
                      ),
                      Positioned(
                        top: 100,
                        left: -50,
                        child: IconButton(
                          icon: const Icon(Icons.arrow_back_ios, color: Colors.grey, size: 24),
                          onPressed: () {},
                        ),
                      ),
                    ],
                  ),
                ),

                const SizedBox(height: 40),

                // Title and Description
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        widget.item['name'] ?? 'Rotini Delight',
                        style: const TextStyle(
                          fontFamily: 'Inter',
                          fontSize: 26,
                          fontWeight: FontWeight.w800,
                          color: AppColors.textMain,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        widget.item['description'] ??
                            'A vibrant and flavorful pasta dish made with rotini, sun-dried tomatoes, and a rich tomato-based sauce.',
                        style: const TextStyle(
                          fontFamily: 'Inter',
                          fontSize: 13,
                          color: AppColors.textMuted,
                          height: 1.5,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 24),

                // SIZE
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'SIZE',
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.bold,
                          color: AppColors.textMuted,
                          letterSpacing: 1,
                        ),
                      ),
                      const SizedBox(height: 12),
                      Row(
                        children: [
                          _buildSizePill('380g'),
                          const SizedBox(width: 10),
                          _buildSizePill('480g'),
                          const SizedBox(width: 10),
                          _buildSizePill('560g'),
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 24),

                // BUILD YOUR MEAL
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'BUILD YOUR MEAL',
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.bold,
                          color: AppColors.textMuted,
                          letterSpacing: 1,
                        ),
                      ),
                      const SizedBox(height: 12),
                      Row(
                        children: [
                          _buildAddonOption('cheese', Icons.water_drop, Colors.orange),
                          const SizedBox(width: 8),
                          _buildAddonOption('tomato', Icons.apple, Colors.red),
                          const SizedBox(width: 8),
                          _buildAddonOption('coriander', Icons.eco, Colors.green),
                          const SizedBox(width: 8),
                          _buildAddonOption('pepper', Icons.local_fire_department, Colors.redAccent),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),

          // BOTTOM BAR
          Positioned(
            bottom: 0,
            left: 0,
            right: 0,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: const BorderRadius.only(
                  topLeft: Radius.circular(30),
                  topRight: Radius.circular(30),
                ),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withOpacity(0.05),
                    blurRadius: 20,
                    offset: const Offset(0, -5),
                  )
                ],
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    '₱${((widget.item['price'] ?? 4.50) * _quantity).toStringAsFixed(2)}',
                    style: const TextStyle(
                      fontFamily: 'Inter',
                      fontSize: 24,
                      fontWeight: FontWeight.w900,
                      color: AppColors.textMain,
                    ),
                  ),
                  Row(
                    children: [
                      Container(
                        decoration: BoxDecoration(
                          color: AppColors.textMain,
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: Row(
                          children: [
                            IconButton(
                              icon: const Icon(Icons.remove, color: Colors.white, size: 16),
                              onPressed: () {
                                if (_quantity > 1) {
                                  setState(() => _quantity--);
                                }
                              },
                              constraints: const BoxConstraints(minWidth: 35, minHeight: 35),
                              padding: EdgeInsets.zero,
                            ),
                            Text(
                              '$_quantity',
                              style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 13),
                            ),
                            IconButton(
                              icon: const Icon(Icons.add, color: Colors.white, size: 16),
                              onPressed: () {
                                setState(() => _quantity++);
                              },
                              constraints: const BoxConstraints(minWidth: 35, minHeight: 35),
                              padding: EdgeInsets.zero,
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 15),
                      ElevatedButton(
                        onPressed: () {
                          // Add to cart with specific quantity
                          Map<String, dynamic> itemToAdd = Map.from(widget.item);
                          itemToAdd['quantity'] = _quantity;
                          
                          // Handle existing item logic manually since CartScreen uses a quantity increaser
                          bool exists = false;
                          for (var cartItem in CartScreen.items) {
                            if (cartItem['id'] == widget.item['id']) {
                              cartItem['quantity'] += _quantity;
                              exists = true;
                              break;
                            }
                          }
                          if (!exists) {
                           CartScreen.items.add({
                              'id': widget.item['id'],
                              'name': widget.item['name'],
                              'price': widget.item['price'],
                              'image_url': widget.item['image_url'],
                              'category': widget.item['category'],
                              'quantity': _quantity,
                            });
                          }
                          CartScreen.saveCart();

                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(content: Text('${widget.item['name']} added to cart!', style: const TextStyle(color: Colors.white)), backgroundColor: AppColors.primary),
                          );
                          Navigator.pop(context);
                        },
                        style: ElevatedButton.styleFrom(
                          backgroundColor: AppColors.primary,
                          elevation: 0,
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
                          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                        ),
                        child: const Text('Add to order', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          )
        ],
      ),
    );
  }

  Widget _buildCatPill(String name, bool isActive) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        color: isActive ? AppColors.textMain : Colors.transparent,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        name,
        style: TextStyle(
          color: isActive ? Colors.white : AppColors.textMuted,
          fontWeight: isActive ? FontWeight.bold : FontWeight.normal,
          fontSize: 13,
        ),
      ),
    );
  }

  Widget _buildSizePill(String size) {
    bool isSel = _selectedSize == size;
    return GestureDetector(
      onTap: () => setState(() => _selectedSize = size),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
        decoration: BoxDecoration(
          color: isSel ? AppColors.textMain : Colors.white,
          borderRadius: BorderRadius.circular(20),
          border: isSel ? null : Border.all(color: Colors.grey.shade300),
          boxShadow: isSel ? [
            BoxShadow(color: AppColors.textMain.withOpacity(0.3), blurRadius: 8, offset: const Offset(0, 4))
          ] : [],
        ),
        child: Text(
          size,
          style: TextStyle(
            color: isSel ? Colors.white : AppColors.textMain,
            fontWeight: FontWeight.bold,
            fontSize: 12,
          ),
        ),
      ),
    );
  }

  Widget _buildAddonOption(String id, IconData icon, Color color) {
    bool isSel = _selectedAddons.contains(id);
    return GestureDetector(
      onTap: () => _toggleAddon(id),
      child: Stack(
        alignment: Alignment.center,
        clipBehavior: Clip.none,
        children: [
          Container(
            width: 55,
            height: 55,
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(15),
              border: Border.all(color: Colors.grey.shade200),
              boxShadow: isSel ? [
                BoxShadow(color: Colors.black.withOpacity(0.05), blurRadius: 10, offset: const Offset(0, 5))
              ] : [],
            ),
            child: Icon(icon, color: color, size: 28),
          ),
          if (isSel)
            Positioned(
              bottom: -5,
              child: Container(
                padding: const EdgeInsets.all(2),
                decoration: const BoxDecoration(color: AppColors.textMain, shape: BoxShape.circle),
                child: const Icon(Icons.check, color: Colors.white, size: 12),
              ),
            ),
        ],
      ),
    );
  }

  Widget _fallbackImage() {
    return Container(
      color: AppColors.primary.withOpacity(0.1),
      child: const Icon(Icons.restaurant, size: 80, color: AppColors.primary),
    );
  }
}
