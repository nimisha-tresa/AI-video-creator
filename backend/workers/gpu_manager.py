from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Generator

import structlog

logger = structlog.get_logger()


@dataclass
class GPUSlot:
    gpu_id: int
    lock: threading.Lock = field(default_factory=threading.Lock)
    in_use: bool = False
    vram_free_gb: float = 0.0


class GPUManager:
    """
    Simple GPU slot manager. Each Celery worker acquires a GPU slot
    before submitting work to ComfyUI, ensuring we don't over-schedule.
    """

    def __init__(self) -> None:
        self._slots: list[GPUSlot] = []
        self._global_lock = threading.Lock()
        self._semaphore: threading.Semaphore | None = None
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return
        try:
            import pynvml

            pynvml.nvmlInit()
            count = pynvml.nvmlDeviceGetCount()
            for i in range(count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                free_gb = mem.free / 1024**3
                self._slots.append(GPUSlot(gpu_id=i, vram_free_gb=free_gb))
            pynvml.nvmlShutdown()
            logger.info("GPU manager initialized", gpus=count)
        except Exception:
            # No NVIDIA GPU / pynvml not available — use a single CPU "slot"
            self._slots.append(GPUSlot(gpu_id=0, vram_free_gb=999.0))
            logger.warning("No NVIDIA GPU detected; using CPU slot")

        self._semaphore = threading.Semaphore(len(self._slots))
        self._initialized = True

    @contextmanager
    def acquire(self) -> Generator[GPUSlot, None, None]:
        """Acquire a GPU slot. Blocks until one is free."""
        if not self._initialized:
            self.initialize()

        assert self._semaphore is not None
        self._semaphore.acquire()
        slot = self._pick_slot()
        try:
            logger.info("GPU slot acquired", gpu_id=slot.gpu_id)
            yield slot
        finally:
            with slot.lock:
                slot.in_use = False
            self._semaphore.release()
            logger.info("GPU slot released", gpu_id=slot.gpu_id)

    def _pick_slot(self) -> GPUSlot:
        with self._global_lock:
            for slot in self._slots:
                with slot.lock:
                    if not slot.in_use:
                        slot.in_use = True
                        return slot
        # Should not reach here due to semaphore
        raise RuntimeError("No GPU slot available")

    def status(self) -> list[dict]:
        return [
            {"gpu_id": s.gpu_id, "in_use": s.in_use, "vram_free_gb": s.vram_free_gb}
            for s in self._slots
        ]


gpu_manager = GPUManager()
