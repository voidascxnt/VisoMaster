Bei Code-Extraktion und Migration fokussiere dich AUSSCHLIESSLICH auf das angeforderte Feature.

Wenn Screen Recording Features angefragt werden:
- Extrahiere NUR Code der mit recording, capture, screen, video recording zu tun hat
- IGNORIERE komplett: ReSwapper, face swapping, ONNX models, performance optimizations
- IGNORIERE: Threading improvements, GPU optimizations, batch processing

Analysiere Dateien nach diesen Keywords für Screen Recording:
- Dateinamen: *record*, *capture*, *screen*, *video*
- Funktionen: record_*, capture_*, start_recording, stop_recording
- Imports: cv2, PIL, screen capture libraries

NIEMALS mischen: Verschiedene Features sollen getrennt bleiben.
