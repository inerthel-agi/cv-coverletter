<!-- FICTITIOUS TEST FIXTURE -->
# Projets — Sacha Morel

## TickStore {#tickstore}
- Dates : oct. 2025 – mars 2026. Projet personnel, seul. Statut : déployé, usage personnel.
- Problème : collecter chaque soir des cours de bourse publics pour mes propres analyses, sans copier-coller.
- Ce que j'ai fait : un pipeline Python qui télécharge les cours de clôture publiés gratuitement, les contrôle (dates manquantes, doublons) et les charge dans PostgreSQL. Une API FastAPI expose les séries. Le tout tourne dans Docker Compose sur un serveur virtuel loué, lancé chaque nuit par cron.
- Résultat : fonctionne chaque nuit depuis mars 2026 ; je suis le seul utilisateur. Pas d'autre mesure.

## Contribution à calendrix {#calendrix}
- Dates : janv. 2026 – févr. 2026. Contribution open source à calendrix, une bibliothèque Python de calendriers de jours ouvrés.
- Ce que j'ai fait : 2 pull requests acceptées par les mainteneurs : la correction d'un bug sur les jours fériés glissants et l'ajout de tests pytest pour ce cas.
- Lien : github.example/calendrix/pulls?author=sacha-morel
- Résultat : intégré dans une version publiée de la bibliothèque. Pas d'autre mesure.

## Mini-cluster Kubernetes {#kube-lab}
- Dates : avril 2026. Exercice final de la formation en ligne Docker et Kubernetes.
- Ce que j'ai fait : déployé l'API de TickStore sur un cluster Kubernetes local (une machine, outil d'apprentissage), avec un Deployment et un Service.
- Résultat : exercice de formation, jamais utilisé en production.
