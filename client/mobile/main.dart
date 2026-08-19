import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:permission_handler/permission_handler.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
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
    print("DON says: $message");
  });
}

class MyApp extends StatefulWidget {
  const MyApp({super.key});

  @override
  State<MyApp> createState() => _MyAppState();
}

class _MyAppState extends State<MyApp> {
  String status = "Waiting for permissions...";

  @override
  void initState() {
    super.initState();
    _requestPermissions();
  }

  Future<void> _requestPermissions() async {
    Map<Permission, PermissionStatus> statuses = await [
      Permission.microphone,
      Permission.notification,
    ].request();

    if (statuses[Permission.microphone]!.isGranted && 
        (statuses[Permission.notification]!.isGranted || statuses[Permission.notification]!.isRestricted)) {
      setState(() {
        status = "Permissions granted. Starting DON...";
      });
      await initializeService();
      setState(() {
        status = 'DON is running in the background.\nSay "Hey Don" from anywhere!';
      });
    } else {
      setState(() {
        status = "Microphone and Notification permissions are required.";
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      home: Scaffold(
        appBar: AppBar(title: const Text('DON Mobile Daemon')),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(20.0),
            child: Text(
              status,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 18),
            ),
          ),
        ),
      ),
    );
  }
}
