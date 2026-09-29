from pydantic import BaseModel
from typing import List, Optional

class LoginRequest(BaseModel):
    username: str
    password: str
    role: str

class ConsentPayload(BaseModel):
    citizen_id: str
    purpose: str
    scopes: List[str]
    expiry_timestamp: str

class ServiceApplicationRequest(BaseModel):
    citizen_id: str
    service_id: str
    bank_account: str
    scheme_category: str
    consent_token: str

class ApplicationStatusUpdate(BaseModel):
    status: str
    remarks: Optional[str] = "Desk Officer verified"
