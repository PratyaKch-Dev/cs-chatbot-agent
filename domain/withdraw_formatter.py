"""
Withdrawal diagnosis response formatter.

Converts a WithdrawalDiagnosis into a clear, friendly message
with the reason and next steps in Thai or English.
"""

from domain.withdraw_diagnosis import WithdrawalDiagnosis, WithdrawalFailureCase

_THAI_MESSAGES: dict[str, dict] = {
    WithdrawalFailureCase.BLOCKED: {
        "reason": "บัญชีของคุณถูกระงับโดยผู้ดูแลระบบ",
        "next_steps": ["ติดต่อฝ่าย HR หรือผู้ดูแลระบบเพื่อปลดล็อกบัญชี"],
    },
    WithdrawalFailureCase.BLACKLISTED: {
        "reason": "บัญชีของคุณอยู่ในรายการระงับการใช้งาน",
        "next_steps": ["ติดต่อฝ่าย HR เพื่อตรวจสอบสถานะบัญชี"],
    },
    WithdrawalFailureCase.LIMIT_REACHED: {
        "reason": "คุณถึงวงเงินถอนสูงสุดสำหรับรอบนี้แล้ว",
        "next_steps": ["รอรอบการจ่ายเงินถัดไป หรือติดต่อ HR เพื่อเพิ่มวงเงิน"],
    },
    WithdrawalFailureCase.COOLDOWN: {
        "reason": "ยังอยู่ในช่วงรอหลังจากการถอนครั้งล่าสุด",
        "next_steps": ["กรุณารอสักครู่แล้วลองใหม่อีกครั้ง"],
    },
    WithdrawalFailureCase.NOT_ENROLLED: {
        "reason": "คุณยังไม่ได้ลงทะเบียนใช้บริการ Salary Hero",
        "next_steps": ["ติดต่อ HR เพื่อสมัครใช้บริการ Salary Hero"],
    },
    WithdrawalFailureCase.SYNC_PENDING: {
        "reason": "ข้อมูลเงินเดือนยังไม่ได้รับการซิงค์ในรอบนี้",
        "next_steps": ["กรุณารอระบบซิงค์ข้อมูล หรือติดต่อ HR ให้ดำเนินการซิงค์"],
    },
}

_ENGLISH_MESSAGES: dict[str, dict] = {
    WithdrawalFailureCase.BLOCKED: {
        "reason": "Your account has been suspended by an administrator.",
        "next_steps": ["Contact HR or your system admin to unblock your account."],
    },
    WithdrawalFailureCase.BLACKLISTED: {
        "reason": "Your account is on the restricted list.",
        "next_steps": ["Contact HR to review your account status."],
    },
    WithdrawalFailureCase.LIMIT_REACHED: {
        "reason": "You have reached the maximum withdrawal limit for this period.",
        "next_steps": ["Wait for the next pay cycle, or contact HR to increase your limit."],
    },
    WithdrawalFailureCase.COOLDOWN: {
        "reason": "You are in the cooldown period after your last withdrawal.",
        "next_steps": ["Please wait a moment and try again."],
    },
    WithdrawalFailureCase.NOT_ENROLLED: {
        "reason": "You are not enrolled in the Salary Hero service.",
        "next_steps": ["Contact HR to enroll in Salary Hero."],
    },
    WithdrawalFailureCase.SYNC_PENDING: {
        "reason": "Your payroll data has not been synced for this period yet.",
        "next_steps": ["Please wait for the sync to complete, or contact HR to trigger a manual sync."],
    },
}


def format_diagnosis(diagnosis: WithdrawalDiagnosis, language: str) -> str:
    """
    Format a WithdrawalDiagnosis into a Thai or English reply string.

    TODO Phase 6: implement.
    """
    raise NotImplementedError("Phase 6")
