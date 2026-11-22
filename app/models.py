from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class SourceReceipt(BaseModel):
    id: str
    patient_id: str
    document_kind: str
    issuer: str | None = None
    document_date: str | None = None
    imported_at: str
    sha256: str
    page_count: int
    extraction_method: str
    original_retained: bool = False
    retention_until: str | None = None


class Observation(BaseModel):
    id: str
    patient_id: str
    code: str
    label: str
    value: float
    unit: str
    measured_at: str
    original_value: str
    original_unit: str
    source_id: str
    page: int | None = None
    context: str = ""
    status: Literal['synthetic_verified', 'extracted_pending', 'patient_confirmed', 'professional_verified'] = 'extracted_pending'
    reference_range: str | None = None


class Candidate(BaseModel):
    code: str
    label: str
    value: float
    unit: str
    original_value: str
    original_unit: str
    page: int
    measured_at: str | None = None
    source_text: str = ""
    confidence: Literal['high','review'] = 'review'
    context: str = ""


class MedicationCandidate(BaseModel):
    name: str
    strength: str
    directions: str
    page: int
    source_text: str = ''
    document_date: str | None = None


class ImportPreview(BaseModel):
    import_token: str
    patient_id: str
    patient_name: str
    sha256: str
    document_kind: str
    issuer: str | None
    document_date: str | None
    page_count: int
    extraction_method: str
    candidates: list[Candidate]
    medications: list[MedicationCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    expires_at: str


class ConfirmCandidate(BaseModel):
    code: str
    value: float
    unit: str
    measured_at: str
    page: int
    original_value: str
    original_unit: str
    label: str
    context: str = ""


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


class MedicationPlan(BaseModel):
    id: str
    patient_id: str
    name: str
    schedule: str
    state: Literal['historical', 'declared', 'professional_verified']
    since: str
    note: str = ""


class Patient(BaseModel):
    id: str
    name: str
    age: int
    profile: str
    initials: str
    last_consultation: str
    synthetic: bool = True
