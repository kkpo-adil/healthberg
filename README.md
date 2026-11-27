# Ajour — base v0.9.7

Application locale de démonstration pour importer et relire un historique médical fictif, avec un accès adapté au patient et aux professionnels. Ce dépôt reprend la **v0.9.7** et ajoute la maintenance ainsi que les tests automatisés de ses parcours. Il ne contient aucun document personnel.

## Démarrer le code

Python 3.12 est la version vérifiée par la CI. Depuis la racine :

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m app
```

Ouvrir <http://127.0.0.1:8765>. Les comptes et le mot de passe affichés sont des identités fictives de démonstration. Sur Mac, `bash LANCER_SUR_MAC.command` prépare le moteur puis ouvre le navigateur. Ce dépôt lance l’application web locale ; il ne fabrique pas à lui seul une application macOS signée.

Les paramètres sont dans `.env.example` : les exporter dans le shell si nécessaire. Le programme ne charge pas automatiquement un fichier `.env`. `AJOUR_PORT` permet de choisir un autre port local.

Pour les photos et PDF scannés, installer Tesseract et les langues française/anglaise :

```bash
# macOS avec Homebrew
brew install tesseract tesseract-lang
# Ubuntu
sudo apt-get install tesseract-ocr tesseract-ocr-fra
```

Les PDF contenant du texte lisible ne nécessitent pas Tesseract.

## Import d’historique

1. Lire le texte et les tableaux, ou utiliser l’OCR pour les scans.
2. Présenter les résultats reconnus et les conclusions littérales, sans interprétation clinique.
3. Confirmer une date commune si elle est absente ou ambiguë ; chaque date reste modifiable individuellement.
4. Vérifier les transcriptions sélectionnées puis confirmer l’enregistrement.
5. Retrouver les résultats et textes avec leur page, empreinte et source.

Les résultats qualitatifs et bornés, par exemple « Négatif » et « >1000 UI/L », sont conservés comme tels. Ils ne deviennent pas des points numériques fictifs sur une courbe. Le texte non classé reste consultable dans les pages vérifiées. Les transcriptions complètes sont réservées au patient et au médecin ayant accès au dossier complet.

L’import d’historique ne conserve pas le PDF original, ses images ou sa mise en page. Le parcours distinct d’import d’ordonnance SPECIMEN conserve son PDF fictif pour la consultation par QR autorisé. Ces deux règles ne doivent pas être confondues. Conserver les originaux séparément. Un même document déjà confirmé est refusé pour éviter un doublon.

## Tests automatiques

[GitHub Actions](https://github.com/kkpo-adil/healthberg/actions) lance, à chaque push et pull request :

- les contrôles de code Python et de syntaxe JavaScript ;
- les tests API, droits d’accès, conservation, dates, import et OCR français sur Linux et macOS ;
- les parcours dans Chromium sur Linux et WebKit sur macOS : connexion, dépôt d’un PDF fictif, date commune, contrôle des lignes, enregistrement, rechargement et agenda professionnel.

En local :

```bash
python -m ruff check app scripts tests
python -m pytest -q --ignore=tests/e2e
python -m playwright install chromium
python -m pytest -q tests/e2e
```

Pour utiliser WebKit : `python -m playwright install webkit`, puis `AJOUR_TEST_BROWSER=webkit python -m pytest -q tests/e2e`. Un binaire Chromium installé peut être indiqué par `AJOUR_TEST_CHROMIUM=/chemin/vers/chromium`.

Le contrôle `python scripts/check_ci.py <SHA>` autorise l’installation uniquement si le workflow complet du même commit a réussi ; une exécution plus récente en échec bloque l’installation.

Les tests utilisent des bases temporaires et génèrent des documents synthétiques en mémoire. Ils ne modifient pas la base locale de l’utilisateur. La CI ne remplace pas une vérification de l’installation et de la fenêtre native macOS ; elle valide le moteur et l’interface web.

## Organisation

- `app/` : API, permissions, stockage SQLite et parcours métiers.
- `app/extraction.py`, `app/report_findings.py` : lecture documentaire et résultats littéraux.
- `static/` : interface ; `practice.js`, `journeys.js` et `careflows.js` complètent les vues métier.
- `tests/` : régressions du moteur et de l’API ; `tests/e2e/` : parcours réels de navigateur.
- `verify_import.py` : contrôle rapide de l’import sur un PDF synthétique.

## Limites

Ce moteur reste un prototype avec base SQLite non chiffrée et comptes de démonstration. Il ne convient pas à des dossiers de santé réels. La reconnaissance reste limitée aux formats et termes programmés ; l’OCR peut se tromper et exige une vérification. Les interfaces officielles de santé, les dispositifs connectés et les annuaires externes ne sont pas connectés. Ajour n’établit ni diagnostic, ni posologie, ni triage.
