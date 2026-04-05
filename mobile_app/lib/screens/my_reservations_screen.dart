import 'package:flutter/material.dart';
import '../theme.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';

class MyReservationsScreen extends StatefulWidget {
  const MyReservationsScreen({super.key});

  @override
  State<MyReservationsScreen> createState() => _MyReservationsScreenState();
}

class _MyReservationsScreenState extends State<MyReservationsScreen> with SingleTickerProviderStateMixin {
  late TabController _tabController;
  bool _loading = true;
  List<dynamic> _upcoming = [];
  List<dynamic> _past = [];

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
    _loadData();
  }

  Future<void> _loadData() async {
    setState(() => _loading = true);
    final uid = await AuthService.getUserId();
    if (uid == null) return;
    
    final res = await ApiService.get('/api/user/$uid/reservations');
    if (res != null && mounted) {
      setState(() {
        _upcoming = res['upcoming'] ?? [];
        _past = res['past'] ?? [];
        _loading = false;
      });
    } else if (mounted) {
      setState(() => _loading = false);
    }
  }

  void _msg(String m, bool ok) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(m),
        backgroundColor: ok ? AppColors.success : AppColors.danger,
      ),
    );
  }

  Future<void> _cancelReservation(dynamic r) async {
    String selectedReason = 'Change of plans';
    final otherReasonCtrl = TextEditingController();

    final result = await showDialog<bool>(
      context: context,
      builder: (context) {
        return StatefulBuilder(
          builder: (context, setDialogState) {
            return AlertDialog(
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
              title: const Text('Cancel Reservation', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 18)),
              content: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Text('Are you sure you want to cancel this reservation?', style: TextStyle(fontSize: 14)),
                  const SizedBox(height: 16),
                  DropdownButtonFormField<String>(
                    value: selectedReason,
                    items: [
                      'Change of plans',
                      'Emergency at home/work',
                      'Traffic or transportation issues',
                      'Found another venue',
                      'Others'
                    ].map((String value) {
                      return DropdownMenuItem<String>(
                        value: value,
                        child: Text(value, style: const TextStyle(fontSize: 14)),
                      );
                    }).toList(),
                    onChanged: (val) {
                      setDialogState(() => selectedReason = val!);
                    },
                    decoration: const InputDecoration(labelText: 'Reason for Cancellation', border: OutlineInputBorder()),
                  ),
                  if (selectedReason == 'Others') ...[
                    const SizedBox(height: 12),
                    TextField(
                      controller: otherReasonCtrl,
                      maxLines: 2,
                      decoration: const InputDecoration(labelText: 'Please specify', border: OutlineInputBorder()),
                    )
                  ]
                ],
              ),
              actions: [
                TextButton(child: const Text('Keep it', style: TextStyle(color: Colors.grey)), onPressed: () => Navigator.pop(context, false)),
                TextButton(
                  child: const Text('Cancel Booking', style: TextStyle(color: AppColors.danger, fontWeight: FontWeight.bold)),
                  onPressed: () {
                    if (selectedReason == 'Others' && otherReasonCtrl.text.trim().isEmpty) return;
                    Navigator.pop(context, true);
                  },
                ),
              ],
            );
          }
        );
      }
    );

    if (result == true) {
      final uid = await AuthService.getUserId();
      final reason = selectedReason == 'Others' ? otherReasonCtrl.text.trim() : selectedReason;
      
      if (!mounted) return;
      showDialog(context: context, barrierDismissible: false, builder: (_) => const Center(child: CircularProgressIndicator()));
      
      final res = await ApiService.post('/api/reserve/cancel', {
        'user_id': uid,
        'reservation_id': r['id'],
        'reason': reason,
      });
      
      if (!mounted) return;
      Navigator.pop(context); // close loader
      
      if (res['success'] == true) {
        _msg('Reservation cancelled successfully.', true);
        _loadData();
      } else {
        _msg(res['message'] ?? 'Failed to cancel reservation.', false);
      }
    }
  }

  void _showReservationDetails(Map r) {
    final order = r['linked_order'];
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => Container(
        height: MediaQuery.of(context).size.height * 0.8,
        decoration: const BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: Column(
          children: [
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: AppColors.primary.withOpacity(0.05),
                borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
              ),
              child: Column(
                children: [
                  Container(
                    width: 40,
                    height: 4,
                    decoration: BoxDecoration(color: Colors.grey[300], borderRadius: BorderRadius.circular(2)),
                  ),
                  const SizedBox(height: 20),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text('Reservation Detail', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: Color(0xFF3E2723))),
                          Text('Reference ID: #${r['id']}', style: TextStyle(fontSize: 12, color: Colors.grey[600])),
                        ],
                      ),
                      _badge(r['status']),
                    ],
                  ),
                ],
              ),
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.all(24),
                children: [
                  _detailRow(Icons.calendar_today_rounded, 'Date & Time', '${r['date_formatted']} at ${r['time_formatted']}'),
                  _detailRow(Icons.people_outline_rounded, 'Guests', '${r['guest_count']} person(s)'),
                  _detailRow(Icons.star_outline_rounded, 'Occasion', r['occasion'] ?? 'None'),
                  if (r['cancellation_reason'] != null)
                    _detailRow(Icons.cancel, 'Cancellation Reason', r['cancellation_reason']),
                  if (order != null) ...[
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 20),
                      child: Divider(height: 1, thickness: 1.5, color: Color(0xFFF1F1F1)),
                    ),
                    const Text('Pre-ordered items', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Color(0xFF5D4037))),
                    const SizedBox(height: 12),
                    ...List.generate(order['items'].length, (i) {
                      final itm = order['items'][i];
                      return Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: Row(
                          children: [
                            Container(
                              width: 45,
                              height: 45,
                              decoration: BoxDecoration(
                                borderRadius: BorderRadius.circular(10),
                                image: DecorationImage(
                                  image: NetworkImage('${ApiService.getBaseUrl()}${itm['image_url']}'),
                                  fit: BoxFit.cover,
                                  onError: (_, __) => const AssetImage('assets/placeholder.jpg'),
                                ),
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(child: Text(itm['name'], style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: Color(0xFF5D4037)))),
                            Text('₱${itm['price'].toStringAsFixed(2)} x ${itm['quantity']}', style: AppTextStyles.muted),
                          ],
                        ),
                      );
                    }),
                  ],
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 8, 24, 16),
              child: GradientButton(
                label: 'Close View',
                icon: Icons.close_rounded,
                onPressed: () => Navigator.pop(context),
                height: 52,
              ),
            ),

            if (r['status'] == 'PENDING')
              Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(horizontal: 20).copyWith(bottom: 20),
                child: SizedBox(
                  height: 52,
                  child: OutlinedButton(
                    onPressed: () {
                      Navigator.pop(context);
                      _cancelReservation(r);
                    },
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppColors.danger,
                      side: const BorderSide(color: AppColors.danger, width: 1.5),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                    ),
                    child: const Text('Cancel Reservation', style: TextStyle(fontWeight: FontWeight.bold)),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _detailRow(IconData icon, String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Row(
        children: [
          Icon(icon, size: 20, color: AppColors.accent),
          const SizedBox(width: 12),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: TextStyle(color: Colors.grey[600], fontSize: 11, fontWeight: FontWeight.bold, letterSpacing: 0.5)),
              Text(value, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: Color(0xFF5D4037))),
            ],
          ),
        ],
      ),
    );
  }

  Widget _badge(String s) {
    final c = s == 'CONFIRMED' ? AppColors.success : s == 'PENDING' ? AppColors.warning : Colors.grey;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(color: c.withOpacity(0.1), borderRadius: BorderRadius.circular(20)),
      child: Text(s[0] + s.substring(1).toLowerCase(), style: TextStyle(color: c, fontSize: 11, fontWeight: FontWeight.w600)),
    );
  }

  Widget _reservationList(List items, {required String emptyText}) {
    if (items.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.event_busy, size: 48, color: AppColors.primary.withOpacity(0.2)),
            const SizedBox(height: 16),
            Text(emptyText, style: AppTextStyles.muted),
          ],
        ),
      );
    }
    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: items.length,
      itemBuilder: (ctx, i) {
        final r = items[i];
        return GestureDetector(
          onTap: () => _showReservationDetails(r),
          child: Container(
            margin: const EdgeInsets.only(bottom: 12),
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(16),
              boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.04), blurRadius: 10, offset: const Offset(0, 4))],
            ),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(color: AppColors.primary.withOpacity(0.1), shape: BoxShape.circle),
                  child: const Icon(Icons.calendar_month, color: AppColors.primary, size: 24),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${r['date_formatted']} · ${r['time_formatted']}', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14, color: AppColors.textMain)),
                      const SizedBox(height: 2),
                      Text('${r['guest_count']} guests · ${r['booking_type']}', style: AppTextStyles.muted.copyWith(fontSize: 12)),
                    ],
                  ),
                ),
                _badge(r['status']),
              ],
            ),
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('My Reservations', style: AppTextStyles.heading.copyWith(fontSize: 20)),
        centerTitle: true,
        backgroundColor: Colors.white,
        bottom: TabBar(
          controller: _tabController,
          labelColor: AppColors.primary,
          unselectedLabelColor: AppColors.textMuted,
          indicatorColor: AppColors.primary,
          labelStyle: const TextStyle(fontWeight: FontWeight.bold),
          tabs: const [Tab(text: 'Upcoming'), Tab(text: 'Past')],
        ),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: AppColors.primary))
          : TabBarView(
              controller: _tabController,
              children: [
                RefreshIndicator(
                  color: AppColors.primary,
                  onRefresh: _loadData,
                  child: _reservationList(_upcoming, emptyText: 'No upcoming reservations'),
                ),
                RefreshIndicator(
                  color: AppColors.primary,
                  onRefresh: _loadData,
                  child: _reservationList(_past, emptyText: 'No past reservations'),
                ),
              ],
            ),
    );
  }
}
