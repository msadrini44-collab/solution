"""
Detector 5 — Audio-visual sync & voice authenticity.

Two complementary checks for video that contains an audio track:

1. **Lip-sync (phoneme/viseme alignment)** — extract the audio envelope (speech
   energy over time) and the mouth-openness signal from lip landmarks across
   frames. Genuine talking-head footage shows high correlation between mouth
   movement and speech energy; lip-synced deepfakes drift out of alignment.
2. **Voice authenticity** — analyse the audio spectrogram for the unnaturally
   smooth/over-regular harmonic structure and missing high-band energy typical
   of TTS / voice-conversion models.

Uses ``librosa`` for audio and mouth landmarks from mediapipe. Gracefully
degrades (and is SKIPPED for images / silent video).
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np

from .base import DetectorResult, DetectorStatus, errored, skipped

NAME = "audio_sync"

# mediapipe FaceMesh indices for upper / lower inner lip.
_UPPER_LIP = 13
_LOWER_LIP = 14


def _load_audio(path: str):
    """Return (waveform, sr) or None if librosa/audio unavailable."""
    try:
        import librosa

        y, sr = librosa.load(path, sr=16000, mono=True)
        if y is None or len(y) < sr // 2:
            return None
        return y, sr
    except Exception:
        return None


def _voice_authenticity(y, sr) -> float:
    """Return probability the voice is AI-generated [0, 1]."""
    import librosa

    S = np.abs(librosa.stft(y, n_fft=1024)) ** 2
    # Spectral flatness: synthetic voices are often flatter / more regular.
    flatness = float(np.mean(librosa.feature.spectral_flatness(S=np.sqrt(S))))
    # High-frequency energy ratio: TTS often rolls off the top band.
    freqs = np.linspace(0, sr / 2, S.shape[0])
    hf = float(S[freqs > 6000].sum() / (S.sum() + 1e-9))
    fake_p = float(np.clip(0.6 * min(flatness / 0.4, 1.0) + 0.4 * (1.0 - min(hf / 0.05, 1.0)), 0.0, 1.0))
    return fake_p


def run(
    path: str,
    *,
    media_type: str,
    frames: Optional[List[np.ndarray]] = None,
    **_: object,
) -> DetectorResult:
    if media_type != "video":
        return skipped(NAME, "Audio-sync analysis only applies to video.")
    try:
        audio = _load_audio(path)
        if audio is None:
            return skipped(NAME, "No usable audio track found.")
        y, sr = audio

        voice_fake_p = _voice_authenticity(y, sr)

        # Lip-sync correlation when landmarks are available.
        sync_fake_p = None
        try:
            import librosa
            import mediapipe as mp

            mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=False, max_num_faces=1, refine_landmarks=True
            )
            mouth_open: List[float] = []
            for fr in frames or []:
                res = mesh.process(fr.astype("uint8"))
                if res.multi_face_landmarks:
                    lm = res.multi_face_landmarks[0].landmark
                    mouth_open.append(abs(lm[_LOWER_LIP].y - lm[_UPPER_LIP].y))
                else:
                    mouth_open.append(0.0)
            if len(mouth_open) >= 3:
                # Audio energy resampled to the number of frames.
                rms = librosa.feature.rms(y=y)[0]
                idx = np.linspace(0, len(rms) - 1, len(mouth_open)).astype(int)
                energy = rms[idx]
                mo = np.asarray(mouth_open)
                if np.std(mo) > 1e-6 and np.std(energy) > 1e-6:
                    corr = float(np.corrcoef(mo, energy)[0, 1])
                    # Low/negative correlation -> out of sync -> fake.
                    sync_fake_p = float(np.clip((0.5 - corr) / 1.0 + 0.25, 0.0, 1.0))
        except Exception:
            sync_fake_p = None

        if sync_fake_p is not None:
            fake_p = 0.5 * voice_fake_p + 0.5 * sync_fake_p
            status = DetectorStatus.OK
            summary = "Lip-sync correlation and voice-spectrogram authenticity."
        else:
            fake_p = voice_fake_p
            status = DetectorStatus.DEGRADED
            summary = "Voice-spectrogram authenticity only (no lip tracking)."

        return DetectorResult(
            name=NAME,
            fake_probability=fake_p,
            status=status,
            summary=summary,
            details={
                "voice_fake_probability": round(voice_fake_p, 4),
                "lip_sync_fake_probability": (
                    round(sync_fake_p, 4) if sync_fake_p is not None else None
                ),
            },
        )
    except Exception as exc:
        return errored(NAME, exc)
