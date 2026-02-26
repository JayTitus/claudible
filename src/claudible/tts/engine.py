"""TTS engine wrapping Coqui XTTS v2 with voice cloning support."""

from __future__ import annotations

import io
import logging
from pathlib import Path

import numpy as np
import soundfile as sf

log = logging.getLogger(__name__)


class TTSEngine:
    """Manages the XTTS v2 model and generates speech from text."""

    def __init__(self, model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2"):
        self._model_name = model_name
        self._tts = None

    def load(self) -> None:
        """Load the TTS model onto GPU. Call once at server startup."""
        import torch
        from TTS.api import TTS

        # Coqui TTS 0.22 checkpoints require weights_only=False (PyTorch >=2.6 default changed)
        _orig_load = torch.load
        torch.load = lambda *a, **kw: _orig_load(*a, **{**kw, "weights_only": False})
        try:
            log.info("Loading TTS model: %s", self._model_name)
            self._tts = TTS(model_name=self._model_name, gpu=True)
            log.info("TTS model loaded")
        finally:
            torch.load = _orig_load

    @property
    def is_loaded(self) -> bool:
        return self._tts is not None

    def synthesize(
        self,
        text: str,
        speaker_wav: str | Path,
        language: str = "en",
        speed: float = 1.0,
    ) -> tuple[np.ndarray, int]:
        """Generate speech audio from text using a reference voice.

        Returns (audio_array, sample_rate).
        """
        if not self._tts:
            raise RuntimeError("TTS model not loaded — call engine.load() first")

        wav = self._tts.tts(
            text=text,
            speaker_wav=str(speaker_wav),
            language=language,
            speed=speed,
        )
        audio = np.array(wav, dtype=np.float32)
        sample_rate = self._tts.synthesizer.output_sample_rate
        return audio, sample_rate

    def synthesize_to_bytes(
        self,
        text: str,
        speaker_wav: str | Path,
        language: str = "en",
        speed: float = 1.0,
        fmt: str = "wav",
    ) -> bytes:
        """Generate speech and return as audio bytes."""
        audio, sr = self.synthesize(text, speaker_wav, language, speed)
        buf = io.BytesIO()
        sf.write(buf, audio, sr, format=fmt)
        buf.seek(0)
        return buf.read()
