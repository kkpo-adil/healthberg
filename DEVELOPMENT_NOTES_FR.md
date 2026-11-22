# HEALTHBERG — État du code et prochaines étapes

## Décisions appliquées le 22 novembre 2026

- Code opérationnel prioritaire sur la recherche réglementaire exhaustive.
- Architecture locale Python FastAPI + SQLite + frontend sans dépendances externes pour tester rapidement le workflow. La préférence Phase 0 pour TypeScript demeure une option future, pas une contrainte de ce premier exécutable.
- Documents d'entrée non stockés dans la base. Seuls les faits structurés, origines déclarées, empreintes SHA-256, pages et statuts sont conservés. Les fichiers peuvent être temporairement spoulés en cours de traitement par le framework/OS ; aucune promesse d'effacement forensique n'est faite.
- Conservation provisoire des valeurs structurées **730 jours** par défaut (`HEALTHBERG_RETENTION_DAYS`). Le nettoyage existe mais n'est pas encore planifié en tâche continue : il se fait au démarrage ou manuellement dans la démo. La durée exacte et le mécanisme de suppression en production seront validés ultérieurement.
- Démonstration **sans données réelles**, sans obligation de connexion à Mon espace santé.

## Fonctionnel maintenant

- Liste de cinq patients synthétiques, sans aucun patient réel.
- Graphiques multiples et vues médecin, historiques et médicaments fictifs.
- Import natif PDF + OCR image/scan, validation explicite de la bonne identité du patient.
- Extraction ciblée de valeurs biologiques, tension et lignes de prescriptions basiques.
- Conversion conservatrice des unités, refus d'unités non reconnues, valeurs censurées exclues.
- Date de la mesure distincte de la date de l'import.
- Provenance documentaire avec empreinte SHA-256, sans fichier original.
- Détection de réimport du même fichier pour un même patient.
- Parcours de validation utilisateur et statut explicitement non clinique.
- Export CSV et synthèse de consultation HTML imprimable avec provenance, API de démonstration, CI et tests.

## Limitations expressément non dissimulées

- L'OCR n'a pas été validé pour dossiers médicaux réels ; résultats dépendant de la qualité du scan.
- Extraction insuffisante pour textes manuscrits, nombreux formats de tableaux, prescriptions complexes, imagerie DICOM, etc.
- Les historiques préchargés sont fictifs et produisent des courbes de démonstration.
- Aucun partage sécurisé réel entre proches et professionnels, aucune authentification ni rôle métier fonctionnel.
- Aucun mode de surveillance, alerte clinique, recommandation médicale, EHR/Mon espace santé, appareil connecté ou ordonnance numérique.
- Pas de véritable système HDS ni conformité garantie. **Interdiction de données réelles jusqu'à une version validée.**

## Priorité de la prochaine itération

1. OCR robuste de bilans multicolonnes et de scans dégradés + tests de reconnaissance sur corpus synthétique.
2. Vérification visuelle mettant côte à côte le document éphémère et les données candidates avant purge.
3. Historique des corrections et réconciliations médicamenteuses versionnées.
4. Authentification, autorisation patient/soignant/aidant, authentification forte et audit append-only.
5. Conservation avec planificateur fiable, politiques d'effacement, sauvegardes et reprise.
6. Interopérabilité FHIR, vocabulaire clinique versionné, dispositif de validation de la provenance.
7. Évaluations des coûts de fonctionnement et garde-fous réglementaires avant pilotes.

## Mise en ligne GitHub

Le dépôt GitHub de référence est `kkpo-adil/healthberg`. Le connecteur ChatGPT affiche le dépôt public avec des droits déclarés, mais les appels d'écriture ont renvoyé 403 (« Resource not accessible by integration ») au 22/11/2026. Tant que l'intégration GitHub ne reçoit pas la permission Contents: Read and write, publier les fichiers via une authentification Git locale ou l'interface GitHub. Ne jamais publier de dossiers patients réels, de bases SQLite ou de secrets.
