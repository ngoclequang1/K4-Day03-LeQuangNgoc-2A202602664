"""Pet care tools backed by SQLite, using fictional lab data."""
import json
import os
import sqlite3
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ["bath", "grooming", "brushing"]
TOOLS_SCHEMA = [
    {"name": "query_pet_care", "description": "Tra cứu hồ sơ, lịch sử, lịch hẹn và khung giờ trống. Thời gian Asia/Bangkok.",
     "parameters": {"type": "object", "properties": {
         "pet_id": {"type": "string", "description": "Mã thú cưng người dùng cung cấp, ví dụ PET001."},
         "service_type": {"type": "string", "enum": SERVICES},
         "date_from": {"type": "string", "description": "Ngày bắt đầu YYYY-MM-DD."},
         "date_to": {"type": "string", "description": "Ngày kết thúc YYYY-MM-DD."}
     }, "required": ["pet_id"], "additionalProperties": False}},
    {"name": "schedule_pet_care", "description": "Đặt lịch sau khi tra cứu và người dùng yêu cầu đặt. Kiểm tra lại khung giờ và xung đột trước khi lưu.",
     "parameters": {"type": "object", "properties": {
         "pet_id": {"type": "string"}, "slot_id": {"type": "string", "description": "Mã từ query_pet_care."},
         "owner_name": {"type": "string", "description": "Tên chủ nuôi người dùng cung cấp."}
     }, "required": ["pet_id", "slot_id", "owner_name"], "additionalProperties": False}}
]


class PetCareStore:
    def __init__(self, path=None):
        self.path = str(path or os.getenv("PET_CARE_DB", ROOT / "data" / "pet_care.sqlite3"))
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS pets (pet_id TEXT PRIMARY KEY, name TEXT, species TEXT);
            CREATE TABLE IF NOT EXISTS history (pet_id TEXT REFERENCES pets, service_type TEXT, performed_at TEXT);
            CREATE TABLE IF NOT EXISTS slots (
                slot_id TEXT PRIMARY KEY, service_type TEXT, species TEXT,
                starts_at TEXT, ends_at TEXT, price_vnd INTEGER);
            CREATE TABLE IF NOT EXISTS appointments (
                booking_id INTEGER PRIMARY KEY AUTOINCREMENT,
                pet_id TEXT REFERENCES pets, slot_id TEXT UNIQUE REFERENCES slots, owner_name TEXT);
        """)
        if not self.db.execute("SELECT 1 FROM pets LIMIT 1").fetchone():
            seed = json.loads((ROOT / "config" / "pet_care_seed.json").read_text(encoding="utf-8"))
            with self.db:
                self.db.executemany("INSERT INTO pets VALUES (:pet_id,:name,:species)", seed["pets"])
                self.db.executemany("INSERT INTO history VALUES (:pet_id,:service_type,:performed_at)", seed["history"])
                self.db.executemany("INSERT INTO slots VALUES (:slot_id,:service_type,:species,:starts_at,:ends_at,:price_vnd)", seed["slots"])
                self.db.executemany("INSERT INTO appointments(pet_id,slot_id,owner_name) VALUES (:pet_id,:slot_id,:owner_name)", seed["appointments"])

    def close(self):
        self.db.close()

    def appointments(self, pet_id):
        return [dict(row) for row in self.db.execute("""
            SELECT a.*, s.service_type, s.starts_at, s.ends_at, s.price_vnd
            FROM appointments a JOIN slots s USING(slot_id) WHERE pet_id=? ORDER BY starts_at
        """, (pet_id,))]

    def query_pet_care(self, pet_id, service_type=None, date_from=None, date_to=None):
        pet_id = pet_id.strip().upper()
        pet = self.db.execute("SELECT * FROM pets WHERE pet_id=?", (pet_id,)).fetchone()
        if not pet:
            return {"status": "NOT_FOUND", "message": "Không tìm thấy mã thú cưng.", "pet_id": pet_id}
        for value in (date_from, date_to):
            if value:
                date.fromisoformat(value)
        if date_from and date_to and date_from > date_to:
            raise ValueError("date_from phải trước hoặc bằng date_to.")
        appointments = self.appointments(pet_id)
        slots = []
        for row in self.db.execute("""
            SELECT s.* FROM slots s LEFT JOIN appointments a USING(slot_id)
            WHERE a.booking_id IS NULL ORDER BY starts_at, slot_id
        """):
            slot = dict(row)
            if slot["species"] != pet["species"] or (service_type and slot["service_type"] != service_type):
                continue
            day = slot["starts_at"][:10]
            if (date_from and day < date_from) or (date_to and day > date_to):
                continue
            slot["conflicts_with_pet"] = any(
                slot["starts_at"] < a["ends_at"] and a["starts_at"] < slot["ends_at"] for a in appointments)
            slots.append(slot)
        history = [dict(r) for r in self.db.execute(
            "SELECT * FROM history WHERE pet_id=? ORDER BY performed_at DESC", (pet_id,))]
        return {"status": "SUCCESS", "pet": dict(pet), "care_history": history,
                "appointments": appointments, "available_slots": slots, "timezone": "Asia/Bangkok"}

    def schedule_pet_care(self, pet_id, slot_id, owner_name):
        pet_id, slot_id = pet_id.strip().upper(), slot_id.strip().upper()
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            pet = self.db.execute("SELECT * FROM pets WHERE pet_id=?", (pet_id,)).fetchone()
            slot = self.db.execute("SELECT * FROM slots WHERE slot_id=?", (slot_id,)).fetchone()
            if not pet or not slot:
                return {"status": "NOT_FOUND", "message": "Không tìm thấy thú cưng hoặc khung giờ."}
            existing = self.db.execute("SELECT * FROM appointments WHERE slot_id=?", (slot_id,)).fetchone()
            if existing:
                status = "ALREADY_BOOKED" if existing["pet_id"] == pet_id else "SLOT_UNAVAILABLE"
                return {"status": status, "message": "Khung giờ đã có lịch hẹn; không tạo thêm."}
            if pet["species"] != slot["species"]:
                return {"status": "INCOMPATIBLE_SERVICE", "message": "Dịch vụ không phù hợp loại thú cưng."}
            if any(slot["starts_at"] < a["ends_at"] and a["starts_at"] < slot["ends_at"]
                   for a in self.appointments(pet_id)):
                return {"status": "SCHEDULE_CONFLICT", "message": "Thú cưng đã có lịch hẹn chồng chéo."}
            cursor = self.db.execute(
                "INSERT INTO appointments(pet_id,slot_id,owner_name) VALUES (?,?,?)",
                (pet_id, slot_id, owner_name.strip()))
            return {"status": "SUCCESS", "booking_id": f"PC-{cursor.lastrowid:04d}",
                    "pet_id": pet_id, "owner_name": owner_name.strip(), **dict(slot),
                    "message": "Đã lưu lịch chăm sóc thú cưng."}


def dispatch_tool_call(tool_name, arguments, store=None):
    schema = next((t["parameters"] for t in TOOLS_SCHEMA if t["name"] == tool_name), None)
    if schema is None:
        return json.dumps({"status": "UNKNOWN_TOOL", "message": "Công cụ không tồn tại."})
    if not isinstance(arguments, dict):
        return json.dumps({"status": "INVALID_ARGUMENTS", "message": "Tham số phải là object."})
    if set(arguments) - set(schema["properties"]) or any(k not in arguments for k in schema["required"]):
        return json.dumps({"status": "INVALID_ARGUMENTS", "message": "Thiếu hoặc thừa tham số."})
    for key, value in arguments.items():
        prop = schema["properties"][key]
        if not isinstance(value, str) or not value.strip() or ("enum" in prop and value not in prop["enum"]):
            return json.dumps({"status": "INVALID_ARGUMENTS", "message": f"Tham số không hợp lệ: {key}"})
    owned = store is None
    store = store or PetCareStore()
    try:
        return json.dumps(getattr(store, tool_name)(**arguments), ensure_ascii=False)
    except ValueError as error:
        return json.dumps({"status": "INVALID_ARGUMENTS", "message": str(error)}, ensure_ascii=False)
    finally:
        if owned:
            store.close()
