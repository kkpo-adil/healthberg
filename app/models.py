from typing import Literal
from pydantic import BaseModel, Field






class Candidate(BaseModel):
    code: str
    label: str
    value: float = Field(allow_inf_nan=False)
    unit: str
    original_value: str
    original_unit: str
    page: int
    measured_at: str | None = None
    source_text: str = ""
    confidence: Literal['high','review'] = 'review'
    context: str = ""


class ReportFinding(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=160)
    value: str = Field(min_length=1, max_length=160)
    unit: str = Field(default='', max_length=30)
    kind: Literal['qualitative', 'bounded', 'reported_number']
    page: int = Field(ge=1, le=30)
    measured_at: str | None = None


class MedicationCandidate(BaseModel):
    name: str
    strength: str
    directions: str
    page: int
    source_text: str = ''
    document_date: str | None = None




class ConfirmCandidate(BaseModel):
    code: str
    value: float = Field(allow_inf_nan=False)
    unit: str
    measured_at: str
    page: int
    original_value: str
    original_unit: str
    label: str
    context: str = ""
    manual: bool = False


class ConfirmMedication(BaseModel):
    name: str
    strength: str
    directions: str
    page: int
    since: str


class ImportConfirm(BaseModel):
    import_token: str
    patient_id: str
    confirm_patient_identity: bool
    candidates: list[ConfirmCandidate]
    medications: list[ConfirmMedication] = Field(default_factory=list)
    manual_verified: bool = False
    document_date: str | None = None
    retained_pages: list[int] = Field(default_factory=list)
    transcription_verified: bool = False
    findings: list[ReportFinding] = Field(default_factory=list)




