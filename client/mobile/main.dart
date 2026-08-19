import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;
import 'package:web_socket_channel/web_socket_channel.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeService();
  runApp(const MyApp());
}

Future<void> initializeService() async {
  final service = FlutterBackgroundService();
  await service.configure(
    androidConfiguration: AndroidConfiguration(
      onStart: onStart,
      autoStart: true,
      isForegroundMode: true,
      notificationChannelId: 'don_channel',
      initialNotificationTitle: 'DON is listening',
      initialNotificationContent: 'Waiting for "Hey Don"...',
    ),
    iosConfiguration: IosConfiguration(
      autoStart: true,
      onForeground: onStart,
    ),
  );
  await service.startService();
}

@pragma('vm:entry-point')
void onStart(ServiceInstance service) async {
  // 1. Initialize WebSocket Connection to Oracle Cloud
  final channel = WebSocketChannel.connect(
    Uri.parse('wss://don-ai-brain.onrender.com/ws/phone'),
  );

  // 2. Initialize Speech to Text
  stt.SpeechToText speech = stt.SpeechToText();
  bool available = await speech.initialize();
  
  if (available) {
    print("Voice recognition ready in background!");
    speech.listen(
      onResult: (result) {
        String words = result.recognizedWords.toLowerCase();
        if (words.contains("hey don")) {
          // Send to DON Cloud
          String command = words.replaceAll("hey don", "").trim();
          if (command.isNotEmpty) {
            channel.sink.add(jsonEncode({
              "id": DateTime.now().millisecondsSinceEpoch.toString(),
              "tool": "voice_prompt",
              "args": {"prompt": command}
            }));
          }
        }
      },
      listenFor: const Duration(hours: 24),
      pauseFor: const Duration(seconds: 3),
      partialResults: true,
      listenMode: stt.ListenMode.dictation,
    );
  }

  // Handle incoming replies from DON (e.g., text-to-speech the reply)
  channel.stream.listen((message) {
    // Implement flutter_tts to speak the reply
    print("DON says: $message");
  });
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      home: Scaffold(
        appBar: AppBar(title: const Text('DON Mobile Daemon')),
        body: const Center(
          child: Text('DON is running in the background.\nSay "Hey Don" from anywhere!'),
        ),
      ),
    );
  }
}
