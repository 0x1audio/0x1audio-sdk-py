"""GAB-43: ox.emit events reach the call that sent them."""

import unittest

import ox1audio as ox
from ox1audio.action import clear

from hosting import Host


class EventsTest(unittest.TestCase):
    def setUp(self):
        clear()

    def test_events_are_tagged_with_their_call(self):
        @ox.action("Scan")
        def scan(count: int = 2):
            for i in range(count):
                ox.emit("partial", {"done": i + 1})
            return count

        host = Host()
        try:
            host.recv()
            host.send({"type": "call", "id": 5, "action": "scan", "input": {}})
            result, seen = host.until("result", 5)
            self.assertEqual(result["body"], 2)
            self.assertEqual([item for item in seen if item["type"] == "event"], [
                {"type": "event", "id": 5, "name": "partial", "body": {"done": 1}},
                {"type": "event", "id": 5, "name": "partial", "body": {"done": 2}},
            ])
        finally:
            host.close()

    def test_ox_test_records_events_and_bad_events_name_the_fix(self):
        @ox.action("Scan")
        def scan(kind: ox.Choice("ok", "name", "body") = "ok"):
            if kind == "name":
                ox.emit("two words")
            if kind == "body":
                ox.emit("partial", {1, 2})
            ox.emit("partial", ["a"])
            return None

        self.assertEqual(ox.test(scan)["events"], [("partial", ["a"])])
        with self.assertRaisesRegex(TypeError, r"short word[\s\S]*fix:"):
            ox.test(scan, kind="name")
        with self.assertRaisesRegex(TypeError, r"set, which can't be sent[\s\S]*fix:"):
            ox.test(scan, kind="body")

    def test_emit_outside_an_action_does_nothing(self):
        ox.emit("partial", 1)


if __name__ == "__main__":
    unittest.main()
