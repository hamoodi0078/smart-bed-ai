import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../src/core/network_status_service.dart';
import '../../theme/app_theme.dart';
import '../../services/api_service.dart';
import '../../widgets/network_banner.dart';

class DanaChatScreen extends ConsumerStatefulWidget {
  const DanaChatScreen({super.key});

  @override
  ConsumerState<DanaChatScreen> createState() => _DanaChatScreenState();
}

class _DanaChatScreenState extends ConsumerState<DanaChatScreen> {
  static const String _historyKey = 'dana_chat_history';
  static const int _maxStoredMessages = 50;

  final TextEditingController _messageController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final List<_Message> _messages = [];
  _DanaPersonality _currentPersonality = _DanaPersonality.guide;
  bool _isTyping = false;

  @override
  void initState() {
    super.initState();
    _loadHistory();
  }

  @override
  void dispose() {
    _messageController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _loadHistory() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_historyKey);
      if (raw != null && raw.isNotEmpty) {
        final List<dynamic> decoded = jsonDecode(raw) as List<dynamic>;
        final loaded = decoded
            .whereType<Map<String, dynamic>>()
            .map(_Message.fromJson)
            .toList();
        if (mounted && loaded.isNotEmpty) {
          setState(() => _messages.addAll(loaded));
          _scrollToBottom();
          return;
        }
      }
    } catch (_) {
      // If history is corrupted just start fresh
    }
    // No history — show greeting
    _addDanaMessage(_getGreeting());
  }

  Future<void> _saveHistory() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final toSave = _messages.length > _maxStoredMessages
          ? _messages.sublist(_messages.length - _maxStoredMessages)
          : _messages;
      await prefs.setString(
          _historyKey, jsonEncode(toSave.map((m) => m.toJson()).toList()));
    } catch (_) {}
  }

  Future<void> _clearHistory() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_historyKey);
    } catch (_) {}
    if (mounted) {
      setState(() => _messages.clear());
      _addDanaMessage(_getGreeting());
    }
  }

  String _getGreeting() {
    switch (_currentPersonality) {
      case _DanaPersonality.coach:
        return "Hey there! Ready to optimize your sleep and crush your goals? 💪";
      case _DanaPersonality.guide:
        return "Peace be with you. How can I help you tonight? 🌙";
      case _DanaPersonality.therapist:
        return "Hello, I'm here to listen. How are you feeling tonight? 🧠";
    }
  }

  void _addDanaMessage(String text) {
    if (!mounted) return;
    setState(() {
      _messages.add(_Message(
        text: text,
        isUser: false,
        timestamp: DateTime.now(),
        personality: _currentPersonality,
      ));
    });
    _scrollToBottom();
    _saveHistory();
  }

  void _addUserMessage(String text) {
    setState(() {
      _messages.add(_Message(
        text: text,
        isUser: true,
        timestamp: DateTime.now(),
      ));
    });
    _scrollToBottom();
    _saveHistory();
  }

  void _scrollToBottom() {
    Future.delayed(const Duration(milliseconds: 100), () {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  void _sendMessage() async {
    final text = _messageController.text.trim();
    if (text.isEmpty || _isTyping) return;

    final isOnline = ref.read(isOnlineProvider);
    if (!isOnline) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('No internet connection. Please check your network.'),
          backgroundColor: AppColors.orange,
        ),
      );
      return;
    }

    _addUserMessage(text);
    _messageController.clear();
    setState(() => _isTyping = true);

    try {
      final personalityKey = _currentPersonality.apiKey;
      final response =
          await ApiService.sendMessage(text, personality: personalityKey);
      if (mounted) {
        setState(() => _isTyping = false);
        _addDanaMessage(response);
      }
    } catch (e) {
      if (mounted) {
        setState(() => _isTyping = false);
        _addDanaMessage(
          "Sorry, I couldn't respond right now. Please try again. 🌙",
        );
      }
    }
  }

  void _switchPersonality(_DanaPersonality newPersonality) {
    setState(() {
      _currentPersonality = newPersonality;
    });
    _addDanaMessage(
      "Personality switched! ${_getGreeting()}",
    );
  }

  void _startVoiceInput() {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Voice input feature coming soon!'),
        backgroundColor: AppColors.accent,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.cardBg,
        foregroundColor: AppColors.white,
        elevation: 0,
        title: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              _currentPersonality.emoji,
              style: const TextStyle(fontSize: 24),
            ),
            const SizedBox(width: 8),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Dana',
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                Text(
                  _currentPersonality.name,
                  style: TextStyle(
                    fontSize: 11,
                    color: _currentPersonality.color,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.delete_sweep_rounded),
            tooltip: 'Clear chat history',
            onPressed: () async {
              final confirm = await showDialog<bool>(
                context: context,
                builder: (ctx) => AlertDialog(
                  backgroundColor: AppColors.cardBg,
                  title: const Text('Clear History',
                      style: TextStyle(color: AppColors.white)),
                  content: const Text(
                    'This will delete all chat messages. Are you sure?',
                    style: TextStyle(color: AppColors.softWhite),
                  ),
                  actions: [
                    TextButton(
                      onPressed: () => Navigator.pop(ctx, false),
                      child: const Text('Cancel'),
                    ),
                    TextButton(
                      onPressed: () => Navigator.pop(ctx, true),
                      style: TextButton.styleFrom(
                          foregroundColor: AppColors.orange),
                      child: const Text('Clear'),
                    ),
                  ],
                ),
              );
              if (confirm == true) _clearHistory();
            },
          ),
          PopupMenuButton<_DanaPersonality>(
            icon: const Icon(Icons.swap_horiz_rounded),
            tooltip: 'Switch Personality',
            color: AppColors.cardBg,
            onSelected: _switchPersonality,
            itemBuilder: (context) => _DanaPersonality.values.map((personality) {
              final isSelected = personality == _currentPersonality;
              return PopupMenuItem(
                value: personality,
                child: Row(
                  children: [
                    Text(
                      personality.emoji,
                      style: const TextStyle(fontSize: 20),
                    ),
                    const SizedBox(width: 10),
                    Text(
                      personality.name,
                      style: TextStyle(
                        color: isSelected ? personality.color : AppColors.white,
                        fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                      ),
                    ),
                    if (isSelected) ...[
                      const Spacer(),
                      Icon(Icons.check_circle, color: personality.color, size: 18),
                    ],
                  ],
                ),
              );
            }).toList(),
          ),
        ],
      ),
      body: Column(
        children: [
          const NetworkBanner(),
          Expanded(
            child: _messages.isEmpty
                ? Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(
                          _currentPersonality.emoji,
                          style: const TextStyle(fontSize: 64),
                        ),
                        const SizedBox(height: 16),
                        const Text(
                          'Start chatting with Dana',
                          style: TextStyle(
                            color: AppColors.softWhite,
                            fontSize: 16,
                          ),
                        ),
                      ],
                    ),
                  )
                : ListView.builder(
                    controller: _scrollController,
                    padding: const EdgeInsets.all(16),
                    itemCount: _messages.length + (_isTyping ? 1 : 0),
                    itemBuilder: (context, index) {
                      if (_isTyping && index == _messages.length) {
                        return _TypingIndicator(
                          personality: _currentPersonality,
                        );
                      }
                      final message = _messages[index];
                      return _MessageBubble(message: message);
                    },
                  ),
          ),
          _buildInputArea(),
        ],
      ),
    );
  }

  Widget _buildInputArea() {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
      decoration: BoxDecoration(
        color: AppColors.cardBg,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.2),
            blurRadius: 10,
            offset: const Offset(0, -2),
          ),
        ],
      ),
      child: SafeArea(
        top: false,
        child: Row(
          children: [
            Semantics(
              button: true,
              label: 'Voice input',
              child: IconButton(
                onPressed: _startVoiceInput,
                icon: const Icon(Icons.mic_rounded),
                color: AppColors.accent,
                iconSize: 28,
                tooltip: 'Voice input',
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: TextField(
                controller: _messageController,
                style: const TextStyle(color: AppColors.white),
                decoration: InputDecoration(
                  hintText: 'Type a message...',
                  hintStyle: const TextStyle(color: AppColors.softWhite),
                  filled: true,
                  fillColor: AppColors.background,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(24),
                    borderSide: BorderSide.none,
                  ),
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 20,
                    vertical: 12,
                  ),
                ),
                onSubmitted: (_) => _sendMessage(),
                textInputAction: TextInputAction.send,
              ),
            ),
            const SizedBox(width: 8),
            Semantics(
              button: true,
              label: 'Send message',
              child: Container(
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: AppColors.accent,
                  boxShadow: [
                    BoxShadow(
                      color: AppColors.accent.withValues(alpha: 0.4),
                      blurRadius: 12,
                      spreadRadius: 2,
                    ),
                  ],
                ),
                child: IconButton(
                  onPressed: _sendMessage,
                  icon: const Icon(Icons.send_rounded),
                  color: AppColors.background,
                  iconSize: 22,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({required this.message});

  final _Message message;

  @override
  Widget build(BuildContext context) {
    final timeStr =
        '${message.timestamp.hour.toString().padLeft(2, '0')}:'
        '${message.timestamp.minute.toString().padLeft(2, '0')}';

    return Semantics(
      label: '${message.isUser ? 'You' : 'Dana'}: ${message.text}. Sent at $timeStr',
      child: Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Row(
          mainAxisAlignment:
              message.isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (!message.isUser) ...[
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: message.personality?.color.withValues(alpha: 0.2) ??
                      AppColors.accent.withValues(alpha: 0.2),
                ),
                child: Center(
                  child: Text(
                    message.personality?.emoji ?? '🤖',
                    style: const TextStyle(fontSize: 18),
                  ),
                ),
              ),
              const SizedBox(width: 8),
            ],
            Flexible(
              child: GestureDetector(
                onLongPress: () {
                  showDialog<void>(
                    context: context,
                    builder: (_) => AlertDialog(
                      backgroundColor: AppColors.cardBg,
                      content: Text(
                        timeStr,
                        style: const TextStyle(
                            color: AppColors.softWhite, fontSize: 13),
                        textAlign: TextAlign.center,
                      ),
                    ),
                  );
                },
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  decoration: BoxDecoration(
                    color: message.isUser ? AppColors.accent : AppColors.cardBg,
                    borderRadius: BorderRadius.only(
                      topLeft: const Radius.circular(16),
                      topRight: const Radius.circular(16),
                      bottomLeft: Radius.circular(message.isUser ? 16 : 4),
                      bottomRight: Radius.circular(message.isUser ? 4 : 16),
                    ),
                    border: message.isUser
                        ? null
                        : Border.all(
                            color: message.personality
                                    ?.color
                                    .withValues(alpha: 0.3) ??
                                AppColors.accent.withValues(alpha: 0.3),
                          ),
                  ),
                  child: Text(
                    message.text,
                    style: TextStyle(
                      color: message.isUser
                          ? AppColors.background
                          : AppColors.white,
                      fontSize: 14,
                      height: 1.4,
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TypingIndicator extends StatefulWidget {
  const _TypingIndicator({required this.personality});

  final _DanaPersonality personality;

  @override
  State<_TypingIndicator> createState() => _TypingIndicatorState();
}

class _TypingIndicatorState extends State<_TypingIndicator>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: widget.personality.color.withValues(alpha: 0.2),
            ),
            child: Center(
              child: Text(
                widget.personality.emoji,
                style: const TextStyle(fontSize: 18),
              ),
            ),
          ),
          const SizedBox(width: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: AppColors.cardBg,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: widget.personality.color.withValues(alpha: 0.3),
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: List.generate(3, (index) {
                return AnimatedBuilder(
                  animation: _controller,
                  builder: (context, child) {
                    final delay = index * 0.2;
                    final value = (_controller.value - delay) % 1.0;
                    final opacity = (0.3 + (value * 0.7)).clamp(0.3, 1.0);
                    return Container(
                      margin: const EdgeInsets.symmetric(horizontal: 2),
                      width: 8,
                      height: 8,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: AppColors.softWhite.withValues(alpha: opacity),
                      ),
                    );
                  },
                );
              }),
            ),
          ),
        ],
      ),
    );
  }
}

enum _DanaPersonality {
  coach,
  guide,
  therapist;

  String get name {
    switch (this) {
      case _DanaPersonality.coach:
        return 'Coach';
      case _DanaPersonality.guide:
        return 'Guide';
      case _DanaPersonality.therapist:
        return 'Therapist';
    }
  }

  String get emoji {
    switch (this) {
      case _DanaPersonality.coach:
        return '💪';
      case _DanaPersonality.guide:
        return '🌙';
      case _DanaPersonality.therapist:
        return '🧠';
    }
  }

  String get apiKey {
    switch (this) {
      case _DanaPersonality.coach:
        return 'coach';
      case _DanaPersonality.guide:
        return 'guide';
      case _DanaPersonality.therapist:
        return 'therapist';
    }
  }

  Color get color {
    switch (this) {
      case _DanaPersonality.coach:
        return AppColors.orange;
      case _DanaPersonality.guide:
        return AppColors.purple;
      case _DanaPersonality.therapist:
        return AppColors.accent;
    }
  }
}

class _Message {
  const _Message({
    required this.text,
    required this.isUser,
    required this.timestamp,
    this.personality,
  });

  final String text;
  final bool isUser;
  final DateTime timestamp;
  final _DanaPersonality? personality;

  Map<String, dynamic> toJson() => {
        'text': text,
        'isUser': isUser,
        'timestamp': timestamp.toIso8601String(),
        'personality': personality?.name,
      };

  static _Message fromJson(Map<String, dynamic> json) {
    _DanaPersonality? personality;
    final p = json['personality'] as String?;
    if (p != null) {
      personality = _DanaPersonality.values.firstWhere(
        (e) => e.name == p,
        orElse: () => _DanaPersonality.guide,
      );
    }
    return _Message(
      text: json['text'] as String? ?? '',
      isUser: json['isUser'] as bool? ?? false,
      timestamp: DateTime.tryParse(json['timestamp'] as String? ?? '') ??
          DateTime.now(),
      personality: personality,
    );
  }
}
