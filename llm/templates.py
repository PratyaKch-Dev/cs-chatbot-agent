"""
Pre-written response templates for simple intents.

Used to respond to greetings, thanks, etc. without hitting the LLM.
All templates must be available in both Thai and English.
"""

from llm.intent import Intent

THAI_TEMPLATES: dict[str, str] = {
    Intent.GREETING: "สวัสดีค่ะ ยินดีให้บริการค่ะ มีอะไรให้ช่วยเหลือไหมคะ?",
    Intent.THANKS: "ยินดีให้บริการค่ะ หากมีข้อสงสัยเพิ่มเติม สามารถถามได้เลยนะคะ",
    Intent.GOODBYE: "ลาก่อนค่ะ หวังว่าจะได้ช่วยเหลือคุณได้อีกในครั้งต่อไปนะคะ",
    Intent.FRUSTRATED: (
        "ขอโทษสำหรับความไม่สะดวกค่ะ เราเข้าใจว่าปัญหานี้อาจทำให้รู้สึกหงุดหงิดได้ "
        "ขอให้เล่าปัญหาให้ฟังนะคะ เราจะพยายามช่วยให้ดีที่สุดค่ะ"
    ),
    Intent.CONFUSED: "ขอโทษนะคะ ช่วยอธิบายปัญหาให้ละเอียดขึ้นได้ไหมคะ?",
    Intent.UNCLEAR: "กรุณาบอกรายละเอียดเพิ่มเติมได้เลยค่ะ เพื่อที่เราจะได้ช่วยได้ถูกต้องค่ะ",
}

ENGLISH_TEMPLATES: dict[str, str] = {
    Intent.GREETING: "Hello! How can I help you today?",
    Intent.THANKS: "You're welcome! Feel free to ask if you have any more questions.",
    Intent.GOODBYE: "Goodbye! Hope I was able to help. Have a great day!",
    Intent.FRUSTRATED: (
        "I'm sorry to hear you're having trouble. I understand this can be frustrating. "
        "Please describe the issue and I'll do my best to help."
    ),
    Intent.CONFUSED: "I'm sorry for the confusion. Could you describe your issue in more detail?",
    Intent.UNCLEAR: "Could you please provide more details so I can assist you correctly?",
}


def get_template(intent: str, language: str) -> str | None:
    """
    Return a template response for simple intents.
    Returns None if the intent requires full pipeline processing (e.g. QUESTION).
    """
    templates = THAI_TEMPLATES if language == "th" else ENGLISH_TEMPLATES
    return templates.get(intent)
