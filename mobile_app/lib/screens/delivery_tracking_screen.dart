import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import '../services/api_service.dart';
import '../theme.dart';

class DeliveryTrackingScreen extends StatefulWidget {
  final int orderId;
  final String? deliveryAddress;

  const DeliveryTrackingScreen({
    super.key,
    required this.orderId,
    this.deliveryAddress,
  });

  @override
  State<DeliveryTrackingScreen> createState() => _DeliveryTrackingScreenState();
}

class _DeliveryTrackingScreenState extends State<DeliveryTrackingScreen> {
  Timer? _refreshTimer;
  final MapController _mapCtrl = MapController();

  String _deliveryStatus = 'WAITING';
  String? _riderName;
  LatLng? _riderLocation;
  String? _lastUpdate;
  bool _loading = true;

  // Le Maison store location (Pagsanjan, Laguna)
  final LatLng _storeLocation = const LatLng(14.2730, 121.4550);

  @override
  void initState() {
    super.initState();
    _loadTrackingData();
    _refreshTimer = Timer.periodic(const Duration(seconds: 5), (_) {
      _loadTrackingData(silent: true);
    });
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    super.dispose();
  }

  Future<void> _loadTrackingData({bool silent = false}) async {
    if (!silent && mounted) setState(() => _loading = true);

    final res = await ApiService.get('/api/delivery/track/${widget.orderId}');
    if (mounted && res != null && res['success'] == true) {
      setState(() {
        _deliveryStatus = res['delivery_status'] ?? 'WAITING';
        _riderName = res['rider_name'];

        if (res['rider_location'] != null) {
          final loc = res['rider_location'];
          _riderLocation = LatLng(
            (loc['lat'] as num).toDouble(),
            (loc['lng'] as num).toDouble(),
          );
          _lastUpdate = loc['timestamp'];
        }
        _loading = false;
      });
    } else if (mounted) {
      setState(() => _loading = false);
    }
  }

  Color _statusColor() {
    switch (_deliveryStatus) {
      case 'WAITING':
        return Colors.orange;
      case 'PICKED_UP':
        return Colors.teal;
      case 'ON_THE_WAY':
        return Colors.blue;
      case 'DELIVERED':
        return Colors.green;
      default:
        return AppColors.primary;
    }
  }

  IconData _statusIcon() {
    switch (_deliveryStatus) {
      case 'WAITING':
        return Icons.hourglass_top;
      case 'PICKED_UP':
        return Icons.inventory_2;
      case 'ON_THE_WAY':
        return Icons.directions_bike;
      case 'DELIVERED':
        return Icons.check_circle;
      default:
        return Icons.schedule;
    }
  }

  String _statusLabel() {
    switch (_deliveryStatus) {
      case 'WAITING':
        return 'Waiting for Rider';
      case 'PICKED_UP':
        return 'Order Picked Up';
      case 'ON_THE_WAY':
        return 'Rider On The Way';
      case 'DELIVERED':
        return 'Delivered!';
      default:
        return _deliveryStatus;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        backgroundColor: Colors.white,
        elevation: 0,
        leading: IconButton(
          onPressed: () => Navigator.pop(context),
          icon: Icon(Icons.arrow_back, color: AppColors.textMain),
        ),
        title: Row(
          children: [
            Icon(Icons.location_on, color: AppColors.primary, size: 22),
            const SizedBox(width: 8),
            Text(
              'Track Order #${widget.orderId}',
              style: TextStyle(
                fontFamily: 'Georgia',
                fontWeight: FontWeight.bold,
                color: AppColors.textMain,
                fontSize: 17,
              ),
            ),
          ],
        ),
      ),
      body: _loading
          ? Center(
              child: CircularProgressIndicator(color: AppColors.primary),
            )
          : Column(
              children: [
                // ═══ STATUS BAR ═══
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: _statusColor().withOpacity(0.08),
                    border: Border(
                      bottom: BorderSide(
                        color: _statusColor().withOpacity(0.2),
                      ),
                    ),
                  ),
                  child: Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: _statusColor().withOpacity(0.15),
                          shape: BoxShape.circle,
                        ),
                        child: Icon(
                          _statusIcon(),
                          color: _statusColor(),
                          size: 24,
                        ),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              _statusLabel(),
                              style: TextStyle(
                                fontWeight: FontWeight.bold,
                                fontSize: 16,
                                color: _statusColor(),
                              ),
                            ),
                            const SizedBox(height: 2),
                            if (_riderName != null)
                              Text(
                                '🏍️ $_riderName',
                                style: TextStyle(
                                  color: AppColors.textMuted,
                                  fontSize: 13,
                                ),
                              )
                            else
                              Text(
                                'Waiting for a rider to pick up...',
                                style: TextStyle(
                                  color: AppColors.textMuted,
                                  fontSize: 13,
                                  fontStyle: FontStyle.italic,
                                ),
                              ),
                          ],
                        ),
                      ),
                      // Live indicator
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 10,
                          vertical: 5,
                        ),
                        decoration: BoxDecoration(
                          color: Colors.green.withOpacity(0.1),
                          borderRadius: BorderRadius.circular(20),
                          border: Border.all(
                            color: Colors.green.withOpacity(0.3),
                          ),
                        ),
                        child: const Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(
                              Icons.circle,
                              color: Colors.green,
                              size: 8,
                            ),
                            SizedBox(width: 4),
                            Text(
                              'LIVE',
                              style: TextStyle(
                                color: Colors.green,
                                fontWeight: FontWeight.bold,
                                fontSize: 10,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),

                // ═══ DELIVERY PROGRESS ═══
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 20,
                    vertical: 14,
                  ),
                  color: Colors.white,
                  child: Row(
                    children: [
                      _progressStep('Waiting', 'WAITING'),
                      _progressLine('PICKED_UP'),
                      _progressStep('Picked Up', 'PICKED_UP'),
                      _progressLine('ON_THE_WAY'),
                      _progressStep('On The Way', 'ON_THE_WAY'),
                      _progressLine('DELIVERED'),
                      _progressStep('Delivered', 'DELIVERED'),
                    ],
                  ),
                ),

                // ═══ MAP ═══
                Expanded(
                  child: ClipRRect(
                    child: FlutterMap(
                      mapController: _mapCtrl,
                      options: MapOptions(
                        initialCenter: _riderLocation ?? _storeLocation,
                        initialZoom: 14,
                      ),
                      children: [
                        TileLayer(
                          urlTemplate:
                              'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                          userAgentPackageName: 'com.lemaison.app',
                        ),
                        MarkerLayer(
                          markers: [
                            // Store marker
                            Marker(
                              point: _storeLocation,
                              width: 50,
                              height: 50,
                              child: Container(
                                decoration: BoxDecoration(
                                  color: AppColors.primary,
                                  shape: BoxShape.circle,
                                  boxShadow: [
                                    BoxShadow(
                                      color: AppColors.primary.withOpacity(0.4),
                                      blurRadius: 8,
                                      spreadRadius: 2,
                                    ),
                                  ],
                                ),
                                child: const Icon(
                                  Icons.coffee,
                                  color: Colors.white,
                                  size: 22,
                                ),
                              ),
                            ),
                            // Rider marker
                            if (_riderLocation != null)
                              Marker(
                                point: _riderLocation!,
                                width: 50,
                                height: 50,
                                child: Container(
                                  decoration: BoxDecoration(
                                    color: _statusColor(),
                                    shape: BoxShape.circle,
                                    boxShadow: [
                                      BoxShadow(
                                        color:
                                            _statusColor().withOpacity(0.4),
                                        blurRadius: 10,
                                        spreadRadius: 3,
                                      ),
                                    ],
                                  ),
                                  child: const Icon(
                                    Icons.delivery_dining,
                                    color: Colors.white,
                                    size: 24,
                                  ),
                                ),
                              ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),

                // ═══ BOTTOM INFO ═══
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withOpacity(0.05),
                        offset: const Offset(0, -2),
                        blurRadius: 10,
                      ),
                    ],
                  ),
                  child: Row(
                    children: [
                      Icon(
                        Icons.location_on,
                        color: AppColors.primary,
                        size: 20,
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          widget.deliveryAddress ?? 'Delivery Address',
                          style: TextStyle(
                            color: AppColors.textMain,
                            fontSize: 13,
                          ),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
    );
  }

  Widget _progressStep(String label, String status) {
    final statuses = ['WAITING', 'PICKED_UP', 'ON_THE_WAY', 'DELIVERED'];
    final currentIdx = statuses.indexOf(_deliveryStatus);
    final stepIdx = statuses.indexOf(status);
    final isCompleted = stepIdx <= currentIdx;
    final isCurrent = stepIdx == currentIdx;

    return Expanded(
      child: Column(
        children: [
          Container(
            width: isCurrent ? 28 : 22,
            height: isCurrent ? 28 : 22,
            decoration: BoxDecoration(
              color: isCompleted
                  ? _statusColor()
                  : Colors.grey.withOpacity(0.2),
              shape: BoxShape.circle,
              boxShadow: isCurrent
                  ? [
                      BoxShadow(
                        color: _statusColor().withOpacity(0.4),
                        blurRadius: 8,
                        spreadRadius: 1,
                      ),
                    ]
                  : null,
            ),
            child: Icon(
              isCompleted ? Icons.check : Icons.circle,
              color: isCompleted ? Colors.white : Colors.grey[400],
              size: isCurrent ? 16 : 12,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            label,
            style: TextStyle(
              fontSize: 9,
              fontWeight: isCurrent ? FontWeight.bold : FontWeight.w500,
              color: isCompleted ? _statusColor() : AppColors.textMuted,
            ),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  Widget _progressLine(String nextStatus) {
    final statuses = ['WAITING', 'PICKED_UP', 'ON_THE_WAY', 'DELIVERED'];
    final currentIdx = statuses.indexOf(_deliveryStatus);
    final nextIdx = statuses.indexOf(nextStatus);
    final isCompleted = nextIdx <= currentIdx;

    return Expanded(
      child: Container(
        height: 3,
        margin: const EdgeInsets.only(bottom: 16),
        decoration: BoxDecoration(
          color: isCompleted ? _statusColor() : Colors.grey.withOpacity(0.2),
          borderRadius: BorderRadius.circular(2),
        ),
      ),
    );
  }
}


