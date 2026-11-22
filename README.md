# Healthberg — Terminal médical longitudinal · Prototype 0.2

**Functional local demonstration, strictly with synthetic patient data. NOT a medical device, NOT an authenticated clinical product, NOT for actual patient records.**

A visual, provenance-first longitudinal health terminal designed for clinician review and patient/caregiver coordination.

## What works today

- French-language responsive dark dashboard, five **fictional** patient profiles; patient switcher.
- Historical charts for blood pressure, laboratory glucose, HbA1c, serum creatinine, weight and pulse.
- Time range and metric selector; data point details and associated source receipt.
- Last-visit changes, events, medications (clearly historical/declared), tabular analytics, CSV export and a self-contained consultation summary HTML (printable as PDF from the browser).
- `Medical History Engine` upload of **fictional** PDF/JPEG/PNG. Native PDF text extraction or Tesseract OCR when needed. Basic prescription-line recognition, always historical and subject to manual review.
- Strict regex extraction of selected measurements (never unsupervised diagnosis or medication dose inference). Requires explicit patient identity confirmation, review/correction and dated values.
- No source PDF/image bytes, scanned pages or full OCR text stored in SQLite; only a SHA-256 fingerprint, minimal provenance, observations, normalization and review status. **SHA-256 is not evidence of source authenticity**. Human confirmation ≠ clinical verification.
- Duplicate document detection scoped to a single patient.
- Two-year **provisional technical retention of new extracted structured data**, configured with `HEALTHBERG_RETENTION_DAYS` (730 default); expiry cleanup at startup and through the local demo administrative endpoint. **Not a validated legal retention rule.**
- Demo-only origin check and strict no-cache response headers; synthetic-only enforced mode.
- Unit tests + API integration tests, source provenance and patient separation.

## Requirements

Python 3.11+, system `tesseract` with French and English trained data. On macOS, after extracting the archive you can use `LANCER_SUR_MAC.command` (right-click > Open if blocked by macOS), or run:

```bash
brew install tesseract tesseract-lang
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m app
```

Then open **http://127.0.0.1:8765**.

To run tests:

```bash
pytest -q
```

Optional clean rebuild of fictional database:

```bash
rm -f healthberg_demo.sqlite3 healthberg_demo.sqlite3-*
python -m app
```

## File upload for fictional test reports

1. Produce or use **fictional** PDF/PNG/JPEG material only.
2. Select a fictional patient, click *Importer un document*, tick the synthetic-only confirmation.
3. Inspect extracted values, reject uncertain entries, enter real **document** sample date.
4. Confirm the selected patient identity and the observations.
5. Data points appear in charts; click a point to show the provenance receipt. No original page remains available.

Sample document generator: `python scripts/generate_demo_report.py` creates a fabricated PDF at `examples/fictional_report.pdf`; this file is excluded by `.gitignore` and should never be committed. A copy may be included in the deliverable ZIP.

## Safety and architecture notes

This is a single-process **local** FastAPI service with HTML/CSS/vanilla JavaScript frontend and SQLite. Its purpose is to validate UX, data pipeline and provenance quickly without cloud dependencies.

**This demo has NO authentication, access grants, HDS-certified production hosting, encryption-at-rest guarantees, malware scanning, clinically validated OCR, regulatory qualification, background deletion scheduling, consent management or real device/DMP integration.** It deliberately binds to `127.0.0.1` and must not be internet-exposed. Do not upload real data, including family records. An upload enters the local Python process memory before extraction; preview candidate snippets exist in memory for up to 10 minutes. The source file bytes are not intentionally written to the database or a source file store. Logs never print OCR text. Operating system paging, temporary data from external dependencies, filesystem backups and telemetry require review for a production implementation.

This is **not** end-to-end encryption or a commercial data protection claim. A conformant real-data pilot will require identity, access control, professional identity, threat modelling, authorization, a validated security and data retention design, and external clinical/legal review. That work can proceed after the prototype while retaining the hard NO-REAL-DATA release gate.

The ingestion parser currently recognizes a **small set of explicit lab formats**, not arbitrary PDF layouts, handwritten orders, or complex lab tables. Unsupported units, censored values (`<`,`>`) and missing dates are never silently invented. Native PDF text is read with PyMuPDF; image-only documents use Tesseract OCR. The planned next phase should use a constrained document classifier, page-layout extraction and a strong human-review interface before any broader document support.

## Data model

- `patients`: fiction-only records, no authentic identifiers.
- `observations`: normalized and original values/units, clinical event date, source ID, review status, page, expiration.
- `receipts`: document metadata, hash, import timestamp, source type, document date, expiration; never original bytes.
- `meds`: fictional medication-history statements; no medication dose recommendations.
- `events`: fictional visit events.

## Publication GitHub

Le code est prévu pour le dépôt `kkpo-adil/healthberg`. Publier uniquement les fichiers sources de ce dossier : jamais la base SQLite locale, des documents médicaux ou des secrets. Le dépôt peut être public puisque cette version ne contient que des données synthétiques. Un dépôt public ne constitue **pas** une infrastructure utilisable pour des données de santé réelles.

## Publier dans GitHub depuis un Mac

Si l'intégration ChatGPT GitHub ne dispose pas de l'autorisation d'écriture Contents, le dossier peut être publié sans transfert par messagerie :

1. Décompresser l'archive Healthberg et ouvrir le dossier.
2. Double-cliquer `PUBLIER_SUR_GITHUB.command` (clic droit → Ouvrir si macOS le bloque).
3. L'outil Git local envoie les sources sur `kkpo-adil/healthberg`. Une connexion GitHub peut être demandée, aucune clé n'est fournie dans ce dossier.

**Important :** le script n'effectue jamais de `push --force`. Si le dépôt a déjà des commits distants, il s'arrête plutôt que d'écraser du travail.

## Synthèse de consultation

Le bouton **Synthèse consultation** exporte un fichier HTML lisible et imprimable localement (Imprimer → PDF depuis le navigateur). Il reprend les dernières mesures, dates, statuts et références des sources, sans diagnostic, sans interprétation, sans document original, et uniquement à partir de profils fictifs.
