"""Verify the installed extraction module using synthetic data only."""
import fitz
from app.extraction import parse_file

doc=fitz.open()
p=doc.new_page()
p.insert_text((40,60),"Date du bilan : 08.11.2026\nAntigène HBs    Négatif\nIndex    0,25\nAnticorps anti-HBs    >1000 UI/L",fontsize=12)
raw=doc.tobytes();doc.close()
r=parse_file(raw,'application/pdf','synthetic-smoke.pdf')
assert len(r.findings)==3, 'Extraction de sérologie non fonctionnelle'
assert any(f.code=='hbs_ab' and f.value=='>1000' for f in r.findings)
assert r.method=='text-native'
assert len(r.page_texts)==1 and 'Antigène HBs' in r.page_texts[0]
print('Import vérifié : qualitatif, index et valeur bornée reconnus.')
