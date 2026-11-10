from typing import Optional
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

class ToggleShiftRequest(BaseModel):
    shift_status: Optional[str] = Field(None, description="'WORKING' yoki 'RESTING'")

class StatusActionRequest(BaseModel):
    status: str # 'APPROVED' yoki 'REJECTED'

class SetEmployeeWorkplaceRequest(BaseModel):
    user_id: int
    workplace_name: str = Field(default="Ish joyi", min_length=1, max_length=100, description="Filial / Ish joyi nomi")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Kenglik (Latitude)")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Uzunlik (Longitude)")
    radius_meters: int = Field(default=50, ge=5, le=5000, description="Geofence radiusi (metrlarda)")
    work_start_time: str = Field(default="09:00", description="Ish boshlanish vaqti (HH:MM)")
    work_end_time: str = Field(default="19:00", description="Ish tugash vaqti (HH:MM)")

class WorkplaceLocationUpdate(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Kenglik (Latitude)")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Uzunlik (Longitude)")
    radius_meters: int = Field(default=50, ge=5, le=5000, description="Geofence radiusi (metrlarda)")
    name: str = Field(default="Bosh Ofis", min_length=1, max_length=100, description="Ish joyi nomi")

class LocationPingRequest(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Xodim kengligi")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Xodim uzunligi")
