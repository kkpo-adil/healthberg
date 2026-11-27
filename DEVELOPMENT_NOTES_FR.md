# Repères de maintenance

La source de référence de cette branche est Ajour v0.9.7, et non le prototype Healthberg v0.2 initialement présent sur `main`.

## Invariants

- Aucune écriture à la prévisualisation : les résultats et textes passent par une confirmation explicite.
- Une valeur qualitative ou bornée reste littérale. Un index n’est pas une concentration et une limite n’est pas une valeur exacte.
- Les colonnes d’antécédents et seuils ne doivent pas être ajoutées comme résultats actuels.
- Une date de naissance n’est pas une date de mesure. Des dates contradictoires restent à confirmer.
- Le texte intégral non classé n’hérite pas d’un partage clinique partiel.
- Les mutations doivent être protégées par la session, le patient, les permissions et l’en-tête d’action locale.
- Les fichiers de test sont synthétiques ; les bases, documents personnels et artefacts locaux ne sont pas suivis par git.

## Nettoyage effectué

Les vues patient et orientation actives ont une définition unique. Les anciens tableaux de bord pharmacie/laboratoire non appelés et cinq modèles de données non utilisés ont été retirés. Le rechargement métier précède le rendu, sans enveloppes de `refresh` et `acceptSession` qui relançaient les mêmes appels. Les vues métier restantes composent explicitement les vues de base sans recopier leur contenu.

Les tests ajoutés couvrent la déduplication des tensions, les erreurs de saisie numérique, l’origine HTTP sur un port local variable, le vrai nombre de pages d’ordonnance et la lecture de pixels OCR. Les contrôles statiques bloquent les imports/variables inutilisés et noms Python non résolus.

La CI teste le moteur sur Linux/macOS et le navigateur Chromium/WebKit. Les fonctionnalités non branchées ne doivent pas être présentées comme opérationnelles. Consulter le README pour la procédure actuelle et les limites.
