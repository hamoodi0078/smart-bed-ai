import 'dart:async';
import 'package:flutter/material.dart';
import '../../theme/app_theme.dart';
import '../../services/api_service.dart';
import '../../widgets/error_state.dart';

class ScenesGalleryScreen extends StatefulWidget {
  const ScenesGalleryScreen({super.key});

  @override
  State<ScenesGalleryScreen> createState() => _ScenesGalleryScreenState();
}

class _ScenesGalleryScreenState extends State<ScenesGalleryScreen> {
  List<_Scene> _scenes = [];
  bool _isLoading = true;
  String? _errorMessage;
  String? _previewingSceneId;
  Timer? _previewTimer;

  @override
  void initState() {
    super.initState();
    _loadScenes();
  }

  @override
  void dispose() {
    _previewTimer?.cancel();
    super.dispose();
  }

  Future<void> _loadScenes() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final response = await ApiService.getScenes();
      if (response['error'] == true) {
        throw Exception(response['message'] ?? 'Failed to load scenes');
      }

      final scenesList = response['items'] as List<dynamic>? ?? [];
      if (mounted) {
        setState(() {
          _scenes = scenesList.map((data) => _Scene.fromJson(data)).toList();
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _errorMessage = e.toString().replaceAll('Exception: ', '');
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _activateScene(_Scene scene) async {
    try {
      await ApiService.activateScene(scene.id);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('${scene.name} activated!'),
            backgroundColor: AppColors.accent,
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to activate scene: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  void _previewScene(_Scene scene) {
    setState(() {
      _previewingSceneId = scene.id;
    });

    _previewTimer?.cancel();
    _previewTimer = Timer(const Duration(seconds: 3), () {
      if (mounted) {
        setState(() {
          _previewingSceneId = null;
        });
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.background,
        foregroundColor: AppColors.white,
        elevation: 0,
        title: const Text(
          'Scenes Gallery',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh_rounded),
            onPressed: _loadScenes,
          ),
        ],
      ),
      body: _isLoading
          ? const Center(
              child: CircularProgressIndicator(color: AppColors.accent),
            )
          : _errorMessage != null
              ? ErrorState(
                  message: _errorMessage!,
                  onRetry: _loadScenes,
                )
              : _scenes.isEmpty
                  ? const EmptyState(
                      title: 'No Scenes Available',
                      message: 'Scene library will be available soon',
                      icon: Icons.palette_rounded,
                    )
                  : RefreshIndicator(
                      color: AppColors.accent,
                      onRefresh: _loadScenes,
                      child: GridView.builder(
                        padding: const EdgeInsets.all(16),
                        gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                          crossAxisCount: 2,
                          childAspectRatio: 0.75,
                          crossAxisSpacing: 12,
                          mainAxisSpacing: 12,
                        ),
                        itemCount: _scenes.length,
                        itemBuilder: (context, index) {
                          return _SceneCard(
                            scene: _scenes[index],
                            isPreviewing: _previewingSceneId == _scenes[index].id,
                            onPreview: () => _previewScene(_scenes[index]),
                            onActivate: () => _activateScene(_scenes[index]),
                          );
                        },
                      ),
                    ),
    );
  }
}

class _SceneCard extends StatelessWidget {
  const _SceneCard({
    required this.scene,
    required this.isPreviewing,
    required this.onPreview,
    required this.onActivate,
  });

  final _Scene scene;
  final bool isPreviewing;
  final VoidCallback onPreview;
  final VoidCallback onActivate;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onActivate,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 300),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(20),
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              scene.color.withValues(alpha: isPreviewing ? 0.4 : 0.2),
              scene.color.withValues(alpha: isPreviewing ? 0.2 : 0.05),
            ],
          ),
          border: Border.all(
            color: isPreviewing
                ? scene.color
                : scene.color.withValues(alpha: 0.3),
            width: isPreviewing ? 2 : 1,
          ),
          boxShadow: isPreviewing
              ? [
                  BoxShadow(
                    color: scene.color.withValues(alpha: 0.5),
                    blurRadius: 20,
                    spreadRadius: 5,
                  ),
                ]
              : [],
        ),
        child: Stack(
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: scene.color.withValues(alpha: 0.2),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Icon(
                          scene.icon,
                          color: scene.color,
                          size: 28,
                        ),
                      ),
                      const Spacer(),
                      if (scene.isPremium)
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 8,
                            vertical: 4,
                          ),
                          decoration: BoxDecoration(
                            color: AppColors.gold.withValues(alpha: 0.2),
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(
                              color: AppColors.gold,
                              width: 1,
                            ),
                          ),
                          child: const Row(
                            children: [
                              Icon(
                                Icons.star_rounded,
                                color: AppColors.gold,
                                size: 12,
                              ),
                              SizedBox(width: 2),
                              Text(
                                'PRO',
                                style: TextStyle(
                                  color: AppColors.gold,
                                  fontSize: 10,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                            ],
                          ),
                        ),
                    ],
                  ),
                  const Spacer(),
                  Text(
                    scene.name,
                    style: const TextStyle(
                      color: AppColors.white,
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    scene.description,
                    style: TextStyle(
                      color: AppColors.softWhite.withValues(alpha: 0.8),
                      fontSize: 12,
                      height: 1.3,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton(
                          onPressed: onPreview,
                          style: OutlinedButton.styleFrom(
                            foregroundColor: scene.color,
                            side: BorderSide(color: scene.color),
                            padding: const EdgeInsets.symmetric(vertical: 8),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(10),
                            ),
                          ),
                          child: Text(
                            isPreviewing ? 'Previewing...' : 'Preview',
                            style: const TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            if (isPreviewing)
              Positioned.fill(
                child: Container(
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(20),
                    gradient: RadialGradient(
                      colors: [
                        scene.color.withValues(alpha: 0.3),
                        Colors.transparent,
                      ],
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

class _Scene {
  const _Scene({
    required this.id,
    required this.name,
    required this.description,
    required this.color,
    required this.icon,
    required this.isPremium,
  });

  final String id;
  final String name;
  final String description;
  final Color color;
  final IconData icon;
  final bool isPremium;

  factory _Scene.fromJson(Map<String, dynamic> json) {
    final colorHex = json['color'] as String? ?? '#00D4FF';
    Color sceneColor = AppColors.accent;
    try {
      sceneColor = Color(
        int.parse(colorHex.replaceFirst('#', '0xFF')),
      );
    } catch (_) {}

    IconData sceneIcon = Icons.palette_rounded;
    final iconName = json['icon'] as String? ?? '';
    if (iconName.contains('sunrise')) {
      sceneIcon = Icons.wb_sunny_rounded;
    } else if (iconName.contains('moon') || iconName.contains('night')) {
      sceneIcon = Icons.nightlight_round;
    } else if (iconName.contains('ocean') || iconName.contains('water')) {
      sceneIcon = Icons.waves_rounded;
    } else if (iconName.contains('fire') || iconName.contains('warm')) {
      sceneIcon = Icons.local_fire_department_rounded;
    } else if (iconName.contains('star')) {
      sceneIcon = Icons.star_rounded;
    } else if (iconName.contains('cloud')) {
      sceneIcon = Icons.cloud_rounded;
    }

    return _Scene(
      id: json['scene_id'] as String? ?? json['id'] as String? ?? '',
      name: json['name'] as String? ?? 'Untitled Scene',
      description: json['description'] as String? ?? '',
      color: sceneColor,
      icon: sceneIcon,
      isPremium: json['premium'] as bool? ?? false,
    );
  }
}
