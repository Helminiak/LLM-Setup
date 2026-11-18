"""Unit tests for the BASALT adapter in llama-swap-reality. No network, no GPU, no service access."""
import importlib.util, json, sys, time, unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("lr", "/home/joe/bin/dev/llama-swap-reality.py")
lr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lr)

BASALT_ARGS = ["/usr/bin/python3", "-m", "serve.server", "--engine-bin",
               "/home/joe/models/basalt/engine/basalt-v0.4.1-linux-x64/bin/basalt",
               "--config", "/home/joe/models/basalt/config/basalt_config.json", "--port", "10100", "--host", "127.0.0.1"]


class Detection(unittest.TestCase):
    def test_basalt_server_recognised(self):
        with mock.patch.object(lr, "_cmdline", return_value=BASALT_ARGS), mock.patch.object(lr, "_comm", return_value="python3"):
            self.assertTrue(lr.is_basalt_server(1))
            self.assertTrue(lr.is_model_server(1))

    def test_unrelated_python_not_a_model(self):
        args = ["/usr/bin/python3", "-m", "http.server", "8000"]
        with mock.patch.object(lr, "_cmdline", return_value=args), mock.patch.object(lr, "_comm", return_value="python3"):
            self.assertFalse(lr.is_basalt_server(2))
            self.assertFalse(lr.is_model_server(2))

    def test_llama_server_still_recognised(self):
        with mock.patch.object(lr, "_cmdline", return_value=["llama-server", "-m", "x.gguf"]), mock.patch.object(lr, "_comm", return_value="llama-server"):
            self.assertTrue(lr.is_model_server(3))
            self.assertFalse(lr.is_basalt_server(3))

    def test_unrelated_cuda_process_not_a_model(self):
        with mock.patch.object(lr, "_cmdline", return_value=["/usr/bin/some-cuda-tool"]), mock.patch.object(lr, "_comm", return_value="some-cuda-tool"):
            self.assertFalse(lr.is_model_server(4))


class GpuAttribution(unittest.TestCase):
    def test_descendants_summed_once_and_unrelated_ignored(self):
        parents = {600: [300], 601: [300], 900: []}          # 600 and 601 are engine children of server 300
        gpu = {600: {0: 1000}, 601: {1: 2000}, 900: {0: 5000}}
        with mock.patch.object(lr, "ancestors", side_effect=lambda p: parents[p]):
            out = lr.attribute_gpu({300}, gpu)
        self.assertEqual(out, {300: {0: 1000, 1: 2000}})     # 5000 from the unrelated CUDA process is not counted

    def test_server_own_gpu_pid_is_not_double_counted(self):
        with mock.patch.object(lr, "ancestors", return_value=[]):
            out = lr.attribute_gpu({300}, {300: {0: 17380, 1: 16906}})
        self.assertEqual(out, {300: {0: 17380, 1: 16906}})


class SlotStep(unittest.TestCase):
    def test_counts_only_while_decoding(self):
        t = 100.0
        prev = None
        rows = [({"state": "prefill", "generated": 0}, t),
                ({"state": "decoding", "generated": 5}, t + 1),
                ({"state": "decoding", "generated": 12}, t + 2),
                ({"state": "idle", "generated": 12}, t + 3)]
        total = 0
        for row, now in rows:
            dn, dt, prev = lr.basalt_slot_step(prev, row, now)
            total += dn
        self.assertEqual(total, 7)        # 5 on the first decoding sample is not counted (no previous point); then 12-5 = 7

    def test_counter_reset_starts_new_request(self):
        dn, dt, nxt = lr.basalt_slot_step(("basalt", 200, 10.0), {"state": "decoding", "generated": 3}, 11.0)
        self.assertEqual(dn, 3)
        self.assertEqual(nxt, ("basalt", 3, 11.0))

    def test_idle_clears_state(self):
        dn, dt, nxt = lr.basalt_slot_step(("basalt", 9, 10.0), {"state": "idle", "generated": 9}, 11.0)
        self.assertEqual((dn, nxt), (0, None))


class Payload(unittest.TestCase):
    def test_missing_metrics_are_none_and_zero_is_zero(self):
        self.assertIsNone(lr.summ([])["now"])
        now = time.time()
        zeros = [(now - 2, 0.0, 0.0, 0.0), (now - 1, 0.0, 0.0, 0.0)]
        self.assertEqual(lr.summ(zeros)["now"], 0.0)

    def test_last_completed_request_exposed_when_present(self):
        now = time.time()
        pts = [(now - 1, 31.0, 31.0, 1.0)]
        with lr.LOCK:
            lr.SAMPLES.clear(); lr.SAMPLES["basalt-deepseek-v41"] = __import__("collections").deque(pts)
        lr.LAST.clear(); lr.LAST["basalt-deepseek-v41"] = {"predicted_per_second": 31.1, "prompt_per_second": 26.1, "at": now}
        out = lr.tps_payload(120)
        self.assertEqual(out["stats"]["basalt-deepseek-v41"]["last"]["predicted_per_second"], 31.1)
        self.assertNotIn("basalt-deepseek-v41", [k for k in out["stats"] if k == "absent"])


class SwapMap(unittest.TestCase):
    def test_port_to_model_mapping(self):
        body = json.dumps({"running": [{"model": "basalt-deepseek-v41", "proxy": "http://127.0.0.1:10100", "state": "ready"}]}).encode()

        class FakeResp:
            def read(self): return body

        class FakeConn:
            def __init__(self, *a, **k): pass
            def request(self, *a, **k): pass
            def getresponse(self): return FakeResp()
            def close(self): pass

        with mock.patch.object(lr.http.client, "HTTPConnection", FakeConn):
            m = lr.swap_running_ports()
        self.assertEqual(m[10100]["model"], "basalt-deepseek-v41")


if __name__ == "__main__":
    unittest.main(verbosity=2)
