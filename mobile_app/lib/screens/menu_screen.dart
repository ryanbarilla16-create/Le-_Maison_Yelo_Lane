import 'package:flutter/material.dart';
import '../theme.dart';
import '../services/api_service.dart';
import 'cart_screen.dart';

class MenuScreen extends StatefulWidget {
  const MenuScreen({super.key});

  @override
  State<MenuScreen> createState() => _MenuScreenState();
}

class _MenuScreenState extends State<MenuScreen> {
  List<dynamic> _categories = [];
  List<dynamic> _allItems = [];
  String? _selectedCategory;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadMenu();
  }

  Future<void> _loadMenu() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final results = await Future.wait([
        ApiService.get('/api/menu/categories'),
        ApiService.get('/api/menu'),
      ]);

      if (!mounted) return;

      final cats = results[0];
      final items = results[1];

      if (cats == null && items == null) {
        setState(() {
          _error =
              'Could not connect to server.\nMake sure Flask is running and your device is on the same network.';
          _loading = false;
        });
        return;
      }

      setState(() {
        _categories = cats is List ? cats : [];
        _allItems = items is List ? items : [];
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = 'Connection error: $e';
        _loading = false;
      });
    }
  }

  List<dynamic> get _filteredItems {
    if (_selectedCategory == null) return _allItems;
    return _allItems.where((i) => i['category'] == _selectedCategory).toList();
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
      return _buildErrorView();
    }

    // If a category is selected, show items in grid
    if (_selectedCategory != null) {
      return _buildItemsView();
    }

    // Show categories
    return _buildCategoriesView();
  }

  Widget _buildErrorView() {
    return Center(
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
                Icons.wifi_off_rounded,
                color: AppColors.danger,
                size: 48,
              ),
            ),
            const SizedBox(height: 20),
            Text(
              'Menu Unavailable',
              style: AppTextStyles.heading.copyWith(fontSize: 20),
            ),
            const SizedBox(height: 8),
            Text(
              _error!,
              textAlign: TextAlign.center,
              style: AppTextStyles.muted.copyWith(fontSize: 13),
            ),
            const SizedBox(height: 24),
            SizedBox(
              width: 160,
              child: GradientButton(
                label: 'Try Again',
                icon: Icons.refresh_rounded,
                onPressed: _loadMenu,
                height: 48,
                radius: 12,
              ),
            ),

          ],
        ),
      ),
    );
  }

  Widget _buildCategoriesView() {
    if (_categories.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.restaurant_menu,
              color: AppColors.primary.withOpacity(0.2),
              size: 60,
            ),
            const SizedBox(height: 16),
            Text('No menu categories found', style: AppTextStyles.muted),
            const SizedBox(height: 16),
            SizedBox(
              width: 140,
              child: GradientButton(
                label: 'Refresh',
                icon: Icons.refresh_rounded,
                onPressed: _loadMenu,
                height: 44,
                radius: 12,
              ),
            ),

          ],
        ),
      );
    }

    return RefreshIndicator(
      color: AppColors.primary,
      onRefresh: _loadMenu,
      child: CustomScrollView(
        slivers: [
          SliverAppBar(
            floating: true,
            backgroundColor: Colors.white,
            elevation: 0.5,
            title: Text(
              'Menu',
              style: AppTextStyles.heading.copyWith(fontSize: 20),
            ),
            centerTitle: true,
            actions: [
              IconButton(
                icon: Stack(
                  clipBehavior: Clip.none,
                  children: [
                    const Icon(
                      Icons.shopping_cart_outlined,
                      color: AppColors.primary,
                    ),
                    if (CartScreen.count > 0)
                      Positioned(
                        right: -4,
                        top: -4,
                        child: Container(
                          padding: const EdgeInsets.all(4),
                          decoration: const BoxDecoration(
                            color: Colors.red,
                            shape: BoxShape.circle,
                          ),
                          child: Text(
                            '${CartScreen.count}',
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 10,
                              fontWeight: FontWeight.bold,
                            ),
                            textAlign: TextAlign.center,
                          ),
                        ),
                      ),
                  ],
                ),
                onPressed: () {
                  Navigator.push(
                    context,
                    MaterialPageRoute(builder: (_) => const CartScreen()),
                  ).then((_) => setState(() {}));
                },
              ),
            ],
          ),
          SliverPadding(
            padding: const EdgeInsets.all(16),
            sliver: SliverGrid(
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 2,
                childAspectRatio: 1.1,
                crossAxisSpacing: 12,
                mainAxisSpacing: 12,
              ),
              delegate: SliverChildBuilderDelegate((context, index) {
                final cat = _categories[index];
                return _categoryCard(cat);
              }, childCount: _categories.length),
            ),
          ),
        ],
      ),
    );
  }

  Widget _categoryCard(dynamic cat) {
    return GestureDetector(
      onTap: () => setState(() => _selectedCategory = cat['category']),
      child: Container(
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(14),
          boxShadow: [
            BoxShadow(color: Colors.black.withOpacity(0.04), blurRadius: 10),
          ],
          border: Border.all(color: AppColors.primary.withOpacity(0.06)),
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (cat['sample_image'] != null)
              ClipRRect(
                borderRadius: BorderRadius.circular(10),
                child: Image.network(
                  cat['sample_image'],
                  height: 70,
                  width: 90,
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => Container(
                    height: 70,
                    width: 90,
                    decoration: BoxDecoration(
                      color: AppColors.primary.withOpacity(0.1),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: const Icon(
                      Icons.restaurant,
                      color: AppColors.primary,
                    ),
                  ),
                ),
              )
            else
              Container(
                height: 70,
                width: 90,
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    colors: [AppColors.primary, AppColors.primaryLight],
                  ),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Icon(
                  Icons.restaurant,
                  color: Colors.white54,
                  size: 30,
                ),
              ),
            const SizedBox(height: 10),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8),
              child: Text(
                cat['category'] ?? '',
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontFamily: 'Georgia',
                  fontWeight: FontWeight.w700,
                  fontSize: 12,
                  color: AppColors.textMain,
                ),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  'See More',
                  style: AppTextStyles.muted.copyWith(
                    fontSize: 10,
                    color: AppColors.primary,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(width: 4),
                const Icon(
                  Icons.arrow_forward_ios,
                  size: 8,
                  color: AppColors.primary,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildItemsView() {
    return CustomScrollView(
      slivers: [
        SliverAppBar(
          floating: true,
          backgroundColor: Colors.white,
          elevation: 0.5,
          leading: IconButton(
            icon: const Icon(Icons.arrow_back, color: AppColors.primary),
            onPressed: () => setState(() => _selectedCategory = null),
          ),
          title: Text(
            _selectedCategory ?? 'Menu',
            style: AppTextStyles.heading.copyWith(fontSize: 18),
          ),
          centerTitle: true,
          actions: [
            IconButton(
              icon: Stack(
                clipBehavior: Clip.none,
                children: [
                  const Icon(
                    Icons.shopping_cart_outlined,
                    color: AppColors.primary,
                  ),
                  if (CartScreen.count > 0)
                    Positioned(
                      right: -4,
                      top: -4,
                      child: Container(
                        padding: const EdgeInsets.all(4),
                        decoration: const BoxDecoration(
                          color: Colors.red,
                          shape: BoxShape.circle,
                        ),
                        child: Text(
                          '${CartScreen.count}',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 10,
                            fontWeight: FontWeight.bold,
                          ),
                          textAlign: TextAlign.center,
                        ),
                      ),
                    ),
                ],
              ),
              onPressed: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => const CartScreen()),
                ).then((_) => setState(() {}));
              },
            ),
          ],
        ),
        if (_filteredItems.isEmpty)
          SliverFillRemaining(
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    Icons.restaurant,
                    color: AppColors.primary.withOpacity(0.2),
                    size: 48,
                  ),
                  const SizedBox(height: 12),
                  Text('No items in this category', style: AppTextStyles.muted),
                ],
              ),
            ),
          )
        else
          SliverPadding(
            padding: const EdgeInsets.all(16),
            sliver: SliverList(
              delegate: SliverChildBuilderDelegate((context, index) {
                final item = _filteredItems[index];
                return _menuItemCard(item);
              }, childCount: _filteredItems.length),
            ),
          ),
      ],
    );
  }

  Widget _menuItemCard(dynamic item) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        boxShadow: [
          BoxShadow(color: Colors.black.withOpacity(0.04), blurRadius: 10),
        ],
      ),
      child: Row(
        children: [
          // Image
          Stack(
            children: [
              ClipRRect(
                borderRadius: const BorderRadius.horizontal(
                  left: Radius.circular(14),
                ),
                child: ColorFiltered(
                  colorFilter: ColorFilter.mode(
                    item['is_out_of_stock'] == true ? Colors.grey : Colors.transparent,
                    BlendMode.saturation,
                  ),
                  child: item['image_url'] != null
                      ? Image.network(
                          item['image_url'],
                          width: 110,
                          height: 110,
                          fit: BoxFit.cover,
                          errorBuilder: (_, __, ___) => Container(
                            width: 110,
                            height: 110,
                            color: AppColors.primary.withOpacity(0.1),
                            child: const Icon(
                              Icons.restaurant,
                              color: AppColors.primary,
                              size: 30,
                            ),
                          ),
                        )
                      : Container(
                          width: 110,
                          height: 110,
                          decoration: const BoxDecoration(
                            gradient: LinearGradient(
                              colors: [AppColors.primary, AppColors.primaryLight],
                            ),
                          ),
                          child: const Icon(
                            Icons.restaurant,
                            color: Colors.white54,
                            size: 30,
                          ),
                        ),
                ),
              ),
              if (item['is_out_of_stock'] == true)
                Positioned.fill(
                  child: Container(
                    decoration: BoxDecoration(
                      color: Colors.black.withOpacity(0.2),
                      borderRadius: const BorderRadius.horizontal(
                        left: Radius.circular(14),
                      ),
                    ),
                    child: Center(
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          color: AppColors.danger,
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: const Text(
                          'OUT OF STOCK',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 8,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
            ],
          ),
          // Details
          Expanded(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    item['name'] ?? '',
                    style: TextStyle(
                      fontFamily: 'Georgia',
                      fontWeight: FontWeight.w700,
                      fontSize: 14,
                      color: AppColors.textMain,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 4),
                  if (item['description'] != null && item['description'] != '')
                    Text(
                      item['description'],
                      style: AppTextStyles.muted.copyWith(fontSize: 11),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  const SizedBox(height: 8),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        '₱${item['price']?.toStringAsFixed(2) ?? ''}',
                        style: TextStyle(
                          fontWeight: FontWeight.w800,
                          color: AppColors.primary,
                          fontSize: 16,
                        ),
                      ),
                      // Add to Cart button
                      GestureDetector(
                        onTap: item['is_out_of_stock'] == true ? null : () => _addToCart(item),
                        child: DecoratedBox(
                          decoration: BoxDecoration(
                            gradient: item['is_out_of_stock'] == true
                                ? null
                                : AppColors.buttonGradient,
                            color: item['is_out_of_stock'] == true ? Colors.grey[200] : null,
                            borderRadius: BorderRadius.circular(10),
                            boxShadow: item['is_out_of_stock'] == true ? [] : [
                              BoxShadow(
                                color: AppColors.primary.withOpacity(0.25),
                                blurRadius: 6,
                                offset: const Offset(0, 3),
                              )
                            ],
                          ),
                          child: SizedBox(
                            height: 34,
                            child: Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 12),
                              child: Center(
                                child: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Icon(
                                      item['is_out_of_stock'] == true
                                          ? Icons.block
                                          : Icons.add_shopping_cart_rounded,
                                      color: item['is_out_of_stock'] == true
                                          ? Colors.grey[500]
                                          : Colors.white,
                                      size: 14,
                                    ),
                                    const SizedBox(width: 5),
                                    Text(
                                      item['is_out_of_stock'] == true ? 'Unavailable' : 'Add to Cart',
                                      style: TextStyle(
                                        color: item['is_out_of_stock'] == true
                                            ? Colors.grey[500]
                                            : Colors.white,
                                        fontWeight: FontWeight.bold,
                                        fontSize: 11,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        ),
                      ),

                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
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


