"""Replay hooks through the same normalization boundary as socket requests."""

import unittest

from codex_pet.adapters.codex import event_from_hook
from test_daemon_notifications import isolated_daemon


def hook(instance, name, turn_id="turn-1"):
    event = event_from_hook({"hook_event_name": name, "session_id": "thread-1",
                             "turn_id": turn_id})
    return instance.process({"action": "event", "event": event})


class DaemonLifecycleTests(unittest.TestCase):
    def test_malformed_event_values_do_not_escape_the_ipc_boundary(self):
        with isolated_daemon() as instance:
            for event in ({"state": []}, {"state": "running", "kind": []},
                          {"state": "ready", "kind": "activity"}):
                self.assertFalse(instance.process({"action": "event", "event": event})["ok"])

    def test_semantic_turn_end_rejects_late_activity_without_codex_hook_names(self):
        with isolated_daemon() as instance:
            for kind, state in (("turn_start", "running"), ("turn_end", "ready"),
                                ("activity", "running")):
                result = instance.process({"action": "event", "event": {
                    "kind": kind, "state": state, "session_id": "semantic", "turn_id": "one"}})
            self.assertFalse(result["applied"])
            self.assertEqual(instance.status()["state"], "ready")

    def test_stop_adopts_turn_id_after_a_session_was_restored_without_it(self):
        with isolated_daemon() as instance:
            instance.process({"action": "event", "event": {
                "state": "running", "session_id": "thread-1"}})
            self.assertEqual(hook(instance, "Stop")["state"], "ready")
            self.assertEqual(instance.sessions.sessions["thread-1"].turn_id, "turn-1")
            self.assertEqual(instance.status()["turn_id"], "turn-1")

    def test_new_prompt_without_id_can_adopt_its_later_stop_id(self):
        with isolated_daemon() as instance:
            hook(instance, "UserPromptSubmit")
            hook(instance, "Stop")
            hook(instance, "UserPromptSubmit", "")
            self.assertEqual(hook(instance, "Stop", "turn-2")["state"], "ready")

    def test_finished_turn_cannot_be_reopened_by_late_activity_hooks(self):
        for terminal, expected in (("Stop", "ready"), ("Interrupt", "idle")):
            for turn_id in ("turn-1", ""):
                with self.subTest(terminal=terminal, turn_id=turn_id), isolated_daemon() as instance:
                    hook(instance, "UserPromptSubmit", turn_id)
                    hook(instance, terminal, turn_id)
                    for late in ("PostToolUse", "PermissionRequest"):
                        response = hook(instance, late, turn_id)
                        self.assertEqual(response["state"], expected)
                        self.assertFalse(response["applied"])
                    self.assertEqual(hook(instance, "UserPromptSubmit", "turn-2")["state"], "running")
                    self.assertEqual(hook(instance, "PermissionRequest", "turn-2")["state"], "needs_input")
                    self.assertEqual(hook(instance, "PostToolUse", "turn-2")["state"], "running")

    def test_stale_stop_does_not_finish_a_new_turn(self):
        with isolated_daemon() as instance:
            hook(instance, "UserPromptSubmit")
            hook(instance, "UserPromptSubmit", "turn-2")
            response = hook(instance, "Stop")
            self.assertFalse(response["applied"])
            self.assertEqual(response["state"], "running")

    def test_explicit_manual_state_change_remains_available_after_stop(self):
        with isolated_daemon() as instance:
            hook(instance, "Stop")
            response = instance.process({"action": "event", "event": {
                "state": "running", "session_id": "thread-1", "turn_id": "turn-1"}})
            self.assertEqual(response["state"], "running")


if __name__ == "__main__":
    unittest.main()
