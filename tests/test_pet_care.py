"""Backend invariants and loop behavior, without network calls."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from tools import PetCareStore, dispatch_tool_call
from mcp_server import MCPPetCareServer
from providers import MockOfflineProvider
from app import run_react_agent


class PetCareTests(unittest.TestCase):
    def setUp(self):
        self.store = PetCareStore(":memory:")

    def tearDown(self):
        self.store.close()

    def test_booking_updates_availability_and_is_idempotent(self):
        result = self.store.schedule_pet_care("PET001", "SLOT001", "Ngọc")
        self.assertEqual(result["status"], "SUCCESS")
        self.assertNotIn("SLOT001", [s["slot_id"] for s in
                         self.store.query_pet_care("PET001")["available_slots"]])
        self.assertEqual(self.store.schedule_pet_care("PET001", "SLOT001", "Ngọc")["status"], "ALREADY_BOOKED")
        self.assertEqual(len(self.store.appointments("PET001")), 2)

    def test_overlap_rejected_even_with_different_slot(self):
        self.assertEqual(self.store.schedule_pet_care("PET001", "SLOT004", "Ngọc")["status"],
                         "SCHEDULE_CONFLICT")
        self.assertEqual(len(self.store.appointments("PET001")), 1)

    def test_species_and_unknown_records(self):
        self.assertEqual(self.store.schedule_pet_care("PET001", "SLOT005", "Ngọc")["status"],
                         "INCOMPATIBLE_SERVICE")
        self.assertEqual(self.store.query_pet_care("PET999")["status"], "NOT_FOUND")
        self.assertEqual(self.store.schedule_pet_care("PET001", "BAD", "Ngọc")["status"], "NOT_FOUND")

    def test_invalid_tool_arguments(self):
        for args in ({}, {"pet_id": 1}, {"pet_id": " "}, {"pet_id": "PET001", "extra": "x"},
                     {"pet_id": "PET001", "service_type": "invalid"},
                     {"pet_id": "PET001", "date_from": "invalid"},
                     {"pet_id": "PET001", "date_from": "2026-09-21", "date_to": "2026-09-20"}):
            with self.subTest(args=args):
                result = json.loads(dispatch_tool_call("query_pet_care", args, self.store))
                self.assertEqual(result["status"], "INVALID_ARGUMENTS")
        self.assertEqual(json.loads(dispatch_tool_call("unknown", {}, self.store))["status"], "UNKNOWN_TOOL")

    def test_persistence_and_stale_availability_across_connections(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pets.sqlite3"
            first, second = PetCareStore(path), PetCareStore(path)
            try:
                self.assertTrue(first.query_pet_care("PET001")["available_slots"])
                self.assertEqual(second.schedule_pet_care("PET002", "SLOT001", "Other")["status"], "SUCCESS")
                self.assertEqual(first.schedule_pet_care("PET001", "SLOT001", "Ngọc")["status"], "SLOT_UNAVAILABLE")
            finally:
                first.close()
                second.close()
            reopened = PetCareStore(path)
            try:
                self.assertEqual(len(reopened.appointments("PET002")), 1)
            finally:
                reopened.close()

    def test_loop_observes_then_books_then_finishes(self):
        logs = run_react_agent(
            "Tôi là Ngọc. Đặt lịch tắm PET001 ngày 20/09/2026 sau 14:00, dưới 200.000 đồng.",
            MockOfflineProvider(), MCPPetCareServer(self.store))
        self.assertEqual([e.get("tool_name") for e in logs[:-1]], ["query_pet_care", "schedule_pet_care"])
        self.assertEqual(logs[-1]["action_type"], "FINAL_ANSWER")
        self.assertTrue(all(e["is_mock"] for e in logs))

    def test_provider_error_is_not_mock_success(self):
        class FailingProvider(MockOfflineProvider):
            is_mock = False
            def next_response(self, schemas):
                raise ConnectionError("secret must not be logged")
        logs = run_react_agent("Tra cứu PET001", FailingProvider(), MCPPetCareServer(self.store))
        self.assertEqual(logs[-1]["action_type"], "ERROR")
        self.assertNotIn("secret", str(logs))

    def test_loop_limit_is_explicit(self):
        class LoopingProvider(MockOfflineProvider):
            def next_response(self, schemas):
                return {"type": "tool_calls", "calls": [
                    {"id": "again", "name": "query_pet_care", "arguments": {"pet_id": "PET001"}}]}
        logs = run_react_agent("Tra cứu PET001", LoopingProvider(), MCPPetCareServer(self.store))
        self.assertEqual(logs[-1]["action_type"], "ITERATION_LIMIT")

    def test_guessed_pet_id_is_blocked_before_database_access(self):
        class GuessingProvider(MockOfflineProvider):
            def next_response(self, schemas):
                if self.observations:
                    return {"type": "text", "content": "Vui lòng cung cấp mã thú cưng."}
                return {"type": "tool_calls", "calls": [{"id": "guess", "name": "query_pet_care", "arguments": {"pet_id": "PET001"}}]}
        logs = run_react_agent("Đặt lịch tắm cho thú cưng của tôi", GuessingProvider(), MCPPetCareServer(self.store))
        self.assertFalse(logs[0]["executed"])
        self.assertEqual(logs[0]["observation"]["status"], "CLARIFICATION_REQUIRED")

    def test_booking_tool_removed_after_failed_booking(self):
        from app import race_hook
        class CheckingProvider(MockOfflineProvider):
            def next_response(self, schemas):
                if any(r.get("status") == "SLOT_UNAVAILABLE" for _, r in self.observations):
                    assert "schedule_pet_care" not in [t["name"] for t in schemas]
                return super().next_response(schemas)
        logs = run_react_agent("Tôi là Ngọc. Đặt lịch tắm PET001 ngày 20/09/2026 sau 14:00",
                               CheckingProvider(), MCPPetCareServer(self.store), before_tool=race_hook())
        self.assertEqual(logs[-1]["action_type"], "FINAL_ANSWER")
        self.assertEqual(len(self.store.appointments("PET001")), 1)


if __name__ == "__main__":
    unittest.main()
