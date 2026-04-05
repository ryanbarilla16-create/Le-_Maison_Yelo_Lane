import 'package:flutter/material.dart';
import '../theme.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';
import 'xendit_sandbox_screen.dart';

class ReserveCheckoutScreen extends StatefulWidget {
  final Map<String, dynamic> reservationData;
  final List<Map<String, dynamic>> selectedItems;
  final double totalPrice;

  const ReserveCheckoutScreen({
    super.key,
    required this.reservationData,
    required this.selectedItems,
    required this.totalPrice,
  });

  @override
  State<ReserveCheckoutScreen> createState() => _ReserveCheckoutScreenState();
}

class _ReserveCheckoutScreenState extends State<ReserveCheckoutScreen> {
  bool _submitting = false;

  Future<void> _submitReservation() async {
    setState(() => _submitting = true);
    final uid = await AuthService.getUserId();
    
    // Format items for the API: [{'id': 1, 'qty': 2}, ...]
    final itemsList = widget.selectedItems.map((e) => {
      'id': e['id'],
      'qty': e['qty'],
    }).toList();
    
    final payload = {
      ...widget.reservationData,
      'user_id': uid,
      'menu_items': itemsList,
    };

    final res = await ApiService.post('/api/reserve', payload);
    setState(() => _submitting = false);

    if (res['success'] == true) {
      if (res['invoice_url'] != null) {
        // Redirect to Xendit payment screen
        if (!mounted) return;
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(
            builder: (context) => XenditSandboxScreen(
              url: res['invoice_url'],
            ),
          ),
        );
      } else {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Reservation submitted successfully!'),
            backgroundColor: AppColors.success,
          ),
        );
        // Pop all the way back to home
        Navigator.of(context).popUntil((route) => route.isFirst);
      }
    } else {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(res['message'] ?? 'Failed to submit reservation.'),
          backgroundColor: AppColors.danger,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Step 3: Summary & Payment'),
        centerTitle: true,
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView(
              padding: const EdgeInsets.all(20),
              children: [
                const Text(
                  'Review Your Reservation',
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                    color: AppColors.textMain,
                  ),
                ),
                const SizedBox(height: 16),
                
                // Reservation Details Card
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(14),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withOpacity(0.04),
                        blurRadius: 10,
                      )
                    ],
                    border: Border.all(color: Colors.grey.shade100),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _detailRow(Icons.calendar_today, 'Date', widget.reservationData['date']),
                      _detailRow(Icons.access_time, 'Time', widget.reservationData['time']),
                      _detailRow(Icons.people, 'Guests', '${widget.reservationData['guest_count']} person(s)'),
                      if (widget.reservationData['occasion'] != null && widget.reservationData['occasion'].toString().isNotEmpty)
                        _detailRow(Icons.star, 'Occasion', widget.reservationData['occasion']),
                    ],
                  ),
                ),
                const SizedBox(height: 24),
                
                const Text(
                  'Pre-ordered Food',
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                    color: AppColors.textMain,
                  ),
                ),
                const SizedBox(height: 16),
                
                // Items List
                ...widget.selectedItems.map((item) => Container(
                  margin: const EdgeInsets.only(bottom: 12),
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(12),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withOpacity(0.03),
                        blurRadius: 8,
                      )
                    ],
                  ),
                  child: Row(
                    children: [
                      Container(
                        width: 50,
                        height: 50,
                        decoration: BoxDecoration(
                          color: Colors.grey.shade100,
                          borderRadius: BorderRadius.circular(8),
                          image: item['image_url'] != null
                              ? DecorationImage(
                                  image: NetworkImage(item['image_url']),
                                  fit: BoxFit.cover,
                                )
                              : null,
                        ),
                        child: item['image_url'] == null
                            ? const Icon(Icons.fastfood, color: Colors.grey, size: 20)
                            : null,
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              item['name'],
                              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                            ),
                            Text(
                              '${item['qty']}x',
                              style: TextStyle(color: Colors.grey[600], fontSize: 13),
                            ),
                          ],
                        ),
                      ),
                      Text(
                        '₱${((item['price'] as num) * item['qty']).toStringAsFixed(2)}',
                        style: const TextStyle(
                          fontWeight: FontWeight.w800,
                          color: AppColors.accent,
                          fontFamily: 'Georgia',
                          fontSize: 14,
                        ),
                      ),
                    ],
                  ),
                )),
              ],
            ),
          ),
          
          // Bottom Payment Bar
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: Colors.white,
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withOpacity(0.05),
                  blurRadius: 10,
                  offset: const Offset(0, -5),
                ),
              ],
            ),
            child: SafeArea(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Total Amount', style: AppTextStyles.muted),
                          Text(
                            '(incl. taxes)',
                            style: TextStyle(fontSize: 10, color: Colors.grey),
                          ),
                        ],
                      ),
                      Text(
                        '₱${widget.totalPrice.toStringAsFixed(2)}',
                        style: const TextStyle(
                          fontSize: 24,
                          fontWeight: FontWeight.w900,
                          color: AppColors.accent,
                          fontFamily: 'Georgia',
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 20),
                  GradientButton(
                    label: 'Pay via GCash (Xendit)',
                    icon: Icons.payment_rounded,
                    onPressed: _submitting ? null : _submitReservation,
                    isLoading: _submitting,
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

  Widget _detailRow(IconData icon, String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        children: [
          Icon(icon, size: 18, color: AppColors.primary),
          const SizedBox(width: 12),
          Text(
            '$label:',
            style: TextStyle(color: Colors.grey[600], fontSize: 13),
          ),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: AppColors.textMain),
            ),
          ),
        ],
      ),
    );
  }
}
