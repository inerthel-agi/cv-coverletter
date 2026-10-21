---
fixture: true
url: https://volterre-data.example/blog/migration-airflow-kubernetes
title: Pourquoi nous migrons nos pipelines vers Airflow sur Kubernetes
published: 2026-06-10
accessed: 2026-10-21
---
Nos premiers pipelines tournaient en tâches cron sur des serveurs dédiés. Avec la hausse du nombre de flux, nous les migrons vers Airflow, déployé sur Kubernetes. La migration a commencé en mai 2026 ; la moitié des pipelines de l'équipe Marchés reste à migrer. Le contrôle qualité des données (trous, doublons, retards de publication) devient une étape explicite de chaque pipeline.
