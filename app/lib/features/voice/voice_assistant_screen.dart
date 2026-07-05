import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:go_router/go_router.dart';
import 'package:speech_to_text/speech_to_text.dart';

import '../../core/design/app_colors.dart';
import '../../core/design/app_spacing.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/gradient_button.dart';
import '../../domain/voice_intent.dart';
import 'voice_assistant_controller.dart';

/// Metro Assistant: a voice-first companion that answers metro-related
/// questions only — never a general-purpose chatbot. Speech is classified by
/// [parseVoiceIntent] (a fixed set of intents) and answered by
/// [VoiceAssistantController] using the app's real, existing data, then
/// spoken back with text-to-speech.
class VoiceAssistantScreen extends ConsumerStatefulWidget {
  const VoiceAssistantScreen({super.key});

  @override
  ConsumerState<VoiceAssistantScreen> createState() => _VoiceAssistantScreenState();
}

class _VoiceAssistantScreenState extends ConsumerState<VoiceAssistantScreen> {
  final SpeechToText _speech = SpeechToText();
  final FlutterTts _tts = FlutterTts();
  bool _speechAvailable = false;
  bool _listening = false;
  bool _thinking = false;
  String _transcript = '';
  String? _response;
  String? _error;

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    final available = await _speech.initialize(
      onStatus: (status) {
        if ((status == 'notListening' || status == 'done') && mounted) {
          setState(() => _listening = false);
        }
      },
      onError: (error) {
        if (!mounted) return;
        setState(() {
          _listening = false;
          _error = "I couldn't hear that — try again.";
        });
      },
    );
    await _tts.setLanguage('en-IN');
    await _tts.setSpeechRate(0.48);
    if (mounted) setState(() => _speechAvailable = available);
  }

  @override
  void dispose() {
    _speech.stop();
    _tts.stop();
    super.dispose();
  }

  Future<void> _toggleListening() async {
    if (_listening) {
      await _speech.stop();
      if (mounted) setState(() => _listening = false);
      return;
    }
    if (!_speechAvailable) {
      setState(() => _error = "Voice input isn't available on this device.");
      return;
    }
    setState(() {
      _error = null;
      _response = null;
      _transcript = '';
      _listening = true;
    });
    await _speech.listen(
      onResult: (result) async {
        if (!mounted) return;
        setState(() => _transcript = result.recognizedWords);
        if (result.finalResult) {
          await _handleFinalTranscript(result.recognizedWords);
        }
      },
    );
  }

  Future<void> _handleFinalTranscript(String text) async {
    if (text.trim().isEmpty) {
      if (mounted) setState(() => _listening = false);
      return;
    }
    setState(() {
      _listening = false;
      _thinking = true;
    });
    final intent = parseVoiceIntent(text);
    final answer = await ref.read(voiceAssistantControllerProvider).answer(intent);
    if (!mounted) return;
    setState(() {
      _thinking = false;
      _response = answer;
    });
    await _tts.speak(answer);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final statusText = _listening
        ? 'Listening…'
        : _thinking
            ? 'Thinking…'
            : 'Ask about your journey';

    return Scaffold(
      body: AmbientBackground(
        intensity: 1.2,
        child: SafeArea(
          child: Column(
            children: [
              Padding(
                padding: const EdgeInsets.all(AppSpacing.lg),
                child: Row(
                  children: [
                    IconPillButton(icon: Icons.close_rounded, onPressed: () => context.pop()),
                  ],
                ),
              ),
              Expanded(
                child: Center(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xxl),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Container(
                          width: 72,
                          height: 72,
                          decoration: BoxDecoration(gradient: AppColors.heroGradientFor(), shape: BoxShape.circle),
                          child: const Icon(Icons.directions_subway_filled, color: Colors.white, size: 32),
                        ),
                        const SizedBox(height: AppSpacing.lg),
                        Text('Metro Assistant', style: theme.textTheme.headlineMedium),
                        const SizedBox(height: AppSpacing.sm),
                        Text(statusText, style: theme.textTheme.bodyLarge),
                        const SizedBox(height: AppSpacing.xxxl),
                        if (_transcript.isNotEmpty)
                          Padding(
                            padding: const EdgeInsets.only(bottom: AppSpacing.lg),
                            child: GlassSurface(child: Text('"$_transcript"', style: theme.textTheme.titleMedium)),
                          ),
                        if (_response != null)
                          GlassSurface(
                            gradient: AppColors.heroGradientFor(),
                            border: false,
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Icon(Icons.directions_subway_filled, color: Colors.white, size: 20),
                                const SizedBox(width: AppSpacing.md),
                                Expanded(
                                  child: Text(
                                    _response!,
                                    style: const TextStyle(
                                        color: Colors.white, fontSize: 15, fontWeight: FontWeight.w600, height: 1.4),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        if (_error != null)
                          Padding(
                            padding: const EdgeInsets.only(top: AppSpacing.lg),
                            child: Text(_error!, style: TextStyle(color: theme.colorScheme.error)),
                          ),
                        const SizedBox(height: AppSpacing.xl),
                        const Wrap(
                          alignment: WrapAlignment.center,
                          spacing: AppSpacing.sm,
                          runSpacing: AppSpacing.sm,
                          children: [
                            _SamplePrompt('When should I leave?'),
                            _SamplePrompt('Which coach should I board?'),
                            _SamplePrompt('What is my next station?'),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.giant),
                child: _MicButton(listening: _listening, onTap: _toggleListening),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SamplePrompt extends StatelessWidget {
  const _SamplePrompt(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerHighest.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(text, style: Theme.of(context).textTheme.labelMedium),
    );
  }
}

class _MicButton extends StatefulWidget {
  const _MicButton({required this.listening, required this.onTap});

  final bool listening;
  final VoidCallback onTap;

  @override
  State<_MicButton> createState() => _MicButtonState();
}

class _MicButtonState extends State<_MicButton> with SingleTickerProviderStateMixin {
  late final AnimationController _pulse =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 1200))..repeat(reverse: true);

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: widget.onTap,
      child: AnimatedBuilder(
        animation: _pulse,
        builder: (context, child) {
          final scale = widget.listening ? 1.0 + _pulse.value * 0.12 : 1.0;
          return Transform.scale(
            scale: scale,
            child: Container(
              width: 84,
              height: 84,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: AppColors.heroGradientFor(),
                boxShadow: [
                  BoxShadow(
                    color: AppColors.brandViolet.withValues(alpha: widget.listening ? 0.6 : 0.35),
                    blurRadius: widget.listening ? 36 : 20,
                    spreadRadius: widget.listening ? 4 : 0,
                  ),
                ],
              ),
              child: Icon(widget.listening ? Icons.mic_rounded : Icons.mic_none_rounded,
                  color: Colors.white, size: 36),
            ),
          );
        },
      ),
    );
  }
}
