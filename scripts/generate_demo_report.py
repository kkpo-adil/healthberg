"""Generate a 100% fictitious medical lab report to exercise document import."""
from pathlib import Path
import fitz

root=Path(__file__).resolve().parents[1]
out=root/'examples'/'fictional_report.pdf';out.parent.mkdir(exist_ok=True)
doc=fitz.open();page=doc.new_page(width=595,height=842)
lines=[
    'LABORATOIRE DEMONSTRATION - RAPPORT 100 % FICTIF',
    'Patient : Marie Martin (profil fictif)',
    'Date du bilan : 14/09/2025',
    'Glycemie : 1,23 g/L',
    'HbA1c : 7,2 %',
    'Creatinine : 12,4 mg/L',
    'DFG : 67 mL/min/1,73m2',
    'Cholesterol total : 1,89 g/L',
    'Tension arterielle : 142/88 mmHg',
    'Document fabrique uniquement pour une demonstration logicielle.',
]
for i,line in enumerate(lines):page.insert_text((55,70+i*37),line,fontsize=13)
doc.save(out);doc.close();print(out)
