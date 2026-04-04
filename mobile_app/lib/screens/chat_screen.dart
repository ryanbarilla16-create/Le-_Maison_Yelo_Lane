import 'dart:async';
import 'package:flutter/material.dart';
import '../theme.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> with TickerProviderStateMixin {
  final TextEditingController _msgCtrl = TextEditingController();
  final ScrollController _scrollCtrl = ScrollController();
  List<Map<String, dynamic>> _messages = [];
  bool _loading = true;
  bool _sending = false;
  int? _userId;
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    _userId = await AuthService.getUserId();
    if (_userId == null) return;
    await _loadMessages();
    // Poll for new messages every 5 seconds
    _pollTimer = Timer.periodic(const Duration(seconds: 5), (_) {
      _loadMessages(scroll: false);
    });
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _msgCtrl.dispose();
    _scrollCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadMessages({bool scroll = true}) async {
    if (_userId == null) return;
    final res = await ApiService.get('/api/chat/$_userId');
    if (!mounted) return;
    if (res != null && res['success'] == true) {
      final newMessages = List<Map<String, dynamic>>.from(
        res['messages'] ?? [],
      );
      final hadNewMessage = newMessages.length != _messages.length;
      setState(() {
        _messages = newMessages;
        _loading = false;
      });
      if (scroll && hadNewMessage) {
        _scrollToBottom();
      }
    } else {
      setState(() => _loading = false);
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent + 80,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _sendMessage() async {
    final text = _msgCtrl.text.trim();
    if (text.isEmpty || _userId == null || _sending) return;

    setState(() => _sending = true);
    _msgCtrl.clear();

    // Optimistic UI: add message immediately
    setState(() {
      _messages.add({
        'id': DateTime.now().millisecondsSinceEpoch,
        'sender': 'USER',
        'message': text,
        'created_at': DateTime.now().toIso8601String(),
      });
    });
    _scrollToBottom();

    final res = await ApiService.post('/api/chat/$_userId/send', {
      'message': text,
      'sender': 'USER',
    });

    if (!mounted) return;
    setState(() => _sending = false);

    if (res['success'] != true) {
      // Remove optimistic message on failure
      setState(() => _messages.removeLast());
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(res['message'] ?? 'Failed to send message'),
          backgroundColor: AppColors.danger,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 20),
          onPressed: () => Navigator.pop(context),
        ),
        title: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [AppColors.primary, Color(0xFF6D4C41)],
                ),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Icon(
                Icons.smart_toy_rounded,
                color: Colors.white,
                size: 20,
              ),
            ),
            const SizedBox(width: 12),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'AI Assistant',
                  style: ThemeText.heading(context).copyWith(fontSize: 16),
                ),
                Text(
                  'Online - How can I help?',
                  style: ThemeText.muted(context).copyWith(fontSize: 11),
                ),
              ],
            ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh_rounded, color: AppColors.primary),
            tooltip: 'Restart Chat',
            onPressed: () {
              showDialog(
                context: context,
                builder: (context) => AlertDialog(
                  title: const Text('End & Restart?'),
                  content: const Text(
                    'This will clear your current chat and restart the AI Assistant.',
                  ),
                  actions: [
                    TextButton(
                      onPressed: () => Navigator.pop(context),
                      child: const Text('Cancel'),
                    ),
                    TextButton(
                      onPressed: () {
                        Navigator.pop(context);
                        setState(() {
                          _messages.clear();
                        });
                      },
                      child: const Text(
                        'Restart',
                        style: TextStyle(color: AppColors.primary),
                      ),
                    ),
                  ],
                ),
              );
            },
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: Column(
        children: [
          // Messages area
          Expanded(
            child: _loading
                ? const Center(
                    child: CircularProgressIndicator(color: AppColors.primary),
                  )
                : _messages.isEmpty
                ? _buildEmptyChat(isDark)
                : ListView.builder(
                    controller: _scrollCtrl,
                    padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                    itemCount: _messages.length,
                    itemBuilder: (_, i) =>
                        _buildMessageBubble(_messages[i], isDark),
                  ),
          ),

          // Input area
          _buildInputBar(isDark),
        ],
      ),
    );
  }

  Widget _buildEmptyChat(bool isDark) {
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 40),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [
                    AppColors.primary.withOpacity(0.15),
                    AppColors.primary.withOpacity(0.05),
                  ],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                shape: BoxShape.circle,
              ),
              child: const Icon(
                Icons.smart_toy_rounded,
                size: 56,
                color: AppColors.primary,
              ),
            ),
            const SizedBox(height: 24),
            Text(
              'Le Maison AI Assistant',
              textAlign: TextAlign.center,
              style: ThemeText.heading(context).copyWith(fontSize: 22),
            ),
            const SizedBox(height: 12),
            Text(
              'Hello! How can I assist you with your dining experience today? I can help with menu prices, delivery, and more.',
              textAlign: TextAlign.center,
              style: ThemeText.muted(
                context,
              ).copyWith(fontSize: 14, height: 1.5),
            ),
            const SizedBox(height: 32),

            // Core Bot Actions
            _botActionGroup([
              _botAction('Menu Categories 📋', 'CATEGORY_MENU'),
              _botAction('Item Prices ₱', 'PRICE_INFO'),
            ]),
            const SizedBox(height: 10),
            _botActionGroup([
              _botAction('Delivery Areas 📍', 'DELIVERY_INFO'),
              _botAction('Talk to Admin 👤', 'TALK_ADMIN'),
            ]),

            const SizedBox(height: 24),
            TextButton(
              onPressed: () => _handleBotAction('HOURS_BTN', 'Check Hours'),
              child: const Text(
                'View Operating Hours ⏰',
                style: TextStyle(
                  color: AppColors.primary,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _botActionGroup(List<Widget> children) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: children
          .map(
            (w) => Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 5),
                child: w,
              ),
            ),
          )
          .toList(),
    );
  }

  Widget _botAction(String label, String actionId, {String? data}) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () => _handleBotAction(actionId, label, data: data),
        borderRadius: BorderRadius.circular(16),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 14),
          decoration: BoxDecoration(
            color: AppColors.primary.withOpacity(0.06),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: AppColors.primary.withOpacity(0.12)),
          ),
          child: Text(
            label,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: AppColors.primary,
              fontSize: 13,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _handleBotAction(
    String id,
    String userText, {
    String? data,
  }) async {
    setState(() {
      _messages.add({
        'id': DateTime.now().millisecondsSinceEpoch,
        'sender': 'USER',
        'message': userText,
        'created_at': DateTime.now().toIso8601String(),
      });
    });
    _scrollToBottom();

    await Future.delayed(const Duration(milliseconds: 600));
    if (!mounted) return;

    String botReply = "";

    switch (id) {
      case 'CATEGORY_MENU':
        setState(() => _loading = true);
        final res = await ApiService.get('/api/menu/categories');
        setState(() => _loading = false);
        if (res != null) {
          botReply =
              "Fetching categories... Please select one from the menu below!";
          // Show categories as a list or options
          // For now, we'll give a summary and let them type or ideally we'd show buttons
          botReply = "Which category would you like to explore?\n";
          for (var c in (res as List)) {
            botReply += "• ${c['category']} (${c['count']} items)\n";
          }
          botReply += "\nType the category name to see items!";
        } else {
          botReply = "Error reaching menu service.";
        }
        break;

      case 'BOT_CAT_ITEMS':
        final cat = data ?? "";
        setState(() => _loading = true);
        final res = await ApiService.get('/api/menu');
        setState(() => _loading = false);
        if (res != null) {
          final filtered = (res as List)
              .where((i) => i['category'] == cat)
              .toList();
          botReply = "Items in $cat:\n";
          for (var i in filtered) {
            botReply += "• ${i['name']} - ₱${i['price']}\n";
          }
        }
        break;
      case 'PRICE_INFO':
        botReply =
            "Prices range from ₱90 to ₱1,800. Tap 'Menu Categories' to see specific details!";
        break;
      case 'DELIVERY_INFO':
        botReply =
            "We deliver to Santa Cruz, Magdalena, Los Baños, and Cavinti Laguna. Typically 30-45 mins!";
        break;
      case 'TALK_ADMIN':
        botReply = "Support notified. A human agent will join shortly.";
        break;
      case 'HOURS_BTN':
        botReply = "Daily 11:30 AM - 8:30 PM. See you!";
        break;
      case 'BOT_BACK':
        botReply = "How else can I assist you?";
        break;
      default:
        botReply = "I've logged your request. Help is coming!";
    }

    if (!mounted) return;
    setState(() {
      _messages.add({
        'id': DateTime.now().millisecondsSinceEpoch + 1,
        'sender': 'BOT',
        'message': botReply,
        'created_at': DateTime.now().toIso8601String(),
      });
    });
    _scrollToBottom();
  }

  Widget _buildMessageBubble(Map<String, dynamic> msg, bool isDark) {
    final isUser = msg['sender'] == 'USER';
    final timeStr = _formatTime(msg['created_at'] ?? '');

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: EdgeInsets.only(
          bottom: 10,
          left: isUser ? 50 : 0,
          right: isUser ? 0 : 50,
        ),
        child: Column(
          crossAxisAlignment: isUser
              ? CrossAxisAlignment.end
              : CrossAxisAlignment.start,
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              decoration: BoxDecoration(
                gradient: isUser
                    ? const LinearGradient(
                        colors: [AppColors.primary, Color(0xFF6D4C41)],
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                      )
                    : null,
                color: isUser
                    ? null
                    : (isDark ? AppColors.darkCard : const Color(0xFFF5F0EB)),
                borderRadius: BorderRadius.only(
                  topLeft: const Radius.circular(18),
                  topRight: const Radius.circular(18),
                  bottomLeft: Radius.circular(isUser ? 18 : 4),
                  bottomRight: Radius.circular(isUser ? 4 : 18),
                ),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withOpacity(0.04),
                    blurRadius: 6,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: Column(
                crossAxisAlignment: isUser
                    ? CrossAxisAlignment.end
                    : CrossAxisAlignment.start,
                children: [
                  if (!isUser)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 4),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            msg['sender'] == 'BOT'
                                ? Icons.smart_toy_rounded
                                : Icons.support_agent_rounded,
                            size: 14,
                            color: AppColors.primary.withOpacity(0.7),
                          ),
                          const SizedBox(width: 4),
                          Text(
                            msg['sender'] == 'BOT' ? 'AI Assistant' : 'Admin',
                            style: const TextStyle(
                              color: AppColors.primary,
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ],
                      ),
                    ),
                  Text(
                    msg['message'] ?? '',
                    style: TextStyle(
                      color: isUser
                          ? Colors.white
                          : (isDark ? AppColors.darkText : AppColors.textMain),
                      fontSize: 14,
                      height: 1.4,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 3),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 4),
              child: Text(
                timeStr,
                style: TextStyle(
                  color: isDark ? AppColors.darkMuted : AppColors.textMuted,
                  fontSize: 10,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildInputBar(bool isDark) {
    return Container(
      padding: EdgeInsets.fromLTRB(
        16,
        10,
        8,
        MediaQuery.of(context).padding.bottom + 10,
      ),
      decoration: BoxDecoration(
        color: isDark ? AppColors.darkCard : Colors.white,
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
          Expanded(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              decoration: BoxDecoration(
                color: isDark ? AppColors.darkBg : const Color(0xFFF5F0EB),
                borderRadius: BorderRadius.circular(24),
              ),
              child: TextField(
                controller: _msgCtrl,
                maxLines: 4,
                minLines: 1,
                textCapitalization: TextCapitalization.sentences,
                style: TextStyle(
                  color: isDark ? AppColors.darkText : AppColors.textMain,
                  fontSize: 14,
                ),
                decoration: InputDecoration(
                  hintText: 'Type your message...',
                  hintStyle: TextStyle(
                    color: isDark ? AppColors.darkMuted : AppColors.textMuted,
                    fontSize: 14,
                  ),
                  border: InputBorder.none,
                  contentPadding: const EdgeInsets.symmetric(vertical: 12),
                ),
                onSubmitted: (_) => _sendMessage(),
              ),
            ),
          ),
          const SizedBox(width: 8),
          GestureDetector(
            onTap: _sendMessage,
            child: Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [AppColors.primary, Color(0xFF6D4C41)],
                ),
                borderRadius: BorderRadius.circular(22),
                boxShadow: [
                  BoxShadow(
                    color: AppColors.primary.withOpacity(0.3),
                    blurRadius: 8,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: Icon(
                _sending ? Icons.hourglass_top_rounded : Icons.send_rounded,
                color: Colors.white,
                size: 20,
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _formatTime(String dateStr) {
    try {
      final dt = DateTime.parse(dateStr);
      final now = DateTime.now();
      final diff = now.difference(dt);

      if (diff.inMinutes < 1) return 'Just now';
      if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
      if (diff.inHours < 24) return '${diff.inHours}h ago';
      if (diff.inDays < 7) return '${diff.inDays}d ago';

      final months = [
        'Jan',
        'Feb',
        'Mar',
        'Apr',
        'May',
        'Jun',
        'Jul',
        'Aug',
        'Sep',
        'Oct',
        'Nov',
        'Dec',
      ];
      final hour = dt.hour > 12 ? dt.hour - 12 : (dt.hour == 0 ? 12 : dt.hour);
      final ampm = dt.hour >= 12 ? 'PM' : 'AM';
      return '${months[dt.month - 1]} ${dt.day}, $hour:${dt.minute.toString().padLeft(2, '0')} $ampm';
    } catch (_) {
      return '';
    }
  }
}


