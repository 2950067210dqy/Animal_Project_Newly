import threading
import time
import unittest

from public.entity.barrier.DynamicBarrier import DynamicBarrier


class DynamicBarrierTests(unittest.TestCase):
    def test_early_stage_notifications_are_not_lost(self):
        ufc_finished = threading.Semaphore(0)
        ugc_finished = threading.Semaphore(0)
        action_count = 0

        def action():
            nonlocal action_count
            action_count += 1

        barrier = DynamicBarrier(4, action=action, timeout=0.5)

        def ufc_worker():
            ufc_finished.release()
            barrier.wait()

        def ugc_worker():
            time.sleep(0.05)
            self.assertTrue(ufc_finished.acquire(timeout=0.2))
            ugc_finished.release()
            barrier.wait()

        def zos_worker():
            time.sleep(0.1)
            self.assertTrue(ugc_finished.acquire(timeout=0.2))
            barrier.wait()

        threads = [
            threading.Thread(target=ufc_worker),
            threading.Thread(target=ugc_worker),
            threading.Thread(target=zos_worker),
            threading.Thread(target=barrier.wait),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=1)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(action_count, 1)

    def test_all_participants_complete_one_generation(self):
        action_count = 0
        action_lock = threading.Lock()
        results = []

        def action():
            nonlocal action_count
            with action_lock:
                action_count += 1

        barrier = DynamicBarrier(4, action=action, timeout=0.5)

        def worker():
            results.append(barrier.wait())

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=1)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(action_count, 1)
        self.assertEqual(len(results), 4)
        self.assertEqual(barrier.n_waiting, 0)

    def test_timeout_releases_waiter_and_reset_allows_next_generation(self):
        barrier = DynamicBarrier(2, timeout=0.05)
        failures = []

        def timed_out_worker():
            try:
                barrier.wait()
            except threading.BrokenBarrierError as exc:
                failures.append(str(exc))

        first_thread = threading.Thread(target=timed_out_worker)
        first_thread.start()
        first_thread.join(timeout=0.5)

        self.assertFalse(first_thread.is_alive())
        self.assertEqual(len(failures), 1)
        self.assertTrue(barrier.broken)

        with self.assertRaises(threading.BrokenBarrierError):
            barrier.wait()

        barrier.reset()
        self.assertFalse(barrier.broken)

        results = []
        threads = [
            threading.Thread(target=lambda: results.append(barrier.wait()))
            for _ in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=0.5)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(len(results), 2)

    def test_reset_releases_current_waiters(self):
        barrier = DynamicBarrier(2, timeout=1.0)
        failures = []

        def worker():
            try:
                barrier.wait()
            except threading.BrokenBarrierError:
                failures.append(True)

        thread = threading.Thread(target=worker)
        thread.start()
        deadline = time.monotonic() + 0.5
        while barrier.n_waiting != 1 and time.monotonic() < deadline:
            time.sleep(0.005)

        barrier.reset(parties=1)
        thread.join(timeout=0.5)

        self.assertFalse(thread.is_alive())
        self.assertEqual(failures, [True])
        self.assertEqual(barrier.wait(), 0)


if __name__ == "__main__":
    unittest.main()
