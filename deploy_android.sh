#!/bin/bash
set -e

echo "=== DON Android Build Wizard ==="

# 1. Setup Directories
mkdir -p ~/.local/bin
mkdir -p ~/Android/Sdk/cmdline-tools
mkdir -p ~/.local/flutter
mkdir -p ~/.local/java
export PATH="$HOME/.local/bin:$PATH"

# 2. Download Java (Required for Android SDK)
echo "=> Installing local Java JDK 17..."
cd ~/.local/java
if [ ! -d "jdk-17" ]; then
    wget -qO openjdk-17.tar.gz https://download.java.net/java/GA/jdk17.0.2/dfd4a8d0985749f896bed50d7138ee7f/8/GPL/openjdk-17.0.2_linux-x64_bin.tar.gz
    tar -xzf openjdk-17.tar.gz
    mv jdk-17.0.2 jdk-17
    rm openjdk-17.tar.gz
fi
export JAVA_HOME="$HOME/.local/java/jdk-17"
export PATH="$JAVA_HOME/bin:$PATH"

# 3. Download Android SDK cmdline-tools
echo "=> Installing Android SDK..."
cd ~/Android/Sdk/cmdline-tools
if [ ! -d "latest" ]; then
    wget -qO cmdline-tools.zip https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip
    unzip -q cmdline-tools.zip
    mv cmdline-tools latest
    rm cmdline-tools.zip
fi
export ANDROID_HOME="$HOME/Android/Sdk"
export PATH="$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH"

# 4. Accept Licenses & Install Platforms
echo "=> Accepting Android SDK Licenses..."
yes | sdkmanager --licenses > /dev/null
sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0" > /dev/null

# 5. Download Flutter SDK
echo "=> Installing Flutter SDK..."
cd ~/.local
if [ ! -d "flutter/bin" ]; then
    wget -qO flutter.tar.xz https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_3.24.0-stable.tar.xz
    tar -xf flutter.tar.xz
    rm flutter.tar.xz
fi
export PATH="$HOME/.local/flutter/bin:$PATH"

echo "=> Running flutter doctor to verify..."
flutter config --no-analytics
flutter doctor -v

# 6. Scaffold App
echo "=> Scaffolding Flutter App..."
cd /home/mullainathan/Documents/Coding/Projects/pa\ ai\ agent/client/mobile
if [ ! -d "don_mobile" ]; then
    flutter create don_mobile --empty
fi

cd don_mobile
# Inject our main.dart
cp ../main.dart lib/main.dart

# Add dependencies
echo "=> Adding Flutter dependencies..."
flutter pub add flutter_background_service
flutter pub add speech_to_text
flutter pub add web_socket_channel

# Add Android Permissions to AndroidManifest.xml
echo "=> Updating AndroidManifest.xml..."
MANIFEST="android/app/src/main/AndroidManifest.xml"
sed -i '/<application/i \    <uses-permission android:name="android.permission.INTERNET"/>\n    <uses-permission android:name="android.permission.RECORD_AUDIO"/>\n    <uses-permission android:name="android.permission.FOREGROUND_SERVICE"/>\n    <uses-permission android:name="android.permission.WAKE_LOCK"/>' $MANIFEST

# 7. Build APK
echo "=> Compiling APK... (this will take several minutes)"
flutter build apk --release

# 8. Copy out
echo "=> Build complete! Moving APK..."
cp build/app/outputs/flutter-apk/app-release.apk /home/mullainathan/Documents/Coding/Projects/pa\ ai\ agent/don-mobile-release.apk
echo "=== Done! APK saved to don-mobile-release.apk ==="
