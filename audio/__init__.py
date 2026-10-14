"""Audio package: microphone capture, speech-to-text, and text-to-speech.

This package is deliberately **Qt-free** and **controller-free**. It only deals
with audio. All hardware access is behind small, injectable classes so the rest
of the application (and the tests) can substitute fakes.

Third-party imports (``sounddevice``, ``vosk``, ``pyttsx3``) are performed lazily
inside methods so that importing this package never fails when the optional
voice dependencies are not installed.
"""
