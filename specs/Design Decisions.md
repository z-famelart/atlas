# Project Intelligence — Design Decisions

Ce document répond aux questions posées dans [Design Questions.md](Design%20Questions.md), section par section, en s'appuyant sur les principes fondamentaux du [Product Brief & Vision](Product%20Brief%20%26%20Vision.md) (existing tools first, deterministic first, LLM for interpretation, evidence first, never pretend to know, repository != system) et sur les priorités de la [Capability Matrix](Capability%20Matrix.md).

Statut de chaque réponse :
- **Décidé** — la question est tranchée, la décision engage l'architecture.
- **Proposition** — une réponse par défaut raisonnable est donnée mais reste ouverte à discussion.
- **Ouvert** — la question nécessite un arbitrage produit/business avant d'être tranchée (marqué **⚠️ impact architectural**).

**Depuis le 2026-09-17, toutes les questions sont Décidé** : les dernières Propositions et points Ouverts ont été tranchés en s'appuyant sur ce que l'implémentation a réellement montré (entrées marquées « résolu 2026-09-17 »). Les deux statuts ci-dessus ne servent plus qu'à lire l'historique. « Décidé » ne veut pas dire « implémenté » : chaque décision non encore implémentée le dit explicitement, et la liste complète est dans la [synthèse finale](#synthèse--décisions-non-encore-implémentées).

Ce document est lui-même vivant : chaque réponse doit être révisée quand l'implémentation contredit une hypothèse.

---

# A. Scope et modèle mental

**1. Qu'est-ce qu'on appelle exactement un `Project` ?**
Décidé. Un `Project` est l'unité de configuration et d'exécution de Project Intelligence : un ensemble nommé d'une ou plusieurs sources (repositories + sources externes optionnelles) que l'utilisateur déclare comme représentant un seul effort d'analyse. Un `Project` n'est pas un `System` — il peut analyser un sous-ensemble d'un système, ou plusieurs systèmes par erreur (à détecter, cf. Q84/Q166).

**2. Quelle différence formelle entre `Project`, `Repository`, `System` et `Environment` ?**
Décidé. `Repository` = une racine de code versionné (Git). `Project` = la configuration d'analyse (liste de repositories + sources + scope). `System` = le regroupement logique de composants qui coopèrent pour fournir une capacité métier (peut couvrir plusieurs repositories, est en partie une hypothèse tant qu'elle n'est pas confirmée par l'utilisateur). `Environment` = une instance runtime d'un système (dev/staging/prod), avec sa propre configuration et infra. Ces quatre entités sont représentées explicitement dans le modèle de Facts (cf. Q35).

**3. Peut-on analyser plusieurs repositories simultanément ?**
Décidé — oui, dès le MVP en configuration explicite (cf. Q195) : c'est une conséquence directe du principe "Repository != System".

**4. Comment déclare-t-on que plusieurs repositories appartiennent au même système ?**
Décidé (résolu 2026-09-17). Déclaration explicite uniquement : chaque entrée `[[repositories]]` de `.atlas.toml` pourra porter un champ optionnel `system = "<nom>"` (many-to-many possible, Q5). Pas de détection automatique : l'appartenance à un système est une connaissance organisationnelle que le code seul ne prouve pas — la deviner contredirait « Never pretend to know » ; une heuristique éventuelle (P2) ne produirait que des `hypothesis`. **Statut : implémenté (Feature 13b, 2026-09-22)** : `system` est lu et, pour chaque système déclaré par 2+ repositories, des facts `System`/`Repository`/`belongs_to` (provenance `observed`) sont écrits dans un store dédié `<project_root>/.atlas-cache/system-<nom>.sqlite`, séparé du store propre à chaque repository. Exposé en lecture via MCP par [Feature 12e](features/12e-mcp-system-query.md) (`get_system`). Chaque repository garde son propre store et son propre rapport HTML (non fusionnés) ; *comment* les repositories se relient reste non inféré, conformément à cette décision — c'est la lecture de l'agent (Feature 14) qui porte cette interprétation, pas un fact Atlas.

**5. Un repository peut-il appartenir à plusieurs systèmes ?**
Décidé — oui (ex. un monorepo partagé, une librairie interne). La relation `Repository -> System` est many-to-many dans le modèle.

**6. Comment représente-t-on une source externe non disponible localement ?**
Décidé. Un nœud `ExternalSource` typé (ex. `iac-repo`, `saas-dashboard`, `ci-system`) avec un statut `not_analyzed` et, si connu, une référence (URL, nom) mais aucune donnée extraite. Il apparaît dans le rapport comme un "trou" explicite plutôt que d'être omis (cf. principe Never pretend to know).

**7. Comment représente-t-on une information inconnue ?**
Décidé. Un champ n'est jamais laissé implicitement vide : soit il porte une valeur avec `provenance` et `confidence`, soit il porte explicitement un statut `unknown` / `not_analyzed` / `insufficient_evidence`. Aucune valeur par défaut silencieuse (pas de `null` interprété comme "non applicable" par le rapport).

**8. Quelle granularité d'analyse doit être supportée : repository, directory, file, symbol, system ?**
Décidé. Les cinq granularités doivent être adressables dans le modèle de Facts dès le MVP, même si tous les analyzers ne produisent pas toutes les granularités immédiatement. Le graphe de code (Q34+) est l'endroit où `file` et `symbol` doivent être navigables individuellement.

**9. L'utilisateur peut-il limiter explicitement le scope ?**
Décidé — oui, obligatoire au MVP : include/exclude par path glob, par langage, et par repository dans la configuration. C'est un garde-fou direct contre le non-goal "agent qui explore aveuglément toute la codebase". **Statut (2026-09-17) : partiel** — include/exclude par glob et `max_depth` (`[scope]`), appliqués par le stage `discovery` seulement ; `git`/`code_graph`/`hotspots` voient tout `PATH` ; pas de filtre par langage. Contournement documenté : passer un sous-dossier en `PATH`.

**10. L'outil doit-il pouvoir fonctionner complètement offline ?**
Décidé — oui pour toute la partie déterministe (discovery, code graph, hotspots, Git). Le mode offline désactive uniquement les étapes LLM et connectors externes ; le rapport HTML doit rester généré et utile sans ces étapes (cf. Q198, Q137).

---

# B. Discovery

**11. Comment détecte-t-on automatiquement les langages ?**
Décidé. Délégué à un outil existant (ex. `github-linguist`, `tokei`, ou équivalent) sur extension + heuristique de contenu, jamais réimplémenté en interne (principe Existing tools first).

**12. Comment détecte-t-on les frameworks ?**
Décidé. Détection par signatures de manifests (package.json deps, requirements.txt, pom.xml, Gemfile, go.mod, etc.) via des règles déclaratives par écosystème, pas par LLM. Extensible (cf. Q182).

**13. Comment détecte-t-on les build systems ?**
Décidé. Détection par présence de fichiers caractéristiques (Makefile, pom.xml, build.gradle, package.json scripts, Cargo.toml, etc.), règle déclarative par écosystème.

**14. Comment détecte-t-on les package managers ?**
Décidé. Même mécanisme que Q12/Q13 : détection par fichier de lock/manifest caractéristique.

**15. Comment détecte-t-on les repositories Git ?**
Décidé. Présence d'un répertoire `.git` (ou `.git` file pour un submodule/worktree) à la racine ou dans les sous-répertoires scannés, via l'outil Git lui-même.

**16. Comment détecte-t-on qu'une partie du système est probablement ailleurs ?**
Décidé (résolu 2026-09-17). P2, hors MVP. Les signaux listés (hôtes/services non résolus, variables d'environnement, mentions en documentation, imports de packages internes absents du scope) produiront des `ExternalSource` de provenance `hypothesis`, jamais des faits. Différé parce que chaque signal est bruité et demande son propre analyzer, alors que le cas explicite (Q6/Q119) suffit au MVP ; le type d'entité `ExternalSource` existe déjà dans le modèle (`facts/enums.py`), aucune refonte ne sera nécessaire.

**17. Comment détecte-t-on les fichiers d'IaC ?**
Décidé. Détection déclarative par pattern de fichier/extension par outil IaC (`*.tf`, `Chart.yaml`, `*.yaml` avec `kind:` Kubernetes connu, `serverless.yml`, `cdk.json`, etc.).

**18. Comment détecte-t-on Docker / Kubernetes / Helm / CI ?**
Décidé. Même approche : `Dockerfile`/`docker-compose.yml`, manifests K8s (par champ `apiVersion`/`kind`), `Chart.yaml`, et fichiers de config CI connus (`.github/workflows`, `.gitlab-ci.yml`, `Jenkinsfile`, `.circleci`, etc.) via une table de signatures.

**19. Comment gère-t-on les technologies inconnues ?**
Décidé. Le résultat de discovery inclut toujours une catégorie "unrecognized" listant les fichiers/dépendances non reconnus, jamais silencieusement ignorée. Elle nourrit l'amélioration continue de la table de signatures.

**20. Comment l'utilisateur peut-il ajouter manuellement une source ou un outil ?**
Décidé (résolu 2026-09-17). Deux voies, sans mécanisme de plugin (Q189) : (1) une **source** se déclare en configuration (`[[repositories]]` ; à terme `[[external_sources]]` pour une `ExternalSource` non analysée) ; (2) un **outil** s'ajoute in-tree : un `AdapterManifest` + un stage dans `STAGE_REGISTRY` (Q181). On refuse volontairement la déclaration d'une commande d'analyzer arbitraire dans la configuration : un `.atlas.toml` présent dans un repository analysé deviendrait un vecteur d'exécution de code non consenti. Statut : voie (2) implémentée ; `[[external_sources]]` non implémenté.

---

# C. Existing tools / adapters

**21. Quelle est la liste initiale des outils supportés ?**
Décidé. Un outil par catégorie P0 : **tokei** pour la détection de langages et LOC (binaire Rust, sortie JSON, offline), **graphify** pour l'extraction du graphe de code (imports/calls/symbols, multi-langages), **Git** natif pour l'historique. Complexité et scanners IaC/CI restent optionnels/dégradables au MVP.

**22. Quels outils sont considérés comme obligatoires pour le MVP ?**
Décidé (résolu 2026-09-17, confirmé par l'implémentation). Requis pour un rapport complet : Git, tokei (langages/LOC), graphify (code graph), lizard (complexité). Aucun n'est bloquant pour l'exécution : un outil absent marque son stage `skipped:tool_not_found` avec la commande d'installation (Q25/Q29) — « obligatoire » veut dire « nécessaire à la qualité », pas « nécessaire au démarrage ». lizard est une dépendance Python d'Atlas (toujours présente) et couvre à lui seul les langages du MVP (Q193), ce qui remplace « un outil de complexité par langage ».

**23. Quels outils sont optionnels ?**
Décidé (résolu 2026-09-17). Tout le reste est optionnel et best-effort : IaC, Kubernetes, CI/CD, OpenAPI, observabilité, security scanning. Au MVP seule leur **détection** par signatures existe (stage `discovery`), pas leur analyse ; leur absence n'empêche rien (cf. Q196, Q199).

**24. Comment un analyzer est-il déclaré ?**
Décidé. Manifest déclaratif par adapter : nom, catégorie, langages/écosystèmes supportés, commande d'invocation, format de sortie attendu, version minimale, mode d'échec. Pas de code custom requis pour un simple wrapping CLI → JSON.

**25. Comment son installation est-elle gérée ?**
Décidé (résolu 2026-09-17, implémenté). Vérification de présence (`shutil.which`) puis de version (`<binaire> --version` comparé à `min_version`/`max_version`) avant exécution. Jamais d'installation automatique : installer un binaire sur le poste de l'utilisateur sans consentement explicite est un risque de sécurité. L'absence produit `skipped:tool_not_found` avec l'`install_hint` du manifest, affiché dans la sortie CLI.

**26. Peut-on utiliser un binaire externe ?**
Décidé — oui, c'est le mode principal d'un adapter (invocation de process, capture stdout/stderr, parsing du format de sortie).

**27. Peut-on utiliser Docker pour encapsuler un analyzer ?**
Décidé (résolu 2026-09-17). Non au MVP : aucun des outils retenus (git, tokei, graphify, lizard) n'en a besoin, et Docker ajouterait un prérequis lourd, un coût de démarrage et casserait l'usage offline sur les postes sans Docker. Le contrat d'adapter (commande argv ou callable) permettrait de l'ajouter sans changement si un futur outil n'existait qu'en image.

**28. Comment gère-t-on une version incompatible d'un outil ?**
Décidé. Le manifest d'adapter déclare une plage de version supportée ; une version hors plage produit un warning explicite et l'analyzer est marqué `skipped: version_mismatch`, jamais exécuté à l'aveugle.

**29. Comment gère-t-on l'absence d'un outil ?**
Décidé. L'analyzer est marqué `skipped: tool_not_found` dans les facts ; le rapport affiche explicitement la section comme non analysée plutôt que de l'omettre silencieusement.

**30. Comment gère-t-on un analyzer qui échoue ?**
Décidé. Échec isolé par analyzer (try/catch au niveau de l'orchestrateur), jamais fatal pour l'ensemble de l'analyse. Statut `failed` + message d'erreur capturé comme evidence, cf. Q180.

**31. Comment versionne-t-on les adapters ?**
Décidé (résolu 2026-09-17, implémenté). `AdapterManifest.version` est la semver propre à l'adapter, indépendante de l'outil wrappé (dont la plage supportée est `min_version`/`max_version`) ; elle est tracée dans chaque fact via `source_analyzer = "<nom>@<version>"`. Ce qui compte pour les consommateurs est le format normalisé produit par l'adapter, pas la version de l'outil.

**32. Comment testons-nous les adapters ?**
Décidé (résolu 2026-09-17, implémenté). Tests de contrat sur sortie brute réelle enregistrée (`tests/fixtures/*_output.json`) → assertions sur les `Fact` produits ; la suite ne requiert aucun outil externe. Les tests d'intégration contre les vrais outils sont remplacés par le **dogfooding obligatoire** (CLAUDE.md) après toute modification d'`analyze` — c'est ce qui a trouvé l'essentiel des bugs réels (Features 04b, 08b, 09b, 10b, 11c…).

**33. Quel contrat de sortie impose-t-on à tous les adapters ?**
Décidé. Chaque adapter doit produire une liste de `Fact` (cf. section D) avec `type`, `entities`/`relations` concernées, `evidence`, `confidence`, `provenance = deterministic|existing_tool`. Aucune sortie libre non structurée n'est acceptée en sortie d'adapter.

---

# D. Normalized Facts

**34. Quelle est la structure exacte d'un `Fact` ?**
Décidé. `{ id, type, subject, predicate?, object?, value?, evidence: Evidence[], provenance: observed|computed|inferred|hypothesis, confidence, source_analyzer, created_at, schema_version }`. `subject`/`object` référencent des entités du modèle (Q35), `value` porte une valeur scalaire pour les métriques.

**35. Quels types d'entités supportons-nous ?**
Décidé (liste MVP, extensible cf. Q186) : `System`, `Environment`, `Repository`, `Project`, `Directory`, `File`, `Symbol` (fonction/classe/module), `Commit`, `Contributor`, `Service`, `Database`, `Queue`, `ExternalSource`, `Tool`, `Document`.

**36. Quels types de relations supportons-nous ?**
Décidé (liste MVP) : `depends_on`, `calls`, `imports`, `inherits_from`, `contains` (structure), `belongs_to` (repo→system), `changed_in` (fichier→commit), `authored_by`, `deployed_by`, `communicates_with`, `documents`, `tests`.

**37. Quelle structure pour une `Evidence` ?**
Décidé. `{ kind: file|line|symbol|commit|config|tool_output|documentation|external, ref, source_analyzer, retrieved_at }`. `ref` est typé selon `kind` (cf. Q38-Q42).

**38. Comment référence-t-on un fichier ?**
Décidé. Chemin relatif à la racine du repository + identifiant du repository (pas de chemin absolu, pour rester portable/versionnable).

**39. Comment référence-t-on une ligne ?**
Décidé. Référence fichier (Q38) + numéro de ligne (et plage début/fin optionnelle), avec le hash du commit au moment de l'analyse pour permettre l'invalidation si le fichier a changé (cf. Q103).

**40. Comment référence-t-on un symbole ?**
Décidé. Référence fichier + identifiant du symbole tel que fourni par l'outil de code graph (nom qualifié, ex. `module.Class.method`), plus la plage de lignes si disponible.

**41. Comment référence-t-on un commit ?**
Décidé. Hash de commit complet + identifiant du repository. Pas de dépendance à un hash court.

**42. Comment référence-t-on une ressource externe ?**
Décidé. `{ source_type, identifier, url? }` — ex. `{ source_type: "confluence", identifier: "...", url: "..." }`. Ne stocke jamais de contenu sensible extrait, seulement la référence + un résumé si nécessaire.

**43. Comment représente-t-on la provenance d'une donnée ?**
Décidé. Champ `provenance` sur chaque Fact (`observed|computed|inferred|hypothesis`, cf. Q45) + `source_analyzer` (quel adapter/composant l'a produit) + `retrieved_at`.

**44. Comment représente-t-on la confiance ?**
Décidé (résolu 2026-09-17, implémenté). `confidence: float` dans `[0,1]` sur chaque fact : 1.0 pour `observed`/`computed` ; fourni explicitement par le composant qui infère ou par le LLM pour `inferred`/`hypothesis`, jamais implicite. Une énumération (low/medium/high) aurait perdu l'ordre fin nécessaire pour classer des hypothèses concurrentes (Q82).

**45. Comment distingue-t-on `observed`, `computed`, `inferred` et `hypothesis` ?**
Décidé. `observed` = extrait directement d'une source sans transformation (ex. "ce fichier existe"). `computed` = dérivé déterministiquement de facts observés (ex. centralité, churn). `inferred` = déduction non déterministe mais raisonnée par une règle interne (ex. "ce répertoire est probablement une boundary"). `hypothesis` = proposition LLM non vérifiable déterministiquement (ex. "ce système suit un pattern hexagonal"). Ce sont les quatre valeurs du champ `provenance`, et le rapport HTML doit visuellement les distinguer (cf. Q136).

**46. Les facts sont-ils immuables ?**
Décidé — oui. Un fact n'est jamais modifié après création ; une ré-analyse produit de nouveaux facts liés à un nouveau `run_id` et à un nouveau timestamp/commit. L'historique des analyses reste donc traçable.

**47. Peut-on recalculer les insights à partir des facts sans relancer les analyzers ?**
Décidé — oui, c'est une exigence : la couche `Calculations`/`LLM synthesis` (cf. architecture conceptuelle) doit être rejouable indépendamment sur des facts déjà persistés, pour permettre l'itération sur le scoring/les prompts sans re-scanner le code.

**48. Les facts doivent-ils être persistés ?**
Décidé — oui, obligatoire dès le MVP (condition de Q47 et de la génération du rapport/MCP).

**49. Quel format de stockage : JSON, SQLite, graph DB, autre ?**
Décidé (résolu 2026-09-17, implémenté). SQLite via l'ORM SQLAlchemy, un fichier par chemin analysé : `<repo>/.atlas-cache/facts.sqlite` (tables `facts`, `fact_evidence`, `entities`, `schema_meta`). Raisons : un fichier, aucun serveur, requêtable par le MCP, append-only naturel (Q46). Pas de graph DB tant qu'aucun goulot n'est mesuré (Q158) : le graphe est reconstruit en mémoire (networkx) quand un calcul en a besoin. L'export JSON est couvert par `atlas facts query --json` (filtrable par type, run, provenance) ; pas de commande d'export complet tant qu'aucun usage ne la demande.

**50. Comment versionne-t-on le schema des facts ?**
Décidé. Champ `schema_version` sur chaque Fact ; migrations explicites documentées entre versions majeures ; le store SQLite embarque sa propre version de schema vérifiée au démarrage.

**50b. Le contenu du champ `value` (dict libre) doit-il être typé/validé quelque part ?**
Décidé (résolu 2026-09-15, suite à un audit complet du code déclenché par 4 bugs confirmés dans la même session — tous de la même cause : un consommateur lisait `fact.value.get("mauvaise_clé", défaut)`, `.get()` ne lève jamais d'erreur sur une clé absente, donc l'erreur ne s'est jamais manifestée par un crash). Oui — un module `facts/value_schemas.py` définit une dataclass frozen/slotted par type de fact (une par type déjà utilisé : `hotspot_score`, `centrality`, `technology_detected`, etc.), avec des accesseurs typés qui lèvent une erreur immédiate si les clés ne correspondent pas — au lieu du `.get(clé, défaut)` actuel qui masque silencieusement toute divergence. L'audit a confirmé que tous les producteurs actuels sont corrects (le défaut était toujours côté lecture, jamais côté écriture) ; cette feature ne retouche donc aucun des consommateurs déjà livrés et corrects, elle rend seulement la *prochaine* erreur de ce type impossible pour le nouveau code, plus un test de validation qui détecte automatiquement toute dérive future d'un producteur. Implémenté par la nouvelle **Feature 01b**, additive sur la Feature 01 déjà livrée.

---

# E. Graph

**51. Quelle partie du graph est fournie directement par des outils existants ?**
Décidé. L'extraction structurelle (symboles, imports, appels, héritage) vient entièrement d'un outil de code graph existant (Graphify ou équivalent) — Project Intelligence ne réimplémente pas de parsing AST.

**52. Quelle partie est construite par Project Intelligence ?**
Décidé. Les calculs transverses (centralité, communautés, cycles si non fournis, corrélation avec Git/hotspots) et la fusion multi-repository/multi-outil du graph.

**53. Utilisons-nous Graphify directement ?**
Décidé (résolu 2026-09-17, implémenté). graphify est le provider de référence, derrière le protocole `GraphProvider` (`code_graph/provider.py`) : le modèle de facts et les calculs de graph ne dépendent pas de graphify.

**54. Quels autres graph providers devons-nous supporter ?**
Décidé (résolu 2026-09-17). Aucun autre provider au MVP : graphify couvre les langages retenus (Q193). Un second provider ne sera ajouté que sur un manque constaté (langage non couvert, relations manquantes mesurées), via `GraphProvider`, sans toucher au modèle (Q183).

**55. Comment normalisons-nous les différents graph formats ?**
Décidé. Chaque `GraphProvider` traduit sa sortie native vers les entités/relations standard du modèle de Facts (Q35/Q36) — la normalisation est la responsabilité de l'adapter, pas du consommateur.

**56. Quelles relations doivent être standards ?**
Décidé — cf. Q36 : `depends_on`, `calls`, `imports`, `inherits_from` au minimum pour tout provider de graph.

**57. Comment distingue-t-on une relation extraite d'une relation inférée ?**
Décidé — via `provenance` sur la relation comme sur tout Fact (Q45) : une relation `imports` extraite du code est `observed` ; une relation "probable boundary" est `inferred`.

**58. Comment gère-t-on les graphs énormes ?**
Décidé (résolu 2026-09-17). Pas de pagination/streaming depuis le store au MVP : les repositories dogfoodés (jusqu'à ggshield et ses 374 communautés) tiennent en mémoire. Le volume est maîtrisé côté consommation : le rapport n'embarque que des vues bornées (top-N centralité pour le system map, 20 plus grandes communautés pour le code map, Q140d/Q140e) et chaque requête MCP est bornée (Q152). Rouvert si la taille cible (Q155) est dépassée en pratique.

**59. Faut-il produire plusieurs niveaux de graph ?**
Décidé — oui : au moins `system` (repositories/services), `module/directory`, et `file/symbol`. Le rapport doit permettre de naviguer du niveau macro au niveau micro (drill-down), pas d'afficher un graph plat de milliers de nœuds. **Statut (2026-09-17) : partiel** — l'agrégation par répertoire/module existe (`code_graph/aggregation.py`) ; le rapport offre une vue fichiers (system map) et une vue communautés (code map), sans drill-down navigable entre niveaux (vue interactive P2, Q129).

**60. Comment calcule-t-on les communautés ?**
Décidé (résolu 2026-09-17, implémenté). Louvain (`networkx.algorithms.community.louvain_communities`) sur le graphe imports/calls rendu non orienté, au niveau fichier, avec `seed=42` pour que deux runs sur le même code donnent les mêmes communautés.

**61. Comment calcule-t-on la centralité ?**
Décidé (résolu 2026-09-17, implémenté). Centralité de degré entrant/sortant (networkx) uniquement. Betweenness/eigenvector : non au MVP — coût bien supérieur sur les gros graphes, gain non démontré pour l'onboarding ; rouvert si l'évaluation (Q203) montre que le degré rate des fichiers pivots.

**62. Comment détecte-t-on les cycles ?**
Décidé. Détection algorithmique classique (Tarjan/SCC) sur le graph de dépendances, déterministe, fournie par une librairie existante ou par le graph provider s'il l'expose déjà.

**63. Quelle information doit être accessible au MCP ?**
Décidé (résolu 2026-09-17, implémenté par les primitives de Q141). Voisinage direct (`get_dependencies`/`get_dependents`), plus court chemin borné (`get_path`), top-N (`get_hotspots`, repli centralité de `where_to_start`), au niveau fichier ; jamais de dump. Les niveaux `module`/`symbol` via MCP seront ajoutés sur un besoin d'agent constaté.

---

# F. Hotspots

**64. Quelles métriques entrent dans le hotspot score ?**
Décidé (MVP, cf. Capability Matrix section 4) : complexité, taille (LOC), couplage/centralité du graph, churn Git. Runtime data en P1 si disponible.

**65. Le score doit-il être configurable ?**
Décidé (résolu 2026-09-17). Oui : section `[hotspot_weights]` de `.atlas.toml`, défauts complexity 1.0, size 0.5, centrality 1.0, churn 1.0 (la taille à demi-poids car fortement corrélée à la complexité). Statut : défauts implémentés ; la configuration est lue mais **pas encore transmise** au stage hotspots.

**66. Les poids sont-ils fixes ou adaptatifs ?**
Décidé (résolu 2026-09-17). Fixes. Des poids adaptatifs rendraient le score non reproductible et plus difficile à expliquer (Q73) ; le besoin « contexte de mission » est couvert par la configuration (Q65).

**67. Comment normalise-t-on les métriques entre projets ?**
Décidé (résolu 2026-09-17, implémenté). Rang percentile par composante, calculé sur la distribution du repository analysé (ex æquo = rang moyen). Pas de z-score : trop sensible aux distributions très asymétriques typiques du churn et de la complexité. Pas de comparaison inter-projets.

**68. Comment évite-t-on qu'un énorme fichier domine artificiellement ?**
Décidé (résolu 2026-09-17, implémenté). `log1p(LOC)` avant le rang percentile, poids réduit (0.5), et la taille n'est jamais un signal seul : elle n'entre que dans le score combiné, dont les composantes disponibles sont explicites (`components_available`, Q74).

**69. Comment intègre-t-on Git churn ?**
Décidé. Nombre de commits touchant le fichier sur une fenêtre configurable (cf. Q108/Q109), normalisé, comme une des composantes du score.

**70. Comment intègre-t-on graph centrality ?**
Décidé. Centralité (Q61) normalisée comme composante du score — un fichier très dépendu pèse plus qu'un fichier isolé de même complexité.

**71. Comment intègre-t-on complexity ?**
Décidé. Sortie de l'outil de complexité (cyclomatic/cognitive selon disponibilité par langage) normalisée comme composante du score.

**72. Comment intègre-t-on runtime data lorsqu'elle est disponible ?**
Décidé (résolu 2026-09-17). P2, hors MVP : dépend d'un connector d'observabilité qui n'existe pas (Q121). Le jour venu, composante optionnelle soumise à la même règle d'exclusion explicite que Q74.

**73. Comment explique-t-on le score ?**
Décidé — obligatoire (Capability Matrix : "Le hotspot score doit être explicable et décomposable"). Chaque score de hotspot est accompagné de la décomposition par composante (valeur brute + valeur normalisée + poids) et des evidences sous-jacentes.

**74. Comment représente-t-on l'absence de données ?**
Décidé. Une composante manquante (ex. pas de données Git si scope superficiel) est explicitement exclue du calcul et signalée dans l'explication du score, jamais traitée comme zéro silencieux.

**75. Peut-on avoir plusieurs scores : code hotspot, architectural hotspot, Git hotspot, runtime hotspot ?**
Décidé (résolu 2026-09-17, implémenté sous forme de décomposition). Chaque `hotspot_score` stocke, par composante, valeur brute, valeur normalisée et poids, plus le score combiné : le « pourquoi » se lit directement. Pas de scores nommés séparés (code/architectural/Git) : ils se déduisent de la décomposition et multiplieraient les classements contradictoires dans le rapport.

---

# G. Architecture interpretation

**76. Qu'est-ce qu'une architecture "observée" ?**
Décidé. Un ensemble de facts `computed`/`observed` sur la structure du graph (couches détectées par structure de dossiers + direction des dépendances, boundaries par communauté) — sans jugement qualitatif.

**77. Qu'est-ce qu'une architecture "interprétée" ?**
Décidé. Une synthèse `hypothesis` produite par le LLM à partir de l'architecture observée, nommant un pattern connu (layered, hexagonal, microservices, etc.) avec un niveau de confiance et des citations vers les facts observés qui la soutiennent.

**78. Quels patterns architecturaux cherchons-nous ?**
Décidé (résolu 2026-09-17, implémenté). Catalogue fermé : `layered`, `hexagonal`, `microservices`, `modular_monolith`, `event_driven`, `mvc_mvvm`, `big_ball_of_mud`, plus `uncatalogued` (pattern hors catalogue, décrit en texte libre). `big_ball_of_mud` permet au modèle de dire honnêtement qu'aucune structure n'émerge plutôt que de forcer un pattern. Toute valeur hors liste est normalisée à la source (Q83b). Étendre = ajouter une valeur dans `architecture/schema.py`.

**79. Le LLM peut-il proposer un pattern architectural ?**
Décidé — oui, mais uniquement comme `hypothesis` sourcée (cf. Q77), jamais présentée comme fait.

**80. Comment doit-il citer ses preuves ?**
Décidé. Toute affirmation architecturale du LLM doit référencer des `Fact` id existants (cf. Q105) ; une sortie LLM sans citation valide est rejetée par un validateur avant d'être intégrée aux insights.

**81. Comment évite-t-on les hallucinations architecturales ?**
Décidé (mécanisme). Contrainte de sortie structurée (schema JSON, cf. Q106) + validation post-hoc que chaque citation référence un fact réel + rejet/retry si la validation échoue (cf. Q104/Q107).

**82. Peut-on avoir plusieurs hypothèses concurrentes ?**
Décidé — oui, le modèle d'insight supporte une liste d'hypothèses avec confiance individuelle plutôt qu'une réponse unique forcée, en particulier quand l'architecture est ambiguë.

**83. Comment exprime-t-on la confiance ?**
Décidé — même mécanisme que Q44 : score `[0,1]` explicite fourni par le LLM et affiché à côté de chaque hypothèse.

**83b. Que faire si le LLM renvoie une valeur de `pattern` hors catalogue ?**
Décidé (résolu 2026-09-15, suite à un diagnostic concret sur des facts réels : le modèle Ollama/qwen3 local renvoyait un glob de fichiers, ex. `"ggshield/verticals/secret/output/secret_*.py"`, dans `pattern` au lieu d'une valeur de la catalogue Q78, et `pattern_description` toujours `null` — un bug de contenu, pas de rendu). Deux mesures : (1) renforcer le prompt (instruction explicite + contre-exemple : `pattern` n'est jamais un chemin/glob, cette information va dans `fact_ids`) ; (2) validation défensive après structuration de la réponse — toute valeur de `pattern` hors catalogue est automatiquement transformée en `pattern="uncatalogué"` avec la valeur brute du modèle déplacée dans `pattern_description` (préfixée pour indiquer qu'elle est invalide). Garantit que `pattern` est **toujours** une valeur valide de la catalogue dans les facts stockés, quel que soit le modèle utilisé — la garantie vit à la source, pas chez chaque consommateur (rapport, MCP, etc.). Implémenté par la nouvelle **Feature 08b**, additive sur la Feature 08 déjà livrée.

**83c. Le modèle confond-il parfois un dossier `services/` avec une architecture microservices ?**
Décidé (résolu 2026-09-15, trouvé dans une synthèse réelle produite par l'agent `atlas-synthesis` sur un backend Django : une hypothèse renvoyait `pattern="microservices"` pour une app dont le seul "service" est un package Python interne `services/`, sans le moindre déploiement séparé — le "My read" de l'agent l'a lui-même signalé comme faux). Différent du bug de Q83b : ici la valeur `pattern` est **valide** au sens de la catalogue, donc la validation défensive de la Feature 08b ne peut rien détecter — c'est un mauvais choix sémantique, pas une valeur hors catalogue. Fix : clarification explicite dans le prompt — "microservices" signifie des processus/services déployés indépendamment (déployables séparés), jamais un simple nom de dossier/package interne à un seul processus. Implémenté par la nouvelle **Feature 08c**, additive sur la Feature 08/08b déjà livrée.

**84. Peut-on comparer architecture déclarée dans la documentation et architecture observée ?**
Décidé (résolu 2026-09-17). P2, non implémenté. Utile (documentation drift), mais demande une passe LLM de plus sur la documentation ; priorité après la qualité des trois passes existantes.

---

# H. Domain understanding

**85. Quels artefacts fournissons-nous au LLM ?**
Décidé (résolu 2026-09-17, implémenté par les Features 09/09b/04b). Les facts hotspot/centralité et le **contenu** d'au plus `top_n=20` fichiers candidats, par priorité hotspot > entrypoint > test de workflow, fichiers vides exclus. README/docs : non envoyés au MVP. Les symboles (`symbol_defined`) sont fournis à la passe onboarding (Q205b).

**86. Combien de contexte LLM maximum ?**
Décidé (résolu 2026-09-17). Pas de plafond de tokens global au MVP : la borne est **structurelle** — au plus 20 fichiers (Q85) et une sélection de facts par passe — ce qui garde les prompts dans la fenêtre des modèles locaux ~14B visés (Ollama) comme des modèles Claude. Une borne en nombre de fichiers est prévisible et explicable ; une borne en tokens dépend du tokenizer de chaque provider. Le mécanisme de budget en tokens existe (Feature 07, `BudgetTracker`) et sera câblé depuis la configuration avec Q101.

**87. Comment sélectionnons-nous les fichiers importants ?**
Décidé. Réutilisation directe du score de hotspot/centralité (section F) et des entrypoints détectés (Q43 de la Capability Matrix / graph) — sélection déterministe, pas de LLM pour choisir quoi lire.

**88. Comment sélectionnons-nous les tests importants ?**
Décidé (résolu 2026-09-17, implémenté par la Feature 09b). Fichiers réellement identifiés comme tests (chemin sous `tests/`, `test_*`, `*_test`) **et** dont le nom évoque un workflow (`workflow`, `process`, `service`, `domain`, `handler`, `controller`), en dernière priorité dans le budget de Q85. Pas de mapping test→code : aucun outil du MVP ne le fournit.

**89. Comment identifions-nous les workflows candidats ?**
Décidé (résolu 2026-09-17). Au MVP, la passe domaine fait proposer les workflows par le LLM à partir des fichiers candidats (Q85/Q88), chaque workflow citant ses facts (implémenté). Reconstituer des chemins d'exécution dans le call graph depuis les entrypoints : P1, non implémenté — les relations `calls` inter-fichiers ne sont pas encore assez fiables pour cela.

**90. Comment extrayons-nous les états ?**
Décidé (résolu 2026-09-17). P2, non implémenté. La méthode proposée (enums/constantes de statut détectés déterministiquement, state machine nommée par le LLM en `hypothesis`) reste la cible.

**91. Comment extrayons-nous les événements ?**
Décidé (résolu 2026-09-17). P2, non implémenté. Même approche : signaux de nommage déterministes (`*Event`, `emit`, `publish`, topics), interprétation métier par le LLM en `hypothesis`.

**92. Comment conservons-nous les preuves ?**
Décidé — même mécanisme que tout le reste (Q37) : chaque affirmation de domain understanding référence les facts/fichiers/lignes qui l'ont motivée.

**93. Comment évitons-nous d'envoyer tout le repository au LLM ?**
Décidé — c'est un principe non négociable du Product Brief. Mécanisme : sélection déterministe bornée par budget (Q86/Q87) + refus explicite de tout mode "envoyer le repo entier".

**94. Comment gère-t-on plusieurs LLM providers ?**
Décidé (résolu 2026-09-14). Interface `LLMProvider` abstraite (prompt structuré in, réponse structurée validée out) permettant de brancher différents providers/modèles sans changer la couche synthèse. Provider par défaut du MVP : le CLI **Claude Code** déjà installé et authentifié sur la machine, invoqué en mode non-interactif avec sortie structurée — aucune clé API séparée à gérer. Repli : le no-op provider déjà requis par Q95 (LLM désactivé). Un provider LLM local (Ollama, cf. Q168) sera ajouté plus tard, quand disponible, sans re-discuter ce choix ni changer l'interface `LLMProvider`.

**95. Peut-on désactiver complètement le LLM ?**
Décidé — oui, obligatoire (cohérent avec Q10/Q198) : le rapport reste généré avec les sections LLM marquées `not_analyzed` plutôt que le pipeline entier bloqué.

**87b. La sélection de candidats (Q87) reste-t-elle vraiment bornée par `top_n`, et le domain understanding produit-il une couverture correcte sur un vrai repository ?**
Décidé (résolu 2026-09-17, suite à un retour direct — *"les domain concepts ne devraient vraiment pas être aussi pauvre dans une application aussi simple"* — après un diagnostic qui a d'abord mal ciblé le problème côté agent de synthèse au lieu d'Atlas lui-même). Non aux deux, bugs réels trouvés en rejouant `domain/selector.py` directement contre un vrai `FactStore` (crewlybase, 165 fichiers scorés, une seule run) :
1. **Le bound `top_n=20` documenté comme "bounded candidate set" ne l'est pas.** Seule l'étape 1 (hotspots) respecte `top_n` ; l'étape 2 (entrypoints, `in_degree == 0`) ajoute *tous* les entrypoints trouvés au-dessus des 20 déjà choisis (le commentaire "Cap entrypoints to top_n" plafonne la liste des entrypoints elle-même, pas le total cumulé) ; l'étape 3 (fichiers de test) ajoute encore par-dessus, toujours sans plafond. Sur crewlybase : 20 → 38 → 42 candidats réels, plus du double du budget documenté — un prompt ~2x plus gros que prévu envoyé à un modèle local faible (qwen2.5-coder), plausiblement la cause directe de la synthèse ne s'ancrant que sur 2 des 42 fichiers fournis (vérifié : les 4 facts `business_concept`/`business_workflow`/`glossary_term` produits ne citent que `festivals/services/team.py` et `accounts/services.py`, alors qu'`applications/services.py`, `scheduling/services.py`, `festivals/services/core.py` étaient bien dans les candidats).
2. **L'étape 3 n'est pas vraiment une sélection de fichiers de test.** Le docstring dit "Test files: name-match to selected source files", mais `is_workflow_test` matche n'importe quel chemin contenant un des mots `_WORKFLOW_KEYWORDS` (`"workflow"`, `"process"`, `"service"`, `"domain"`, `"handler"`, `"controller"`) — sans jamais vérifier que le fichier est réellement un test. Sur crewlybase ça a fait remonter `.github/workflows/ci.yml` (faux positif total, "workflow" dans un chemin CI, aucun rapport avec un test) au même titre qu'un vrai fichier de test.
3. **Le prompt (`domain/analyzer.py`) ne demande jamais une couverture explicite de tous les candidats fournis** — juste "identify the business concepts... present in this codebase", sans instruction de parcourir chaque fichier/module fourni plutôt que de s'arrêter sur le premier qui saute aux yeux. Sur un repository avec plusieurs apps/modules distincts (festivals, applications, scheduling, journal, accounts, registration_forms), un modèle faible s'arrête après 1-2 fichiers sans qu'aucune instruction ne le pousse à continuer.
Fix, dans `domain/selector.py` et `domain/analyzer.py` uniquement (pas de changement à `DomainResponse`/`BusinessConcept`, cf. `domain/schema.py`) : le budget `top_n` devient un vrai plafond cumulé sur les trois étapes (arrêt dès que `top_n` est atteint, avec un ordre de priorité clair hotspot > entrypoint > test) ; `is_workflow_test` exige en plus un vrai indicateur de fichier de test (chemin sous `tests/`, préfixe/suffixe `test_`/`_test`, cf. `_TEST_STEM_RE` déjà existant) avant de matcher sur les mots-clés ; le prompt ajoute une instruction explicite de couverture ("examine every file provided below, not just the first one or two — a repository with several distinct apps/modules should produce concepts spanning more than one of them when the evidence supports it"). Complément trouvé au passage, secondaire mais réel : `select_candidates` interroge `hotspot_score`/`centrality` sans filtre `run_id` (même famille de bug que Q140d/Q154f, déjà corrigée côté rapport HTML et MCP) — sur un repository à runs multiples ça re-crée le même risque de doublons/dilution ; scopé sous run_id le plus récent, même mécanisme que les fixes précédents. Implémenté par la nouvelle **Feature 09b**, additive sur la Feature 09 déjà livrée.

---

# I. LLM orchestration

**96. Combien de passes LLM sont nécessaires ?**
Décidé (résolu 2026-09-17, implémenté). Trois passes spécialisées et séquentielles — architecture, domaine, onboarding — chacune avec son schéma de réponse (dataclass → JSON Schema), ses citations, un retry ; l'onboarding consomme les résultats des deux premières.

**97. Peut-on réaliser le rapport avec un seul appel final ?**
Décidé — non par défaut, pour les raisons de Q96 (validation, citations, budget) ; peut rester une option "fast/cheap" dégradée en P2 avec avertissement de confiance réduite.

**98. Quels agents spécialisés sont réellement nécessaires ?**
Décidé (résolu 2026-09-17, implémenté). Exactement ces trois-là. L'agent `atlas-synthesis` (Q154b) n'est pas un agent du pipeline : c'est un consommateur externe du MCP.

**99. Quels agents peuvent être remplacés par des analyzers déterministes ?**
Décidé — aucun agent "LLM" ne doit exister là où la Capability Matrix marque une case déterministe/interne sans LLM (ex. hotspots, centralité, cycles) : le principe deterministic-first s'applique strictement à la conception des agents, pas seulement aux données.

**100. Comment limite-t-on les tokens ?**
Décidé — mécanisme combiné : sélection de contenu bornée (Q87), budget par passe (Q101), troncature explicite avec log plutôt que silencieuse.

**101. Comment impose-t-on un budget ?**
Décidé (résolu 2026-09-17). Budget en tokens par run (`llm.budget_tokens`), vérifié avant chaque appel par `BudgetTracker` ; dépassement → `not_analyzed: budget_exceeded` pour la passe concernée, le pipeline continue (jamais d'échec dur). Statut : mécanisme implémenté (Feature 07) ; la configuration est lue mais **pas encore câblée** (budget illimité aujourd'hui) ; la répartition par passe viendra avec ce câblage.

**102. Comment cache-t-on les résultats ?**
Décidé (résolu 2026-09-17, implémenté). Clé SHA-256 de (instructions + contenu + version de schéma + `provider_id`, qui inclut le modèle, ex. `ollama:qwen3:14b`) → réponse JSON. Persisté dans `.atlas-cache/llm_cache.sqlite`, fichier distinct du store de facts pour pouvoir vider le cache sans perdre l'historique. Seules les réponses ayant passé la validation de citations sont mises en cache.

**103. Comment invalidons-nous un résultat après modification du code ?**
Décidé — conséquence directe de Q102 : si le contenu sous-jacent (fichiers sélectionnés, facts amont) change, le hash change, donc le cache est naturellement invalidé sans mécanisme de dépendance explicite à maintenir.

**104. Comment détecte-t-on les hallucinations ?**
Décidé — validation structurelle systématique : toute citation LLM doit référencer un `Fact` id existant (Q80/Q81) ; toute citation invalide est un échec de validation, pas une correction silencieuse.

**105. Le LLM doit-il obligatoirement produire des citations ?**
Décidé — oui, pour toute affirmation non triviale (cohérent avec le principe evidence-first). Une sortie LLM sans citation sur un champ qui l'exige est rejetée.

**106. Quel modèle de sortie doit-il respecter ?**
Décidé. JSON structuré validé par schema (par type de passe), jamais de texte libre parsé heuristiquement. Chaque champ narratif est accompagné d'un tableau de `fact_ids` cités.

**107. Que se passe-t-il si le LLM échoue ?**
Décidé — échec isolé par passe (même logique que Q30 pour les adapters) : la section correspondante du rapport est marquée `not_analyzed: llm_failed`, le reste du pipeline continue.

---

# J. Git

**108. Quelle profondeur d'historique analyse-t-on ?**
Décidé (résolu 2026-09-17). Historique complet par défaut — ce qui s'écarte de la proposition initiale (12 mois) : sur les repositories dogfoodés, `git log --numstat` sur tout l'historique reste rapide, et une fenêtre courte masquait des fichiers structurellement instables mais peu modifiés récemment. La fenêtre est supportée par le code (`AnalysisWindow`) ; son exposition en CLI/configuration n'est **pas implémentée**.

**109. Analyse-t-on toute l'histoire ou une fenêtre configurable ?**
Décidé — fenêtre configurable par défaut (cf. Q108), historique complet en option explicite.

**110. Comment calcule-t-on le churn ?**
Décidé. Nombre de commits (ou lignes modifiées, les deux exposées séparément) touchant un fichier sur la fenêtre, via `git log`/`git blame`, calcul interne déterministe.

**111. Comment calcule-t-on le co-change ?**
Décidé (résolu 2026-09-17, implémenté). Paires de fichiers modifiés dans un même commit (hors merges), retenues à partir de 2 commits communs sur la fenêtre analysée.

**112. Comment gère-t-on les renames ?**
Décidé. Suivi de renommage natif de Git (`git log --follow` / détection de similarité) pour préserver la continuité de l'historique d'un fichier à travers ses renommages. **Statut (2026-09-17) : implémenté par la Feature 04c** — la détection de renommage de Git (`-M`) est lue en une seule passe de `git log` (notations `old => new` et `pre{old => new}post` pour le churn, `--name-status` pour le co-change) : tout l'historique d'un fichier renommé, y compris antérieur au renommage, est rattaché à son chemin le plus récent, sans entité fantôme. `--follow` par fichier n'est pas utilisé (une passe par fichier) ; cf. `docs/improvement-ideas.md` §2.1.

**113. Comment gère-t-on les merge commits ?**
Décidé (résolu 2026-09-17, implémenté). Merges exclus (`--no-merges`) pour churn et co-change. L'inclusion existe dans le code (`include_merges`) mais n'est pas exposée en CLI.

**114. Comment gère-t-on les monorepos ?**
Décidé (résolu 2026-09-17, implémenté par la Feature 04b). On analyse le sous-dossier passé en `PATH` : l'historique Git est lu pour tout le dépôt, mais les chemins sont rebasés sur ce sous-dossier, si bien que seuls ses fichiers se joignent aux autres facts et entrent dans les hotspots. Pratique documentée pour un monorepo : passer le sous-projet comme `PATH` (Q158).

**115. Comment détecte-t-on les hotspots historiques ?**
Décidé — c'est la combinaison churn + centralité + complexité déjà définie en section F ; pas de mécanisme distinct.

**116. Comment corrèle-t-on Git et code graph ?**
Décidé. Jointure sur le chemin de fichier normalisé (Q38) entre les facts Git (churn, contributeurs, co-change) et les facts du graph (centralité, appartenance à un composant) au niveau du store de facts.

**116b. La jointure sur "chemin de fichier normalisé" (Q116/Q38) tient-elle vraiment quand `repo_path` est un sous-dossier du dépôt git (cas monorepo, Q114) ?**
Décidé (résolu 2026-09-17, bug réel trouvé en comparant deux tables de hotspots qui "parlaient de fichiers différents alors que c'est les mêmes" — retour direct de l'agent `atlas-synthesis` re-exécuté après la Feature 09b, sur `repo_path=crewlybase/backend`, un sous-dossier du vrai dépôt git racine `crewlybase/`). Non — Q116 suppose une normalisation de chemin déjà cohérente entre facts Git et facts de graph, mais ce n'est vrai qu'à la racine du dépôt, par coïncidence. `git log`/`git log --numstat` (Feature 04, `churn.py`/`cochange.py`) rapporte toujours des chemins relatifs à la **racine du dépôt git** (`git rev-parse --show-toplevel`), quel que soit le `cwd` (`ctx.target_path`) depuis lequel la commande tourne — mais `normalize_churn`/`normalize_cochange` utilisent ce chemin tel quel comme `subject.id`, sans le rebaser sur `repo_path`. Tous les autres producteurs de facts (discovery, lizard/complexity, graphify/code graph) calculent leurs chemins relatifs à `repo_path` lui-même. Quand `repo_path` est la racine du dépôt (cas non-monorepo le plus courant), les deux conventions coïncident par accident et le bug est invisible. Dès que `repo_path` est un sous-dossier (`crewlybase/backend`), elles divergent d'un préfixe fixe (`backend/`) et **chaque fichier se fragmente en deux identités distinctes** : une portant `git_churn`/`git_co_change` (chemin préfixé), une portant tout le reste — `centrality`, `complexity`, `community`, `calls`/`imports` (chemin non préfixé) — jamais réunies, la jointure de Q116 échoue silencieusement fichier par fichier. Conséquences mesurées sur crewlybase (`backend/.atlas-cache/facts.sqlite`, une seule run) : 60 fichiers fragmentés en deux `hotspot_score` incomplets chacun (`components_available` à `1/4` pour la quasi-totalité des 165+ fichiers du repo, au lieu de `3/4`/`4/4` attendus) ; pire, l'entité "fantôme" côté churn (chemin préfixé) se classe artificiellement haut dans le classement hotspot (un seul composant très élevé, non pondéré par les autres) et devient candidate pour le sélecteur de domain understanding (Feature 09/09b) — mais la lecture de son contenu (`domain/selector.py::_read`, `repository_path / path`) tente alors d'ouvrir `<repo_path>/backend/...` (double préfixe, chemin inexistant), échoue silencieusement (`OSError` capturé, retourne `""`), et envoie un candidat au contenu **vide** au LLM sous un nom de fichier plausible. C'est la cause racine directe du glossaire de domaine dominé par un seul fichier (`festivals/admin.py`, source de 21 des 28 facts domain de cette run) et de l'absence totale du vocabulaire "shift"/"swap" (`scheduling/services.py` se classe haut uniquement via son entité fantôme au contenu vide ; son entité réelle et lisible, privée du boost churn, ne rentre pas forcément dans le top `top_n`). La Feature 09b (budget réel, instruction de couverture) était nécessaire mais ne pouvait pas suffire : elle opère sur un pool de candidats déjà corrompu en amont par ce bug de Feature 04. Fix scopé à `git_analysis/churn.py` et `git_analysis/cochange.py` uniquement : rebaser chaque chemin retourné par `git log` sur `ctx.target_path` (calculer l'offset de `ctx.target_path` par rapport à la racine git via `git rev-parse --show-toplevel`, puis retirer ce préfixe de chaque chemin avant de construire le `Fact`) — aucune autre feature ne change, la convention "chemin relatif à `repo_path`" déjà utilisée partout ailleurs (et déjà supposée par Q116) devient enfin réellement universelle. Complément défensif, peu coûteux : `domain/selector.py::select_candidates` doit exclure un candidat dont le contenu lu est vide plutôt que l'envoyer tel quel au LLM (protection contre toute future désynchronisation de chemin, pas seulement celle-ci). Implémenté par la nouvelle **Feature 04b**, additive sur la Feature 04 déjà livrée.

---

# K. Infrastructure / external sources

**117. Comment déclare-t-on qu'un IaC repository appartient au système ?**
Décidé — même mécanisme que Q4 : déclaration explicite dans la configuration du `Project` (repository supplémentaire tagué comme IaC pour un `System` donné).

**118. Peut-on analyser plusieurs repositories différents avec des adapters différents ?**
Décidé — oui, c'est la conséquence naturelle du modèle multi-repository (Q3) : chaque repository est scanné avec les adapters pertinents à son contenu détecté (Q11-19), indépendamment des autres.

**119. Comment gère-t-on les repositories absents ?**
Décidé — même traitement que Q6/Q29 : `ExternalSource`/`Repository` avec statut `not_analyzed`, jamais une absence silencieuse.

**120. Comment gère-t-on les sources accessibles uniquement via API ?**
Décidé (résolu 2026-09-17). P2, non implémenté. Contrat retenu : un `Connector` produit des `Fact` exactement comme un adapter (Q33) et lit ses credentials dans l'environnement (Q122).

**121. Quels connectors sont supportés ?**
Décidé (résolu 2026-09-17). Aucun connector au MVP. Premier candidat quand un utilisateur en exprimera le besoin : un dépôt Git distant déclaré (repository IaC/GitOps cloné en lecture) — c'est celui qui sert le plus directement « Repository != System » sans credentials SaaS. Les connectors SaaS (dashboards, registres) suivront l'usage réel.

**122. Comment gère-t-on les credentials ?**
Décidé (résolu 2026-09-17). Jamais stockés ni journalisés par Atlas ; lus dans l'environnement au moment de l'exécution. Au MVP, le seul secret en jeu est l'authentification du CLI `claude` (provider `claude-code`), entièrement gérée par Claude Code : Atlas ne la voit pas.

**123. Le système doit-il fonctionner sans credentials ?**
Décidé — oui, obligatoire : tout connector nécessitant des credentials est optionnel et son absence dégrade proprement (Q29/Q119), jamais bloquant pour le reste du pipeline.

**124. Comment sépare-t-on données locales et données sensibles ?**
Décidé (résolu 2026-09-17). Au MVP la séparation est choisie par l'utilisateur au niveau du run : provider local (Ollama) ou `--no-llm` → aucune donnée ne sort ; provider `claude-code` → la sélection bornée de Q85 sort. Un marquage de sensibilité par source est P2, avec les analyses multi-sources.

**125. Quelles données ne doivent jamais être envoyées au LLM ?**
Décidé (résolu 2026-09-17). Ne sortent jamais : le repository complet, tout contenu hors sélection bornée (Q93), les données nominatives Git (Atlas ne collecte d'ailleurs pas les auteurs), les secrets détectés (Q165). Statut : la borne de volume est implémentée ; le filtrage des secrets ne l'est pas — d'où la recommandation documentée d'utiliser Ollama ou `--no-llm` sur du code client.

---

# L. HTML report

**126. Quelle structure exacte du rapport ?**
Décidé — reprend directement la liste du Product Brief section 5 : executive summary, system map, architecture, code map, hotspots, domain understanding, runtime, infrastructure, CI/CD, data architecture, observability, tests, Git evolution, risks/anomalies, onboarding path, glossary, evidence. **Statut (2026-09-17) : partiel** — voir Q199 : les sections runtime, infrastructure, CI/CD, data, observabilité et tests arriveront avec leurs analyzers.

**127. Quelle navigation ?**
Décidé (résolu 2026-09-17, implémenté). Navigation latérale persistante par section + recherche globale. Pas de fil d'Ariane : il n'y a pas de drill-down multi-niveaux au MVP (vue graphe interactive différée, Q129).

**128. Quels diagrammes ?**
Décidé (résolu 2026-09-17, implémenté). System map (Mermaid, top-N fichiers par centralité avec leurs arêtes) et code map (SVG des communautés : taille, importance, liens). Diagrammes CI/CD et entités de données : ajoutés avec les analyses correspondantes (Q196), pas avant.

**129. Mermaid ou autre moteur ?**
Décidé (résolu 2026-09-14, suite à un constat direct sur le rapport généré : les blocs Mermaid n'affichaient qu'un texte "Load mermaid.js locally to render diagram" — aucun diagramme ne s'affichait jamais, en contradiction avec Q137/Q138 déjà Décidé). Mermaid pour les diagrammes statiques simples, mais **vendoré/embarqué inline** : le bundle UMD complet de mermaid.js est inclus tel quel dans un `<script>` du fichier HTML généré (pas de `<script src="https://...">`, pas de placeholder "chargez-le vous-même") — c'est la seule façon dont "autonome/offline" (Q137/Q138) peut signifier "le diagramme s'affiche réellement dans le navigateur" plutôt que "le HTML ne fait pas d'appel réseau mais n'affiche rien d'utile". Un rendu graphe interactif dédié (ex. force-directed / cytoscape.js) pour le code graph navigable est différé en P2 (décidé 2026-09-17, cf. Q134) — Mermaid seul ne scale pas à un graph de milliers de nœuds mais suffit au MVP. Implémenté par la nouvelle **Feature 11b** (additive sur la Feature 11 déjà livrée).

**130. Les diagrammes doivent-ils être générés à partir des facts ?**
Décidé — oui, systématiquement : jamais de diagramme dessiné à la main ou par le LLM sans passer par les facts structurés, pour garantir que chaque élément visuel est cliquable vers son evidence (Q131).

**131. Peut-on cliquer sur un composant et voir ses preuves ?**
Décidé — oui, obligatoire (cohérent avec evidence-first) : chaque nœud/élément du rapport est lié à ses `Evidence` sous-jacentes.

**132. Peut-on cliquer sur une relation et voir son origine ?**
Décidé — oui, même exigence que Q131 appliquée aux relations (quel adapter/analyzer l'a produite, avec quelle provenance).

**133. Peut-on rechercher un symbole ?**
Décidé — oui, recherche full-text sur les entités (fichiers, symboles, composants) exigée dès le MVP pour la navigation.

**134. Peut-on filtrer le graph ?**
Décidé (résolu 2026-09-17). P2. Le filtre texte global existe ; les filtres par type de relation / provenance / composant arriveront avec la vue graphe interactive (Q129).

**135. Comment affiche-t-on les niveaux de confiance ?**
Décidé (résolu 2026-09-17, implémenté). Badge de provenance coloré sur chaque élément, confiance en pourcentage en infobulle. Un encodage visuel supplémentaire (opacité, bordure) est P2.

**136. Comment distingue-t-on fact / insight / hypothesis ?**
Décidé — obligatoire (principe evidence-first) : un marqueur visuel systématique et explicite (badge/couleur/icône) reflétant le champ `provenance` (Q45), cohérent entre toutes les sections du rapport.

**137. Le rapport doit-il fonctionner totalement offline ?**
Décidé — oui, fichier HTML autonome sans dépendance réseau à l'ouverture (cf. Q138), y compris pour les diagrammes et la recherche.

**138. Doit-il être un fichier HTML autonome ?**
Décidé — oui : toutes les données et assets nécessaires embarqués (ou en fichiers locaux adjacents), pour être partageable/archivable sans serveur.

**139. Peut-on exporter certaines vues ?**
Décidé (résolu 2026-09-17). Pas d'export de vue dédié : le rapport est lui-même un fichier autonome partageable, et les données s'exportent via `atlas facts query --json`. Export image/PDF : P2.

**140. Le rapport doit-il être versionnable ?**
Décidé — oui : chaque génération de rapport embarque un timestamp, le `run_id`, et le commit hash de chaque repository analysé, pour permettre de comparer deux rapports dans le temps. **Statut (2026-09-17) : partiel** — le rapport embarque `run_id` et horodatage (balises `meta`), pas encore le commit hash analysé.

**140b. Le rapport doit-il présenter du texte narratif lisible, ou une liste de facts suffit-elle ?**
Décidé (résolu 2026-09-14, suite à un retour utilisateur direct sur le v1 livré : *"c'est un listicle des facts avec lesquels on doit interagir pour espérer lire quelque chose"*). Non — une liste de facts cliquables ne suffit pas, même si elle respecte Q130 ("toujours rendre depuis les facts"). Chaque section doit présenter, en contenu principal, un **texte narratif en langage naturel** ; les facts individuels restent accessibles (comme aujourd'hui, via le drill-down evidence de Q131/Q132) mais deviennent des citations à l'appui du texte, pas le texte lui-même. Deux cas :
- **Sections déterministes/observées/computed** (technos détectées, churn, hotspots, etc.) : phrase(s) générées par **template déterministe**, pas par un appel LLM — cohérent avec le principe "Deterministic first" — ex. *"Atlas a détecté les technologies suivantes : Flask, PostgreSQL, Docker."* plutôt qu'une ligne par techno.
- **Sections déjà interprétatives** (architecture, domain understanding, onboarding path — Features 08/09/10) : ces features produisent déjà un texte narratif LLM (`pattern_description`, description de concept métier, etc.) avec citations (`fact_ids`) — le gap n'est pas dans ces features, il est dans le renderer HTML (Feature 11) qui n'affiche aujourd'hui que le label extrait en ligne de liste au lieu du texte complet déjà généré. Rien à ajouter côté LLM ici, seulement afficher ce qui existe déjà.

Implémenté par la nouvelle **Feature 11b** (additive sur la Feature 11 déjà livrée, cf. [specs/features/README.md](features/README.md#regeneration-contract)).

**140c. Si le stage LLM d'un run a échoué mais qu'un run précédent du même repository a réussi, le rapport doit-il le montrer ?**
Décidé (résolu 2026-09-15, suite à un diagnostic concret : le rapport d'un run réel affichait "Not analyzed" pour Architecture/Domain alors que le même repository, analysé quelques heures plus tôt, avait produit 15 `architecture_hypothesis` et 5 `business_concept` dans le même store append-only — juste sous un autre `run_id`). Oui — chaque section interroge d'abord le `run_id` courant puis, si vide, retombe sur le **run le plus récent qui a des facts de ce type**, tous runs confondus pour ce repository (le store le permet déjà, `query_facts` sans filtre `run_id`). Le fallback n'est **jamais silencieux** : la prose de la section indique explicitement qu'il s'agit d'un résultat antérieur, avec le `run_id`/date d'origine. En complément (cf. Q180b) : les trois états auparavant confondus sous "Not analyzed" sont maintenant distingués et affichés — jamais lancé, LLM désactivé, LLM a échoué (avec la raison réelle), ou stage réussi mais rien trouvé. Répond directement au problème remonté : un texte LLM absent pour cause d'échec ne doit plus être indiscernable d'un texte absent parce qu'il n'y a vraiment rien à trouver. Implémenté par la nouvelle **Feature 11c**, additive sur la Feature 11/11b déjà livrée, qui s'appuie sur les facts `stage_run_result` de la Feature 06c (Q180b).

**140d. Les bugs de correspondance de champs (fact → rendu) et l'absence d'arêtes dans le system map sont-ils un problème de scope ou un bug ?**
Décidé (résolu 2026-09-15). Bug, pas un nouveau choix de design — confirmé en lisant un rapport réel contre son `FactStore` : le renderer lit des clés qui n'existent pas dans les facts réellement produits (`technology` au lieu de `name`, `score` au lieu de `combined` pour les hotspots, `score` inexistant pour la centrality qui n'a que `in_degree`/`out_degree`), avec repli silencieux vers une valeur trompeuse plutôt qu'une erreur visible. Le diagramme Mermaid du system map ne déclarait que des nœuds, jamais d'arêtes (les facts `imports`/`calls` existent pourtant), et l'identifiant de nœud (basename seul) provoque des collisions entre fichiers homonymes de chemins différents. Décision explicite sur la portée des arêtes : limiter aux relations entre les nœuds déjà sélectionnés (top-N par centralité), pas le graphe complet — une vue interactive complète (cytoscape.js, P2, cf. Q129) reste un sujet séparé, volontairement pas traité ici. Implémenté par la nouvelle **Feature 11c**.

**140e. La section Code Map doit-elle montrer un vrai graphe de communautés (taille, liens, importance) plutôt qu'une liste de facts par fichier ?**
Décidé (résolu 2026-09-15, suite à une demande directe). Oui — Code Map agrège les facts `community` par `community_id` (pas un par fichier comme aujourd'hui) et affiche : **taille** = nombre de fichiers membres, **importance** = somme de la centralité (`in_degree + out_degree`) des fichiers membres — les deux dimensions demandées explicitement, jamais confondues en un seul nombre. Rendu en **SVG inline** généré au moment du rapport (pas Mermaid, qui ne sait pas encoder une taille de nœud) : rayon des bulles ∝ `sqrt(taille)`, couleur ∝ importance normalisée sur l'ensemble affiché, les deux valeurs aussi écrites en clair (l'encodage visuel ne remplace jamais le chiffre). Liens entre communautés = relations `imports`/`calls` inter-communautés agrégées, pondérées par leur nombre. Limité aux 20 plus grandes communautés (repli visuel nécessaire : un vrai repo peut en avoir plusieurs centaines — 374 pour ggshield), avec le nombre de communautés omises indiqué en prose. Layout circulaire déterministe, pas de physique interactive (P2, cf. Q129). Implémenté par la nouvelle **Feature 11d**, additive sur la Feature 11/11b/11c déjà livrée.

**140f. Le repli inter-runs (Q140c) et le résumé de l'architecture "uncatalogued" (Q83) produisent-ils un texte réellement lisible, ou juste une prose techniquement présente ?**
Décidé (résolu 2026-09-17, suite à un retour direct sur deux rapports réels — *"les textes sont trop succincts, et forment à peine des phrases compréhensibles"*). Non, deux défauts distincts trouvés en lisant `html_report/renderer.py` contre les rapports générés :
1. **Prose de repli contradictoire.** Chaque section avec repli (Q140c) construit sa phrase de contenu au présent ("Detected 6 technologies: …") puis lui accole, sans reformulation, la note de repli ("No technology data for this run. Showing results from a previous analysis…") — deux affirmations qui semblent se contredire alors qu'elles décrivent la même donnée (celle du run de repli). Ce pattern est dupliqué à l'identique dans les huit fonctions `_render_*` qui utilisent `_fallback_note`, pas un cas isolé. Fix : un seul point de composition (`_content_sentence` ou équivalent) qui, quand un repli est utilisé, construit **une** phrase cohérente au passé/repli (ex. *"No technology data for this run — showing 6 technologies from a previous analysis (run `a38537cb`, 2026-09-16 07:30): npm, flask, …"*) au lieu de deux phrases juxtaposées qui se contredisent en apparence ; sans repli, la phrase au présent existante est inchangée.
2. **Mur de bruit dans la prose Architecture.** Quand le modèle assigne `pattern="uncatalogued"` à plusieurs hypothèses (bug déjà mitigé côté données par 08b/Q83 — `normalize_pattern` force la valeur et pousse le nom de fichier original dans `pattern_description`, préfixé `"(unrecognized pattern value: '<fichier>')"`), le renderer concatène aujourd'hui **une occurrence par hypothèse** de cette chaîne de debug dans le paragraphe narratif — jusqu'à 10 répétitions quasi identiques dans un rapport réel, illisible. Cette chaîne est un artefact de debug destiné au fact-row/evidence (Q131/Q132), jamais pensé pour la prose. Fix : le renderer détecte ce préfixe et **n'inclut jamais** ces descriptions synthétiques dans la prose telle quelles ; à la place, toutes les hypothèses "uncatalogued" avec description synthétique sont résumées en **une seule phrase** avec un compte (ex. *"Atlas flagged 10 individual files as architecturally notable but could not assign a named pattern to any of them — see evidence for detail."*). Une `pattern_description` réelle (texte libre fourni par le modèle, pas la chaîne synthétique) continue d'être affichée telle quelle, comme aujourd'hui.

Les deux fixes sont des changements de composition de prose dans `html_report/renderer.py` uniquement — aucun changement aux facts produits par les features en amont (03/05/06/08/09/10), à `_query_fallback`, ni à la logique de repli/états de gap elle-même (Q140c/Q180b, déjà correctes). Implémenté par la nouvelle **Feature 11e**, additive sur la Feature 11/11b/11c/11d déjà livrée.

---

# M. MCP

**141. Quelles primitives MCP sont nécessaires ?**
Décidé (résolu 2026-09-17, implémenté par les Features 12/12b/12c). Huit primitives read-only et bornées : `get_component`, `get_dependencies`, `get_dependents`, `find_workflow`, `get_hotspots`, `get_path`, `where_to_start`, et `get_insights` (Feature 12d), chacune avec `repo_path` et `run_id` optionnel (défaut : dernier run contenant le type de fact interrogé, Feature 12d).

**142. Le MCP expose-t-il les facts bruts ?**
Décidé — oui, en lecture filtrée/paginée (pas de dump), pour permettre à un agent de vérifier une evidence précise. **Statut (2026-09-17) : non implémenté** — aucune primitive générique ne renvoie des facts filtrés par type ; seuls les facts d'un fichier (`get_component`), les insights repository (`get_insights`, Feature 12d) et les résultats des primitives dédiées sont exposés.

**143. Le MCP expose-t-il les insights ?**
Décidé — oui, avec leur `provenance`/confiance intacte : un agent consommateur doit pouvoir distinguer fact et hypothesis exactement comme le rapport HTML (Q136). **Statut (2026-09-17) : implémenté** — onboarding (`where_to_start`), workflows (`find_workflow`) et, depuis la Feature 12d, `architecture_hypothesis`, `business_concept` et `glossary_term` (`get_insights(kind=architecture|concepts|glossary)`) sont exposés avec provenance et confiance intactes.

**144. Le MCP expose-t-il les evidence ?**
Décidé — oui, c'est nécessaire pour que le principe evidence-first soit utilisable par un agent, pas seulement par un humain lisant le rapport.

**145. Peut-on interroger un composant ?**
Décidé — oui, primitive de base (lookup par nom/chemin).

**146. Peut-on demander ses dépendances ?**
Décidé — oui, primitive de base sur le graph (Q63).

**147. Peut-on demander ses dépendants ?**
Décidé — oui, symétrique de Q146.

**148. Peut-on chercher un workflow ?**
Décidé — oui, s'appuie sur les insights de domain understanding (section H).

**149. Peut-on demander les hotspots ?**
Décidé — oui, avec leur décomposition (Q73).

**150. Peut-on demander un chemin entre deux composants ?**
Décidé — oui, primitive de graph (plus court chemin) bornée pour éviter une explosion combinatoire (cf. Q152).

**151. Peut-on demander "où commencer pour comprendre X" ?**
Décidé — oui, réutilise directement l'onboarding path (section 16 Capability Matrix) scopé à un composant donné plutôt qu'à tout le système.

**152. Comment éviter que le MCP retourne trop de données ?**
Décidé. Toute primitive MCP est paginée/bornée par défaut (limite de résultats, profondeur de graph maximale), jamais un accès illimité — cohérent avec le non-goal "agent qui explore aveuglément".

**153. Quels outils MCP sont read-only ?**
Décidé — tous, au MVP. Aucune primitive MCP ne doit modifier le code, la configuration ou déclencher une action ayant un effet de bord, à l'exception explicite de Q154.

**154. Le MCP doit-il déclencher une nouvelle analyse à la demande ?**
Décidé (résolu 2026-09-17). Non. Le MCP reste strictement read-only (Q153). L'analyse est déclenchée par l'agent via le CLI, visiblement et sous permission, avec les règles anti-re-analyse de Q154c/Q154d. Un outil « de lecture » capable de lancer des minutes de LLM serait un coût caché ; une commande shell rend ce coût explicite.

**154b. Existe-t-il un chemin de synthèse finale par un agent (Claude Code ou autre), au-dessus du MCP ?**
Décidé (résolu 2026-09-14, précisé le même jour à deux reprises : (1) sortie **HTML**, pas `.docx` — le `.docx` mentionné initialement était une private joke sur le nommage de fichier façon "vraiment-final-v2-FINAL.docx", pas une exigence de format ; (2) l'agent ne doit pas se contenter de relayer/reformater les facts MCP, il doit produire **sa propre interprétation**, clairement distinguée du relais factuel — sinon cette feature ne fait qu'un rapport HTML moins bon que la Feature 11/11b). Oui — un **second** chemin de consommation, complémentaire du rapport HTML autonome (Q137/Q138/Q140b), pas un remplacement : un agent MCP-compatible (Claude Code, ou tout autre) se connecte au serveur MCP déjà livré (Feature 12, read-only, Q141-153) pour interroger facts/insights/evidence, puis produit **lui-même** une synthèse en **HTML autonome**, lisible directement dans un navigateur, sans build ni serveur, reprenant les mêmes conventions visuelles (badges provenance/confiance, liens vers l'evidence) que le rapport principal (Feature 11/11b) pour le matériel relayé, et **ajoutant une couche d'interprétation propre à l'agent**, clairement séparée (pas de badge de provenance Atlas dessus, ce n'est pas un fact) — l'agent doit prendre position (ce qui est vraiment risqué, par où commencer), pas seulement reformuler ce que le MCP a renvoyé — cette synthèse est le travail de l'agent au moment de la session, pas un artefact qu'Atlas génère ou stocke. Ce qu'Atlas fournit en plus du serveur MCP existant : une **recette documentée** (une définition d'agent/prompt réutilisable, ex. un subagent Claude Code) qui encode comment interroger le MCP et comment structurer/rendre la synthèse — pas une nouvelle primitive MCP, pas de dépendance Python partagée avec le rendu du rapport principal (l'agent ne parle qu'au MCP, il n'importe pas le code Atlas). Répond au besoin exprimé : le rapport HTML (Feature 11/11b) doit rester lisible en standalone (sinon il impose de toute façon de passer par un agent) ; ce chemin agent est pour qui veut une synthèse ciblée/personnalisée en plus, toujours en HTML exploitable, jamais un format binaire. Implémenté par la nouvelle **Feature 14**.

**154c. L'agent doit-il exiger qu'un `atlas analyze` ait déjà tourné, ou peut-il le lancer lui-même ?**
Décidé (résolu 2026-09-14, suite à un retour direct : *"je veux pas me farcir le analyze à la main, l'agent doit pouvoir le faire tout seul"*). L'agent (Feature 14) lance lui-même `atlas analyze <repo>` s'il ne trouve pas de facts store existant pour ce repository, avant de démarrer `mcp-serve` et d'interroger le MCP — plus d'étape manuelle. Ce n'est **pas** la primitive MCP envisagée par Q154 (tranchée depuis : non, le MCP reste read-only) : l'agent invoque `atlas analyze` comme un simple appel CLI/subprocess, en dehors du MCP — Feature 12 reste inchangée, read-only, sans nouvel outil "déclenche une analyse". Pas de re-analyse silencieuse si un facts store existe déjà (coût LLM caché à éviter, même logique que Q154) — seulement au premier run ou sur demande explicite. L'agent doit aussi toujours calculer et passer explicitement le même chemin de base de facts aux deux commandes (`analyze` puis `mcp-serve`) plutôt que de compter sur leurs défauts CLI respectifs, qui divergent aujourd'hui (`.atlas-cache/facts.sqlite` pour `analyze`, `.atlas/facts.sqlite` pour le défaut de `mcp-serve`) — bug réel signalé mais pas corrigé ici, contourné côté recette agent (disparu depuis : la Feature 12b a supprimé le chemin par défaut de `mcp-serve`, qui dérive le store de `repo_path` à chaque appel). Implémenté par la nouvelle **Feature 14b**, additive sur la Feature 14 déjà livrée.

**154d. Si le store existant n'a jamais eu de run LLM réel (que du `--no-llm`), l'agent doit-il quand même le réutiliser tel quel ?**
Décidé (résolu 2026-09-15, suite à un cas réel : une synthèse produite sur simple "run with it" a rapporté architecture/domain/onboarding vides "(--no-llm run)" alors qu'Ollama tournait et répondait pendant toute l'exécution — le store réutilisé n'avait en fait jamais eu de run avec LLM activé, uniquement des runs `--no-llm` issus de dogfooding antérieur). Non — avant de sauter l'analyse au motif qu'un store existe déjà (Q154c), l'agent interroge les facts `stage_run_result` (Feature 06c) des stages LLM (architecture/domain/onboarding), tous runs confondus : si **aucun** n'a jamais été tenté avec un vrai provider (tous les `detail` valent `"not_analyzed: llm_disabled"`, ou aucun fact du tout), l'agent relance `analyze` une fois avec un vrai provider plutôt que de faire confiance à un store qui n'a jamais eu sa chance — ce n'est pas la re-analyse silencieuse et coûteuse que Q154c cherche à éviter, c'est l'analyse qui n'a en réalité jamais eu lieu. En complément, suite à un retour direct (*"ça serait assez chanmé si l'agent détecte Ollama"*) : l'agent résout lui-même un modèle Ollama (`ollama list`, même règle "premier modèle listé" que le prompt interactif déjà existant du CLI, `_pick_ollama_model`) plutôt que de dépendre de `$OLLAMA_MODEL` hérité de son propre environnement — le CLI échoue bruyamment (`click.ClickException`) en mode non-interactif si aucun modèle n'est configuré, donc l'agent doit le résoudre en amont plutôt que de heurter cet échec ou de dégrader silencieusement. Si Ollama n'est pas joignable, l'agent continue en `--no-llm` mais le dit explicitement en tête de sa synthèse, pas noyé dans une note de section. Implémenté par la nouvelle **Feature 14c**, additive sur la Feature 14/14b déjà livrée.

**154e. `DisabledProvider` et un vrai échec LLM produisent-ils le même texte, empêchant Q154d/Q170 de les distinguer ?**
Décidé (résolu 2026-09-15, bug réel trouvé en vérifiant 14c en conditions réelles : un run `--no-llm` et un run avec un vrai provider qui échoue sur la validation de citation produisaient tous deux exactement `detail="not_analyzed: llm_failed"` — indiscernables). `LLMCallResult.reason` gagne une troisième valeur `"llm_disabled"` (en plus de `"llm_failed"`/`"budget_exceeded"` déjà livrées par la Feature 07) ; `DisabledProvider.complete()` la retourne au lieu de réutiliser `"llm_failed"`. Corrige au passage le seul consommateur dont la logique reposait sur une chaîne (`"llm_provider not configured"`) qu'aucun chemin réel du CLI ne produit jamais (`_gap_message` de la Feature 11c vérifiait une branche `ctx.llm_provider is None` obsolète, jamais atteinte puisque `--no-llm` construit un vrai objet `DisabledProvider`, jamais `None`). Implémenté par la nouvelle **Feature 07c**, additive sur la Feature 07 déjà livrée ; doit être livrée avec la Feature 14c pour que sa détection fonctionne réellement.

**154f. `get_hotspots` trie-t-il vraiment par score, et les requêtes MCP sont-elles bornées à un run ?**
Décidé (résolu 2026-09-15). Non aux deux, bugs réels trouvés via l'usage réel de l'agent `atlas-synthesis` (son propre "tool caveat" signalant un tri visiblement faux) puis en lisant `queries.py` en entier : (1) `get_hotspots` trie sur `combined_score`, une clé qui n'existe pas dans le fact `hotspot_score` (la vraie clé est `combined`, même famille de bug que Q140d déjà corrigée côté rapport HTML) — tri toujours à `0.0`, donc ordre d'insertion, pas par score. (2) Aucune fonction de requête du MCP ne filtre par `run_id` — sur un repo avec plusieurs runs `analyze` accumulés (9 ici), les résultats mélangent tout l'historique, et pour les facts recréés à l'identique à chaque run (imports/calls/symboles), ça retourne des quasi-doublons qui vident de son sens la limite `top_n`/`limit` déjà exigée bornée par Q152. Fix : clé de tri corrigée, plus un paramètre `run_id` optionnel sur chaque fonction de requête (défaut : run le plus récent via une nouvelle méthode `FactStore.latest_run_id()`, additive sur la Feature 01), avec possibilité de cibler un run précis explicitement. Implémenté par la nouvelle **Feature 12c**, additive sur la Feature 12/12b déjà livrée.

**154g. Quand les stages LLM d'Atlas (architecture/domain) sont pauvres, la section "My read" de l'agent `atlas-synthesis` doit-elle décrire cette pauvreté, ou la combler ?**
Décidé (résolu 2026-09-17, suite à un retour direct sur une synthèse réelle jugée "à côté du point" — la section "My read" écrivait : *"The architecture stage produced ten 'uncatalogued' tags and no synthesized pattern — it's not wrong, it's just empty of content... I would not use either stage as a substitute for reading applications/services.py and festivals/services/core.py directly; use them only as a hint..."* — puis s'arrêtait là). La combler, pas la décrire. L'instruction actuelle de l'agent (§"My read", *"If there are `not_analyzed` gaps, say what it would want to know but cannot"*) confond deux situations que l'agent doit distinguer explicitement :
- un gap **réellement inconnaissable** dans cette session (pas d'analyzer pour cette catégorie — Runtime/Infrastructure/CI-CD/etc., cf. Q140c/Q180b) → dire ce qu'on ne peut pas savoir reste correct ;
- un gap qui est une **limite d'Atlas**, pas une limite de l'agent — l'agent est un coding agent avec accès direct au filesystem du `repo_path` interrogé ; quand l'architecture/domain d'Atlas ressort vide ou "uncatalogued" mais que les fichiers hotspot/centraux concernés sont lisibles, l'agent doit **les lire lui-même** et produire une vraie interprétation (pattern architectural observé, concepts métier, workflow) ancrée dans cette lecture, pas un constat sur ce qu'Atlas n'a pas trouvé suivi d'un renvoi vers "va lire le fichier toi-même" — c'est précisément le travail que Q154b (*"l'agent doit prendre position... pas seulement reformuler ce que le MCP a renvoyé"*) lui confie déjà, et que cette instruction mal formulée sabote pour le cas le plus fréquent (LLM local faible → stages 08/09 pauvres, cf. Q83).
Complément trouvé dans le même retour, côté relais "Atlas findings" (pas "My read") : `avoid_initially` relaie aujourd'hui la liste nue des `component` sans jamais son `rationale`, pourtant déjà présent dans le fact (`onboarding_path`) et déjà accessible via `_fact_to_dict` (aucune perte côté MCP) — l'agent doit toujours relayer le `rationale` disponible, jamais seulement le nom du composant. Implémenté par la nouvelle **Feature 14d**, additive sur la Feature 14/14b/14c déjà livrée ; s'appuie sur **Feature 10c** (Q205c) côté qualité du texte source relayé.

---

# N. Performance

**155. Quelle taille de repository doit être supportée ?**
Décidé (résolu 2026-09-17). Cible de conception du MVP : un repository, ou un sous-dossier de monorepo, de l'ordre de quelques milliers de fichiers source (≈ 5 000) sur un poste développeur — l'ordre de grandeur des projets dogfoodés. Au-delà : analyser un sous-dossier (Q158). C'est un ordre de grandeur et non une limite dure parce qu'aucune mesure systématique n'existe encore ; la durée par stage doit être enregistrée pour l'affiner (`docs/improvement-ideas.md` §6). Conséquences assumées : SQLite et calculs en mémoire suffisent (Q49, Q58, Q161).

**156. Quel temps d'analyse cible ?**
Décidé (résolu 2026-09-17). Cible : la partie déterministe (discovery, git, code_graph, hotspots) en moins de 5 minutes sur la taille de Q155. Les passes LLM ne sont pas bornées en durée totale (elles dépendent du matériel pour un modèle local) mais par appel (timeout 600 s Ollama, 120 s Claude Code), mises en cache (Q102) et relançables isolément (`--only`). Objectif à confirmer par mesure.

**157. Quels analyzers peuvent tourner en parallèle ?**
Décidé — tous les adapters indépendants entre eux (pas de dépendance de données) tournent en parallèle par défaut ; seules les étapes de calcul/LLM qui consomment la sortie d'un adapter attendent explicitement sa complétion. **Statut (2026-09-17) : non implémenté** — stages et adapters s'exécutent séquentiellement ; `adapters/runner.py::run_adapters` (pool de threads) existe mais n'est utilisé par aucun stage.

**158. Comment gère-t-on les gros monorepos ?**
Décidé (résolu 2026-09-17). Passer le sous-projet en `PATH` (implémenté, Q114), avec `[scope]` en complément (appliqué aujourd'hui par `discovery` seulement) ; pas de graph DB sans goulot mesuré.

**159. Comment cache-t-on les résultats ?**
Décidé — même mécanisme que Q102 pour le LLM, étendu aux résultats d'adapters déterministes coûteux : cache clé par (hash des fichiers d'entrée + version d'adapter). **Statut (2026-09-17) : non implémenté pour les adapters** — seul le cache LLM (Q102) existe ; chaque run relance les outils.

**160. Peut-on analyser uniquement les changements depuis une analyse précédente ?**
Décidé (résolu 2026-09-17). P1, non implémenté. Méthode retenue : diff par commit hash depuis le dernier run, réutilisation du cache (Q159) pour les fichiers inchangés.

**161. Comment gère-t-on les limites mémoire ?**
Décidé (résolu 2026-09-17). Pas de streaming au MVP : chaque adapter charge sa sortie en mémoire, ce qui tient pour la taille cible (Q155). Rouvert sur mesure.

**162. Quels résultats doivent être disponibles rapidement avant le reste ?**
Décidé (résolu 2026-09-17). Pas de publication anticipée de résultats partiels : le rapport est généré en fin de pipeline. En revanche chaque stage persiste ses facts dès qu'il se termine et l'affichage live montre sa fin ; un rapport déterministe rapide s'obtient avec `--no-llm`.

---

# O. Security / privacy

**163. L'analyse doit-elle être locale par défaut ?**
Décidé — oui, cohérent avec Q10/Q95/Q123 : aucune donnée ne quitte l'environnement local sauf action explicite (appel LLM ou connector externe configuré).

**164. Quelles données peuvent sortir de l'environnement ?**
Décidé — uniquement le contenu explicitement sélectionné pour les passes LLM (Q85/Q87/Q93/Q125), jamais un export brut du repository.

**165. Comment détecte-t-on les secrets avant appel LLM ?**
Décidé (résolu 2026-09-17). Un scanner de secrets déterministe existant (patterns connus + entropie, type detect-secrets/gitleaks) sur tout contenu sélectionné, avant tout appel LLM ; un fichier avec correspondance est **exclu** du prompt avec une trace (log `WARNING` + mention dans le `stage_run_result`), jamais masqué silencieusement. **Statut : non implémenté** — priorité P0 avant de recommander un provider distant sur du code client.

**166. Comment anonymise-t-on certaines informations ?**
Décidé (résolu 2026-09-17). P2 : pseudonymisation optionnelle des contributeurs. Aujourd'hui Atlas ne collecte aucun nom de contributeur (le churn compte des commits et des lignes), le risque est nul au MVP.

**167. Comment gère-t-on les repositories clients confidentiels ?**
Décidé (principe) — cf. Q163/Q164 : le mode local-only + désactivation LLM (Q95) doit permettre une analyse complète d'un repository confidentiel sans qu'aucune donnée ne sorte, seule dégradation étant l'absence de synthèse LLM.

**168. Peut-on utiliser un LLM local ?**
Décidé (résolu 2026-09-14). Oui — **Ollama** (`http://localhost:11434` par défaut) avec un modèle **Qwen** installé par l'utilisateur. Le nom exact du modèle est une valeur de configuration runtime, jamais codée en dur (ce qui est installé est un fait sur la machine de l'utilisateur, pas une constante de spec). Implémenté par la **Feature 07b** (`specs/features/07b-ollama-provider.md`), en tant que nouvelle implémentation de l'interface `LLMProvider` déjà livrée par la Feature 07 — additive, sans modifier le contrat ni le défaut déjà shippé de Feature 07 (cf. Q94). Résout Q167 : une fois configuré, la synthèse LLM peut rester entièrement locale, pas seulement désactivée.

**169. Peut-on désactiver certaines catégories d'analyse ?**
Décidé — oui, chaque catégorie d'analyzer (section B-K) doit être activable/désactivable en configuration indépendamment des autres. **Statut (2026-09-17) : partiel** — sélection par stage en CLI (`--only <stage>`, répétable), pas encore par fichier de configuration.

**170. Comment journalise-t-on les appels externes ?**
Décidé (résolu 2026-09-14, étendu le même jour suite à la demande explicite que ça couvre toute l'application, pas seulement le LLM — suite au dogfooding réel de l'outil : `atlas analyze` sur son propre repository et sur un projet plus large a révélé des échecs LLM sans information exploitable). Logging structuré **across the app** : chaque feature qui fait un appel externe/LLM porte son propre logger (`logging.getLogger(__name__)`) et journalise selon la même convention à trois niveaux — voir [`specs/features/README.md`](features/README.md#logging-a-convention-every-feature-follows) pour le détail, applicable rétroactivement aux Features 02, 07, 07b, 08 déjà livrées (addition interne, sans changement d'interface). Niveau par défaut `WARNING` — un échec d'appel externe (adapter ou LLM) est toujours journalisé à ce niveau avec au minimum : composant, cible (nom d'adapter ou `provider_id`/modèle), et le détail de l'erreur sous-jacente (type d'exception, message, ou statut HTTP) — jamais juste `not_analyzed: llm_failed` sans plus de contexte. Pas de contenu brut potentiellement sensible dans les logs (cohérent avec l'exigence de transparence evidence-first appliquée à l'outil lui-même). La **Feature 13** ne fait que configurer (niveau, handler) et afficher ce que chaque composant journalise déjà — elle n'ajoute pas les logs elle-même ; résout aussi Q179 pour le détail niveau DEBUG.

---

# P. UX / CLI

**171. Quelle commande lance l'analyse ?**
Décidé — `project-intel analyze <scope>`, tel que défini dans le Product Brief section 7. **Précision (2026-09-17)** : le nom retenu à l'implémentation est `atlas` — `atlas analyze <path>` (le package Python reste `project-intel`).

**172. Quelle configuration est nécessaire ?**
Décidé (résolu 2026-09-17, implémenté par la Feature 13). `.atlas.toml` optionnel, auto-détecté dans `PATH` ou passé par `--config` : `[[repositories]]`, `[scope]`, `[llm]` (`provider`, `model`, `budget_tokens`), `[hotspot_weights]`. Tout a un défaut, `atlas analyze <path>` suffit. Précédence : fichier < variables d'environnement < flags. Pas d'activation d'analyzers par fichier : la sélection se fait par `--only` (Q169).

**173. Faut-il une configuration explicite ou une auto-discovery maximale ?**
Décidé — les deux, en couches : auto-discovery maximale par défaut (Q11-20) pour la détection technique, configuration explicite obligatoire uniquement pour ce qui ne peut pas être déduit de façon fiable (scope multi-repository/système, credentials, budget) — cohérent avec Q9.

**174. Comment affiche-t-on la progression ?**
Décidé (résolu 2026-09-14, étendu le même jour : la CLI entière doit être interactive, avec un timer et un spinner par étape en cours). Sortie CLI progressive par étape du pipeline (Q7 de l'architecture conceptuelle : discovery → analyzers → normalisation → calculs → LLM → rapport), avec statut par analyzer individuel (running/done/failed/skipped) affiché au fur et à mesure — pas seulement dans le résumé final. Sur un terminal interactif (TTY) : affichage **live** via `rich` (nouvelle dépendance, justifiée — spinner et redessin en place ne sont pas raisonnables avec `click`/stdlib seuls) — chaque stage de `STAGE_REGISTRY` apparaît dès son lancement avec un spinner animé et un timer d'écoulement qui s'incrémente pendant son exécution, puis se fige avec un statut (✓/✗/⊘), la durée finale et le nombre de facts produits. Hors TTY (CI, sortie redirigée) ou en `-v`/`--debug` (le flux de logs rendrait un affichage live illisible) : repli sur l'affichage simple ligne-par-ligne de la Feature 06b, sans redessin ANSI. Niveau de détail par défaut : une ligne par stage. `-v`/`--verbose` ajoute une ligne par appel externe individuel (adapter invoqué, appel LLM émis/servi depuis le cache/échoué). Implémenté par la **Feature 13**, même mécanisme de logging que Q170/Q179.

**175. Peut-on relancer uniquement un analyzer ?**
Décidé — oui, nécessaire pour l'itération/debug (cf. Q32/Q179) et cohérent avec la persistance des facts (Q47/Q48).

**176. Peut-on lancer uniquement Git analysis ?**
Décidé — oui, cas particulier de Q175 (sélection par catégorie d'analyzer, cf. Q169).

**177. Peut-on lancer uniquement le LLM synthesis ?**
Décidé — oui, cas particulier de Q175/Q47 : rejouer la synthèse sur des facts déjà persistés sans re-scanner.

**178. Comment inspecte-t-on les facts ?**
Décidé (résolu 2026-09-17, implémenté). `atlas facts query <path> [--type] [--run-id] [--provenance] [--json]`.

**179. Comment debugge-t-on un adapter ?**
Décidé (résolu 2026-09-14). Verbosité graduée plutôt qu'un simple flag binaire : `-v`/`--verbose` (niveau `INFO`, cf. Q174) puis `-vv`/`--debug`/`--log-level=DEBUG` (niveau `DEBUG`) — ce dernier affiche la commande exacte invoquée par adapter, sa sortie brute avant normalisation, et le résultat de la normalisation, nécessaire pour diagnostiquer un échec (Q30) ou une sortie inattendue. Un appel LLM échoué (Q170) est journalisé avec le même niveau de détail (provider, modèle, erreur sous-jacente) dès `WARNING`, sans attendre `--debug`, puisque c'est justement l'information manquante identifiée lors du dogfooding réel de l'outil. Implémenté par la **Feature 13**.

**180. Comment affiche-t-on les erreurs sans interrompre toute l'analyse ?**
Décidé — cohérent avec Q30/Q107 : les erreurs sont collectées et affichées en fin d'exécution (résumé des analyzers `failed`/`skipped`) plutôt que d'interrompre le run global.

**180b. Le résultat de chaque stage (`StageRunResult`) doit-il être persisté au-delà de l'affichage terminal ?**
Décidé (résolu 2026-09-15, suite à un diagnostic concret : le rapport HTML affichait "Not analyzed" pour Architecture/Domain sur un run où le stage avait en réalité échoué avec une raison précise — `not_analyzed: llm_failed` — raison calculée mais jamais conservée au-delà du print terminal de la Feature 13). Oui — chaque `StageRunResult` déjà produit par le runner (Feature 06b/13) est aussi écrit dans le `FactStore` comme fact `stage_run_result` (`stage`, `status`, `facts_produced`, `detail`), en plus de son affichage terminal existant (Q180 inchangé). Aucun nouveau mécanisme de stockage : réutilise `Fact`/`FactStore` tels quels. Permet à tout consommateur ultérieur (rapport HTML, MCP, etc.) de savoir *pourquoi* une section est vide sans avoir à relancer une analyse. Implémenté par la nouvelle **Feature 06c**, additive sur la Feature 06b/13 déjà livrée.

**181. La CLI doit-elle être interactive quand une configuration requise manque (ex. modèle Ollama non précisé) ?**
Décidé (résolu 2026-09-14). Oui, mais seulement quand c'est possible sans surprendre un usage scripté : si l'entrée standard est un terminal interactif (TTY) et qu'une valeur requise manque (ex. `--llm-provider ollama` sans `--ollama-model`), la CLI propose un prompt (`click.prompt`/`click.confirm`) plutôt qu'un échec sec — par exemple lister les modèles Ollama disponibles localement (`ollama list`) et laisser choisir. Si l'entrée standard n'est pas un TTY (CI, script, pipe), aucun prompt : échec immédiat avec le message actionnable déjà spécifié par la Feature 07b. Implémenté par la **Feature 13**, en s'appuyant sur les primitives d'interactivité déjà fournies par `click` (dépendance déjà utilisée par la CLI, aucune nouvelle dépendance).

---

# Q. Extensibility

**181. Comment ajouter un nouvel analyzer ?**
Décidé — via le contrat d'adapter (Q24/Q33) : un manifest déclaratif + la commande d'invocation, sans modification du cœur du système.

**182. Comment ajouter un nouveau langage ?**
Décidé (résolu 2026-09-17). Ajouter les signatures de frameworks/build dans `discovery/data/signatures.toml`, puis vérifier que tokei, graphify et lizard couvrent le langage ; sinon, un nouvel adapter ou `GraphProvider`. Aucun changement du modèle de facts.

**183. Comment ajouter un nouveau provider de graph ?**
Décidé — implémentation de l'interface `GraphProvider` (Q53/Q55), sans changement du modèle de Facts.

**184. Comment ajouter un nouvel outil externe ?**
Décidé — cas général de Q181.

**185. Comment ajouter une nouvelle source externe ?**
Décidé — implémentation d'un `Connector` respectant le même contrat de sortie que les adapters (Q120/Q33).

**186. Comment ajouter une nouvelle métrique ?**
Décidé (résolu 2026-09-17, implémenté par convention). Une métrique = une fonction déterministe produisant des facts `computed` d'un nouveau `type`, avec sa dataclass de valeur dans `facts/value_schemas.py` (Q50b), appelée depuis un stage. Pas de registre `Calculations` distinct : le registre de stages suffit.

**187. Comment ajouter une nouvelle vue HTML ?**
Décidé (résolu 2026-09-17, implémenté par convention). Une section = une fonction `_render_<section>(store, run_id)` dans `html_report/renderer.py` qui ne lit que des facts, avec repli inter-runs et état de gap explicite (Q140c).

**188. Comment ajouter une nouvelle primitive MCP ?**
Décidé (résolu 2026-09-17, implémenté par convention). Une fonction bornée avec `run_id` optionnel dans `mcp_server/queries.py` + son enregistrement `@mcp.tool` dans `mcp_server/server.py`.

**189. Le système doit-il avoir un plugin mechanism ?**
Décidé (résolu 2026-09-17). Pas de mécanisme de plugin. Les extensions se font in-tree via les contrats existants : `AdapterManifest`, `GraphProvider`, `LLMProvider`, `Stage` + `STAGE_REGISTRY` (liste explicite). Raisons : aucun contributeur externe aujourd'hui, et un chargement dynamique figerait des interfaces qui évoluent encore à chaque feature lettrée.

**190. Quelle API stable doit être fournie aux plugins ?**
Décidé (résolu 2026-09-17). Aucune API de plugin n'est garantie. Les interfaces ci-dessus sont stables au sens du regeneration contract des specs (`specs/features/README.md`), pas au sens d'une API publique versionnée. Rouvert uniquement si un plugin externe réel est demandé.

---

# R. MVP

**191. Quelles capacités sont absolument nécessaires au premier release ?**
Décidé (résolu 2026-09-17). Le MVP livré : discovery, analyse Git, code graph, hotspots explicables, trois passes LLM (architecture, domaine, onboarding), rapport HTML autonome, CLI, serveur MCP, agent de synthèse. Écarts assumés par rapport aux lignes P0 de la Capability Matrix : infrastructure, CI/CD, runtime, data, observabilité et tests ne sont que **détectés**, pas analysés.

**192. Quels outils existants devons-nous intégrer en premier ?**
Décidé — tokei (langage/LOC), Git (historique), graphify (code graph). Dans cet ordre de priorité pour le MVP.

**193. Quels langages devons-nous supporter ?**
Décidé, révisé 2026-09-22 : le principe n'est plus une liste figée choisie par Atlas, mais **le périmètre réel des outils wrappés** (Product Brief principe 1 : outils existants d'abord). Concrètement :
- `code_graph/graphify_provider.py` n'applique **aucun filtre d'extension** — il fait confiance à la classification `file_type=="code"` de graphify lui-même, qui couvre déjà toute sa table de dispatch (Python, TS/JS, Go, Java/Kotlin, Ruby, Rust, PHP, **Vue**, Svelte, Astro, C/C++/C#, Swift, Scala, Lua, Zig, JSON, Terraform/HCL, SQL, Fortran, Pascal, …) et exclut correctement le Markdown (que graphify traite lui-même comme documentation, pas comme code).
- `hotspots/complexity_adapter.py` utilise la couverture réelle des *Reader* embarqués dans lizard (`LIZARD_EXTENSIONS` dans `adapters/language_scope.py`, lue directement sur l'attribut `ext` de chaque Reader) — PHP et **Vue** y sont nativement supportés.

**Pourquoi ce changement** : la liste précédente (Python/TS-JS/Go/Java-Kotlin/Ruby/Rust) était un choix manuel qui a immédiatement dérivé du réel — graphify avait déjà un extracteur PHP et Vue complets, lizard aussi, et rien ne les excluait sauf cette liste elle-même. Une liste maintenue à la main est le bug, pas la solution : elle se désynchronise dès que l'outil wrappé progresse. `adapters/language_scope.py` documente cette règle et n'est plus le point où on choisit un sous-ensemble, seulement où `LIZARD_EXTENSIONS` (dérivé de lizard) et `MVP_LANGUAGES` (vue tokei, utilisée uniquement pour la note de couverture ci-dessous) vivent.

Un bug annexe corrigé au passage : le scope MVP était par erreur aussi appliqué à la détection de langage (tokei) dans `discovery/tokei_adapter.py`, qui ne doit jamais être limitée à un périmètre d'extraction — la détection doit voir tout le dépôt. Un fait `code_graph_coverage` (`code_graph/metrics.py`, provenance `computed`) compare le LOC total par langage (tokei, non filtré) à `MVP_LANGUAGES` et signale explicitement, dans la section Code Map du rapport HTML, tout langage réellement hors de la couverture graphify/lizard avec un LOC significatif — pour qu'un langage non couvert soit visible plutôt que redécouvert à la main.

**194. Quelle taille de projet doit être supportée ?**
Décidé (résolu 2026-09-17). Même cible que Q155.

**195. Le MVP doit-il supporter plusieurs repositories ?**
Décidé — oui (cf. Q3), même si l'orchestration multi-repository peut rester simple (parallélisation basique, pas d'optimisation avancée) au tout premier release.

**196. Le MVP doit-il supporter l'IaC externe ?**
Décidé (résolu 2026-09-17). Non : détection par signatures seulement (Q17/Q18). Le type `ExternalSource` existe pour représenter un repository IaC non analysé sans refonte du modèle.

**197. Le MVP doit-il inclure le MCP ?**
Décidé (résolu 2026-09-17, implémenté). Oui (Features 12/12b/12c/12d) : huit primitives read-only (Q141), serveur global enregistré une fois pour tous les repositories.

**198. Le MVP doit-il inclure le LLM ?**
Décidé — oui pour les zones P0 marquées LLM-only dans la Capability Matrix (architecture interpretation, domain understanding, onboarding path), mais le pipeline doit rester fonctionnel LLM désactivé (Q95).

**199. Quel niveau de rapport HTML est nécessaire ?**
Décidé (résolu 2026-09-17). Les sections P0 sont implémentées : executive summary, system map, architecture, code map, hotspots, domain understanding, Git evolution, risks, onboarding path, glossary, evidence. Les sections P1 (runtime, infrastructure, CI/CD, data, observabilité, tests) ne sont **pas** affichées vides : elles arriveront avec leur analyzer. Cela s'écarte de la proposition initiale parce qu'une série de sections vides nuisait à la lisibilité (cf. retours Q140b/Q140f) ; leur absence est documentée comme limite connue (README, *Status*).

**200. Quel résultat démontrerait que le MVP est réellement utile à un senior engineer ?**
Décidé (résolu 2026-09-17). Le MVP est jugé utile si, sur un repository qu'il ne connaît pas, un senior engineer : (1) obtient via *Onboarding path* ou `where_to_start` au moins 3 points d'entrée qu'un connaisseur du projet valide comme pertinents ; (2) reconnaît au moins la moitié du top-10 hotspots comme zones réellement délicates ; (3) ne relève aucune affirmation fausse présentée autrement qu'en `hypothesis` ; (4) déclare avoir gagné du temps sur sa première journée. Mesuré avec le protocole Q206 sur le corpus Q207, et lors des premiers usages par des collègues.

---

# S. Validation

**201. Comment mesurer la qualité du rapport ?**
Décidé (résolu 2026-09-17). Trois mesures : couverture des sections P0 (contenu ou gap explicite, jamais une section silencieusement vide), taux de réponses LLM rejetées par la validation de citations (Q205), évaluation humaine selon Q206.

**202. Comment mesurer la précision des facts ?**
Décidé (résolu 2026-09-17). Échantillon manuel de 20 facts `observed`/`computed` par stage, vérifiés contre le code source, à chaque changement notable d'un adapter ; taux d'erreur suivi par stage.

**203. Comment mesurer la pertinence des hotspots ?**
Décidé (résolu 2026-09-17). Précision du top-10 hotspots contre la liste « fichiers à surveiller » d'un engineer de référence (Q206), sans lui montrer le rapport avant.

**204. Comment mesurer la qualité de l'onboarding path ?**
Décidé (résolu 2026-09-17). Même méthode que Q203 : part des points d'entrée proposés que l'engineer de référence valide, et points d'entrée essentiels qu'il cite et qui manquent.

**205. Comment mesurer les hallucinations ?**
Décidé (mécanisme, cf. Q104) — taux de citations invalides détectées par le validateur structurel comme métrique directe et automatisable, avant même l'évaluation humaine.

**205b. Le validateur de citations (Q104/Q205) attrape-t-il une affirmation spécifique sans aucune citation ?**
Décidé (résolu 2026-09-15, bug réel trouvé en lisant une synthèse produite par l'agent `atlas-synthesis` : `where_to_start()` affirmait "le système n'est pas configuré pour gérer les équipes" — faux, des modèles `FestivalTeam`/`FestivalCoAdmin` bien réels existent, et un fact `business_workflow` "Festival Team Management" présent dans la même réponse le contredisait déjà). Non — `validate_citations` (Feature 07) vérifie uniquement que les `fact_ids` cités *existent*, jamais que le texte libre à côté (`rationale`) est réellement soutenu par ce qui est cité ; pire, une réponse sans aucun `fact_ids` nulle part passe trivialement (`if not cited: return True, []`). Cause racine additionnelle trouvée dans `onboarding/analyzer.py` : `symbol_defined` n'est pas fourni au prompt de synthèse d'onboarding, donc le modèle n'a aucune visibilité sur les classes/modèles réels du code analysé et invente pour combler ce vide. Pas de changement du validateur partagé de la Feature 07 (une règle globale "toujours citer" rejetterait à tort des champs comme `open_questions`, conçus pour nommer ce qui n'est *pas* su) — fix scopé à la Feature 10 : `symbol_defined` ajouté aux facts d'entrée, prompt renforcé contre les affirmations d'absence non prouvées, et un filtre post-réponse dans `onboarding/stage.py` qui retire (sans rejeter toute la réponse) tout `EntryPoint`/`AvoidItem` dont `fact_ids` est vide avant stockage. Implémenté par la nouvelle **Feature 10b**, additive sur la Feature 10 déjà livrée.

**205c. `avoid_initially` et `open_questions` (Feature 10) donnent-ils assez de contexte pour agir, une fois relayés dans une synthèse réelle ?**
Décidé (résolu 2026-09-17, suite à un retour direct sur une synthèse réelle — *"je ne sais pas quoi faire de cette information, elle n'est pas assez précise"* — à propos de : *"Avoid initially (per Atlas): test_undo_an_edit_restores_the_previous_values(), test_set_ops_window_end_before_start_rejected(). Open questions Atlas flagged: how shifts are validated before saving; the relationship between ShiftIn and the DB model."*). Non — deux causes distinctes trouvées en lisant `onboarding/analyzer.py` et `onboarding/schema.py` :
- `AvoidItem` a déjà un champ `rationale` (rempli par le modèle et stocké dans le fact), mais `_INSTRUCTIONS` ne demande au modèle qu'une catégorie ("high-complexity or low-centrality and irrelevant to a first pass"), jamais une explication concrète propre à l'item — le `rationale` produit reste donc souvent un simple recopiage de la catégorie, pas une raison actionnable.
- `open_questions` est un `list[str]` sans structure : l'instruction ("explicit unresolved items — things you cannot determine from the available facts") ne demande qu'un intitulé, jamais pourquoi la question compte ou ce qu'elle bloque. Une chaîne comme "how shifts are validated before saving" nomme l'inconnue sans dire pourquoi un newcomer devrait s'en soucier.
Fix scopé au prompt de la Feature 10 (pas de nouveau champ, `open_questions` reste `list[str]`) : chaque `avoid_initially`/`open_questions` doit être une phrase autonome qui nomme la chose ET pourquoi elle compte (ce qu'elle bloque, ou ce que ça coûterait de l'ignorer) — ex. *"how shifts are validated before saving — unresolved, and central to any change touching `ShiftIn` without risking silently invalid data"* plutôt que la seule question nue. Implémenté par la nouvelle **Feature 10c**, additive sur la Feature 10/10b déjà livrée.

**206. Comment comparer une analyse avec l'expertise d'un engineer connaissant le projet ?**
Décidé (résolu 2026-09-17). Grille par section du rapport : d'accord / partiellement / faux / non vérifiable, remplie par un engineer ayant au moins plusieurs mois sur le projet ; elle sert de référence pour Q200, Q203 et Q204.

**207. Quels repositories de test utiliser ?**
Décidé (résolu 2026-09-17). Trois niveaux : (1) Atlas lui-même, à chaque changement (dogfooding, déjà en place) ; (2) un projet applicatif réel de taille moyenne avec un engineer de référence (le backend Django déjà utilisé pour les Features 09b/04b) ; (3) un projet open-source plus gros (ggshield, déjà utilisé), complété par un repository TypeScript et un repository Go à l'architecture documentée publiquement pour couvrir d'autres langages du MVP.

**208. Comment construire un benchmark multi-langage ?**
Décidé (résolu 2026-09-17). Pas de benchmark multi-langage formel tant que le corpus Q207 ne couvre pas au moins Python, TypeScript et Go ; le benchmark sera alors la grille Q201–Q206 appliquée par langage.

**209. Quel budget maximal d'analyse ?**
Décidé (résolu 2026-09-17). Budget par défaut : zéro coût marginal (Ollama local, provider par défaut du CLI). Pour un provider payant, pas de plafond imposé par Atlas au MVP : le cache (Q102) garantit qu'une ré-analyse sans changement ne coûte rien, et la sélection est bornée (Q86). Un plafond chiffré sera fixé à partir des tokens mesurés une fois `llm.budget_tokens` câblé (Q101).

**210. Quel temps maximal acceptable ?**
Décidé (résolu 2026-09-17). Cf. Q156 : moins de 5 minutes pour la partie déterministe sur la taille cible ; les passes LLM sont bornées par appel, pas en durée totale.

---

## Synthèse : décisions non encore implémentées

Toutes les questions du document sont tranchées (dernière passe : 2026-09-17). Les anciens points ⚠️ (Q21/Q192, Q86, Q121, Q155/Q194, Q156/Q209/Q210, Q190, Q193, Q200, Q207/Q208) ont chacun leur décision dans leur section.

Décidé ne signifie pas implémenté. Au 2026-09-17, les décisions suivantes restent à livrer (chacune demandera une spec de feature, cf. `specs/features/README.md`) ; les priorités et pistes de mise en œuvre sont dans [`docs/improvement-ideas.md`](../docs/improvement-ideas.md).

| Décision | Écart constaté | Priorité |
|---|---|---|
| Q142 — facts bruts via MCP | Pas de requête générique de facts filtrée par type (Q143 livré par la Feature 12d) | P1 |
| Q165 / Q125 — scan de secrets avant appel LLM | Non implémenté | P0 |
| Q205c, Q140f — Features 10c et 11e | Spécifiées, non implémentées | P0 |
| Q65 / Q101 — poids hotspot et budget tokens configurables | Lus dans `.atlas.toml`, non transmis aux stages | P1 |
| Q9 / Q158 — scope | Appliqué par `discovery` seulement | P1 |
| Q108 / Q113 — fenêtre Git, inclusion des merges | Supportés par le code, non exposés | P1 |
| Q157 — parallélisme | Tout est séquentiel | P1 |
| Q159 / Q160 — cache d'adapters, analyse incrémentale | Non implémentés | P1 |
| Q4 / Q3 — système multi-repositories | Repositories analysés séparément, pas de vue système | P1 |
| Q126 / Q199 — sections runtime, infra, CI/CD, data, observabilité, tests | Détection seulement | P1 |
| Q140 — commit hash dans le rapport | `run_id` + horodatage seulement | P2 |
| Q59, Q84, Q89 (call paths), Q90, Q91, Q120/Q121, Q129/Q134/Q135, Q166, Q169 (config) | Différés par décision (P1/P2) | P2 |

Anciennement : « Ces points sont ceux où ce document propose délibérément de ne pas trancher seul ». Ils ont été tranchés à partir des constats d'implémentation et de dogfooding ; les décisions de nature produit (Q155/Q156 cibles de taille et de temps, Q200 critère de succès, Q207 corpus, Q209 budget) sont des engagements de départ à confirmer par la mesure, et doivent être révisées dès qu'une mesure les contredit — ce document reste vivant.
