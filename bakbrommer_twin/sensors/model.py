"""Generic sensor model: noise, bias, resolution, sample rate and delay.

One :class:`Sensor` turns a true value into what the controller would read:

    reading = round((true + bias + noise) / resolution) · resolution

delivered ``delay`` later and only refreshed at the sensor's sample rate.
Noise is Gaussian white noise with the given standard deviation.
"""

from __future__ import annotations

import math
from collections import deque

import numpy as np

_BLOCK = 65536  # random numbers generated per refill


class NoiseSource:
    """Fast stream of standard-normal random numbers (seeded, reproducible)."""

    __slots__ = ("_block", "_position", "_rng")

    def __init__(self, seed: int) -> None:
        self._rng = np.random.default_rng(seed)
        self._block: list[float] = []
        self._position = 0

    def draw(self) -> float:
        """Next random number (mean 0, standard deviation 1)."""
        if self._position >= len(self._block):
            self._block = self._rng.standard_normal(_BLOCK).tolist()
            self._position = 0
        value = self._block[self._position]
        self._position += 1
        return value


class Sensor:
    """One sensor channel. Call :meth:`sample` at the sensor's own rate."""

    __slots__ = ("_noise_source", "_pipeline", "bias", "noise", "period_steps", "resolution",
                 "value")

    def __init__(self, noise: float, bias: float, resolution: float, period_steps: int,
                 delay_samples: int, noise_source: NoiseSource) -> None:
        self.noise = noise  # standard deviation, SI unit of the signal
        self.bias = bias
        self.resolution = resolution  # 0 = no rounding
        self.period_steps = period_steps  # simulation steps between two samples
        self._pipeline: deque[float] = deque(maxlen=delay_samples + 1)
        self._noise_source = noise_source
        self.value = 0.0  # what the controller currently reads

    def sample(self, true_value: float) -> None:
        """Take a new sample of ``true_value`` and release the delayed one."""
        reading = true_value + self.bias
        if self.noise > 0.0:
            reading += self.noise * self._noise_source.draw()
        if self.resolution > 0.0:
            reading = math.floor(reading / self.resolution + 0.5) * self.resolution
        self._pipeline.append(reading)
        self.value = self._pipeline[0]

    def preset(self, true_value: float) -> None:
        """Fill the delay line so the first readings are not zero."""
        self._pipeline.clear()
        for _ in range(self._pipeline.maxlen or 1):
            self._pipeline.append(true_value + self.bias)
        self.value = self._pipeline[0]
