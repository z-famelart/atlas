# Project Intelligence

## 1. Pitch

Project Intelligence est un outil destiné aux software engineers et consultants qui arrivent sur un environnement logiciel qu'ils ne connaissent pas.

Son objectif est de produire rapidement une **carte de compréhension exploitable d'un système logiciel**, permettant de répondre à trois questions :

1. **Qu'est-ce que ce système ?**
2. **Comment est-il construit et comment ses composants interagissent-ils ?**
3. **Où dois-je regarder en priorité pour devenir rapidement efficace ?**

L'outil ne cherche pas à remplacer les outils existants d'analyse de code, de sécurité, de dépendances, de Git, d'infrastructure ou de documentation.

Il doit au contraire **détecter, orchestrer et agréger les outils existants**, normaliser leurs résultats, produire des métriques et graphes transverses, puis utiliser des LLM uniquement lorsqu'une interprétation ou une synthèse humaine apporte une réelle valeur.

Le résultat principal est un **rapport HTML interactif**, accompagné d'un modèle de données exploitable par un agent via MCP.

---

## 2. Problème

Lorsqu'un senior engineer rejoint une nouvelle mission, une grande partie du temps initial est consacrée à reconstruire mentalement :

- la structure du code ;
- les composants importants ;
- les dépendances ;
- les flux ;
- les frontières architecturales ;
- les hotspots ;
- les workflows métier ;
- les mécanismes de build et de déploiement ;
- les dépendances externes ;
- l'historique et les zones instables.

Cette connaissance est souvent répartie entre le code, Git, les tests, les README, plusieurs repositories, l'IaC, la CI/CD, les outils d'observabilité et parfois des systèmes externes.

Project Intelligence doit réduire drastiquement le temps nécessaire pour construire cette représentation mentale.

---

## 3. Cas d'utilisation

L'outil doit être utile pour plusieurs types de missions :

### Onboarding

Comprendre rapidement un nouveau système.

### Développement

Identifier où intervenir lorsqu'une feature ou un bug est donné.

### Assistance

Répondre à des questions sur une codebase existante avec des informations vérifiables.

### Audit

Identifier les hotspots, dépendances, couplages, anomalies, risques et incohérences.

### Architecture

Comprendre les composants, leurs relations et les frontières du système.

### DevOps / Platform

Comprendre build, CI/CD, runtime, infrastructure et observabilité.

---

## 4. Principes fondamentaux

### 4.1 Existing tools first

Ne pas réimplémenter une capacité lorsqu'un outil spécialisé fiable existe.

Exemples de catégories :

- code graph ;
- AST ;
- dependency analysis ;
- complexity ;
- security ;
- Git ;
- IaC ;
- Kubernetes ;
- CI/CD ;
- OpenAPI ;
- documentation.

Project Intelligence fournit des adapters et orchestre ces outils.

---

### 4.2 Deterministic first

Les informations pouvant être obtenues de manière déterministe doivent l'être sans LLM.

Le LLM ne doit pas être utilisé pour :

- compter les fichiers ;
- détecter un langage ;
- construire un dependency graph lorsque celui-ci peut être obtenu par un outil ;
- calculer le churn Git ;
- calculer la centralité ;
- parser du Terraform ;
- parser un manifeste Kubernetes ;
- extraire des métriques simples.

---

### 4.3 LLM for interpretation

Le LLM intervient principalement pour :

- synthétiser ;
- expliquer ;
- identifier des concepts métier ;
- interpréter des patterns architecturaux ;
- construire des workflows compréhensibles ;
- proposer un parcours d'onboarding ;
- relier plusieurs observations.

---

### 4.4 Evidence first

Toute information non triviale doit pouvoir être reliée à une ou plusieurs preuves.

Une preuve peut être :

- fichier ;
- ligne ;
- symbole ;
- commit ;
- configuration ;
- résultat d'un outil ;
- documentation ;
- source externe.

Le système doit permettre de distinguer :

- fait observé ;
- métrique calculée ;
- interprétation ;
- hypothèse.

---

### 4.5 Never pretend to know

Le système doit pouvoir explicitement dire :

- information unavailable ;
- repository not analyzed ;
- source not provided ;
- insufficient evidence ;
- hypothesis only.

L'absence d'information est elle-même une information.

---

### 4.6 Repository != System

Un repository analysé ne représente pas nécessairement l'intégralité du système.

L'infrastructure peut être dans un autre repository.

La CI peut être externe.

Le GitOps peut être séparé.

Les dashboards peuvent être dans un SaaS.

Plusieurs repositories peuvent constituer un même système.

Le modèle doit donc distinguer :

- repository ;
- project ;
- system ;
- environment ;
- external source.

---

## 5. Outputs

### Primary output

Un rapport HTML interactif comprenant notamment :

- executive summary ;
- system map ;
- architecture ;
- code map ;
- hotspots ;
- domain understanding ;
- runtime ;
- infrastructure ;
- CI/CD ;
- data architecture ;
- observability ;
- tests ;
- Git evolution ;
- risks / anomalies ;
- onboarding path ;
- glossary ;
- evidence.

### Machine-readable output

Les facts et insights doivent également être disponibles sous une forme structurée.

### MCP

Les informations pertinentes doivent être interrogables par un agent de coding via MCP.

---

## 6. Architecture conceptuelle

```text
                         PROJECT INTELLIGENCE
                                  |
                         +--------+--------+
                         |                 |
                     Discovery          Config
                         |
                         v
                    Source detection
                         |
              +----------+-----------+
              |          |           |
              v          v           v
            Code        Git       Environment
              |          |           |
         existing    existing    existing tools
           tools       tools
              |          |           |
              +----------+-----------+
                         |
                         v
                  Normalized Facts
                         |
                 +-------+-------+
                 |               |
                 v               v
            Calculations     LLM synthesis
                 |               |
                 +-------+-------+
                         |
                         v
                 Insights / Views
                    /       \
                   v         v
                HTML        MCP
```

---

## 7. Target workflow

```text
project-intel analyze <scope>

        ↓

Discover environment

        ↓

Detect available sources and tools

        ↓

Run relevant analyzers

        ↓

Normalize results

        ↓

Build graph / metrics / relationships

        ↓

Generate insights

        ↓

LLM synthesis where useful

        ↓

Generate HTML report

        ↓

Expose knowledge through MCP
```

---

## 8. Non-goals

Project Intelligence ne doit pas devenir :

- un nouvel analyseur AST généraliste ;
- un nouvel outil de dependency analysis ;
- un nouvel outil de security scanning ;
- un IDE ;
- un remplacement de Git ;
- un remplacement de Terraform/Kubernetes tooling ;
- un agent qui explore aveuglément toute la codebase ;
- un système qui envoie systématiquement le repository à un LLM ;
- un générateur de documentation sans evidence ;
- un système supposant que toute l'infrastructure est présente dans le repository analysé.

---

## 9. Success criterion

Le critère principal n'est pas :

> "Le rapport contient beaucoup d'informations."

Mais :

> "Un senior engineer arrivant sur le projet peut comprendre rapidement où regarder, comment le système fonctionne et quelles sont les zones importantes, sans devoir reconstruire lui-même toute cette connaissance."

Le système doit maximiser le ratio :

**useful understanding / analysis time / LLM cost**