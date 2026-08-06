"""Unit tests for the audio preprocessing pipeline."""

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_RATE = 16000


def _sine_wave(freq_hz: float = 440.0, duration_s: float = 0.5) -> np.ndarray:
    """Generate a float32 mono sine wave for testing."""
    t = np.linspace(0.0, duration_s, int(SAMPLE_RATE * duration_s), endpoint=False)
    return (0.5 * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)


def _white_noise(duration_s: float = 0.1, amplitude: float = 0.1) -> np.ndarray:
    rng = np.random.default_rng(42)
    return (rng.standard_normal(int(SAMPLE_RATE * duration_s)) * amplitude).astype(
        np.float32
    )


def _silence(duration_s: float = 0.1) -> np.ndarray:
    return np.zeros(int(SAMPLE_RATE * duration_s), dtype=np.float32)


# ---------------------------------------------------------------------------
# highpass_filter
# ---------------------------------------------------------------------------


class TestHighpassFilter:
    def test_output_shape_preserved(self) -> None:
        from taskify.audio.preprocessing import highpass_filter

        audio = _sine_wave(440.0)
        result = highpass_filter(audio, SAMPLE_RATE)
        assert result.shape == audio.shape

    def test_output_dtype_is_float32(self) -> None:
        from taskify.audio.preprocessing import highpass_filter

        audio = _sine_wave(440.0)
        result = highpass_filter(audio, SAMPLE_RATE)
        assert result.dtype == np.float32

    def test_attenuates_low_frequency_content(self) -> None:
        """A 30 Hz sine wave should be heavily attenuated by an 80 Hz high-pass."""
        from taskify.audio.preprocessing import highpass_filter

        low_freq_audio = _sine_wave(freq_hz=30.0)
        result = highpass_filter(low_freq_audio, SAMPLE_RATE, cutoff_hz=80.0)
        # Output RMS should be much lower than input
        input_rms = float(np.sqrt(np.mean(low_freq_audio**2)))
        output_rms = float(np.sqrt(np.mean(result**2)))
        assert output_rms < input_rms * 0.1, (
            f"Low-frequency content not attenuated: in={input_rms:.4f}, out={output_rms:.4f}"
        )

    def test_passes_speech_frequency_content(self) -> None:
        """A 300 Hz sine wave (within speech band) should largely pass through."""
        from taskify.audio.preprocessing import highpass_filter

        speech_audio = _sine_wave(freq_hz=300.0)
        result = highpass_filter(speech_audio, SAMPLE_RATE, cutoff_hz=80.0)
        input_rms = float(np.sqrt(np.mean(speech_audio**2)))
        output_rms = float(np.sqrt(np.mean(result**2)))
        # Output RMS should be > 70% of input (not significantly attenuated)
        assert output_rms > input_rms * 0.7, (
            f"Speech frequency over-attenuated: in={input_rms:.4f}, out={output_rms:.4f}"
        )

    def test_coeffs_cached(self) -> None:
        """Repeated calls with the same params should reuse cached coefficients."""
        from taskify.audio.preprocessing import _cached_coeffs, highpass_filter

        _cached_coeffs.clear()
        audio = _sine_wave(440.0)
        highpass_filter(audio, SAMPLE_RATE, cutoff_hz=80.0)
        highpass_filter(audio, SAMPLE_RATE, cutoff_hz=80.0)
        # Only one entry should be cached for these exact parameters
        assert (80.0, SAMPLE_RATE, 4) in _cached_coeffs

    def test_silent_input_stays_silent(self) -> None:
        from taskify.audio.preprocessing import highpass_filter

        silent = _silence(0.2)
        result = highpass_filter(silent, SAMPLE_RATE)
        assert np.allclose(result, 0.0, atol=1e-6)


# ---------------------------------------------------------------------------
# normalize_audio
# ---------------------------------------------------------------------------


class TestNormalizeAudio:
    def test_output_shape_preserved(self) -> None:
        from taskify.audio.preprocessing import normalize_audio

        audio = _sine_wave(440.0)
        result = normalize_audio(audio)
        assert result.shape == audio.shape

    def test_output_rms_close_to_target(self) -> None:
        from taskify.audio.preprocessing import normalize_audio

        target = 0.1
        # Quiet audio
        quiet = (_sine_wave(440.0) * 0.01).astype(np.float32)
        result = normalize_audio(quiet, target_rms=target, max_gain=50.0)
        actual_rms = float(np.sqrt(np.mean(result**2)))
        # Allow 15% tolerance
        assert abs(actual_rms - target) < target * 0.15

    def test_near_silence_not_amplified(self) -> None:
        """Audio near the noise floor should not be blown up."""
        from taskify.audio.preprocessing import normalize_audio

        near_silence = np.full(1600, 1e-8, dtype=np.float32)
        result = normalize_audio(near_silence, target_rms=0.1)
        # Should remain near-silent (not amplified to 0.1)
        rms = float(np.sqrt(np.mean(result**2)))
        assert rms < 0.01

    def test_output_clipped_within_range(self) -> None:
        from taskify.audio.preprocessing import normalize_audio

        audio = _sine_wave(440.0, duration_s=0.5)
        result = normalize_audio(audio, target_rms=0.9)
        assert result.max() <= 1.0
        assert result.min() >= -1.0

    def test_max_gain_respected(self) -> None:
        from taskify.audio.preprocessing import normalize_audio

        # Very quiet signal: would need huge gain to reach target_rms=0.1
        quiet = np.full(1600, 0.0001, dtype=np.float32)
        result = normalize_audio(quiet, target_rms=0.1, max_gain=5.0)
        # Gain of 5 applied to 0.0001 * sqrt(N)/N = 0.0001 → result should be ~0.0005
        rms = float(np.sqrt(np.mean(result**2)))
        assert rms < 0.01


# ---------------------------------------------------------------------------
# noise_gate
# ---------------------------------------------------------------------------


class TestNoiseGate:
    def test_output_shape_preserved(self) -> None:
        from taskify.audio.preprocessing import noise_gate

        audio = _white_noise()
        result = noise_gate(audio)
        assert result.shape == audio.shape

    def test_loud_audio_passes_through(self) -> None:
        from taskify.audio.preprocessing import noise_gate

        # Loud sine wave: should mostly pass through
        loud = _sine_wave(440.0)  # RMS ~0.35
        result = noise_gate(loud, threshold=0.005)
        rms_in = float(np.sqrt(np.mean(loud**2)))
        rms_out = float(np.sqrt(np.mean(result**2)))
        # Should retain at least 85% of energy
        assert rms_out > rms_in * 0.85

    def test_very_quiet_audio_suppressed(self) -> None:
        from taskify.audio.preprocessing import noise_gate

        # Extremely quiet noise that should be gated
        quiet = _white_noise(amplitude=0.001)
        result = noise_gate(quiet, threshold=0.01)
        rms_out = float(np.sqrt(np.mean(result**2)))
        # Output should be very quiet
        assert rms_out < 0.002

    def test_silence_stays_silent(self) -> None:
        from taskify.audio.preprocessing import noise_gate

        silent = _silence(0.1)
        result = noise_gate(silent, threshold=0.005)
        assert np.allclose(result, 0.0, atol=1e-7)


# ---------------------------------------------------------------------------
# preprocess (integration)
# ---------------------------------------------------------------------------


class TestPreprocess:
    def test_output_shape_preserved(self) -> None:
        from taskify.audio.preprocessing import preprocess

        audio = _sine_wave(440.0)
        result = preprocess(audio, SAMPLE_RATE)
        assert result.shape == audio.shape

    def test_output_dtype_is_float32(self) -> None:
        from taskify.audio.preprocessing import preprocess

        audio = _sine_wave(440.0)
        result = preprocess(audio, SAMPLE_RATE)
        assert result.dtype == np.float32

    def test_speech_signal_survives_pipeline(self) -> None:
        """A realistic speech-frequency signal should not be silenced by the pipeline."""
        from taskify.audio.preprocessing import preprocess

        # Mix of common speech frequencies
        t = np.linspace(0, 0.5, int(SAMPLE_RATE * 0.5), endpoint=False)
        speech = np.zeros_like(t, dtype=np.float32)
        for f in (200, 400, 800, 1600):
            speech += 0.1 * np.sin(2 * np.pi * f * t).astype(np.float32)

        result = preprocess(speech, SAMPLE_RATE)
        rms_out = float(np.sqrt(np.mean(result**2)))
        assert rms_out > 0.01, "Speech signal was incorrectly silenced by preprocessing."

    def test_output_within_valid_float_range(self) -> None:
        from taskify.audio.preprocessing import preprocess

        audio = _white_noise(amplitude=0.9)
        result = preprocess(audio, SAMPLE_RATE)
        assert result.max() <= 1.0
        assert result.min() >= -1.0

    def test_disable_all_stages_returns_original(self) -> None:
        from taskify.audio.preprocessing import preprocess

        audio = _sine_wave(440.0)
        result = preprocess(
            audio,
            SAMPLE_RATE,
            enable_highpass=False,
            enable_normalize=False,
            enable_gate=False,
        )
        np.testing.assert_array_equal(result, audio)

    def test_adaptive_gate_threshold(self) -> None:
        """preprocess() with a custom gate_threshold should not crash."""
        from taskify.audio.preprocessing import preprocess

        audio = _sine_wave(300.0)
        result = preprocess(audio, SAMPLE_RATE, gate_threshold=0.002)
        assert result.shape == audio.shape
