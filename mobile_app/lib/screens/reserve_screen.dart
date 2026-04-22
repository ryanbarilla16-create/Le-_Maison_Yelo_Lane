import 'package:flutter/material.dart';
import '../theme.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';
import 'reserve_menu_screen.dart';

class ReserveScreen extends StatefulWidget {
  const ReserveScreen({super.key});
  @override
  State<ReserveScreen> createState() => _ReserveScreenState();
}

class _ReserveScreenState extends State<ReserveScreen> {
  DateTime? _date;
  String? _time;
  int _guests = 2;
  String _bookingType = 'REGULAR';
  int _duration = 2;
  final _occasionCtrl = TextEditingController();
  bool _loading = false;
  List<dynamic> _upcoming = [];
  bool _loadingRes = true;
  final List<String> _timeSlots = [];

  @override
  void initState() {
    super.initState();
    for (int h = 11; h <= 20; h++) {
      for (int m = 0; m < 60; m += 30) {
        if (h == 11 && m == 0) continue;
        if (h == 20 && m > 30) continue;
        _timeSlots.add(
          '${h.toString().padLeft(2, '0')}:${m.toString().padLeft(2, '0')}',
        );
      }
    }
    _loadReservations();
  }

  String _fmt(String t) {
    final p = t.split(':');
    int h = int.parse(p[0]);
    final ap = h >= 12 ? 'PM' : 'AM';
    if (h > 12) h -= 12;
    if (h == 0) h = 12;
    return '$h:${p[1]} $ap';
  }

  Future<void> _loadReservations() async {
    final uid = await AuthService.getUserId();
    if (uid == null) return;
    final res = await ApiService.get('/api/user/$uid/reservations');
    if (res != null && res is Map) {
      setState(() {
        _upcoming = res['upcoming'] ?? [];
        _loadingRes = false;
      });
    } else {
      setState(() => _loadingRes = false);
    }
  }

  List<String> get _getAvailableTimeSlots {
    if (_date == null) return _timeSlots;
    final now = DateTime.now();
    bool isToday = _date!.year == now.year && _date!.month == now.month && _date!.day == now.day;
    if (!isToday) return _timeSlots;
    
    return _timeSlots.where((t) {
      final p = t.split(':');
      final h = int.parse(p[0]);
      final m = int.parse(p[1]);
      return (h > now.hour) || (h == now.hour && m > now.minute);
    }).toList();
  }

  bool get _isTodayClosed {
    final now = DateTime.now();
    // Check if any time slots are still available for today
    final todaySlots = _timeSlots.where((t) {
      final p = t.split(':');
      final h = int.parse(p[0]);
      final m = int.parse(p[1]);
      return (h > now.hour) || (h == now.hour && m > now.minute);
    }).toList();
    return todaySlots.isEmpty;
  }

  bool get _isSelectionInvalid {
    if (_date == null || _time == null) return true;
    final now = DateTime.now();
    bool isToday = _date!.year == now.year && _date!.month == now.month && _date!.day == now.day;
    if (isToday) {
      final p = _time!.split(':');
      final h = int.parse(p[0]);
      final m = int.parse(p[1]);
      if ((h < now.hour) || (h == now.hour && m <= now.minute)) return true;
      if (now.hour >= 20 && (now.hour > 20 || now.minute >= 30)) return true;
    }
    return false;
  }


  Future<void> _pickDate() async {
    final now = DateTime.now();
    final isExclusive = _bookingType == 'EXCLUSIVE';
    final todayClosed = _isTodayClosed;

    // If restaurant is closed for today or exclusive booking, start from tomorrow
    final tomorrow = DateTime(now.year, now.month, now.day).add(const Duration(days: 1));
    final firstDay = (isExclusive || todayClosed) ? tomorrow : now;
    
    DateTime initial = _date ?? firstDay;
    if (initial.isBefore(firstDay)) initial = firstDay;

    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: firstDay,
      lastDate: now.add(const Duration(days: 60)),
      builder: (c, ch) => Theme(
        data: Theme.of(c).copyWith(
          colorScheme: const ColorScheme.light(primary: AppColors.primary),
        ),
        child: ch!,
      ),
    );
    if (picked != null) {
      setState(() {
        _date = picked;
        _time = null; // reset to re-validate time slot
      });
    }
  }

  Future<void> _submit() async {
    if (_date == null) {
      _msg('Please select a date.', false);
      return;
    }
    if (_time == null) {
      _msg('Please select a time.', false);
      return;
    }

    final now = DateTime.now();
    bool isToday = _date!.year == now.year && _date!.month == now.month && _date!.day == now.day;
    if (isToday) {
      final p = _time!.split(':');
      final h = int.parse(p[0]);
      final m = int.parse(p[1]);
      if ((h < now.hour) || (h == now.hour && m <= now.minute)) {
         _msg('This time slot has already passed today.', false);
         return;
      }
      if (now.hour >= 20 && now.minute >= 30) {
        _msg('We are now closed for today. Please book for tomorrow.', false);
        return;
      }
    }

    if (_guests <= 0) {
      _msg('Guest count must be at least 1.', false);
      return;
    }
    final maxG = _bookingType == 'EXCLUSIVE' ? 50 : 20;
    if (_guests > maxG) {
      _msg('Maximum of $maxG guests for ${_bookingType.toLowerCase()} bookings.', false);
      return;
    }

    final uid = await AuthService.getUserId();
    if (uid == null) return;
    final ds =
        '${_date!.year}-${_date!.month.toString().padLeft(2, '0')}-${_date!.day.toString().padLeft(2, '0')}';

    // TRIGGER T&C MODAL FOR EXCLUSIVE BOOKINGS
    if (_bookingType == 'EXCLUSIVE') {
      final agreed = await _showExclusiveTerms();
      if (agreed != true) return; 
    }
    
    // Redirect to Menu Selection Step 2
    if (!mounted) return;
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => ReserveMenuScreen(
          reservationData: {
            'date': ds,
            'time': _time,
            'guest_count': _guests,
            'occasion': _occasionCtrl.text.trim(),
            'booking_type': _bookingType,
            'duration': _duration,
          },
        ),
      ),
    );
  }

  void _msg(String m, bool ok) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(m),
        backgroundColor: ok ? AppColors.success : AppColors.danger,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        title: const Text('RESERVATIONS', style: TextStyle(fontWeight: FontWeight.w900, fontSize: 18, letterSpacing: 1.2)),
        centerTitle: true,
      ),
      body: SingleChildScrollView(
        physics: const BouncingScrollPhysics(),
        padding: const EdgeInsets.symmetric(horizontal: 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 20),
            Container(
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(24),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withOpacity(0.04),
                    blurRadius: 20,
                    offset: const Offset(0, 10),
                  ),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('BOOK A TABLE', style: TextStyle(fontWeight: FontWeight.w900, fontSize: 14, letterSpacing: 1.5, color: AppColors.primary)),
                  const SizedBox(height: 24),
                  
                  // Booking Type
                  _formLabel('Experience Type'),
                  DropdownButtonFormField<String>(
                    isExpanded: true,
                    value: _bookingType,
                    style: const TextStyle(fontWeight: FontWeight.bold, color: AppColors.textMain, fontSize: 15),
                    decoration: _inputDecoration(Icons.restaurant_menu),
                    items: const [
                      DropdownMenuItem(value: 'REGULAR', child: Text('Standard Dining')),
                      DropdownMenuItem(value: 'EXCLUSIVE', child: Text('Private Event')),
                    ],
                    onChanged: (v) => setState(() {
                      if (v != null) {
                        _bookingType = v;
                        _date = null;
                      }
                    }),
                  ),
                  const SizedBox(height: 20),

                  // Date Selection
                  _formLabel('Preferred Date'),
                  GestureDetector(
                    onTap: _pickDate,
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
                      decoration: BoxDecoration(
                        color: Colors.grey.shade50,
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(color: Colors.grey.shade200),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.calendar_today_rounded, color: AppColors.primary, size: 20),
                          const SizedBox(width: 12),
                          Text(
                            _date != null ? '${_date!.month}/${_date!.day}/${_date!.year}' : 'Pick a date',
                            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 15, color: _date != null ? AppColors.textMain : Colors.grey),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 20),

                  // Time Selection
                  _formLabel('Time Slot'),
                  DropdownButtonFormField<String>(
                    isExpanded: true,
                    value: _time,
                    hint: const Text('Choose a time'),
                    decoration: _inputDecoration(Icons.access_time_rounded),
                    items: _getAvailableTimeSlots.map((t) => DropdownMenuItem(value: t, child: Text(_fmt(t)))).toList(),
                    onChanged: (v) => setState(() => _time = v),
                  ),
                  const SizedBox(height: 20),

                  // Guest Count
                  _formLabel('Party Size'),
                  Row(
                    children: [
                      _guestButton(Icons.remove, () => setState(() => _guests > 1 ? _guests-- : null)),
                      Expanded(
                        child: Center(
                          child: Text(
                            '$_guests GUESTS',
                            style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 18, color: AppColors.primary),
                          ),
                        ),
                      ),
                      _guestButton(Icons.add, () => setState(() => _guests++)),
                    ],
                  ),
                  const SizedBox(height: 32),

                  GradientButton(
                    label: 'CONTINUE TO MENU',
                    onPressed: (_loading || _isSelectionInvalid) ? null : _submit,
                    isLoading: _loading,
                    height: 56,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 40),
            const Text('UPCOMING BOOKINGS', style: TextStyle(fontWeight: FontWeight.w900, fontSize: 12, letterSpacing: 1.5, color: Colors.grey)),
            const SizedBox(height: 16),
            if (_loadingRes)
              const Center(child: CircularProgressIndicator(color: AppColors.primary))
            else if (_upcoming.isEmpty)
              _emptyReservations()
            else
              ..._upcoming.map((r) => _reservationCard(r)),
            const SizedBox(height: 30),
          ],
        ),
      ),
    );
  }

  InputDecoration _inputDecoration(IconData icon) {
    return InputDecoration(
      prefixIcon: Icon(icon, color: AppColors.primary, size: 20),
      filled: true,
      fillColor: Colors.grey.shade50,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide(color: Colors.grey.shade200)),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide(color: Colors.grey.shade200)),
    );
  }

  Widget _formLabel(String t) {
    return Padding(
      padding: const EdgeInsets.only(left: 4, bottom: 8),
      child: Text(t, style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Colors.grey.shade600, letterSpacing: 0.5)),
    );
  }

  Widget _guestButton(IconData icon, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(color: AppColors.primary.withOpacity(0.1), borderRadius: BorderRadius.circular(12)),
        child: Icon(icon, color: AppColors.primary, size: 20),
      ),
    );
  }

  Widget _reservationCard(dynamic r) {
    return GestureDetector(
      onTap: () => _showReservationDetails(r),
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(20), border: Border.all(color: Colors.grey.shade100)),
        child: Row(
          children: [
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('${r['date_formatted']}', style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 15)),
                Text('${r['time_formatted']} · ${r['guest_count']} Guests', style: const TextStyle(color: Colors.grey, fontSize: 12, fontWeight: FontWeight.bold)),
              ],
            ),
            const Spacer(),
            _badge(r['status']),
          ],
        ),
      ),
    );
  }

  Widget _emptyReservations() {
    return Center(
      child: Column(
        children: [
          const SizedBox(height: 20),
          Icon(Icons.calendar_today_outlined, color: Colors.grey.shade200, size: 64),
          const SizedBox(height: 12),
          const Text('No bookings found', style: TextStyle(color: Colors.grey, fontWeight: FontWeight.bold)),
        ],
      ),
    );
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
            // Header
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
                    decoration: BoxDecoration(
                      color: Colors.grey[300],
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                  const SizedBox(height: 20),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'Reservation Detail',
                            style: TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.w800,
                              color: Color(0xFF3E2723),
                            ),
                          ),
                          Text(
                            'Reference ID: #${r['id']}',
                            style: TextStyle(fontSize: 12, color: Colors.grey[600]),
                          ),
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
                  // Info Cards
                  _detailRow(Icons.calendar_today_rounded, 'Date & Time', '${r['date_formatted']} at ${r['time_formatted']}'),
                  _detailRow(Icons.people_outline_rounded, 'Guests', '${r['guest_count']} person(s)'),
                  _detailRow(Icons.star_outline_rounded, 'Occasion', r['occasion'] ?? 'None'),
                  _detailRow(Icons.restaurant_rounded, 'Type', r['booking_type'] ?? 'Standard'),

                  if (order != null) ...[
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 20),
                      child: Divider(height: 1, thickness: 1.5, color: Color(0xFFF1F1F1)),
                    ),
                    const Text(
                      'Pre-ordered items',
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w800,
                        color: Color(0xFF3E2723),
                      ),
                    ),
                    const SizedBox(height: 16),
                    ...(order['items'] as List).map((item) => Container(
                      margin: const EdgeInsets.only(bottom: 12),
                      child: Row(
                        children: [
                          Container(
                            width: 50,
                            height: 50,
                            decoration: BoxDecoration(
                              borderRadius: BorderRadius.circular(10),
                              color: Colors.grey[100],
                              image: item['image_url'] != null
                                ? DecorationImage(
                                    image: NetworkImage(item['image_url']),
                                    fit: BoxFit.cover,
                                  )
                                : null,
                            ),
                            child: item['image_url'] == null ? const Icon(Icons.fastfood_outlined, size: 20) : null,
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
                                  '${item['quantity']}x',
                                  style: TextStyle(color: Colors.grey[600], fontSize: 13),
                                ),
                              ],
                            ),
                          ),
                          Text(
                            '₱${(item['price'] * item['quantity']).toStringAsFixed(2)}',
                            style: const TextStyle(
                              fontWeight: FontWeight.w800,
                              color: AppColors.accent,
                              fontFamily: 'Georgia',
                            ),
                          ),
                        ],
                      ),
                    )).toList(),
                    
                    const SizedBox(height: 20),
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: AppColors.primary.withOpacity(0.04),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text(
                            'Total Amount',
                            style: TextStyle(fontWeight: FontWeight.bold),
                          ),
                          Text(
                            '₱${order['total_amount'].toStringAsFixed(2)}',
                            style: const TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.w900,
                              color: AppColors.accent,
                              fontFamily: 'Georgia',
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ],
              ),
            ),
            
            // Footer
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
                    onPressed: () => _cancelReservation(r),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppColors.danger,
                      side: const BorderSide(color: AppColors.danger, width: 1.5),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                      elevation: 0,
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
    final c = s == 'CONFIRMED'
        ? AppColors.success
        : s == 'PENDING'
        ? AppColors.warning
        : Colors.grey;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: c.withOpacity(0.1),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        s[0] + s.substring(1).toLowerCase(),
        style: TextStyle(color: c, fontSize: 11, fontWeight: FontWeight.w600),
      ),
    );
  }

  Future<void> _cancelReservation(Map r) async {
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
      Navigator.pop(context); // close modal bottom sheet
      
      if (res['success'] == true) {
        _msg('Reservation cancelled successfully.', true);
        _loadReservations(); // reload reservations
      } else {
        _msg(res['message'] ?? 'Failed to cancel reservation.', false);
      }
    }
  }

  Future<bool?> _showExclusiveTerms() {
    bool localAgreed = false;
    return showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => StatefulBuilder(
        builder: (context, setDialogState) {
          return AlertDialog(
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
            backgroundColor: Colors.white,
            title: Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: AppColors.primary.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: const Icon(Icons.gavel_rounded, color: AppColors.primary, size: 20),
                ),
                const SizedBox(width: 12),
                const Text(
                  'Exclusive Policy',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 18),
                ),
              ],
            ),
            content: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                   const Text(
                    'Please review the terms for renting the entire venue:',
                    style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.textMain),
                  ),
                  const SizedBox(height: 16),
                  _policyItem(Icons.timer, '3-Day Lead Time', 'Exclusive bookings must be made at least 3 days in advance.'),
                  _policyItem(Icons.payments_outlined, 'Payment First', 'Full payment of the pre-ordered menu is required to confirm your slot.'),
                  _policyItem(Icons.groups_outlined, 'Capacity', 'Accommodates up to 50 guests. Admin approval is required.'),
                  const SizedBox(height: 16),
                  const Divider(),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Checkbox(
                        value: localAgreed,
                        activeColor: AppColors.primary,
                        onChanged: (v) => setDialogState(() => localAgreed = v ?? false),
                      ),
                      const Expanded(
                        child: Text(
                          'I have read and agree to the Exclusive Reservation Terms.',
                          style: TextStyle(fontSize: 12, fontWeight: FontWeight.w500),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('Cancel', style: TextStyle(color: Colors.grey)),
              ),
              ElevatedButton(
                onPressed: localAgreed ? () => Navigator.pop(context, true) : null,
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.primary,
                  foregroundColor: Colors.white,
                  disabledBackgroundColor: Colors.grey.shade300,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
                child: const Text('Continue'),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _policyItem(IconData icon, String title, String desc) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 16, color: AppColors.primary),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                Text(desc, style: const TextStyle(color: Colors.grey, fontSize: 11)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}


