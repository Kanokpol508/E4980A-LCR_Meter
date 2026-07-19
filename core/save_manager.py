# -*- coding: utf-8 -*-
"""
save_manager.py
================
ระบบจัดการไฟล์ Save ผลลัพธ์การวัด (Save / Open / List / Delete)

โฟลเดอร์ที่ใช้เก็บ Save ทุกไฟล์:
    <โฟลเดอร์ Documents ของผู้ใช้>/LCR_Metrology_Saves
    (ถ้าเครื่องไหนไม่มีโฟลเดอร์ Documents จะ fallback ไปที่ Home โดยตรง)

ใช้ path นี้เสมอไม่ว่าจะรันบนคอมพิวเตอร์/โน้ตบุ๊คเครื่องไหนก็ตาม เพราะอิง
Path.home() ของผู้ใช้ที่ล็อกอินอยู่ ณ ขณะนั้น ไม่ hardcode path เฉพาะเครื่อง

รูปแบบไฟล์: JSON (อ่านง่าย, debug ง่าย, ไม่ต้องพึ่ง library เพิ่ม)
ชื่อไฟล์: <YYYYMMDD_HHMMSS>_<ชื่อที่ผู้ใช้ตั้ง>.json
"""

import os
import sys
import json
import time
import re
from pathlib import Path

SAVE_FOLDER_NAME = "LCR_Metrology_Saves"

# โหมดวัดที่รองรับ (ใช้ตรวจสอบ/แสดงผลใน dropdown กรอง)
RUN_MODE_LABELS = {
    "SINGLE": "Single",
    "SWEEP": "Sweep",
    "LIST": "List",
}


def get_save_folder() -> Path:
    """
    คืนค่าโฟลเดอร์ที่ใช้เก็บ Save (สร้างให้อัตโนมัติถ้ายังไม่มี)
    ใช้ ~/Documents/LCR_Metrology_Saves เป็นหลัก เพื่อให้ทุกเครื่อง (Windows/Mac/Linux)
    มีโฟลเดอร์นี้แน่นอนตามผู้ใช้ที่ล็อกอิน ไม่ผูกกับ path เฉพาะเครื่องใดเครื่องหนึ่ง
    """
    home = Path.home()
    docs = home / "Documents"
    base = docs if docs.exists() else home
    folder = base / SAVE_FOLDER_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _safe_filename(name: str) -> str:
    """ตัดอักขระที่ใช้เป็นชื่อไฟล์ไม่ได้ทิ้ง แต่คงตัวอักษรไทย/อังกฤษ/ตัวเลขไว้"""
    name = name.strip()
    # อนุญาต: ตัวอักษร/ตัวเลขทุกภาษา, ช่องว่าง, - _ ( )
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", name)
    cleaned = cleaned.strip().strip(".")
    return cleaned or "Save"


def save_result(save_name: str, snapshot: dict) -> Path:
    """
    บันทึก snapshot (dict) ลงไฟล์ JSON ในโฟลเดอร์ Save
    คืนค่า Path ของไฟล์ที่บันทึกสำเร็จ
    """
    folder = get_save_folder()
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    base_name = f"{timestamp}_{_safe_filename(save_name)}"
    path = folder / f"{base_name}.json"

    counter = 1
    while path.exists():
        path = folder / f"{base_name}_{counter}.json"
        counter += 1

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, ensure_ascii=False, indent=2)

    return path


def load_save(path) -> dict:
    """โหลดข้อมูล Save จาก path ที่ระบุ คืนค่าเป็น dict"""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def delete_save(path) -> bool:
    """ลบไฟล์ Save ที่ระบุ คืนค่า True ถ้าลบสำเร็จ"""
    p = Path(path)
    try:
        p.unlink()
        return True
    except FileNotFoundError:
        return False


def list_saves(run_mode_filter: str = "ALL") -> list:
    """
    คืนค่ารายชื่อ Save ทั้งหมดในโฟลเดอร์ (หรือกรองตามโหมดวัดที่ระบุ)
    เรียงจากล่าสุด -> เก่าสุด (ตามเวลาที่วัดเสร็จ)
    แต่ละรายการ: {'path', 'save_name', 'measurement_time', 'run_mode'}
    """
    folder = get_save_folder()
    items = []
    for f in sorted(folder.glob("*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue

        meta = data.get("meta", {})
        run_mode = meta.get("run_mode", "-")

        if run_mode_filter and run_mode_filter != "ALL" and run_mode != run_mode_filter:
            continue

        items.append({
            "path": str(f),
            "save_name": meta.get("save_name", f.stem),
            "measurement_time": meta.get("measurement_time", ""),
            "measurement_time_sort": meta.get("measurement_time_iso", ""),
            "run_mode": run_mode,
        })

    items.sort(key=lambda x: x["measurement_time_sort"], reverse=True)
    return items


def open_folder_in_explorer():
    """เปิดโฟลเดอร์ Save ด้วย File Explorer / Finder / File Manager ของระบบปฏิบัติการ"""
    folder = get_save_folder()
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(folder))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            os.system(f'open "{folder}"')
        else:
            os.system(f'xdg-open "{folder}"')
        return True
    except Exception:
        return False