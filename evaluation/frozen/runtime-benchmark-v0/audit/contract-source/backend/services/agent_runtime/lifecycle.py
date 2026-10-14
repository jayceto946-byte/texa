"""Desktop/API startup recovery and projection retry; never reruns tools/models."""
import logging
import threading

from backend.services.agent_runtime.locator import runtime_store

logger = logging.getLogger(__name__)


class RuntimeRecoveryWorker:
    def __init__(self, store, projector, interval: float = 2):
        self.store, self.projector, self.interval = store, projector, interval
        self._stop = threading.Event()
        self._thread = None

    def recover(self):
        return self.store.recover_unfinished()

    def start(self):
        if self._thread is not None:
            return
        def work():
            while not self._stop.is_set():
                try:
                    self.projector(self.store)
                except Exception:
                    logger.exception("Runtime outbox projection will retry")
                self._stop.wait(self.interval)
        self._thread = threading.Thread(target=work, name="texa-runtime-recovery", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        return self._thread is None or not self._thread.is_alive()


def start_runtime_recovery():
    store = runtime_store()
    from backend.services.agent_runtime.chat_binding import project_outcomes
    def project(_):
        current = runtime_store()
        if current is not None:
            project_outcomes(current)
    worker = RuntimeRecoveryWorker(store, project)
    if store is not None:
        worker.recover()
    worker.start()
    return worker
