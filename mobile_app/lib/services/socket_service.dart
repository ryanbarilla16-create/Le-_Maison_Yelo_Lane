import 'dart:async';
import 'package:socket_io_client/socket_io_client.dart' as IO;
import 'api_service.dart';

class SocketService {
  static IO.Socket? _socket;
  static final _notificationController = StreamController<dynamic>.broadcast();
  static final _chatController = StreamController<dynamic>.broadcast();
  static final _orderUpdateController = StreamController<dynamic>.broadcast();

  static Stream<dynamic> get notifications => _notificationController.stream;
  static Stream<dynamic> get chatMessages => _chatController.stream;
  static Stream<dynamic> get orderUpdates => _orderUpdateController.stream;

  static void init() {
    if (_socket != null) return;
    
    final baseUrl = ApiService.getBaseUrl();
    
    _socket = IO.io(baseUrl, IO.OptionBuilder()
      .setTransports(['websocket']) // Force WebSocket only for performance
      .enableAutoConnect()
      .setReconnectionAttempts(10)
      .setReconnectionDelay(2000)
      .build());

    _socket!.onConnect((_) {
      print('[Socket] Connected to server: $baseUrl');
    });

    _socket!.onDisconnect((_) {
      print('[Socket] Disconnected');
    });

    // Listen for events (matching backend emits)
    _socket!.on('new_notification', (data) {
      print('[Socket] New Notification: $data');
      _notificationController.add(data);
    });

    _socket!.on('new_chat_message', (data) {
       print('[Socket] New Chat: $data');
      _chatController.add(data);
    });

    _socket!.on('order_update', (data) {
       print('[Socket] Order Update: $data');
      _orderUpdateController.add(data);
    });
    
    // Kitchen updates from admin side
    _socket!.on('kitchen_order_completed', (data) {
       _orderUpdateController.add(data);
    });
  }

  static void emit(String event, dynamic data) {
    _socket?.emit(event, data);
  }

  static void joinUserRoom(int userId) {
    _socket?.emit('join_user_room', {'user_id': userId});
  }

  static void dispose() {
    _socket?.dispose();
    _socket = null;
  }
}
