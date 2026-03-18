import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/models.dart';
import '../../state/auth_controller.dart';
import '../../state/mobile_data.dart';
import '../theme.dart';
import '../widgets/panel_card.dart';
import '../widgets/status_pill.dart';

class DanaChatScreen extends ConsumerStatefulWidget {
  const DanaChatScreen({super.key});

  @override
  ConsumerState<DanaChatScreen> createState() => _DanaChatScreenState();
}

class _DanaChatScreenState extends ConsumerState<DanaChatScreen> {
  final TextEditingController _inputController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final List<_ChatMessage> _messages = <_ChatMessage>[];
  bool _isTyping = false;

  @override
  void initState() {
    super.initState();
    _messages.add(
      _ChatMessage(
        role: _ChatRole.dana,
        text:
            'As-salamu alaykum. I\'m Dana, live and connected to your Danah account. Ask about your sleep, routines, lights, or tonight\'s prayer timing.',
        timestamp: DateTime.now(),
      ),
    );
  }

  @override
  void dispose() {
    _inputController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _sendCurrentMessage() async {
    final message = _inputController.text.trim();
    if (message.isEmpty || _isTyping) {
      return;
    }
    _inputController.clear();
    await _sendMessage(message);
  }

  Future<void> _sendMessage(String message) async {
    setState(() {
      _messages.add(
        _ChatMessage(
          role: _ChatRole.user,
          text: message,
          timestamp: DateTime.now(),
        ),
      );
      _isTyping = true;
    });
    _scrollToBottom();

    try {
      final reply = await ref
          .read(smartBedRepositoryProvider)
          .sendChatMessage(message);
      if (!mounted) {
        return;
      }
      setState(() {
        _messages.add(
          _ChatMessage(
            role: _ChatRole.dana,
            text: reply,
            timestamp: DateTime.now(),
          ),
        );
      });
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _messages.add(
          _ChatMessage(
            role: _ChatRole.dana,
            text: error.message,
            timestamp: DateTime.now(),
          ),
        );
      });
    } finally {
      if (mounted) {
        setState(() {
          _isTyping = false;
        });
        _scrollToBottom();
      }
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) {
        return;
      }
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent + 80,
        duration: const Duration(milliseconds: 220),
        curve: Curves.easeOut,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final session = ref.watch(authControllerProvider).session;
    final settingsBundle = ref.watch(settingsBundleProvider).valueOrNull;
    final fallbackUser = const MobileUser(
      userId: '',
      email: 'user@example.com',
      name: 'User',
      clientName: '',
    );
    final userName = settingsBundle?.profile.resolvedDisplayName(session?.user ?? fallbackUser) ??
        session?.user.firstName ??
        'You';

    return SafeArea(
      bottom: false,
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1100),
          child: Column(
            children: <Widget>[
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 12),
                child: PanelCard(
                  child: Row(
                    children: <Widget>[
                      Container(
                        width: 52,
                        height: 52,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: SmartBedPalette.accent.withValues(alpha: 0.14),
                        ),
                        child: const Icon(
                          Icons.auto_awesome_rounded,
                          color: SmartBedPalette.accent,
                        ),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            Text('Dana', style: theme.textTheme.titleLarge),
                            const SizedBox(height: 2),
                            Text(
                              'Live AI companion for $userName',
                              style: theme.textTheme.bodyMedium,
                            ),
                          ],
                        ),
                      ),
                      const StatusPill(label: 'Dana Live', tone: StatusTone.success),
                    ],
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Wrap(
                    spacing: 10,
                    runSpacing: 10,
                    children: _suggestedPrompts
                        .map(
                          (prompt) => ActionChip(
                            label: Text(prompt),
                            onPressed: _isTyping ? null : () => _sendMessage(prompt),
                          ),
                        )
                        .toList(growable: false),
                  ),
                ),
              ),
              const SizedBox(height: 12),
              Expanded(
                child: ListView.builder(
                  controller: _scrollController,
                  padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
                  itemCount: _messages.length + (_isTyping ? 1 : 0),
                  itemBuilder: (context, index) {
                    if (_isTyping && index == _messages.length) {
                      return const _TypingBubble();
                    }
                    final message = _messages[index];
                    return _MessageBubble(message: message);
                  },
                ),
              ),
              Container(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
                decoration: BoxDecoration(
                  color: SmartBedPalette.surface(theme.brightness).withValues(alpha: 0.94),
                  borderRadius: const BorderRadius.vertical(top: Radius.circular(26)),
                  border: Border.all(
                    color: SmartBedPalette.accent.withValues(alpha: 0.14),
                  ),
                ),
                child: Row(
                  children: <Widget>[
                    Expanded(
                      child: TextField(
                        controller: _inputController,
                        minLines: 1,
                        maxLines: 4,
                        onSubmitted: (_) => _sendCurrentMessage(),
                        decoration: const InputDecoration(
                          hintText: 'Ask Dana about your sleep, prayer timings, or routines...',
                          prefixIcon: Icon(Icons.chat_bubble_outline_rounded),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    FilledButton(
                      onPressed: _isTyping ? null : _sendCurrentMessage,
                      style: FilledButton.styleFrom(
                        shape: const CircleBorder(),
                        padding: const EdgeInsets.all(16),
                      ),
                      child: _isTyping
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.send_rounded),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({required this.message});

  final _ChatMessage message;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isUser = message.role == _ChatRole.user;
    final alignment = isUser ? Alignment.centerRight : Alignment.centerLeft;
    final background = isUser
        ? SmartBedPalette.accent
        : SmartBedPalette.surfaceAlt(theme.brightness);
    final foreground = isUser
        ? SmartBedPalette.background
        : theme.textTheme.bodyLarge?.color ?? Colors.white;

    return Align(
      alignment: alignment,
      child: Padding(
        padding: const EdgeInsets.only(bottom: 14),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 720),
          child: Column(
            crossAxisAlignment: isUser
                ? CrossAxisAlignment.end
                : CrossAxisAlignment.start,
            children: <Widget>[
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                decoration: BoxDecoration(
                  color: background,
                  borderRadius: BorderRadius.only(
                    topLeft: const Radius.circular(22),
                    topRight: const Radius.circular(22),
                    bottomLeft: Radius.circular(isUser ? 22 : 8),
                    bottomRight: Radius.circular(isUser ? 8 : 22),
                  ),
                ),
                child: Text(
                  message.text,
                  style: theme.textTheme.bodyLarge?.copyWith(color: foreground),
                ),
              ),
              const SizedBox(height: 6),
              Text(
                _timeLabel(message.timestamp),
                style: theme.textTheme.bodySmall,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _TypingBubble extends StatelessWidget {
  const _TypingBubble();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Align(
      alignment: Alignment.centerLeft,
      child: Padding(
        padding: const EdgeInsets.only(bottom: 14),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          decoration: BoxDecoration(
            color: SmartBedPalette.surfaceAlt(theme.brightness),
            borderRadius: const BorderRadius.only(
              topLeft: Radius.circular(22),
              topRight: Radius.circular(22),
              bottomRight: Radius.circular(22),
              bottomLeft: Radius.circular(8),
            ),
          ),
          child: Text(
            'Dana is thinking...',
            style: theme.textTheme.bodyMedium?.copyWith(fontStyle: FontStyle.italic),
          ),
        ),
      ),
    );
  }
}

class _ChatMessage {
  const _ChatMessage({
    required this.role,
    required this.text,
    required this.timestamp,
  });

  final _ChatRole role;
  final String text;
  final DateTime timestamp;
}

enum _ChatRole { user, dana }

const _suggestedPrompts = <String>[
  'How should I wind down tonight?',
  'What is the next prayer time?',
  'Set a calmer bedtime routine for me.',
  'How did my sleep look this week?',
];

String _timeLabel(DateTime timestamp) {
  final hour = timestamp.hour % 12 == 0 ? 12 : timestamp.hour % 12;
  final minute = timestamp.minute.toString().padLeft(2, '0');
  final suffix = timestamp.hour >= 12 ? 'PM' : 'AM';
  return '$hour:$minute $suffix';
}
