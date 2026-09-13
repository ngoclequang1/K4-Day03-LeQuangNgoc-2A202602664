"""Native function calling with explicit session history; API errors never fall back to mock."""
import json
import os
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class BaseLLMProvider:
    is_mock = False

    def start_session(self, system_prompt):
        self.system_prompt = system_prompt
        self.messages = []
        self.original_prompt = ""

    def add_user(self, prompt):
        self.original_prompt = prompt
        self.messages.append({"role": "user", "content": prompt})

    def generate(self, prompt, system_prompt=""):
        self.start_session(system_prompt)
        self.add_user(prompt)
        return self.next_response([]).get("content", "")


class MockOfflineProvider(BaseLLMProvider):
    """Small deterministic smoke-test simulator, not an LLM or general language parser."""
    is_mock = True
    model_name = "pet-care-offline-simulator"

    def start_session(self, system_prompt):
        super().start_session(system_prompt)
        self.observations = []

    def add_user(self, prompt):
        super().add_user(prompt)
        self.observations = []

    def record_tool_result(self, call, result):
        self.observations.append((call, result))

    def next_response(self, tools_schema):
        prompt = self.original_prompt
        pet = re.search(r"PET\d+", prompt, re.I)
        if not pet:
            return {"type": "text", "content": "Bạn vui lòng cung cấp mã thú cưng (pet_id) để tôi tra cứu và đặt lịch."}
        pet_id = pet.group().upper()
        booking = "đặt" in prompt.lower()
        if not self.observations:
            args = {"pet_id": pet_id}
            if booking:
                args.update(service_type="bath", date_from="2026-09-20", date_to="2026-09-20")
            return {"type": "tool_calls", "calls": [{"id": "mock-query", "name": "query_pet_care", "arguments": args}]}
        call, result = self.observations[-1]
        if call["name"] == "schedule_pet_care":
            if result["status"] == "SLOT_UNAVAILABLE":
                return {"type": "tool_calls", "calls": [{"id": "mock-requery", "name": "query_pet_care",
                        "arguments": {"pet_id": pet_id, "service_type": "bath", "date_from": "2026-09-20", "date_to": "2026-09-20"}}]}
            return {"type": "text", "content": json.dumps(result, ensure_ascii=False)}
        if result["status"] != "SUCCESS" or not booking:
            return {"type": "text", "content": json.dumps(result, ensure_ascii=False)}
        if any(c["name"] == "schedule_pet_care" for c, _ in self.observations):
            alternatives = [s for s in result["available_slots"] if not s["conflicts_with_pet"]
                            and s["price_vnd"] <= 200000 and s["starts_at"][11:16] > "14:00"]
            return {"type": "text", "content": "Khung giờ vừa hết chỗ. Các lựa chọn khác: " + json.dumps(alternatives, ensure_ascii=False)}
        slots = [s for s in result["available_slots"] if not s["conflicts_with_pet"] and s["price_vnd"] <= 200000]
        if "10:30" in prompt:
            slots = [s for s in slots if "T10:30" in s["starts_at"]]
        else:
            slots = [s for s in slots if s["starts_at"][11:16] > "14:00"]
        if not slots:
            return {"type": "text", "content": "Không có lịch phù hợp hoặc bị trùng lịch. Bạn có muốn chọn giờ khác không?"}
        if "Ngọc" not in prompt:
            return {"type": "text", "content": "Vui lòng cung cấp tên chủ nuôi."}
        return {"type": "tool_calls", "calls": [{"id": "mock-book", "name": "schedule_pet_care",
                "arguments": {"pet_id": pet_id, "slot_id": slots[0]["slot_id"], "owner_name": "Ngọc"}}]}


class OpenAIProvider(BaseLLMProvider):
    def __init__(self, api_key=None, model=None):
        from openai import OpenAI
        self.model_name = model or os.getenv("LLM_MODEL") or "gpt-4o-mini"
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"), timeout=45, max_retries=0)

    def next_response(self, tools_schema):
        kwargs = {}
        if tools_schema:
            kwargs = {"tools": [{"type": "function", "function": t} for t in tools_schema],
                      "parallel_tool_calls": False}
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "system", "content": self.system_prompt}] + self.messages, **kwargs)
        msg = response.choices[0].message
        self.messages.append(msg.model_dump(exclude_none=True))
        if msg.tool_calls:
            return {"type": "tool_calls", "calls": [
                {"id": c.id, "name": c.function.name, "arguments": json.loads(c.function.arguments)}
                for c in msg.tool_calls]}
        return {"type": "text", "content": msg.content or ""}

    def record_tool_result(self, call, result):
        self.messages.append({"role": "tool", "tool_call_id": call["id"],
                              "content": json.dumps(result, ensure_ascii=False)})


class GeminiProvider(BaseLLMProvider):
    def __init__(self, api_key=None, model=None):
        from google import genai
        from google.genai import types
        self.types = types
        self.model_name = model or os.getenv("LLM_MODEL") or "gemini-2.5-flash"
        self.client = genai.Client(api_key=api_key or os.getenv("GEMINI_API_KEY"),
                                   http_options=types.HttpOptions(timeout=45000))

    def add_user(self, prompt):
        self.original_prompt = prompt
        self.messages.append(self.types.Content(role="user", parts=[self.types.Part.from_text(text=prompt)]))

    def next_response(self, tools_schema):
        t = self.types
        # parameters_json_schema supports standard JSON Schema, including additionalProperties.
        declarations = [t.FunctionDeclaration(name=s["name"], description=s["description"],
                        parameters_json_schema=s["parameters"]) for s in tools_schema]
        response = self.client.models.generate_content(
            model=self.model_name, contents=self.messages,
            config=t.GenerateContentConfig(
                system_instruction=self.system_prompt,
                tools=[t.Tool(function_declarations=declarations)] if declarations else None,
                automatic_function_calling=t.AutomaticFunctionCallingConfig(disable=True),
                temperature=0.2))
        if not response.candidates or not response.candidates[0].content:
            raise RuntimeError("Gemini returned no candidate content.")
        content = response.candidates[0].content
        # Preserve the full model Content (including thought signatures).
        self.messages.append(content)
        calls = [p.function_call for p in content.parts or [] if p.function_call]
        if calls:
            return {"type": "tool_calls", "calls": [
                {"id": c.id, "name": c.name, "arguments": dict(c.args or {})} for c in calls]}
        text = "".join(p.text for p in content.parts or [] if p.text and not p.thought)
        return {"type": "text", "content": text}

    def record_tool_result(self, call, result):
        t = self.types
        part = t.Part(function_response=t.FunctionResponse(id=call.get("id"), name=call["name"], response=result))
        if self.messages and self.messages[-1].role == "user":
            self.messages[-1].parts.append(part)
        else:
            self.messages.append(t.Content(role="user", parts=[part]))


def get_llm_provider(provider_type=None, require_live=False):
    name = (provider_type or os.getenv("LLM_PROVIDER", "mock")).lower()
    if name == "mock":
        if require_live:
            raise ValueError("--require-live không cho phép MockOfflineProvider.")
        return MockOfflineProvider()
    classes = {"gemini": (GeminiProvider, "GEMINI_API_KEY"), "openai": (OpenAIProvider, "OPENAI_API_KEY")}
    if name not in classes:
        raise ValueError(f"Provider không được hỗ trợ: {name}")
    cls, key_name = classes[name]
    key = os.getenv(key_name, "")
    if not key or key.startswith("your_"):
        if require_live:
            raise ValueError(f"Chưa cấu hình {key_name}.")
        return MockOfflineProvider()
    return cls()
