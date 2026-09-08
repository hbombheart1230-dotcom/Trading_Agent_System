"""Bounded opening-only input worker; no reporter, strategy or executor calls."""
import threading
from datetime import datetime

from .data_provider import load_btc_signal_rows, load_woori_candles
from .input_delivery import publish_input
from .point_in_time_capture import merge_capture_into_signal_payload
from .vnext.contract import KST, epoch


class InputWorker:
    def __init__(self, day, reports_root, state_path):
        self.day, self.reports_root, self.state_path = day, reports_root, state_path
        self.research = None

    def tick(self, now_epoch):
        # Snapshot collector retains 08:55 ownership. Worker never captures it.
        signals = merge_capture_into_signal_payload({}, day=self.day)
        if self.research is None:
            try:
                fetched = load_btc_signal_rows(day=self.day).get('research_context') or {}
                self.research = fetched if fetched.get('btc_usd_daily') and fetched.get('woori_daily') else None
            except Exception:
                self.research = None
        signals['research_context'] = self.research or {}
        candles = []
        if now_epoch >= epoch(self.day, '09:00') and signals.get('btc_0855_capture_status') == 'CAPTURED':
            candles = load_woori_candles(day=self.day, state_path=self.state_path, allow_fresh_fetch=True)
        return publish_input(day=self.day, reports_root=self.reports_root, signals=signals,
                             candles=candles, now_epoch=now_epoch)


def start_input_worker(*, day, reports_root, state_path):
    stop = threading.Event()
    worker = InputWorker(day, reports_root, state_path)

    def loop():
        while not stop.is_set():
            now = datetime.now(KST)
            if now.date().isoformat() != day or int(now.timestamp()) > epoch(day, '09:12'):
                return
            if int(now.timestamp()) >= epoch(day, '08:50'):
                try:
                    worker.tick(int(now.timestamp()))
                except Exception as exc:
                    # Invalid/missing producer output cannot be masked by an old healthy row.
                    print(f'q12_input_delivery_error={type(exc).__name__}', flush=True)
            stop.wait(15)
    thread = threading.Thread(target=loop, name='q12-opening-input', daemon=True)
    thread.start()
    return stop
