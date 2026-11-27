"""Strict, small demonstrator terminology mapping; never claim exhaustive clinical harmonization."""
from dataclasses import dataclass
from math import isfinite

@dataclass(frozen=True)
class Metric:
    code: str
    label: str
    unit: str
    aliases: tuple[str, ...]

METRICS = (
    Metric('glucose', 'Glycémie', 'g/L', ('glycemie', 'glucose', 'glycémie')),
    Metric('hba1c', 'HbA1c', '%', ('hba1c', 'hemoglobine glyquee', 'hémoglobine glyquée')),
    Metric('creatinine', 'Créatinine', 'mg/L', ('creatinine', 'créatinine')),
    Metric('egfr', 'DFG (rapporté)', 'mL/min/1,73m²', ('dfg', 'egfr', 'debit de filtration glomerulaire')),
    Metric('cholesterol', 'Cholestérol total', 'g/L', ('cholesterol total', 'cholestérol total')),
    Metric('weight', 'Poids', 'kg', ('poids',)),
    Metric('pulse', 'Fréquence cardiaque', 'bpm', ('frequence cardiaque', 'fréquence cardiaque', 'pouls')),
    Metric('systolic', 'Tension systolique', 'mmHg', ('tension', 'pression arterielle', 'pression artérielle', 'ta')),
    Metric('diastolic', 'Tension diastolique', 'mmHg', ('tension', 'pression arterielle', 'pression artérielle', 'ta')),
    Metric('spo2', 'Saturation en oxygène', '%', ('saturation', 'spo2')),
    Metric('temperature', 'Température', '°C', ('temperature', 'température')),
    Metric('respiratory_rate', 'Fréquence respiratoire', '/min', ('frequence respiratoire',)),
    Metric('height', 'Taille', 'cm', ('taille',)),
    Metric('ldl', 'Cholestérol LDL', 'g/L', ('cholesterol ldl', 'ldl')),
    Metric('hdl', 'Cholestérol HDL', 'g/L', ('cholesterol hdl', 'hdl')),
    Metric('triglycerides', 'Triglycérides', 'g/L', ('triglycerides', 'triglycérides')),
    Metric('hemoglobin', 'Hémoglobine', 'g/dL', ('hemoglobine', 'hémoglobine')),
    Metric('potassium', 'Potassium', 'mmol/L', ('potassium',)),
    Metric('sodium', 'Sodium', 'mmol/L', ('sodium',)),
    Metric('crp', 'CRP', 'mg/L', ('crp',)),
    Metric('tsh', 'TSH', 'mUI/L', ('tsh',)),
    Metric('fevg', 'FEVG rapportée', '%', ('fevg',)),
    Metric('ferritin', 'Ferritine', 'µg/L', ('ferritine',)),
    Metric('alat', 'ALAT', 'UI/L', ('alat',)),
    Metric('asat', 'ASAT', 'UI/L', ('asat',)),
    Metric('inr', 'INR rapporté', '1', ('inr',)),
    Metric('psa', 'PSA', 'ng/mL', ('psa',)),
    Metric('platelets', 'Plaquettes', 'G/L', ('plaquettes',)),
    Metric('leukocytes', 'Leucocytes', 'G/L', ('leucocytes',)),
    Metric('albuminuria', 'Albuminurie', 'mg/L', ('albuminurie',)),
    Metric('vems', 'VEMS rapporté', 'L', ('vems',)),
)

METRIC_BY_CODE={m.code:m for m in METRICS}

# Only unambiguous physical unit conversions are applied. No clinical inference.
def normalize(code: str, value: float, unit: str) -> tuple[float, str] | None:
    if not isfinite(value): return None
    u = unit.lower().replace(' ', '').replace('μ','µ')
    if code == 'glucose':
        if u in {'g/l','g·l-1'}: return round(value,4), 'g/L'
        if u in {'mg/dl'}: return round(value/100,4), 'g/L'
        # mmol/L glucose molecular-mass conversion is deliberate and explicit, not inferred from bare numbers
        if u == 'mmol/l': return round(value * 0.180156,4), 'g/L'
    if code == 'creatinine':
        if u=='mg/l': return round(value,4), 'mg/L'
        if u=='µmol/l': return round(value*0.11312,4),'mg/L'
        if u=='mg/dl': return round(value*10,4),'mg/L'
    if code=='cholesterol':
        if u=='g/l': return round(value,4),'g/L'
        if u=='mg/dl': return round(value/100,4),'g/L'
    if code=='hba1c' and u=='%': return value,'%'
    if code=='egfr' and u in {'ml/min/1,73m²','ml/min/1.73m2','ml/min/1,73m2'}:
        return value,'mL/min/1,73m²'
    if code=='weight' and u=='kg': return value,'kg'
    if code=='pulse' and u in {'bpm','/min','min-1'}: return value,'bpm'
    if code in {'systolic','diastolic'} and u=='mmhg': return value,'mmHg'
    if code in {'spo2','fevg'} and u=='%' : return value,'%'
    if code=='temperature' and u in {'°c','c'}: return value,'°C'
    if code=='respiratory_rate' and u in {'/min','min-1'}: return value,'/min'
    if code=='height' and u=='cm':return value,'cm'
    if code in {'ldl','hdl','triglycerides'}:
        if u=='g/l':return value,'g/L'
        if u=='mg/dl':return round(value/100,4),'g/L'
    if code=='hemoglobin':
        if u=='g/dl':return value,'g/dL'
        if u=='g/l':return round(value/10,4),'g/dL'
    if code in {'potassium','sodium'} and u=='mmol/l':return value,'mmol/L'
    if code in {'crp','albuminuria'} and u=='mg/l':return value,'mg/L'
    if code=='tsh' and u in {'mui/l','miu/l'}:return value,'mUI/L'
    if code=='ferritin' and u in {'µg/l','mcg/l'}:return value,'µg/L'
    if code in {'alat','asat'} and u in {'ui/l','iu/l'}:return value,'UI/L'
    if code=='inr' and u in {'1','ratio','sansunité',''}:return value,'1'
    if code=='psa' and u=='ng/ml':return value,'ng/mL'
    if code in {'platelets','leukocytes'} and u=='g/l':return value,'G/L'
    if code=='vems' and u=='l':return value,'L'

    return None
