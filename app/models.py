from pydantic import BaseModel, Field

class LoginRequest(BaseModel):
    telegram_id: int
    password: str

class VerifyOtpRequest(BaseModel):
    telegram_id: int
    otp: str

class CardTopupCreate(BaseModel):
    card_number: str
    card_holder: str
    amount: float = Field(ge=30000, description="Eng kam summa 30 000 so'm bo'lishi shart")

class GivenAmountCreate(BaseModel):
    amount: float = Field(gt=0)
    comment: str

class DailyReportCreate(BaseModel):
    paynet: float = Field(ge=0, default=0)
    leviy: float = Field(ge=0, default=0)
    debt_paid: float = Field(ge=0, default=0)
    sim_cards_count: int = Field(ge=0, default=0)
    kunlik: float = Field(ge=0, default=0)
    terminal: float = Field(ge=0, default=0)
    skidka: float = Field(ge=0, default=0)
    xarajat: float = Field(ge=0, default=0)
    comment: str = ""

class CashierHandoverCreate(BaseModel):
    employee_id: int
    amount_uzs: float = Field(default=0, ge=0, description="So'mda qabul qilingan summa")
    amount_usd: float = Field(default=0, ge=0, description="AQSH dollarida qabul qilingan summa")
    usd_rate: float = Field(default=0, ge=0, description="Dollar kursi (0 bo'lsa tizim kursi olinadi)")
    amount: float = Field(default=0, ge=0, description="Eski moslik uchun umumiy summa")


class CreateUserRequest(BaseModel):
    telegram_id: int
    full_name: str
    initial_debt: float = Field(ge=0, default=0)
    role: str = "EMPLOYEE"

class UpdatePasswordRequest(BaseModel):
    user_id: int
    new_password: str

class SetDebtRequest(BaseModel):
    user_id: int
    debt_amount: float = Field(gt=0, description="Qarz summasi musbat bo'lishi shart")
    reason: str = Field(..., min_length=2, description="Qarz sababi")

class AppointCashierRequest(BaseModel):
    user_id: int

class StatusActionRequest(BaseModel):
    status: str # 'APPROVED' yoki 'REJECTED'
