import 'package:flutter/material.dart';

import '../../services/api_service.dart';
import '../../theme/app_theme.dart';

class DanaChatScreen extends StatefulWidget {
  const DanaChatScreen({super.key});

  @override
  State<DanaChatScreen> createState() => _DanaChatScreenState();
}

class _DanaChatScreenState extends State<DanaChatScreen> {
  final List<Map<String, String>> _messages = <Map<String, String>>[];
  final TextEditingController _inputController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  bool _isTyping = false;

  @override
  void initState() {
    super.initState();
    _messages.add(<String, String>{
      'role': 'dana',
      'text':
          "As-salamu alaykum! I'm Dana, your sleep companion. ðŸŒ™ How can I help you tonight? You can ask me to adjust your lights, set an alarm, or just talk about your sleep.",
      'time': _formatTime(DateTime.now()),
    });
    WidgetsBinding.instance.addPostFrameCallback((_) => _scrollToBottom());
  }

  @override
  void dispose() {
    _inputController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  String _formatTime(DateTime time) {
    final String hour = time.hour.toString().padLeft(2, '0');
    final String minute = time.minute.toString().padLeft(2, '0');
    return '$hour:$minute';
  }

  void _scrollToBottom() {
    if (!_scrollController.hasClients) {
      return;
    }
    _scrollController.animateTo(
      _scrollController.position.maxScrollExtent + 120,
      duration: const Duration(milliseconds: 260),
      curve: Curves.easeOut,
    );
  }

  Future<void> _handleSend() async {
    final String userMessage = _inputController.text.trim();
    if (userMessage.isEmpty) {
      return;
    }

    setState(() {
      _messages.add(<String, String>{
        'role': 'user',
        'text': userMessage,
        'time': _formatTime(DateTime.now()),
      });
      _isTyping = true;
    });
    _inputController.clear();
    WidgetsBinding.instance.addPostFrameCallback((_) => _scrollToBottom());

    final String reply = await ApiService.sendMessage(userMessage);
    if (!mounted) {
      return;
    }

    setState(() {
      _isTyping = false;
      _messages.add(<String, String>{
        'role': 'dana',
        'text': reply,
        'time': _formatTime(DateTime.now()),
      });
    });
    WidgetsBinding.instance.addPostFrameCallback((_) => _scrollToBottom());
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0A1628),
      body: SafeArea(
        child: Column(
          children: [
            _buildTopBar(),
            Expanded(
              child: ListView.builder(
                controller: _scrollController,
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
                itemCount: _messages.length + (_isTyping ? 1 : 0),
                itemBuilder: (context, index) {
                  if (index >= _messages.length) {
                    return _buildTypingBubble();
                  }
                  return _buildMessageBubble(_messages[index]);
                },
              ),
            ),
            _buildInputBar(),
          ],
        ),
      ),
    );
  }

  Widget _buildTopBar() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 6, 8, 8),
      child: Row(
        children: [
          IconButton(
            onPressed: () => Navigator.of(context).maybePop(),
            icon: const Icon(Icons.arrow_back_ios_new_rounded),
            color: AppColors.white,
            tooltip: 'Back',
          ),
          Expanded(
            child: Center(
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 30,
                    height: 30,
                    decoration: const BoxDecoration(
                      color: AppColors.accent,
                      shape: BoxShape.circle,
                    ),
                    child: const Icon(
                      Icons.auto_awesome,
                      size: 16,
                      color: AppColors.background,
                    ),
                  ),
                  const SizedBox(width: 8),
                  const Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Dana',
                        style: TextStyle(
                          color: AppColors.white,
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      Text(
                        'Your Sleep Companion',
                        style: TextStyle(
                          color: Color(0xFF9CA6BF),
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
          Container(
            width: 10,
            height: 10,
            decoration: const BoxDecoration(
              color: Color(0xFF4CAF50),
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 14),
        ],
      ),
    );
  }

  Widget _buildMessageBubble(Map<String, String> message) {
    final bool isUser = message['role'] == 'user';
    final String text = message['text'] ?? '';
    final String time = message['time'] ?? '';

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Align(
        alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 290),
          child: Column(
            crossAxisAlignment:
                isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 14,
                  vertical: 11,
                ),
                decoration: BoxDecoration(
                  color: isUser ? AppColors.accent : const Color(0xFF1A2740),
                  borderRadius: isUser
                      ? const BorderRadius.only(
                          topLeft: Radius.circular(16),
                          topRight: Radius.circular(16),
                          bottomLeft: Radius.circular(16),
                        )
                      : const BorderRadius.only(
                          topLeft: Radius.circular(16),
                          topRight: Radius.circular(16),
                          bottomRight: Radius.circular(16),
                        ),
                ),
                child: Text(
                  text,
                  style: TextStyle(
                    color: isUser ? AppColors.background : AppColors.white,
                    fontSize: 14,
                    height: 1.45,
                  ),
                ),
              ),
              const SizedBox(height: 4),
              Text(
                time,
                style: TextStyle(
                  color: AppColors.softWhite.withValues(alpha: 0.5),
                  fontSize: 10,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTypingBubble() {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Align(
        alignment: Alignment.centerLeft,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 290),
          child: AnimatedOpacity(
            opacity: _isTyping ? 1 : 0,
            duration: const Duration(milliseconds: 280),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
              decoration: const BoxDecoration(
                color: Color(0xFF1A2740),
                borderRadius: BorderRadius.only(
                  topLeft: Radius.circular(16),
                  topRight: Radius.circular(16),
                  bottomRight: Radius.circular(16),
                ),
              ),
              child: const Text(
                'Dana is thinking... ðŸ’­',
                style: TextStyle(
                  color: Color(0xFFA7B4D3),
                  fontSize: 13,
                  fontStyle: FontStyle.italic,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildInputBar() {
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 14),
      decoration: const BoxDecoration(
        color: Color(0xFF111D34),
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(18),
          topRight: Radius.circular(18),
        ),
      ),
      child: SafeArea(
        top: false,
        child: Row(
          children: [
            Expanded(
              child: Container(
                decoration: BoxDecoration(
                  color: const Color(0xFF1A2740),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: TextField(
                  controller: _inputController,
                  style: const TextStyle(
                    color: AppColors.white,
                    fontSize: 14,
                  ),
                  cursorColor: AppColors.accent,
                  textInputAction: TextInputAction.send,
                  onSubmitted: (_) => _handleSend(),
                  decoration: InputDecoration(
                    hintText: 'Ask Dana anything...',
                    hintStyle: TextStyle(
                      color: AppColors.softWhite.withValues(alpha: 0.6),
                    ),
                    border: InputBorder.none,
                    contentPadding: const EdgeInsets.symmetric(
                      horizontal: 14,
                      vertical: 12,
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(width: 10),
            InkWell(
              onTap: _handleSend,
              borderRadius: BorderRadius.circular(30),
              child: Container(
                width: 44,
                height: 44,
                decoration: const BoxDecoration(
                  color: AppColors.accent,
                  shape: BoxShape.circle,
                ),
                child: const Icon(
                  Icons.send,
                  color: AppColors.white,
                  size: 20,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

