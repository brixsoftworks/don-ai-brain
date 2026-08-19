# DON Mobile Voice Client

This directory contains the scaffolding for a **Flutter mobile app** that runs in the background 24/7 on your Android phone, listening for the "Hey Don" wake word.

## Requirements
- Flutter SDK installed on your machine (`sudo snap install flutter --classic` on Linux).
- Android SDK installed (`android-cli` tools).
- USB Debugging enabled on your Android phone.

## Setup Instructions

1. **Create the Flutter App:**
   From your terminal, run:
   ```bash
   flutter create don_mobile
   ```

2. **Replace the Main File:**
   Copy the `main.dart` file provided in this folder over the default `don_mobile/lib/main.dart`:
   ```bash
   cp main.dart don_mobile/lib/main.dart
   ```

3. **Install Dependencies:**
   Navigate into `don_mobile` and add the required packages:
   ```bash
   cd don_mobile
   flutter pub add flutter_background_service
   flutter pub add speech_to_text
   flutter pub add web_socket_channel
   ```

4. **Update IP Address:**
   Open `lib/main.dart` and change `YOUR_ORACLE_IP` to the public IP of your Oracle Cloud instance.

5. **Build and Install:**
   Connect your Android phone via USB and run:
   ```bash
   flutter run --release
   ```

> **Note on Battery:** Background listening uses the microphone constantly. While Flutter's `speech_to_text` is efficient, it will drain more battery than standard apps. To maximize efficiency later, we can migrate to a native Picovoice Porcupine plugin.
