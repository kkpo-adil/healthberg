# Healthberg v0.2 — Livraison prototype

## Fonctionnalités opérationnelles
- Interface française responsive « terminal médical » avec 5 dossiers patients synthétiques.
- Graphiques de suivi : tension artérielle, glycémie, HbA1c, créatinine, DFG rapporté, fréquence cardiaque, cholestérol, poids.
- Évolution des paramètres sans diagnostic, seuils calculés ni alerte clinique.
- Import de documents **fictifs** PDF/PNG/JPEG ; extraction PDF textuelle ou OCR Tesseract ; confirmation obligatoire.
- Ordonnances reconnues comme *historiques* ; aucun traitement automatiquement présumé actif.
- Conservation des seules valeurs structurées et fiches de provenance (empreinte SHA-256, date, page, source déclarée).
- Détection de doublons par patient et isolation des fiches source.
- Export CSV et nouvelle synthèse de consultation imprimable localement en HTML, avec mention explicite des sources.
- Durée technique provisoire de 730 jours par défaut, paramétrable. Nettoyage au démarrage ou manuel uniquement.
- 22 tests automatisés réussis, contrôle syntaxique JavaScript.

## Sécurité / périmètre
Ce démonstrateur local n'est pas destiné à recevoir des données médicales réelles : pas d'identification forte, d'hébergement HDS, de droits d'accès réels ni de qualification médicale. Les documents originaux ne sont pas enregistrés dans SQLite, mais des copies techniques temporaires peuvent exister durant l'OCR dans l'OS.

## Publication GitHub
Dépot cible : https://github.com/kkpo-adil/healthberg
Au 22/11/2026, la lecture du dépôt public était accessible, mais l'écriture via le connecteur GitHub a été refusée HTTP 403 : « Resource not accessible by integration ». L'archive peut être publiée par `PUBLIER_SUR_GITHUB.command` depuis un Mac authentifié ou par téléversement des fichiers extraits dans GitHub.
