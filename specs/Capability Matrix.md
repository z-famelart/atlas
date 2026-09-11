# Project Intelligence — Capability Matrix

## Legend

- P0 = essentiel au MVP
- P1 = important mais peut suivre
- P2 = extension
- Deterministic = analyse sans LLM
- Existing tool = capacité fournie par un outil externe
- Internal = calcul propre à Project Intelligence
- LLM = interprétation / synthèse

---

## 1. Discovery

| Question | P | Source | Existing tool | Deterministic | Internal | LLM | Evidence |
|---|---|---|---|---|---|---|---|
| Quels langages sont présents ? | P0 | filesystem/code | language detector | ✓ | | | fichiers |
| Quelle quantité de code par langage ? | P0 | code | LOC tool | ✓ | | | fichiers |
| Quels frameworks ? | P0 | manifests/code | ecosystem tools | ✓ | | | fichiers |
| Quel build system ? | P0 | config | ecosystem tools | ✓ | | | fichiers |
| Quels package managers ? | P0 | manifests | ecosystem tools | ✓ | | | fichiers |
| Quelle structure de repository ? | P0 | filesystem | filesystem tools | ✓ | | | fichiers |
| Monorepo ou multi-repo ? | P0 | Git/filesystem | Git | ✓ | ✓ | | repositories |
| Quels documents existent ? | P0 | filesystem | filesystem tools | ✓ | | | fichiers |
| Quels fichiers de configuration existent ? | P0 | filesystem | filesystem tools | ✓ | | | fichiers |
| Quelle taille / complexité globale ? | P0 | code | existing metrics tools | ✓ | ✓ | | metrics |

---

## 2. Code Graph

| Question | P | Source | Existing tool | Deterministic | Internal | LLM | Evidence |
|---|---|---|---|---|---|---|---|
| Quels sont les composants ? | P0 | code | Graphify / équivalent | ✓ | | | symbols |
| Qui dépend de qui ? | P0 | code | Graphify / équivalent | ✓ | | | relations |
| Qui appelle qui ? | P0 | code | Graphify / équivalent | ✓ | | | relations |
| Quelles relations d'héritage ? | P0 | code | Graphify / équivalent | ✓ | | | symbols |
| Quels sont les nœuds centraux ? | P0 | graph | Graphify | ✓ | ✓ | | graph |
| Quels clusters existent ? | P0 | graph | Graphify | ✓ | ✓ | | graph |
| Où sont les cycles ? | P0 | graph | existing tool / internal | ✓ | ✓ | | graph |
| Quels sont les entrypoints ? | P0 | code/config | framework-specific tools | ✓ | ✓ | | files/symbols |
| Quels sont les boundaries probables ? | P0 | graph + structure | internal | ✓ | ✓ | 🟡 | graph |

---

## 3. Architecture Interpretation

| Question | P | Source | Existing tool | Deterministic | Internal | LLM | Evidence |
|---|---|---|---|---|---|---|---|
| Quelle architecture est observée ? | P0 | graph | graph tools | 🟡 | ✓ | 🟡 | graph |
| Le système semble-t-il layered ? | P0 | graph/code | | | | ✓ | graph/files |
| Existe-t-il des boundaries métier ? | P0 | graph/code | | 🟡 | ✓ | ✓ | graph/files |
| Existe-t-il des violations de boundaries ? | P1 | graph | | ✓ | ✓ | 🟡 | graph |
| Quels composants sont centraux ? | P0 | graph | Graphify | ✓ | ✓ | | graph |
| Quels composants sont isolés ? | P1 | graph | Graphify | ✓ | ✓ | | graph |

---

## 4. Hotspots

| Question | P | Source | Existing tool | Deterministic | Internal | LLM |
|---|---|---|---|---|---|---|
| Quels fichiers sont complexes ? | P0 | code | complexity tool | ✓ | | |
| Quels fichiers sont gros ? | P0 | code | LOC tool | ✓ | | |
| Quels fichiers sont fortement couplés ? | P0 | graph | Graphify | ✓ | ✓ | |
| Quels fichiers sont centraux ? | P0 | graph | Graphify | ✓ | ✓ | |
| Quels fichiers changent souvent ? | P0 | Git | Git | ✓ | ✓ | |
| Quels fichiers ont beaucoup de contributeurs ? | P1 | Git | Git | ✓ | ✓ | |
| Quels fichiers changent ensemble ? | P1 | Git | Git | ✓ | ✓ | |
| Quels hotspots combinent plusieurs signaux ? | P0 | tous | | | ✓ | |
| Pourquoi ce composant est-il un hotspot ? | P0 | facts | | | | ✓ |

Le hotspot score doit être explicable et décomposable.

---

## 5. Code Navigation

| Question | P | Source | Deterministic | Internal | LLM |
|---|---|---|---|---|---|
| Par où entrer dans le système ? | P0 | code | ✓ | ✓ | |
| Quels fichiers sont importants ? | P0 | graph + Git | ✓ | ✓ | |
| Quelles dépendances possède X ? | P0 | graph | ✓ | | |
| Quels composants dépendent de X ? | P0 | graph | ✓ | | |
| Quel est le chemin entre A et B ? | P0 | graph | ✓ | ✓ | |
| Quels tests couvrent X ? | P1 | code/tests | 🟡 | ✓ | |
| Quels fichiers lire en premier ? | P0 | tous | | ✓ | ✓ |
| Quel parcours d'exploration recommander ? | P0 | tous | | ✓ | ✓ |

---

## 6. Domain / Business Understanding

| Question | P | Source | Deterministic | Internal | LLM |
|---|---|---|---|---|---|
| Quels concepts métier existent ? | P0 | code/docs/tests | 🟡 | | ✓ |
| Quels acteurs existent ? | P1 | docs/code | | | ✓ |
| Quels workflows existent ? | P0 | code/tests/docs | | | ✓ |
| Quelles règles métier sont détectables ? | P0 | code/tests | 🟡 | | ✓ |
| Quelles entités existent ? | P0 | schema/types/code | ✓ | ✓ | 🟡 |
| Quelles relations entre entités ? | P0 | schema/code | ✓ | ✓ | 🟡 |
| Quelles machines à états existent ? | P1 | code/tests | 🟡 | ✓ | ✓ |
| Quel vocabulaire métier est utilisé ? | P1 | code/docs | | | ✓ |
| Quels concepts restent ambigus ? | P1 | tous | | | ✓ |

---

## 7. Runtime

| Question | P | Source | Deterministic | Internal | LLM |
|---|---|---|---|---|---|
| Quels processus tournent ? | P0 | Docker/config/runtime | ✓ | | |
| Quels services existent ? | P0 | Docker/K8s/config | ✓ | ✓ | |
| Quels workers existent ? | P0 | code/config | ✓ | | |
| Quels jobs/schedulers existent ? | P0 | code/config | ✓ | | |
| Quelles queues existent ? | P0 | code/config | ✓ | | |
| Quelles bases sont utilisées ? | P0 | config/code | ✓ | | |
| Quelles APIs externes sont utilisées ? | P0 | code/config/docs | 🟡 | ✓ | 🟡 |
| Comment les composants communiquent-ils runtime ? | P0 | tous | 🟡 | ✓ | ✓ |

---

## 8. Infrastructure

| Question | P | Source | Deterministic | Internal | LLM |
|---|---|---|---|---|---|
| Existe-t-il de l'IaC dans le scope ? | P0 | scope discovery | ✓ | | |
| Quel IaC est utilisé ? | P0 | infra repos | ✓ | | |
| Quels clusters/services sont déclarés ? | P0 | K8s/IaC | ✓ | ✓ | |
| Comment sont déployés les services ? | P0 | IaC/CI | ✓ | ✓ | 🟡 |
| Quels environnements existent ? | P0 | IaC/CI/docs | 🟡 | ✓ | 🟡 |
| Où se trouve l'infrastructure si elle n'est pas dans le repo ? | P0 | metadata/docs/connectors | | ✓ | ✓ |
| Quelles ressources externes existent ? | P1 | IaC/cloud | ✓ | ✓ | |
| Quelle architecture infrastructure est probable ? | P1 | tous | | ✓ | ✓ |

---

## 9. CI/CD

| Question | P | Source | Deterministic | Internal | LLM |
|---|---|---|---|---|---|
| Quel système CI est utilisé ? | P0 | CI config | ✓ | | |
| Quelles étapes de validation ? | P0 | CI | ✓ | ✓ | |
| Comment est construit l'artifact ? | P0 | CI/Docker | ✓ | | |
| Comment est effectué le déploiement ? | P0 | CI/IaC | ✓ | ✓ | |
| Y a-t-il des approvals manuels ? | P1 | CI | ✓ | | |
| Quels environnements sont traversés ? | P0 | CI | ✓ | ✓ | |
| Quel est le chemin commit → production ? | P0 | CI/IaC | | ✓ | ✓ |

---

## 10. Data

| Question | P | Source | Deterministic | Internal | LLM |
|---|---|---|---|---|---|
| Quelles bases existent ? | P0 | config/IaC | ✓ | | |
| Quels schemas/tables ? | P0 | schema/migrations | ✓ | | |
| Quelles entités principales ? | P0 | schema/code | ✓ | ✓ | 🟡 |
| Quelles relations ? | P0 | schema | ✓ | | |
| Quels caches ? | P1 | code/config | ✓ | | |
| Quels systèmes de messaging ? | P0 | code/config | ✓ | | |
| Quels systèmes de stockage ? | P1 | code/IaC | ✓ | | |
| Quelle est la source of truth probable ? | P1 | tous | | | ✓ |

---

## 11. Tests

| Question | P | Source | Deterministic | Internal | LLM |
|---|---|---|---|---|---|
| Quels types de tests existent ? | P0 | code | ✓ | | |
| Quels domaines sont couverts ? | P0 | tests/code | 🟡 | ✓ | |
| Quels workflows sont testés ? | P1 | tests | 🟡 | | ✓ |
| Quels composants ont peu/pas de tests ? | P0 | code/tests | ✓ | ✓ | |
| Quels tests sont probablement critiques ? | P1 | tests | | ✓ | ✓ |

---

## 12. Git Evolution

| Question | P | Source | Deterministic | Internal | LLM |
|---|---|---|---|---|---|
| Quel âge a le projet ? | P1 | Git | ✓ | | |
| Quels fichiers changent le plus ? | P0 | Git | ✓ | ✓ | |
| Quels composants ont le plus de churn ? | P0 | Git + graph | ✓ | ✓ | |
| Quels fichiers changent ensemble ? | P1 | Git | ✓ | ✓ | |
| Quels contributeurs sont concentrés sur certains composants ? | P1 | Git | ✓ | ✓ | |
| Quelles zones sont historiquement instables ? | P1 | Git | | ✓ | 🟡 |
| Quels changements récents sont importants ? | P1 | Git | ✓ | ✓ | ✓ |

---

## 13. Observability

| Question | P | Source | Deterministic | Internal | LLM |
|---|---|---|---|---|---|
| Quel logging est utilisé ? | P0 | code/config | ✓ | | |
| Les logs sont-ils structurés ? | P1 | code | 🟡 | ✓ | |
| Le tracing existe-t-il ? | P1 | code/config | ✓ | | |
| Les metrics existent-elles ? | P1 | code/config | ✓ | | |
| Quels health checks existent ? | P0 | code/config | ✓ | | |
| Quels outils d'observabilité sont détectés ? | P0 | config/dependencies | ✓ | | |
| Comment diagnostiquer un incident ? | P1 | tous | | | ✓ |

---

## 14. Documentation

| Question | P | Source | Deterministic | Internal | LLM |
|---|---|---|---|---|---|
| Quels documents existent ? | P0 | filesystem | ✓ | | |
| Quels documents semblent importants ? | P0 | docs | | ✓ | ✓ |
| Les docs correspondent-elles au code ? | P1 | docs + code | | ✓ | ✓ |
| Où existe-t-il un documentation drift ? | P1 | docs + facts | | ✓ | ✓ |

---

## 15. Anomalies / Risks

| Signal | P | Source | Deterministic | Internal | LLM |
|---|---|---|---|---|---|
| Forte complexité + forte churn | P0 | code + Git | | ✓ | 🟡 |
| Forte centralité + fort couplage | P0 | graph | | ✓ | 🟡 |
| Cycle architectural | P0 | graph | ✓ | ✓ | |
| Documentation contradictoire | P1 | docs + facts | | ✓ | ✓ |
| Configuration incohérente | P1 | configs | 🟡 | ✓ | |
| Code non testé critique | P1 | code + tests | | ✓ | 🟡 |
| Architecture supposée mais non démontrée | P1 | facts | | | ✓ |
| Source manquante critique | P0 | discovery | ✓ | ✓ | |

---

## 16. Onboarding Path

| Question | P | Source | Deterministic | Internal | LLM |
|---|---|---|---|---|---|
| Quels composants comprendre en premier ? | P0 | graph/hotspots | | ✓ | ✓ |
| Quels fichiers lire en premier ? | P0 | graph/Git/tests | | ✓ | ✓ |
| Quel workflow suivre ? | P0 | graph/domain | | ✓ | ✓ |
| Quelles zones éviter initialement ? | P1 | graph/hotspots | | ✓ | ✓ |
| Que peut-on comprendre en 30 min ? | P0 | tous | | ✓ | ✓ |
| Que peut-on comprendre en 2 h ? | P0 | tous | | ✓ | ✓ |
| Quelles questions restent ouvertes ? | P0 | tous | | ✓ | ✓ |