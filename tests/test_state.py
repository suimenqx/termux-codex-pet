"""State synchronization follows explicit Codex hook evidence."""

import unittest

from codex_pet.state import SessionStore, direct_event, event_from_hook


def event(state: str, session_id: str, turn_id: str = "", message: str = "",
          starts_turn: bool = False) -> dict:
    value = direct_event({"state": state, "session_id": session_id,
                          "turn_id": turn_id, "project": session_id, "message": message,
                          "starts_turn": starts_turn})
    assert value is not None
    return value


class StateSynchronizationTests(unittest.TestCase):
    def test_hook_events_use_official_activity_states(self) -> None:
        cases = {
            "UserPromptSubmit": "running",
            "PermissionRequest": "needs_input",
            "PostToolUse": "running",
            "Stop": "ready",
            "Interrupt": "idle",
        }
        for hook_name, expected in cases.items():
            with self.subTest(hook=hook_name):
                parsed = event_from_hook({"hook_event_name": hook_name, "session_id": "thread-1",
                                          "turn_id": "turn-1"})
                self.assertIsNotNone(parsed)
                self.assertEqual(parsed["state"], expected)
                self.assertEqual(parsed["starts_turn"], hook_name == "UserPromptSubmit")

    def test_compaction_does_not_reset_a_running_session(self) -> None:
        self.assertIsNone(event_from_hook({"hook_event_name": "SessionStart",
                                           "source": "compact", "session_id": "thread-1"}))
        resumed = event_from_hook({"hook_event_name": "SessionStart",
                                   "source": "resume", "session_id": "thread-1"})
        self.assertEqual(resumed["state"], "idle")

    def test_post_tool_use_resolves_input_and_returns_to_running(self) -> None:
        store = SessionStore()
        store.apply(event("running", "thread-1", "turn-1"))
        store.apply(event("needs_input", "thread-1", "turn-1"))
        self.assertEqual(store.snapshot()["state"], "needs_input")
        store.apply(event("running", "thread-1", "turn-1"))
        self.assertEqual(store.snapshot()["state"], "running")

    def test_ready_persists_until_a_later_hook_event_changes_the_session(self) -> None:
        store = SessionStore()
        store.apply(event("ready", "thread-1", "turn-1", "Finished the task"))
        snapshot = store.snapshot()
        self.assertEqual(snapshot["state"], "ready")
        self.assertEqual(snapshot["message"], "Finished the task")
        self.assertEqual(snapshot["session_id"], "thread-1")
        self.assertEqual(store.snapshot()["state"], "ready")

        store.apply(event("running", "thread-1", "turn-1"))
        self.assertEqual(store.snapshot()["state"], "running")

    def test_late_events_from_a_previous_turn_are_ignored(self) -> None:
        store = SessionStore()
        store.apply(event("running", "thread-1", "turn-1", starts_turn=True))
        store.apply(event("running", "thread-1", "turn-2", starts_turn=True))
        self.assertFalse(store.apply(event("running", "thread-1", "turn-1")))
        self.assertFalse(store.apply(event("ready", "thread-1", "turn-1")))
        self.assertFalse(store.apply(event("needs_input", "thread-1", "turn-1")))
        self.assertEqual(store.snapshot()["state"], "running")
        self.assertEqual(store.sessions["thread-1"].turn_id, "turn-2")

    def test_session_priority_matches_official_pet_order(self) -> None:
        store = SessionStore()
        for state, sid in (("running", "run"), ("ready", "ready"),
                           ("blocked", "blocked"), ("needs_input", "input")):
            store.apply(event(state, sid))
        self.assertEqual(store.snapshot()["state"], "needs_input")
        store.sessions.pop("input")
        self.assertEqual(store.snapshot()["state"], "blocked")
        store.sessions.pop("blocked")
        self.assertEqual(store.snapshot()["state"], "ready")

    def test_hook_payloads_do_not_infer_blocked_from_tool_exit_status(self) -> None:
        parsed = event_from_hook({"hook_event_name": "PostToolUse", "session_id": "thread-1",
                                  "turn_id": "turn-1", "tool_response": {"exit_code": 1}})
        self.assertEqual(parsed["state"], "running")
        self.assertNotEqual(parsed["state"], "blocked")


if __name__ == "__main__":
    unittest.main()
