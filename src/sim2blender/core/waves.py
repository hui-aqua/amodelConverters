"""Deep-water JONSWAP synthesis; SI units, sigma=0.07/0.09.

Spectrum convention: https://wavespectra.readthedocs.io/en/latest/generated/wavespectra.core.npstats.jonswap.html
"""
import math
import random
from functools import lru_cache

WAVE_DEFAULTS = dict(wave_type="regular", jonswap_gamma=3.3,
                     wave_components=64, wave_seed=42, wave_spread_deg=20.0)


def wave_options(config):
    return {key: config.get(key, value) for key, value in WAVE_DEFAULTS.items()}


@lru_cache(maxsize=128)
def jonswap_components(height, period, direction=0.0, gamma=3.3,
                       count=64, seed=42, spread=20.0):
    """Return (amplitude, omega, kx, ky, phase) tuples.

    Normalize discrete energy to m0=(Hs/4)**2 over 0.5..3 fp.
    Spread is the Gaussian heading standard deviation in degrees.
    Stratified random frequencies avoid a short artificial repeat period.
    """
    if not all(math.isfinite(v) for v in (height, period, direction, gamma, spread)):
        raise ValueError("Wave parameters must be finite")
    if height < 0 or period <= 0 or not 1 <= gamma <= 10 or not 0 <= spread <= 90:
        raise ValueError("Require Hs >= 0, Tp > 0, gamma in [1,10], spread in [0,90]")
    if isinstance(count, bool) or int(count) != count or not 8 <= count <= 256:
        raise ValueError("Wave component count must be an integer in [8,256]")
    rng = random.Random(seed)
    fp = 1.0 / period
    df = 2.5 * fp / count
    samples = []
    for i in range(int(count)):
        f = 0.5 * fp + (i + rng.random()) * df
        ratio = f / fp
        sigma = 0.07 if f <= fp else 0.09
        peak = math.exp(-0.5 * ((ratio - 1) / sigma)**2)
        energy = ratio**-5 * math.exp(-1.25 * ratio**-4) * gamma**peak
        omega = math.tau * f
        k = omega**2 / 9.81
        angle = math.radians(direction + rng.gauss(0, spread))
        samples.append((energy, omega, k*math.cos(angle), k*math.sin(angle), rng.random()*math.tau))
    scale = (height / 4)**2 / sum(s[0] for s in samples)
    return tuple((math.sqrt(2*s[0]*scale), *s[1:]) for s in samples)


def spectral_elevation(components, x, y, t):
    return sum(a * math.cos(kx*x + ky*y - omega*t + phase)
               for a, omega, kx, ky, phase in components)
