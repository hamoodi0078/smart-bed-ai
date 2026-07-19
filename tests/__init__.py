"""Must exist: SpeechRecognition ships a top-level `tests` package into
site-packages, and a regular package anywhere on sys.path shadows a plain
directory everywhere. Without this file, `import tests.env_isolation`
resolves to SpeechRecognition's tests/ and fails on machines with the
voice stack installed (CI doesn't install it, so CI never sees the bug).
"""
