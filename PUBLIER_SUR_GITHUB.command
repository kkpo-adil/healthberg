#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
printf '\nHEALTHBERG — Publication du prototype sur GitHub\n'
printf 'Dépôt cible : https://github.com/kkpo-adil/healthberg\n\n'
printf 'AVERTISSEMENT : ne pas inclure de données médicales réelles.\n'
if ! command -v git >/dev/null 2>&1; then
  echo "Git est requis. Installer les outils Command Line Tools : xcode-select --install"
  exit 1
fi
if ! git config user.name >/dev/null || ! git config user.email >/dev/null; then
  echo "Git doit connaître votre nom et votre e-mail avant de faire un commit."
  echo 'Exemple : git config --global user.name "Prénom Nom"'
  echo '          git config --global user.email "vous@example.com"'
  exit 1
fi
if [ ! -d .git ]; then git init; fi
git branch -M main
if git remote get-url origin >/dev/null 2>&1; then
  current=$(git remote get-url origin)
  if [ "$current" != "https://github.com/kkpo-adil/healthberg.git" ] && [ "$current" != "git@github.com:kkpo-adil/healthberg.git" ]; then
    echo "Un autre dépôt distant est configuré : $current. Arrêt par sécurité."
    exit 1
  fi
else
  git remote add origin https://github.com/kkpo-adil/healthberg.git
fi
git add .
if ! git diff --cached --quiet; then git commit -m "feat: Healthberg synthetic health intelligence prototype v0.2"; fi
printf '\nEnvoi vers GitHub (GitHub peut demander une authentification) ...\n'
git push -u origin main
printf '\nPublication terminée : https://github.com/kkpo-adil/healthberg\n'
