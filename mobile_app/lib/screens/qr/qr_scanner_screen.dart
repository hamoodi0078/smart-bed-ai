import 'package:flutter/material.dart';

import '../../theme/app_theme.dart';
import '../home/home_screen.dart';

class QRScannerScreen extends StatefulWidget {
  const QRScannerScreen({super.key});

  @override
  State<QRScannerScreen> createState() => _QRScannerScreenState();
}

class _QRScannerScreenState extends State<QRScannerScreen> {
  bool _isScanning = true;
  bool _isPaired = false;
  String _deviceId = '';

  final TextEditingController _deviceController = TextEditingController();

  @override
  void dispose() {
    _deviceController.dispose();
    super.dispose();
  }

  void _goBack() {
    if (Navigator.of(context).canPop()) {
      Navigator.of(context).pop();
      return;
    }
    Navigator.of(context).pushReplacement(
      MaterialPageRoute<void>(builder: (_) => const HomeScreen()),
    );
  }

  void _simulatePairing() {
    final String entered = _deviceController.text.trim();
    if (entered.isEmpty) {
      return;
    }
    FocusScope.of(context).unfocus();
    setState(() {
      _deviceId = entered;
      _isScanning = false;
      _isPaired = true;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0A1628),
      body: _isPaired ? _buildSuccessView() : _buildScanningView(),
    );
  }

  Widget _buildScanningView() {
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
        child: Column(
          children: [
            _buildTopBar(),
            const SizedBox(height: 18),
            if (_isScanning) ...[
              const Icon(
                Icons.qr_code_scanner,
                color: AppColors.accent,
                size: 80,
              ),
              const SizedBox(height: 12),
              const Text(
                "Scan Your Bed's QR Code",
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: AppColors.white,
                  fontSize: 20,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 8),
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 14),
                child: Text(
                  'Find the QR sticker on the side or bottom of your Danah bed frame',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: AppColors.softWhite,
                    fontSize: 14,
                    height: 1.5,
                  ),
                ),
              ),
              const SizedBox(height: 18),
              _buildViewFinder(),
              const SizedBox(height: 20),
            ],
            const Text(
              "Can't scan? Enter code manually",
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppColors.softWhite,
                fontSize: 12,
              ),
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _deviceController,
                    style: const TextStyle(color: AppColors.white, fontSize: 13),
                    decoration: InputDecoration(
                      hintText: 'e.g. DANA-KW-001-X7F2',
                      hintStyle: TextStyle(
                        color: AppColors.softWhite.withValues(alpha: 0.65),
                        fontSize: 12,
                      ),
                      filled: true,
                      fillColor: AppColors.cardBg,
                      contentPadding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 12,
                      ),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: const BorderSide(
                          color: AppColors.accent,
                          width: 1.1,
                        ),
                      ),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: const BorderSide(
                          color: AppColors.accent,
                          width: 1.4,
                        ),
                      ),
                    ),
                    onSubmitted: (_) => _simulatePairing(),
                  ),
                ),
                const SizedBox(width: 8),
                FilledButton(
                  onPressed: _simulatePairing,
                  style: FilledButton.styleFrom(
                    backgroundColor: AppColors.accent,
                    foregroundColor: AppColors.background,
                    padding: const EdgeInsets.symmetric(
                      horizontal: 14,
                      vertical: 13,
                    ),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                  child: const Text(
                    'Connect',
                    style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTopBar() {
    return Row(
      children: [
        IconButton(
          onPressed: _goBack,
          icon: const Icon(Icons.arrow_back_ios_new_rounded),
          color: AppColors.white,
          tooltip: 'Back',
        ),
        const Expanded(
          child: Text(
            'Connect Your Bed 🛏️',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: AppColors.white,
              fontSize: 20,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
        const SizedBox(width: 48),
      ],
    );
  }

  Widget _buildViewFinder() {
    return SizedBox(
      width: 250,
      height: 250,
      child: Stack(
        children: [
          Container(
            width: 250,
            height: 250,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(18),
              border: Border.all(
                color: AppColors.accent.withValues(alpha: 0.8),
                width: 1.2,
              ),
              color: AppColors.cardBg.withValues(alpha: 0.25),
            ),
            alignment: Alignment.center,
            child: const Text(
              'Camera Preview',
              style: TextStyle(
                color: Color(0xFF9E9E9E),
                fontSize: 14,
              ),
            ),
          ),
          Positioned(
            top: 0,
            left: 0,
            child: _buildCornerBracket(isTop: true, isLeft: true),
          ),
          Positioned(
            top: 0,
            right: 0,
            child: _buildCornerBracket(isTop: true, isLeft: false),
          ),
          Positioned(
            bottom: 0,
            left: 0,
            child: _buildCornerBracket(isTop: false, isLeft: true),
          ),
          Positioned(
            bottom: 0,
            right: 0,
            child: _buildCornerBracket(isTop: false, isLeft: false),
          ),
        ],
      ),
    );
  }

  Widget _buildCornerBracket({
    required bool isTop,
    required bool isLeft,
  }) {
    const BorderSide borderSide = BorderSide(
      color: AppColors.accent,
      width: 3,
    );
    return Container(
      width: 20,
      height: 20,
      decoration: BoxDecoration(
        border: Border(
          top: isTop ? borderSide : BorderSide.none,
          bottom: isTop ? BorderSide.none : borderSide,
          left: isLeft ? borderSide : BorderSide.none,
          right: isLeft ? BorderSide.none : borderSide,
        ),
      ),
    );
  }

  Widget _buildSuccessView() {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(
              Icons.check_circle,
              color: AppColors.accent,
              size: 100,
            ),
            const SizedBox(height: 16),
            const Text(
              'Bed Connected! 🎉',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppColors.white,
                fontSize: 24,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Device ID: $_deviceId',
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: AppColors.accent,
                fontSize: 14,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 18),
            const Text(
              "MashaAllah! Your bed is now connected. I am Dana, your sleep companion. Let's set up your profile!",
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppColors.softWhite,
                fontSize: 14,
                fontStyle: FontStyle.italic,
                height: 1.5,
              ),
            ),
            const SizedBox(height: 28),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: () {
                  Navigator.of(context).pushAndRemoveUntil(
                    MaterialPageRoute<void>(builder: (_) => const HomeScreen()),
                    (route) => false,
                  );
                },
                style: FilledButton.styleFrom(
                  backgroundColor: AppColors.accent,
                  foregroundColor: AppColors.background,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(16),
                  ),
                ),
                child: const Text(
                  'Continue to Setup →',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
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
