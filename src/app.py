"""Pet Care Planner CLI: native tool loop, isolated evaluations and measured traces."""
import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from mcp_server import MCPPetCareServer
from tools import PetCareStore
from prompts import CHATBOT_BASELINE_PROMPT, REACT_AGENT_SYSTEM_PROMPT, MAX_ITERATIONS
from providers import get_llm_provider

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load_test_cases():
    return json.loads((ROOT / "config" / "test_cases.json").read_text(encoding="utf-8"))


def save_waterfall_trace(trace_data, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(trace_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Trace: {path}")


def run_baseline_chatbot(user_query, provider):
    return provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)


def run_react_agent(user_query, provider, mcp_server, *, new_session=True, before_tool=None, case_id=None):
    if new_session:
        provider.start_session(REACT_AGENT_SYSTEM_PROMPT)
        provider.user_inputs = []
    provider.user_inputs.append(user_query)
    provider.add_user(user_query)
    logs = []
    booking_failed = False
    recovery_observed = False
    known_pet_ids = set(re.findall(r"PET\d+", " ".join(provider.user_inputs).upper()))
    metadata = {"query": user_query, "case_id": case_id,
                "provider": type(provider).__name__, "model": provider.model_name,
                "is_mock": provider.is_mock, "started_at": datetime.now(timezone.utc).isoformat()}
    for step in range(1, MAX_ITERATIONS + 1):
        start = time.perf_counter()
        try:
            available_tools = [t for t in mcp_server.list_tools()
                               if not recovery_observed and (not booking_failed or t["name"] != "schedule_pet_care")]
            original_system_prompt = provider.system_prompt
            if recovery_observed:
                provider.system_prompt += "\nTRẠNG THÁI THỰC THI: Lần đặt đã thất bại, đã tra cứu lại. Chưa tạo lịch thay thế và hiện không được phép đặt thêm. Câu trả lời cuối phải nói rõ chưa đặt được, chỉ đề xuất giờ phù hợp còn trống và hỏi người dùng chọn. Không nói sẽ đặt, đang đặt, tiến hành đặt hoặc đã đặt."
            try:
                response = provider.next_response(available_tools)
            finally:
                provider.system_prompt = original_system_prompt
        except Exception as error:
            # Avoid including raw API exceptions, which may contain credentials or request URLs.
            logs.append({**metadata, "step": step, "action_type": "ERROR",
                         "output": f"Provider request failed: {type(error).__name__}",
                         "latency_ms": round((time.perf_counter() - start) * 1000, 2)})
            print(logs[-1]["output"])
            return logs
        llm_ms = round((time.perf_counter() - start) * 1000, 2)
        if response["type"] == "text":
            logs.append({**metadata, "step": step, "action_type": "FINAL_ANSWER",
                         "thought": "Tổng hợp phản hồi từ ngữ cảnh và kết quả công cụ.",
                         "output": response["content"], "latency_ms": llm_ms})
            print(response["content"])
            return logs
        calls = response.get("calls", [])
        if not calls:
            logs.append({**metadata, "step": step, "action_type": "ERROR", "output": "Empty tool response."})
            return logs
        for index, call in enumerate(calls):
            arguments = call.get("arguments", {})
            requested_pet = arguments.get("pet_id", "") if isinstance(arguments, dict) else ""
            blocked = None
            if isinstance(requested_pet, str) and requested_pet.strip().upper() not in known_pet_ids:
                blocked = {"status": "CLARIFICATION_REQUIRED", "message": "Mã thú cưng chưa được người dùng cung cấp. Hỏi mã thú cưng; không đoán từ ví dụ schema."}
            elif booking_failed and call["name"] == "schedule_pet_care":
                blocked = {"status": "ACTION_BLOCKED", "message": "Lần đặt vừa thất bại. Chỉ tra cứu lại và đề xuất, chờ người dùng chọn ở lượt tiếp theo."}
            if before_tool and blocked is None:
                event = before_tool(call, mcp_server)
                if event:
                    logs.append({**metadata, "step": step, "action_type": "TEST_SETUP", **event})
            start = time.perf_counter()
            envelope = ({"id": None, "result": blocked} if blocked is not None
                        else mcp_server.call_tool(call["name"], call["arguments"]))
            result = envelope["result"]
            if call["name"] == "schedule_pet_care" and result.get("status") != "SUCCESS":
                booking_failed = True
            elif booking_failed and call["name"] == "query_pet_care" and result.get("status") == "SUCCESS":
                recovery_observed = True
            tool_ms = round((time.perf_counter() - start) * 1000, 2)
            provider.record_tool_result(call, result)
            logs.append({**metadata, "step": step, "action_type": "TOOL_EXECUTION",
                         "thought": f"Model selected {call['name']}; observable action summary, not hidden reasoning.",
                         "tool_name": call["name"], "arguments": call["arguments"],
                         "observation": result, "request_id": envelope["id"], "executed": blocked is None,
                         "llm_latency_ms": llm_ms if index == 0 else 0,
                         "latency_ms": tool_ms})
            print(f"  {call['name']}: {result.get('status')}")
    logs.append({**metadata, "step": MAX_ITERATIONS, "action_type": "ITERATION_LIMIT",
                 "output": "Đã đạt giới hạn vòng lặp; chưa có câu trả lời cuối cùng."})
    return logs


def evaluate_case(tc, logs, store):
    calls = [e for e in logs if e["action_type"] == "TOOL_EXECUTION"]
    names = [e["tool_name"] for e in calls]
    final = logs[-1] if logs else {}
    bookings = [a for a in store.appointments("PET001") if a["slot_id"] != "SLOT003"]
    ok = final.get("action_type") == "FINAL_ANSWER" and bool(final.get("output", "").strip())
    expected = tc["expected"]
    if expected == "lookup":
        ok = ok and "query_pet_care" in names and "schedule_pet_care" not in names and not bookings
    elif expected == "booking":
        successful = [e for e in calls if e["tool_name"] == "schedule_pet_care" and e["observation"]["status"] == "SUCCESS"]
        ok = ok and len(bookings) == 1 and bool(successful)
        if ok:
            a = bookings[0]
            ok = (a["service_type"] == "bath" and a["starts_at"][:10] == "2026-09-20"
                  and a["starts_at"][11:16] > "14:00" and a["price_vnd"] <= 200000
                  and "query_pet_care" in names
                  and names.index("query_pet_care") < names.index("schedule_pet_care")
                  and successful[0]["observation"]["booking_id"] in final["output"])
    elif expected == "conflict":
        ok = ok and "query_pet_care" in names and not bookings
    elif expected == "clarification":
        text = final.get("output", "").lower()
        ok = ok and not any(e.get("executed", True) for e in calls) and not bookings and ("mã" in text or "pet_id" in text)
    elif expected == "race":
        failures = [i for i,e in enumerate(calls) if e["observation"].get("status") == "SLOT_UNAVAILABLE"]
        ok = ok and not bookings and bool(failures)
        if failures:
            ok = ok and any(e["tool_name"] == "query_pet_care" for e in calls[failures[0] + 1:])
    return {"id": tc["id"], "passed": bool(ok), "tool_calls": sum(e.get("executed", True) for e in calls),
            "note": "Automated tool/state checks; final wording also requires review."}


def race_hook():
    fired = False
    def hook(call, server):
        nonlocal fired
        if not fired and call["name"] == "schedule_pet_care":
            fired = True
            result = server.store.schedule_pet_care("PET002", call["arguments"]["slot_id"], "Test fixture")
            return {"description": "Simulated competing booking immediately before agent booking.",
                    "fixture_result": result}
    return hook


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--all", action="store_true")
    mode.add_argument("--interactive", action="store_true")
    mode.add_argument("--baseline", action="store_true")
    parser.add_argument("--provider", choices=["mock", "gemini", "openai"])
    parser.add_argument("--require-live", action="store_true")
    parser.add_argument("--trace", type=Path)
    args = parser.parse_args()
    provider = get_llm_provider(args.provider, args.require_live)
    suffix = "offline" if provider.is_mock else "live"
    path = args.trace or ROOT / "docs" / ("trace_offline.json" if provider.is_mock else "trace_waterfall.json")
    print(f"Pet Care Planner | {type(provider).__name__} | {provider.model_name}")
    if args.all:
        traces, results = [], []
        for tc in load_test_cases():
            print(f"\n{tc['id']}: {tc['question']}")
            store = PetCareStore(":memory:")
            try:
                logs = run_react_agent(tc["question"], provider, MCPPetCareServer(store),
                    before_tool=race_hook() if tc.get("simulate_slot_race") else None, case_id=tc["id"])
                traces.extend(logs)
                results.append(evaluate_case(tc, logs, store))
            finally:
                store.close()
        save_waterfall_trace(traces, path)
        report = {"provider": type(provider).__name__, "model": provider.model_name, "is_mock": provider.is_mock,
                  "passed": sum(r["passed"] for r in results), "total": len(results), "results": results}
        save_waterfall_trace(report, path.with_name(f"eval_{suffix}.json"))
        print(f"PASS: {report['passed']}/{report['total']}")
        return 0 if report["passed"] == report["total"] else 1
    if args.baseline:
        print(run_baseline_chatbot(load_test_cases()[1]["question"], provider))
        return 0
    store = PetCareStore()
    try:
        server = MCPPetCareServer(store)
        if args.interactive:
            print("Nhập yêu cầu chăm sóc thú cưng; exit để thoát. Ví dụ: Tra cứu PET001.")
            logs = []
            first = True
            while True:
                try:
                    prompt = input("Bạn: ").strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if prompt.lower() in ("exit", "quit"):
                    break
                if not prompt:
                    continue
                turn = run_react_agent(prompt, provider, server, new_session=first)
                first = False
                logs.extend(turn)
                save_waterfall_trace(logs, path)
        else:
            save_waterfall_trace(run_react_agent(load_test_cases()[0]["question"], provider, server), path)
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
