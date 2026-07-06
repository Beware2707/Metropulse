import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:go_router/go_router.dart';
import 'package:speech_to_text/speech_to_text.dart';

import '../../core/design/app_colors.dart';
import '../../core/design/app_motion.dart';
import '../../core/design/app_radius.dart';
import '../../core/design/app_spacing.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/gradient_button.dart';
import '../../domain/voice_intent.dart';
import '../home/home_providers.dart';
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
  VoiceAnswer? _response;

  /// A benign, retryable hiccup (e.g. speech recognition simply mis-heard
  /// something) — rendered in the screen's calm default text style, never
  /// red, since nothing is actually broken.
  String? _softError;

  /// A genuine capability failure (voice input unavailable on this device at
  /// all) — the only error state serious enough to render in
  /// [ColorScheme.error].
  String? _capabilityError;

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
          _capabilityError = null;
          _softError = "I couldn't hear that — try again.";
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
      setState(() {
        _softError = null;
        _capabilityError = "Voice input isn't available on this device.";
      });
      return;
    }
    setState(() {
      _softError = null;
      _capabilityError = null;
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
      _transcript = text;
      _response = null;
      _softError = null;
      _capabilityError = null;
    });
    final intent = parseVoiceIntent(text);
    final answer = await ref.read(voiceAssistantControllerProvider).answer(intent);
    if (!mounted) return;
    setState(() {
      _thinking = false;
      _response = answer;
    });
    await _tts.speak(answer.text);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    final commuteCard = ref.watch(commuteCardProvider).valueOrNull;
    final statusText = _listening
        ? 'Listening…'
        : _thinking
            ? 'Thinking…'
            : commuteCard != null
                ? 'Ask about your trip to ${commuteCard.destinationName}'
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
                            child: _response != null
                                ? Text(
                                    '"$_transcript"',
                                    style: theme.textTheme.bodySmall
                                        ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                                  )
                                : GlassSurface(child: Text('"$_transcript"', style: theme.textTheme.titleMedium)),
                          ),
                        if (_response != null)
                          GlassSurface(
                            gradient: AppColors.heroGradientFor(),
                            border: false,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    const Icon(Icons.directions_subway_filled, color: Colors.white, size: 20),
                                    const SizedBox(width: AppSpacing.md),
                                    Expanded(
                                      child: Text(
                                        _response!.text,
                                        style: theme.textTheme.headlineSmall?.copyWith(
                                          color: Colors.white,
                                          fontSize: 22,
                                          fontWeight: FontWeight.w700,
                                          height: 1.3,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                                if (_response!.isLive != null) ...[
                                  const SizedBox(height: AppSpacing.md),
                                  _LiveSourcePill(isLive: _response!.isLive!),
                                ],
                              ],
                            ),
                          ),
                        if (_softError != null)
                          Padding(
                            padding: const EdgeInsets.only(top: AppSpacing.lg),
                            child: Text(_softError!, style: theme.textTheme.bodyLarge),
                          ),
                        if (_capabilityError != null)
                          Padding(
                            padding: const EdgeInsets.only(top: AppSpacing.lg),
                            child: Text(_capabilityError!, style: TextStyle(color: theme.colorScheme.error)),
                          ),
                        const SizedBox(height: AppSpacing.xl),
                        AnimatedOpacity(
                          opacity: _response == null ? 1.0 : 0.0,
                          duration: reduceMotion ? Duration.zero : AppMotion.fast,
                          curve: AppMotion.standard,
                          child: IgnorePointer(
                            ignoring: _response != null,
                            child: Wrap(
                              alignment: WrapAlignment.center,
                              spacing: AppSpacing.sm,
                              runSpacing: AppSpacing.sm,
                              children: [
                                for (final prompt in _samplePrompts(ref))
                                  _SamplePrompt(prompt, onTap: _handleFinalTranscript),
                              ],
                            ),
                          ),
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

/// Compact echo of Journey Mode's "LIVE TRACKING" / "SCHEDULED ESTIMATE" pill
/// (see journey_mode_screen.dart), reused verbatim here so the assistant
/// never implies more certainty than the underlying data actually has.
class _LiveSourcePill extends StatelessWidget {
  const _LiveSourcePill({required this.isLive});

  final bool isLive;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = isLive ? AppColors.live : Colors.white;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.2),
        borderRadius: AppRadius.pillR,
      ),
      child: Text(
        isLive ? 'LIVE TRACKING' : 'SCHEDULED ESTIMATE',
        style: theme.textTheme.labelSmall?.copyWith(color: color),
      ),
    );
  }
}

/// Generic prompts shown when the user has an active journey, a known
/// commute, and a favourite set aren't distinguishing enough — i.e. the
/// existing fallback set, unchanged.
const _genericPrompts = [
  'When should I leave?',
  "I'm running late",
  'Which coach should I board?',
  'What is my next station?',
];

/// Chooses the four sample prompts based on real app state, most relevant
/// first: an active journey beats a known commute beats a true cold start,
/// each falling back to the generic set otherwise. Every prompt here is
/// confirmed answerable by [VoiceAssistantController] via [parseVoiceIntent].
List<String> _samplePrompts(WidgetRef ref) {
  final journey = ref.watch(activeJourneyProvider).valueOrNull;
  if (journey != null) {
    return const [
      'Which coach should I board?',
      'What is my next station?',
      'Am I going the right way?',
      "I'm running late",
    ];
  }
  final commuteCard = ref.watch(commuteCardProvider).valueOrNull;
  if (commuteCard != null) {
    return const [
      'When should I leave?',
      "I'm running late",
      'Which coach should I board?',
      'What is the fare?',
    ];
  }
  final favourites = ref.watch(favouriteStationsProvider).valueOrNull ?? const [];
  if (favourites.isEmpty) {
    return const [
      'How do I get to Rajiv Chowk?',
      'How do I get to Connaught Place?',
      "What's the fare to Connaught Place?",
      'When should I leave?',
    ];
  }
  return _genericPrompts;
}

/// A tappable example question — tapping it answers immediately, exactly as
/// if it had been spoken, so the "instant answer, no long conversation"
/// promise is demonstrable without a working microphone.
class _SamplePrompt extends StatefulWidget {
  const _SamplePrompt(this.text, {required this.onTap});

  final String text;
  final ValueChanged<String> onTap;

  @override
  State<_SamplePrompt> createState() => _SamplePromptState();
}

class _SamplePromptState extends State<_SamplePrompt> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    final content = Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () => widget.onTap(widget.text),
        borderRadius: AppRadius.pillR,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: AppSpacing.sm),
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.surfaceContainerHighest.withValues(alpha: 0.6),
            borderRadius: AppRadius.pillR,
          ),
          child: Text(widget.text, style: Theme.of(context).textTheme.labelMedium),
        ),
      ),
    );

    return GestureDetector(
      onTapDown: reduceMotion ? null : (_) => setState(() => _pressed = true),
      onTapUp: reduceMotion ? null : (_) => setState(() => _pressed = false),
      onTapCancel: reduceMotion ? null : () => setState(() => _pressed = false),
      child: AnimatedScale(
        scale: reduceMotion ? 1.0 : (_pressed ? 0.96 : 1.0),
        duration: AppMotion.fast,
        curve: AppMotion.standard,
        child: content,
      ),
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
      AnimationController(vsync: this, duration: AppMotion.pulse)..repeat(reverse: true);

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    Widget button(double scale) {
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
          child: Icon(widget.listening ? Icons.mic_rounded : Icons.mic_none_rounded, color: Colors.white, size: 36),
        ),
      );
    }

    return GestureDetector(
      onTap: widget.onTap,
      child: MediaQuery.of(context).disableAnimations
          ? button(1.0)
          : AnimatedBuilder(
              animation: _pulse,
              builder: (context, child) => button(widget.listening ? 1.0 + _pulse.value * 0.12 : 1.0),
            ),
    );
  }
}
