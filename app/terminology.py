"""Strict, small demonstrator terminology mapping; never claim exhaustive clinical harmonization."""
from dataclasses import dataclass

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
)

METRIC_BY_CODE={m.code:m for m in METRICS}

# Only unambiguous physical unit conversions are applied. No clinical inference.
def normalize(code: str, value: float, unit: str) -> tuple[float, str] | None:
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
    return None
