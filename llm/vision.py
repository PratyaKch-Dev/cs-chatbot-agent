"""
Vision helper — describe a user-sent image for the pipeline.

Uses the same provider configured in LLM_PROVIDER (defaults to Google Gemini).
"""

import base64
import logging
import os

_logger = logging.getLogger("llm.vision")

_PROMPT = (
    "ผู้ใช้ส่งภาพนี้ในแชทระบบ HR/Payroll (Salary Hero / Salary on Demand)\n"
    "สรุปสั้นๆ ว่า:\n"
    "1. ภาพแสดงอะไร (หน้าจอ, ข้อความ, ตัวเลข สำคัญ)\n"
    "2. ปัญหาหรือสถานะที่เห็นชัดเจนคืออะไร (เช่น มีค่าธรรมเนียมค้างชำระ, ยอดเป็น 0, มี error message)\n"
    "ตอบเป็นข้อความธรรมดาไม่เกิน 3 บรรทัด ใช้ภาษาเดียวกับที่เห็นในภาพ ห้ามละเว้นตัวเลขหรือข้อความสำคัญ"
)


def describe_image(image_bytes: bytes, media_type: str = "image/jpeg") -> str:
    """Return a text description of the image to use as the user's message."""
    try:
        import google.generativeai as genai
        genai.configure(api_key=os.environ.get("GOOGLE_API_KEY", ""))
        model = genai.GenerativeModel(
            os.environ.get("LLM_MODEL", "gemini-2.5-flash")
        )
        response = model.generate_content([
            {"mime_type": media_type, "data": base64.standard_b64encode(image_bytes).decode()},
            _PROMPT,
        ])
        return response.text.strip()
    except Exception as exc:
        _logger.warning(f"[vision] describe failed: {exc}")
        return "ผู้ใช้ส่งรูปภาพ"
