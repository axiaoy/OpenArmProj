"""CAN joint-state providers for OpenArm collection."""

from __future__ import annotations

import math
import time
from abc import ABC, abstractmethod

from .models import JointState


class JointStateProvider(ABC):
    """Interface for reading OpenArm joint states."""

    @abstractmethod
    def read(self) -> JointState:
        """Return the latest joint position, velocity, and torque sample.

        Returns:
            A ``JointState`` with monotonic timestamp and arrays ordered by
            ``joint_names``.
        """


class MockCANJointStateProvider(JointStateProvider):
    """Deterministic OpenArm-like CAN stream simulator.

    Parameters:
        joint_count: Number of joints to simulate.
        frequency_hz: Nominal update frequency for the simulated CAN stream.
    """

    def __init__(self, joint_count: int = 16, frequency_hz: float = 100.0) -> None:
        self.joint_names = tuple(f"j{i + 1:02d}" for i in range(joint_count))
        self.frequency_hz = frequency_hz
        self._start_ns = time.monotonic_ns()
        self._last_timestamp_ns = self._start_ns

    def read(self) -> JointState:
        """Generate one smooth position/velocity/torque sample.

        Returns:
            Simulated ``JointState`` values generated from deterministic waves.
        """

        target_period_ns = int(1_000_000_000 / self.frequency_hz)
        now_ns = time.monotonic_ns()
        elapsed_since_last = now_ns - self._last_timestamp_ns
        if elapsed_since_last < target_period_ns:
            time.sleep((target_period_ns - elapsed_since_last) / 1_000_000_000)
            now_ns = time.monotonic_ns()

        self._last_timestamp_ns = now_ns
        t = (now_ns - self._start_ns) / 1_000_000_000
        positions = []
        velocities = []
        torques = []
        for i, _name in enumerate(self.joint_names):
            phase = i * 0.31
            amplitude = 0.6 + (i % 4) * 0.08
            omega = 0.5 + (i % 5) * 0.07
            positions.append(amplitude * math.sin(omega * t + phase))
            velocities.append(amplitude * omega * math.cos(omega * t + phase))
            torques.append(0.15 * math.sin(0.7 * t + phase) + 0.01 * i)

        return JointState(
            timestamp_ns=now_ns,
            joint_names=self.joint_names,
            position=tuple(positions),
            velocity=tuple(velocities),
            torque=tuple(torques),
            source="mock",
        )


class SocketCANJointStateProvider(JointStateProvider):
    """Adapter boundary for real OpenArm CAN FD joint-state reading.

    Parameters:
        interfaces: CAN interfaces to read, normally ``("can0", "can1")``.
        timeout_s: Maximum time to wait for a complete joint update.
    """

    def __init__(self, interfaces: tuple[str, ...] = ("can0", "can1"), timeout_s: float = 0.02) -> None:
        self.interfaces = interfaces
        self.timeout_s = timeout_s

    def read(self) -> JointState:
        """Read one joint-state sample from OpenArm CAN FD hardware.

        Raises:
            NotImplementedError: Until robot-specific OpenArm CAN bindings or
                frame schema are available in the deployment image.
        """

        raise NotImplementedError(
            "Install/use the OpenArm CAN bindings here, then decode CAN FD frames "
            "from can0/can1 into JointState(position, velocity, torque)."
        )
