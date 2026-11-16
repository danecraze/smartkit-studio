"""Shared helpers: make small drum-like WAV files so the tests need no plugin, no samples and no module."""
import os, sys, wave
import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def write_wav(path, sr=44100, ch=1, amp=0.5, dur=0.6, f0=None, seed=0):
    rng = np.random.default_rng(seed)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    t = np.arange(int(sr * dur)) / sr
    tone = np.sin(2 * np.pi * f0 * t) if f0 else rng.standard_normal(len(t))
    x = amp * np.exp(-t * 8) * (tone + 0.2 * rng.standard_normal(len(t)))
    a = np.stack([x, 0.9 * x][:ch], 1)
    with wave.open(path, 'wb') as f:
        f.setnchannels(ch); f.setsampwidth(2); f.setframerate(sr)
        f.writeframes((np.clip(a, -1, 1) * 32767).astype('<i2').tobytes())


@pytest.fixture
def converter_library(tmp_path):
    """A small library named like common drum converters: '<drum>_<id> <CODE> <n>v<velocity>.wav'."""
    root = tmp_path / 'Test Kit'
    vels = [127, 100, 70, 40, 15]

    def mk(folder, base, code, f0=None, dur=0.6):
        for i, v in enumerate(vels):
            write_wav(str(root / folder / f'{base} {code} {i + 1}v{v}.wav'), amp=0.9 * (v / 127) ** 1.5,
                      dur=dur, f0=f0, seed=i + len(code))
    mk('KICK', '22 Maple Kick_Q1', 'K', f0=60)
    mk('SNARE', '14 Brass Snare_Q1', 'Sn', f0=200)
    mk('SNARE', '14 Brass Snare_Q1', 'SnR', f0=230)
    for i, (size, f0) in enumerate([(10, 180), (12, 140), (16, 90)], 1):
        mk('TOM', f'{size} Maple Tom_Q1', f'T{i}', f0=f0, dur=1.0)
    for code in ('HBC', 'HEC', 'HEO1', 'HEO2', 'HCH', 'HSP'):
        mk('HIHAT', '14 Test Hats_Z8', code, dur=1.0)
    mk('CRASH', '18 Test Crash_J6', 'C1E', dur=1.5)
    for code in ('Ri1', 'Ri1B'):
        mk('RIDE', '21 Test Ride_O6', code, dur=1.5)
    return str(root)
