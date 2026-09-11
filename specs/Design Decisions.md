# Project Intelligence — Design Decisions

Ce document répond aux questions posées dans [Design Questions.md](Design%20Questions.md), section par section, en s'appuyant sur les principes fondamentaux du [Product Brief & Vision](Product%20Brief%20%26%20Vision.md) (existing tools first, deterministic first, LLM for interpretation, evidence first, never pretend to know, repository != system) et sur les priorités de la [Capability Matrix](Capability%20Matrix.md).

Statut de chaque réponse :
- **Décidé** — la question est tranchée, la décision engage l'architecture.
- **Proposition** — une réponse par défaut raisonnable est donnée mais reste ouverte à discussion.
- **Ouvert** — la question nécessite un arbitrage produit/business avant d'être tranchée (marqué **⚠️ impact architectural**).

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
Proposition. Déclaration explicite dans la configuration du `Project` (liste de repositories + tag `system: <name>` optionnel par repository). Pas de détection automatique au MVP ; une heuristique (noms proches, dépendances croisées via manifests, mentions croisées en documentation) peut être ajoutée en P2 comme *hypothèse*, jamais comme fait.

**5. Un repository peut-il appartenir à plusieurs systèmes ?**
Décidé — oui (ex. un monorepo partagé, une librairie interne). La relation `Repository -> System` est many-to-many dans le modèle.

**6. Comment représente-t-on une source externe non disponible localement ?**
Décidé. Un nœud `ExternalSource` typé (ex. `iac-repo`, `saas-dashboard`, `ci-system`) avec un statut `not_analyzed` et, si connu, une référence (URL, nom) mais aucune donnée extraite. Il apparaît dans le rapport comme un "trou" explicite plutôt que d'être omis (cf. principe Never pretend to know).

**7. Comment représente-t-on une information inconnue ?**
Décidé. Un champ n'est jamais laissé implicitement vide : soit il porte une valeur avec `provenance` et `confidence`, soit il porte explicitement un statut `unknown` / `not_analyzed` / `insufficient_evidence`. Aucune valeur par défaut silencieuse (pas de `null` interprété comme "non applicable" par le rapport).

**8. Quelle granularité d'analyse doit être supportée : repository, directory, file, symbol, system ?**
Décidé. Les cinq granularités doivent être adressables dans le modèle de Facts dès le MVP, même si tous les analyzers ne produisent pas toutes les granularités immédiatement. Le graphe de code (Q34+) est l'endroit où `file` et `symbol` doivent être navigables individuellement.

**9. L'utilisateur peut-il limiter explicitement le scope ?**
Décidé — oui, obligatoire au MVP : include/exclude par path glob, par langage, et par repository dans la configuration. C'est un garde-fou direct contre le non-goal "agent qui explore aveuglément toute la codebase".

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
Proposition. Signaux déterministes : références à des noms d'hôtes/services non résolus dans le repo, variables d'environnement pointant vers des systèmes non présents, mentions dans la documentation de repositories/systèmes externes, imports vers des packages internes non présents dans le scope. Chaque signal produit une entrée `ExternalSource` hypothétique (cf. Q6), jamais une affirmation.

**17. Comment détecte-t-on les fichiers d'IaC ?**
Décidé. Détection déclarative par pattern de fichier/extension par outil IaC (`*.tf`, `Chart.yaml`, `*.yaml` avec `kind:` Kubernetes connu, `serverless.yml`, `cdk.json`, etc.).

**18. Comment détecte-t-on Docker / Kubernetes / Helm / CI ?**
Décidé. Même approche : `Dockerfile`/`docker-compose.yml`, manifests K8s (par champ `apiVersion`/`kind`), `Chart.yaml`, et fichiers de config CI connus (`.github/workflows`, `.gitlab-ci.yml`, `Jenkinsfile`, `.circleci`, etc.) via une table de signatures.

**19. Comment gère-t-on les technologies inconnues ?**
Décidé. Le résultat de discovery inclut toujours une catégorie "unrecognized" listant les fichiers/dépendances non reconnus, jamais silencieusement ignorée. Elle nourrit l'amélioration continue de la table de signatures.

**20. Comment l'utilisateur peut-il ajouter manuellement une source ou un outil ?**
Proposition. Via la configuration du `Project` : entrées manuelles de type source (`ExternalSource` avec métadonnées) et déclaration d'un analyzer custom respectant le contrat d'adapter (cf. Q33).

---

# C. Existing tools / adapters

**21. Quelle est la liste initiale des outils supportés ?**
Décidé. Un outil par catégorie P0 : **tokei** pour la détection de langages et LOC (binaire Rust, sortie JSON, offline), **graphify** pour l'extraction du graphe de code (imports/calls/symbols, multi-langages), **Git** natif pour l'historique. Complexité et scanners IaC/CI restent optionnels/dégradables au MVP.

**22. Quels outils sont considérés comme obligatoires pour le MVP ?**
Proposition. Un détecteur de langage/LOC, Git (natif), un outil de code graph (Graphify ou équivalent), un outil de complexité par langage supporté. Tout le reste est optionnel/dégradable.

**23. Quels outils sont optionnels ?**
Proposition. IaC, Kubernetes, CI/CD, OpenAPI, observabilité, security scanning — tous "meilleur effort" : leur absence dégrade le rapport (sections marquées `not_analyzed`) sans bloquer l'exécution.

**24. Comment un analyzer est-il déclaré ?**
Décidé. Manifest déclaratif par adapter : nom, catégorie, langages/écosystèmes supportés, commande d'invocation, format de sortie attendu, version minimale, mode d'échec. Pas de code custom requis pour un simple wrapping CLI → JSON.

**25. Comment son installation est-elle gérée ?**
Proposition. Détection de présence (`which`/version check) avant exécution ; pas d'installation automatique au MVP (risque de sécurité/consentement) — l'outil signale l'absence et propose la commande d'installation à l'utilisateur.

**26. Peut-on utiliser un binaire externe ?**
Décidé — oui, c'est le mode principal d'un adapter (invocation de process, capture stdout/stderr, parsing du format de sortie).

**27. Peut-on utiliser Docker pour encapsuler un analyzer ?**
Proposition — oui en option pour les outils sans binaire natif portable, mais pas comme dépendance obligatoire au MVP (coût de démarrage, contrainte offline).

**28. Comment gère-t-on une version incompatible d'un outil ?**
Décidé. Le manifest d'adapter déclare une plage de version supportée ; une version hors plage produit un warning explicite et l'analyzer est marqué `skipped: version_mismatch`, jamais exécuté à l'aveugle.

**29. Comment gère-t-on l'absence d'un outil ?**
Décidé. L'analyzer est marqué `skipped: tool_not_found` dans les facts ; le rapport affiche explicitement la section comme non analysée plutôt que de l'omettre silencieusement.

**30. Comment gère-t-on un analyzer qui échoue ?**
Décidé. Échec isolé par analyzer (try/catch au niveau de l'orchestrateur), jamais fatal pour l'ensemble de l'analyse. Statut `failed` + message d'erreur capturé comme evidence, cf. Q180.

**31. Comment versionne-t-on les adapters ?**
Proposition. Version sémantique propre à l'adapter (indépendante de la version de l'outil externe qu'il wrappe), pour permettre l'évolution du format de sortie normalisé sans casser les facts existants.

**32. Comment testons-nous les adapters ?**
Proposition. Tests de contrat : fixtures de sortie brute réelle de l'outil externe → assertion sur le format `Fact[]` normalisé produit. Pas de dépendance à l'outil externe installé en CI (sauf tests d'intégration optionnels).

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
Proposition. Score continu `[0,1]` plutôt qu'une énumération, calculé différemment selon `provenance` : `observed`/`computed` = 1.0 par défaut (fiabilité de l'outil source) ; `inferred`/`hypothesis` = score explicite fourni par le composant qui infère, jamais implicite.

**45. Comment distingue-t-on `observed`, `computed`, `inferred` et `hypothesis` ?**
Décidé. `observed` = extrait directement d'une source sans transformation (ex. "ce fichier existe"). `computed` = dérivé déterministiquement de facts observés (ex. centralité, churn). `inferred` = déduction non déterministe mais raisonnée par une règle interne (ex. "ce répertoire est probablement une boundary"). `hypothesis` = proposition LLM non vérifiable déterministiquement (ex. "ce système suit un pattern hexagonal"). Ce sont les quatre valeurs du champ `provenance`, et le rapport HTML doit visuellement les distinguer (cf. Q136).

**46. Les facts sont-ils immuables ?**
Décidé — oui. Un fact n'est jamais modifié après création ; une ré-analyse produit de nouveaux facts liés à un nouveau `run_id` et à un nouveau timestamp/commit. L'historique des analyses reste donc traçable.

**47. Peut-on recalculer les insights à partir des facts sans relancer les analyzers ?**
Décidé — oui, c'est une exigence : la couche `Calculations`/`LLM synthesis` (cf. architecture conceptuelle) doit être rejouable indépendamment sur des facts déjà persistés, pour permettre l'itération sur le scoring/les prompts sans re-scanner le code.

**48. Les facts doivent-ils être persistés ?**
Décidé — oui, obligatoire dès le MVP (condition de Q47 et de la génération du rapport/MCP).

**49. Quel format de stockage : JSON, SQLite, graph DB, autre ?**
Proposition. SQLite comme store principal (facts + relations en tables, portable, pas de dépendance serveur, interrogeable en SQL pour le MCP), avec export JSON pour portabilité/versioning et debug humain. Une vraie graph DB (Neo4j etc.) est un P2 pour les très gros monorepos si SQLite devient limitant (cf. Q158).

**50. Comment versionne-t-on le schema des facts ?**
Décidé. Champ `schema_version` sur chaque Fact ; migrations explicites documentées entre versions majeures ; le store SQLite embarque sa propre version de schema vérifiée au démarrage.

---

# E. Graph

**51. Quelle partie du graph est fournie directement par des outils existants ?**
Décidé. L'extraction structurelle (symboles, imports, appels, héritage) vient entièrement d'un outil de code graph existant (Graphify ou équivalent) — Project Intelligence ne réimplémente pas de parsing AST.

**52. Quelle partie est construite par Project Intelligence ?**
Décidé. Les calculs transverses (centralité, communautés, cycles si non fournis, corrélation avec Git/hotspots) et la fusion multi-repository/multi-outil du graph.

**53. Utilisons-nous Graphify directement ?**
Proposition — oui par défaut comme provider de référence, mais via une interface `GraphProvider` abstraite pour ne pas coupler le modèle de Facts à un outil spécifique (cf. Q54).

**54. Quels autres graph providers devons-nous supporter ?**
Proposition. Au moins un provider par écosystème majeur non couvert nativement par Graphify si besoin (ex. un outil spécifique à un langage). Décision concrète différée jusqu'à connaître les limites réelles de Graphify sur les langages cibles du MVP (cf. Q193).

**55. Comment normalisons-nous les différents graph formats ?**
Décidé. Chaque `GraphProvider` traduit sa sortie native vers les entités/relations standard du modèle de Facts (Q35/Q36) — la normalisation est la responsabilité de l'adapter, pas du consommateur.

**56. Quelles relations doivent être standards ?**
Décidé — cf. Q36 : `depends_on`, `calls`, `imports`, `inherits_from` au minimum pour tout provider de graph.

**57. Comment distingue-t-on une relation extraite d'une relation inférée ?**
Décidé — via `provenance` sur la relation comme sur tout Fact (Q45) : une relation `imports` extraite du code est `observed` ; une relation "probable boundary" est `inferred`.

**58. Comment gère-t-on les graphs énormes ?**
Proposition. Pagination/streaming depuis le store (SQLite) plutôt que chargement en mémoire complet ; le rapport HTML charge le graph par niveau (cf. Q59) et à la demande plutôt que d'embarquer un graph complet dans le HTML pour les gros repos.

**59. Faut-il produire plusieurs niveaux de graph ?**
Décidé — oui : au moins `system` (repositories/services), `module/directory`, et `file/symbol`. Le rapport doit permettre de naviguer du niveau macro au niveau micro (drill-down), pas d'afficher un graph plat de milliers de nœuds.

**60. Comment calcule-t-on les communautés ?**
Proposition. Algorithme standard de détection de communauté (ex. Louvain) appliqué au graph de dépendances au niveau module/fichier, calcul interne déterministe (pas de LLM), fourni par une librairie de graph existante plutôt que réimplémenté.

**61. Comment calcule-t-on la centralité ?**
Proposition. Centralité de degré (in/out) comme métrique de base P0 ; betweenness/eigenvector centrality en P1 si le coût de calcul reste acceptable sur les tailles ciblées (cf. Q155).

**62. Comment détecte-t-on les cycles ?**
Décidé. Détection algorithmique classique (Tarjan/SCC) sur le graph de dépendances, déterministe, fournie par une librairie existante ou par le graph provider s'il l'expose déjà.

**63. Quelle information doit être accessible au MCP ?**
Proposition. Le graph au niveau `module`/`file`/`symbol` interrogeable par requêtes bornées (voisinage direct, chemin entre deux nœuds, top-N centralité) — jamais un dump complet du graph (cf. Q152).

---

# F. Hotspots

**64. Quelles métriques entrent dans le hotspot score ?**
Décidé (MVP, cf. Capability Matrix section 4) : complexité, taille (LOC), couplage/centralité du graph, churn Git. Runtime data en P1 si disponible.

**65. Le score doit-il être configurable ?**
Proposition — oui, pondérations exposées en configuration avec des valeurs par défaut raisonnables, pour s'adapter à des contextes de mission différents (ex. audit sécurité vs onboarding).

**66. Les poids sont-ils fixes ou adaptatifs ?**
Proposition. Fixes par défaut (transparence et reproductibilité) ; un mode adaptatif basé sur le contexte de mission est un P2, pas un prérequis MVP.

**67. Comment normalise-t-on les métriques entre projets ?**
Proposition. Normalisation par percentile/z-score au sein du projet analysé (pas de comparaison inter-projets au MVP) — chaque métrique est ramenée à sa distribution locale avant pondération.

**68. Comment évite-t-on qu'un énorme fichier domine artificiellement ?**
Proposition. Pénaliser une métrique de taille brute par une normalisation logarithmique, et ne jamais utiliser la taille seule comme signal — toujours combinée à complexité/couplage/churn (cf. Q72).

**69. Comment intègre-t-on Git churn ?**
Décidé. Nombre de commits touchant le fichier sur une fenêtre configurable (cf. Q108/Q109), normalisé, comme une des composantes du score.

**70. Comment intègre-t-on graph centrality ?**
Décidé. Centralité (Q61) normalisée comme composante du score — un fichier très dépendu pèse plus qu'un fichier isolé de même complexité.

**71. Comment intègre-t-on complexity ?**
Décidé. Sortie de l'outil de complexité (cyclomatic/cognitive selon disponibilité par langage) normalisée comme composante du score.

**72. Comment intègre-t-on runtime data lorsqu'elle est disponible ?**
Proposition — P1. Si des données runtime (fréquence d'invocation, erreurs) sont disponibles via un connector observabilité, elles s'ajoutent comme composante additionnelle optionnelle, jamais requise.

**73. Comment explique-t-on le score ?**
Décidé — obligatoire (Capability Matrix : "Le hotspot score doit être explicable et décomposable"). Chaque score de hotspot est accompagné de la décomposition par composante (valeur brute + valeur normalisée + poids) et des evidences sous-jacentes.

**74. Comment représente-t-on l'absence de données ?**
Décidé. Une composante manquante (ex. pas de données Git si scope superficiel) est explicitement exclue du calcul et signalée dans l'explication du score, jamais traitée comme zéro silencieux.

**75. Peut-on avoir plusieurs scores : code hotspot, architectural hotspot, Git hotspot, runtime hotspot ?**
Proposition — oui, en plus d'un score combiné : exposer les sous-scores par catégorie permet à l'utilisateur de comprendre *pourquoi* un fichier ressort, aligné avec le principe evidence-first.

---

# G. Architecture interpretation

**76. Qu'est-ce qu'une architecture "observée" ?**
Décidé. Un ensemble de facts `computed`/`observed` sur la structure du graph (couches détectées par structure de dossiers + direction des dépendances, boundaries par communauté) — sans jugement qualitatif.

**77. Qu'est-ce qu'une architecture "interprétée" ?**
Décidé. Une synthèse `hypothesis` produite par le LLM à partir de l'architecture observée, nommant un pattern connu (layered, hexagonal, microservices, etc.) avec un niveau de confiance et des citations vers les facts observés qui la soutiennent.

**78. Quels patterns architecturaux cherchons-nous ?**
Proposition. Un catalogue initial couvrant les patterns les plus fréquents en usage courant : layered/N-tier, hexagonal/ports-adapters, microservices, monolith modulaire, event-driven, MVC/MVVM. Extensible sans blocage (le LLM peut nommer un pattern hors catalogue en le marquant `uncatalogued`).

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

**84. Peut-on comparer architecture déclarée dans la documentation et architecture observée ?**
Proposition — P1. Utile pour détecter le "documentation drift" (Capability Matrix section 14) ; nécessite d'extraire une architecture "déclarée" depuis les docs (LLM, `hypothesis`) puis de la confronter à l'architecture observée.

---

# H. Domain understanding

**85. Quels artefacts fournissons-nous au LLM ?**
Proposition. Un sous-ensemble sélectionné : fichiers d'entrée jugés importants (cf. Q87), README/docs pertinents, signatures de types/entités extraites déterministiquement, noms de tests significatifs — jamais le repository complet (cf. Q93, non-goal explicite).

**86. Combien de contexte LLM maximum ?**
⚠️ **Ouvert — impact architectural.** Dépend du provider choisi (cf. Q94) et du budget (cf. Q101). Proposition par défaut : un budget de tokens configurable par run avec un plafond conservateur, le sélecteur de contenu (Q87) devant respecter ce budget plutôt que l'inverse.

**87. Comment sélectionnons-nous les fichiers importants ?**
Décidé. Réutilisation directe du score de hotspot/centralité (section F) et des entrypoints détectés (Q43 de la Capability Matrix / graph) — sélection déterministe, pas de LLM pour choisir quoi lire.

**88. Comment sélectionnons-nous les tests importants ?**
Proposition. Tests couvrant les fichiers sélectionnés en Q87 (via mapping test→code si disponible) + tests dont le nom/chemin indique un workflow métier (heuristique de nommage).

**89. Comment identifions-nous les workflows candidats ?**
Proposition. Combinaison de chemins d'exécution dans le graph d'appel depuis les entrypoints + noms de tests d'intégration/e2e comme signal supplémentaire ; le LLM synthétise ensuite un workflow lisible à partir de ces candidats sourcés.

**90. Comment extrayons-nous les états ?**
Proposition — P1. Détection déterministe d'enums/constantes de statut dans les entités identifiées (Q102 Capability Matrix), complétée par le LLM pour nommer une éventuelle state machine implicite (`hypothesis`).

**91. Comment extrayons-nous les événements ?**
Proposition — P1. Signal déterministe : noms de classes/fonctions/topics contenant des patterns d'event (`*Event`, `emit`, `publish`, noms de topics de queue détectés en Q118 Capability Matrix) ; interprétation métier laissée au LLM.

**92. Comment conservons-nous les preuves ?**
Décidé — même mécanisme que tout le reste (Q37) : chaque affirmation de domain understanding référence les facts/fichiers/lignes qui l'ont motivée.

**93. Comment évitons-nous d'envoyer tout le repository au LLM ?**
Décidé — c'est un principe non négociable du Product Brief. Mécanisme : sélection déterministe bornée par budget (Q86/Q87) + refus explicite de tout mode "envoyer le repo entier".

**94. Comment gère-t-on plusieurs LLM providers ?**
Proposition. Interface `LLMProvider` abstraite (prompt structuré in, réponse structurée validée out) permettant de brancher différents providers/modèles sans changer la couche synthèse ; le choix du provider par défaut est une décision produit hors scope de ce document.

**95. Peut-on désactiver complètement le LLM ?**
Décidé — oui, obligatoire (cohérent avec Q10/Q198) : le rapport reste généré avec les sections LLM marquées `not_analyzed` plutôt que le pipeline entier bloqué.

---

# I. LLM orchestration

**96. Combien de passes LLM sont nécessaires ?**
Proposition. Multi-passes spécialisées plutôt qu'un unique appel monolithique : au minimum une passe par grande section nécessitant interprétation (architecture, domaine, onboarding path), chacune avec un contexte borné et un schema de sortie dédié — plus fiable à valider (Q81) qu'un unique prompt géant.

**97. Peut-on réaliser le rapport avec un seul appel final ?**
Décidé — non par défaut, pour les raisons de Q96 (validation, citations, budget) ; peut rester une option "fast/cheap" dégradée en P2 avec avertissement de confiance réduite.

**98. Quels agents spécialisés sont réellement nécessaires ?**
Proposition (alignée avec la Capability Matrix, colonnes LLM) : synthèse architecture, synthèse domaine/business, génération onboarding path. Ce sont les trois seules zones où la Capability Matrix marque LLM comme requis en P0 sans alternative déterministe.

**99. Quels agents peuvent être remplacés par des analyzers déterministes ?**
Décidé — aucun agent "LLM" ne doit exister là où la Capability Matrix marque une case déterministe/interne sans LLM (ex. hotspots, centralité, cycles) : le principe deterministic-first s'applique strictement à la conception des agents, pas seulement aux données.

**100. Comment limite-t-on les tokens ?**
Décidé — mécanisme combiné : sélection de contenu bornée (Q87), budget par passe (Q101), troncature explicite avec log plutôt que silencieuse.

**101. Comment impose-t-on un budget ?**
Proposition. Budget de tokens (et donc de coût) configurable par run au niveau `Project`, réparti par passe LLM selon des quotas par défaut, avec arrêt/dégradation propre (cf. Q107) si dépassement plutôt qu'un échec dur.

**102. Comment cache-t-on les résultats ?**
Proposition. Cache clé par (hash du contenu envoyé au LLM + version du prompt + provider/modèle) → réponse. Persisté dans le même store que les facts pour survivre entre runs.

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
Proposition. Fenêtre configurable, par défaut une période raisonnable (ex. 12 mois) plutôt que l'historique complet, pour borner le coût sur de vieux/gros repositories — configurable à "tout l'historique" si l'utilisateur le souhaite.

**109. Analyse-t-on toute l'histoire ou une fenêtre configurable ?**
Décidé — fenêtre configurable par défaut (cf. Q108), historique complet en option explicite.

**110. Comment calcule-t-on le churn ?**
Décidé. Nombre de commits (ou lignes modifiées, les deux exposées séparément) touchant un fichier sur la fenêtre, via `git log`/`git blame`, calcul interne déterministe.

**111. Comment calcule-t-on le co-change ?**
Proposition. Fichiers apparaissant ensemble dans un même commit au-delà d'un seuil de fréquence sur la fenêtre analysée — calcul interne déterministe, standard dans les outils de Git mining.

**112. Comment gère-t-on les renames ?**
Décidé. Suivi de renommage natif de Git (`git log --follow` / détection de similarité) pour préserver la continuité de l'historique d'un fichier à travers ses renommages.

**113. Comment gère-t-on les merge commits ?**
Proposition. Exclusion des merge commits du calcul de churn par défaut (pour ne pas gonfler artificiellement les fichiers touchés par de gros merges), avec option pour les inclure.

**114. Comment gère-t-on les monorepos ?**
Proposition. Le calcul de churn/co-change reste global au repository, mais les hotspots (section F) sont toujours rapportés au niveau `Project`/scope déclaré, pour que le bruit d'un monorepo entier ne pollue pas l'analyse d'un sous-scope ciblé.

**115. Comment détecte-t-on les hotspots historiques ?**
Décidé — c'est la combinaison churn + centralité + complexité déjà définie en section F ; pas de mécanisme distinct.

**116. Comment corrèle-t-on Git et code graph ?**
Décidé. Jointure sur le chemin de fichier normalisé (Q38) entre les facts Git (churn, contributeurs, co-change) et les facts du graph (centralité, appartenance à un composant) au niveau du store de facts.

---

# K. Infrastructure / external sources

**117. Comment déclare-t-on qu'un IaC repository appartient au système ?**
Décidé — même mécanisme que Q4 : déclaration explicite dans la configuration du `Project` (repository supplémentaire tagué comme IaC pour un `System` donné).

**118. Peut-on analyser plusieurs repositories différents avec des adapters différents ?**
Décidé — oui, c'est la conséquence naturelle du modèle multi-repository (Q3) : chaque repository est scanné avec les adapters pertinents à son contenu détecté (Q11-19), indépendamment des autres.

**119. Comment gère-t-on les repositories absents ?**
Décidé — même traitement que Q6/Q29 : `ExternalSource`/`Repository` avec statut `not_analyzed`, jamais une absence silencieuse.

**120. Comment gère-t-on les sources accessibles uniquement via API ?**
Proposition — P1. Un `Connector` (distinct d'un adapter local) qui interroge une API externe (ex. dashboard SaaS, registre de conteneurs) selon le même contrat de sortie que les adapters (Q33), avec gestion explicite des credentials (Q122).

**121. Quels connectors sont supportés ?**
⚠️ **Ouvert.** Non spécifié dans les documents actuels ; à trancher avec la liste d'outils MVP (Q21).

**122. Comment gère-t-on les credentials ?**
Proposition. Jamais stockés par Project Intelligence lui-même : lecture depuis l'environnement/gestionnaire de secrets de l'utilisateur au moment de l'exécution, jamais persistés dans les facts ni loggés (cf. Q170).

**123. Le système doit-il fonctionner sans credentials ?**
Décidé — oui, obligatoire : tout connector nécessitant des credentials est optionnel et son absence dégrade proprement (Q29/Q119), jamais bloquant pour le reste du pipeline.

**124. Comment sépare-t-on données locales et données sensibles ?**
Proposition. Marquage explicite au niveau de la source (repository/connector) d'un niveau de sensibilité ; ce marquage conditionne ce qui peut être envoyé au LLM (cf. Q125) et ce qui reste local uniquement.

**125. Quelles données ne doivent jamais être envoyées au LLM ?**
Proposition. Secrets détectés (Q165), credentials, contenu de fichiers marqués confidentiels par configuration, et par défaut tout contenu brut de fichier au-delà de la sélection bornée déjà définie (Q93) — le principe s'applique aussi bien à la donnée qu'au volume.

---

# L. HTML report

**126. Quelle structure exacte du rapport ?**
Décidé — reprend directement la liste du Product Brief section 5 : executive summary, system map, architecture, code map, hotspots, domain understanding, runtime, infrastructure, CI/CD, data architecture, observability, tests, Git evolution, risks/anomalies, onboarding path, glossary, evidence.

**127. Quelle navigation ?**
Proposition. Navigation latérale persistante par section (miroir de Q126) + recherche globale (Q133) + fil d'Ariane pour le drill-down graph (Q59).

**128. Quels diagrammes ?**
Proposition. Au minimum : system map (composants/repositories), code graph par niveau (Q59), diagramme de dépendances CI/CD (commit→prod, Q150 Capability Matrix), diagramme d'entités de données.

**129. Mermaid ou autre moteur ?**
Proposition. Mermaid pour les diagrammes statiques simples (rendu portable dans un fichier HTML autonome), complété par un rendu graphe interactif dédié (ex. force-directed / cytoscape.js) pour le code graph navigable — Mermaid seul ne scale pas à un graph interactif de milliers de nœuds.

**130. Les diagrammes doivent-ils être générés à partir des facts ?**
Décidé — oui, systématiquement : jamais de diagramme dessiné à la main ou par le LLM sans passer par les facts structurés, pour garantir que chaque élément visuel est cliquable vers son evidence (Q131).

**131. Peut-on cliquer sur un composant et voir ses preuves ?**
Décidé — oui, obligatoire (cohérent avec evidence-first) : chaque nœud/élément du rapport est lié à ses `Evidence` sous-jacentes.

**132. Peut-on cliquer sur une relation et voir son origine ?**
Décidé — oui, même exigence que Q131 appliquée aux relations (quel adapter/analyzer l'a produite, avec quelle provenance).

**133. Peut-on rechercher un symbole ?**
Décidé — oui, recherche full-text sur les entités (fichiers, symboles, composants) exigée dès le MVP pour la navigation.

**134. Peut-on filtrer le graph ?**
Proposition — oui : par type de relation, par niveau de confiance/provenance, par composant/module — nécessaire pour rendre un gros graph exploitable.

**135. Comment affiche-t-on les niveaux de confiance ?**
Proposition. Codage visuel cohérent (ex. opacité ou bordure) reflétant le score de confiance (Q44/Q83), appliqué uniformément à tous les éléments visuels dérivés de facts `inferred`/`hypothesis`.

**136. Comment distingue-t-on fact / insight / hypothesis ?**
Décidé — obligatoire (principe evidence-first) : un marqueur visuel systématique et explicite (badge/couleur/icône) reflétant le champ `provenance` (Q45), cohérent entre toutes les sections du rapport.

**137. Le rapport doit-il fonctionner totalement offline ?**
Décidé — oui, fichier HTML autonome sans dépendance réseau à l'ouverture (cf. Q138), y compris pour les diagrammes et la recherche.

**138. Doit-il être un fichier HTML autonome ?**
Décidé — oui : toutes les données et assets nécessaires embarqués (ou en fichiers locaux adjacents), pour être partageable/archivable sans serveur.

**139. Peut-on exporter certaines vues ?**
Proposition — P1. Export du JSON de facts sous-jacent (déjà requis, Q49) suffit comme export "données" ; un export image/PDF par vue est un nice-to-have P2.

**140. Le rapport doit-il être versionnable ?**
Décidé — oui : chaque génération de rapport embarque un timestamp, le `run_id`, et le commit hash de chaque repository analysé, pour permettre de comparer deux rapports dans le temps.

---

# M. MCP

**141. Quelles primitives MCP sont nécessaires ?**
Proposition (dérivée de la Capability Matrix section 5/16 et des questions suivantes) : lookup composant, dépendances/dépendants, recherche de workflow, hotspots, chemin entre composants, "où commencer".

**142. Le MCP expose-t-il les facts bruts ?**
Décidé — oui, en lecture filtrée/paginée (pas de dump), pour permettre à un agent de vérifier une evidence précise.

**143. Le MCP expose-t-il les insights ?**
Décidé — oui, avec leur `provenance`/confiance intacte : un agent consommateur doit pouvoir distinguer fact et hypothesis exactement comme le rapport HTML (Q136).

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
Proposition — P1, optionnelle et explicitement consentie (pas un comportement par défaut d'une simple requête de lecture), pour ne pas transformer un outil read-only en déclencheur caché de coût LLM/compute.

---

# N. Performance

**155. Quelle taille de repository doit être supportée ?**
⚠️ **Ouvert — impact architectural.** Non chiffré dans les documents actuels ; conditionne le choix du store (Q49) et des algorithmes de graph (Q58/Q61). À définir avec le MVP (cf. Q194).

**156. Quel temps d'analyse cible ?**
⚠️ **Ouvert.** Non chiffré ; proposition de principe : les résultats déterministes rapides (Q162) doivent être disponibles en quelques minutes sur un repository de taille moyenne, indépendamment du temps LLM.

**157. Quels analyzers peuvent tourner en parallèle ?**
Décidé — tous les adapters indépendants entre eux (pas de dépendance de données) tournent en parallèle par défaut ; seules les étapes de calcul/LLM qui consomment la sortie d'un adapter attendent explicitement sa complétion.

**158. Comment gère-t-on les gros monorepos ?**
Proposition. Scope explicite obligatoire (Q9) plutôt qu'un scan complet par défaut sur un monorepo ; passage à une graph DB dédiée (cf. Q49) si SQLite devient un goulot mesuré, pas par anticipation.

**159. Comment cache-t-on les résultats ?**
Décidé — même mécanisme que Q102 pour le LLM, étendu aux résultats d'adapters déterministes coûteux : cache clé par (hash des fichiers d'entrée + version d'adapter).

**160. Peut-on analyser uniquement les changements depuis une analyse précédente ?**
Proposition — P1. Analyse incrémentale basée sur le diff de commit hash par rapport au dernier `run_id` connu, réutilisant le cache (Q159) pour les fichiers inchangés.

**161. Comment gère-t-on les limites mémoire ?**
Proposition. Traitement en streaming/par lot au niveau des adapters et du store plutôt que chargement intégral en mémoire, particulièrement pour le parsing Git sur de longs historiques (Q108).

**162. Quels résultats doivent être disponibles rapidement avant le reste ?**
Proposition. Discovery (section B) et structure de base du repository, car ils ne dépendent d'aucun autre analyzer et donnent une première valeur immédiate à l'utilisateur pendant que le reste tourne.

---

# O. Security / privacy

**163. L'analyse doit-elle être locale par défaut ?**
Décidé — oui, cohérent avec Q10/Q95/Q123 : aucune donnée ne quitte l'environnement local sauf action explicite (appel LLM ou connector externe configuré).

**164. Quelles données peuvent sortir de l'environnement ?**
Décidé — uniquement le contenu explicitement sélectionné pour les passes LLM (Q85/Q87/Q93/Q125), jamais un export brut du repository.

**165. Comment détecte-t-on les secrets avant appel LLM ?**
Proposition. Passage systématique de tout contenu sélectionné pour le LLM à travers un scanner de secrets déterministe existant (pattern-matching connu, entropie) avant envoi ; tout match bloque l'inclusion de ce contenu plutôt que de le masquer silencieusement sans trace.

**166. Comment anonymise-t-on certaines informations ?**
Proposition — P1. Non détaillé dans les documents actuels ; à minima, les noms de contributeurs (Q189 Capability Matrix) pourraient être pseudonymisés en option avant envoi au LLM ou dans un rapport destiné à être partagé largement.

**167. Comment gère-t-on les repositories clients confidentiels ?**
Décidé (principe) — cf. Q163/Q164 : le mode local-only + désactivation LLM (Q95) doit permettre une analyse complète d'un repository confidentiel sans qu'aucune donnée ne sorte, seule dégradation étant l'absence de synthèse LLM.

**168. Peut-on utiliser un LLM local ?**
Proposition — oui, souhaitable : l'interface `LLMProvider` (Q94) doit pouvoir cibler un modèle local (ex. via Ollama ou équivalent) sans changement de la couche synthèse, ce qui résout Q167 sans désactiver complètement l'interprétation.

**169. Peut-on désactiver certaines catégories d'analyse ?**
Décidé — oui, chaque catégorie d'analyzer (section B-K) doit être activable/désactivable en configuration indépendamment des autres.

**170. Comment journalise-t-on les appels externes ?**
Proposition. Log structuré de chaque appel sortant (connector API, appel LLM) avec horodatage, destination, volume de données (pas le contenu brut si sensible), consultable par l'utilisateur pour audit — cohérent avec l'exigence de transparence du principe evidence-first appliqué à l'outil lui-même.

---

# P. UX / CLI

**171. Quelle commande lance l'analyse ?**
Décidé — `project-intel analyze <scope>`, tel que défini dans le Product Brief section 7.

**172. Quelle configuration est nécessaire ?**
Proposition. Un fichier de configuration par `Project` (repositories, scope, analyzers activés, budget LLM, provider) avec des valeurs par défaut permettant de lancer une analyse minimale sans configuration explicite sur un seul repository.

**173. Faut-il une configuration explicite ou une auto-discovery maximale ?**
Décidé — les deux, en couches : auto-discovery maximale par défaut (Q11-20) pour la détection technique, configuration explicite obligatoire uniquement pour ce qui ne peut pas être déduit de façon fiable (scope multi-repository/système, credentials, budget) — cohérent avec Q9.

**174. Comment affiche-t-on la progression ?**
Proposition. Sortie CLI progressive par étape du pipeline (Q7 de l'architecture conceptuelle : discovery → analyzers → normalisation → calculs → LLM → rapport), avec statut par analyzer individuel (running/done/failed/skipped).

**175. Peut-on relancer uniquement un analyzer ?**
Décidé — oui, nécessaire pour l'itération/debug (cf. Q32/Q179) et cohérent avec la persistance des facts (Q47/Q48).

**176. Peut-on lancer uniquement Git analysis ?**
Décidé — oui, cas particulier de Q175 (sélection par catégorie d'analyzer, cf. Q169).

**177. Peut-on lancer uniquement le LLM synthesis ?**
Décidé — oui, cas particulier de Q175/Q47 : rejouer la synthèse sur des facts déjà persistés sans re-scanner.

**178. Comment inspecte-t-on les facts ?**
Proposition. Sous-commande CLI dédiée (ex. `project-intel facts query`) permettant de filtrer/afficher les facts stockés sans passer par le rapport HTML, utile pour le debug (Q179).

**179. Comment debugge-t-on un adapter ?**
Proposition. Mode `--verbose`/`--debug` par adapter affichant la commande exacte invoquée, la sortie brute avant normalisation, et le résultat de la normalisation — nécessaire pour diagnostiquer un échec (Q30) ou une sortie inattendue.

**180. Comment affiche-t-on les erreurs sans interrompre toute l'analyse ?**
Décidé — cohérent avec Q30/Q107 : les erreurs sont collectées et affichées en fin d'exécution (résumé des analyzers `failed`/`skipped`) plutôt que d'interrompre le run global.

---

# Q. Extensibility

**181. Comment ajouter un nouvel analyzer ?**
Décidé — via le contrat d'adapter (Q24/Q33) : un manifest déclaratif + la commande d'invocation, sans modification du cœur du système.

**182. Comment ajouter un nouveau langage ?**
Proposition. Ajout d'une entrée dans la table de signatures de détection (Q12/Q13) + déclaration des adapters de complexité/graph compatibles pour ce langage ; pas de changement structurel requis.

**183. Comment ajouter un nouveau provider de graph ?**
Décidé — implémentation de l'interface `GraphProvider` (Q53/Q55), sans changement du modèle de Facts.

**184. Comment ajouter un nouvel outil externe ?**
Décidé — cas général de Q181.

**185. Comment ajouter une nouvelle source externe ?**
Décidé — implémentation d'un `Connector` respectant le même contrat de sortie que les adapters (Q120/Q33).

**186. Comment ajouter une nouvelle métrique ?**
Proposition. Une métrique est un `Fact` de type `computed` produit par un composant de calcul enregistré dans le pipeline `Calculations` (architecture conceptuelle) ; l'ajout ne nécessite pas de changement du schema de Fact générique.

**187. Comment ajouter une nouvelle vue HTML ?**
Proposition. Le rapport est structuré en sections indépendantes (Q126) consommant des facts/insights typés ; une nouvelle vue est une nouvelle section consommant des types de facts existants ou nouveaux, sans dépendre du reste du rapport.

**188. Comment ajouter une nouvelle primitive MCP ?**
Proposition. Chaque primitive MCP est une requête typée et bornée (Q152) sur le store de facts ; l'ajout d'une primitive est l'ajout d'une nouvelle requête, pas un changement du serveur MCP lui-même.

**189. Le système doit-il avoir un plugin mechanism ?**
Proposition — oui, dans la mesure où Q181-188 impliquent déjà des interfaces stables (`Adapter`, `GraphProvider`, `Connector`, `Calculation`) : un mécanisme de plugin formel (découverte + chargement dynamique) est une formalisation de ces interfaces plutôt qu'un système séparé, à prévoir en P1 après validation du MVP avec des extensions "in-tree".

**190. Quelle API stable doit être fournie aux plugins ?**
⚠️ **Ouvert.** Dépend de la formalisation de Q189 ; à spécifier une fois les interfaces internes (Q24, Q53, Q120, Q186) stabilisées par l'usage réel dans le MVP plutôt que figées prématurément.

---

# R. MVP

**191. Quelles capacités sont absolument nécessaires au premier release ?**
Proposition — toutes les lignes P0 de la Capability Matrix, en particulier : Discovery complète, Code Graph (composants/dépendances/appels/centralité/entrypoints), Hotspots avec score explicable, Code Navigation de base, un socle de Domain Understanding et d'Onboarding Path (seules zones LLM P0), rapport HTML avec les sections correspondantes.

**192. Quels outils existants devons-nous intégrer en premier ?**
Décidé — tokei (langage/LOC), Git (historique), graphify (code graph). Dans cet ordre de priorité pour le MVP.

**193. Quels langages devons-nous supporter ?**
Décidé. MVP : **Python, TypeScript/JavaScript, Go, Java/Kotlin, Ruby, Rust**. Critère de sélection : couverture tokei native (LOC) + grammaires graphify disponibles. Extensions futures selon demande utilisateur, sans refonte du modèle.

**194. Quelle taille de projet doit être supportée ?**
⚠️ **Ouvert.** Lié à Q155 ; à définir conjointement.

**195. Le MVP doit-il supporter plusieurs repositories ?**
Décidé — oui (cf. Q3), même si l'orchestration multi-repository peut rester simple (parallélisation basique, pas d'optimisation avancée) au tout premier release.

**196. Le MVP doit-il supporter l'IaC externe ?**
Proposition — non au strict MVP (marqué optionnel en section K) ; le modèle doit néanmoins pouvoir représenter un `ExternalSource` IaC non analysé dès le MVP (Q6/Q119), pour ne pas nécessiter de refonte du modèle plus tard.

**197. Le MVP doit-il inclure le MCP ?**
Proposition — oui, sous une forme minimale (primitives read-only de base : lookup, dépendances/dépendants, hotspots) plutôt qu'un P2, car c'est un output primaire du Product Brief (section 5) et non une extension.

**198. Le MVP doit-il inclure le LLM ?**
Décidé — oui pour les zones P0 marquées LLM-only dans la Capability Matrix (architecture interpretation, domain understanding, onboarding path), mais le pipeline doit rester fonctionnel LLM désactivé (Q95).

**199. Quel niveau de rapport HTML est nécessaire ?**
Proposition — les sections correspondant aux capacités P0 (Q191) au minimum ; les sections purement P1 (ex. observability, data architecture avancée) peuvent apparaître comme sections "non analysées" plutôt qu'absentes du template.

**200. Quel résultat démontrerait que le MVP est réellement utile à un senior engineer ?**
⚠️ **Ouvert.** C'est une question de validation produit, pas de design technique — à répondre empiriquement via la section S (Validation), pas par anticipation dans ce document.

---

# S. Validation

**201. Comment mesurer la qualité du rapport ?**
Proposition — combinaison de métriques objectives (couverture des sections P0, taux d'evidence manquante) et d'évaluation humaine structurée (cf. Q206), pas une métrique unique.

**202. Comment mesurer la précision des facts ?**
Proposition. Échantillonnage manuel de facts `observed`/`computed` vérifiés contre le code source réel, taux d'erreur mesuré par catégorie d'analyzer.

**203. Comment mesurer la pertinence des hotspots ?**
Proposition. Comparaison contre le jugement d'un engineer connaissant réellement le projet (cf. Q206) : les fichiers qu'il désignerait comme "à surveiller" recoupent-ils les hotspots calculés.

**204. Comment mesurer la qualité de l'onboarding path ?**
Proposition — même méthode que Q203, appliquée au parcours recommandé plutôt qu'aux hotspots seuls.

**205. Comment mesurer les hallucinations ?**
Décidé (mécanisme, cf. Q104) — taux de citations invalides détectées par le validateur structurel comme métrique directe et automatisable, avant même l'évaluation humaine.

**206. Comment comparer une analyse avec l'expertise d'un engineer connaissant le projet ?**
Proposition. Protocole d'évaluation : un engineer expérimenté sur le projet note l'accord/désaccord avec les affirmations du rapport section par section, sert de référence pour Q203/Q204.

**207. Quels repositories de test utiliser ?**
⚠️ **Ouvert.** Non spécifié ; recommandation : un mix de repositories open-source connus (architecture documentée publiquement, donc vérifiable) et, une fois disponible, un projet réel avec un engineer de référence pour Q206.

**208. Comment construire un benchmark multi-langage ?**
⚠️ **Ouvert.** Dépend de Q193/Q207 ; à construire après stabilisation du MVP sur les 1-2 langages initiaux plutôt qu'en pré-requis.

**209. Quel budget maximal d'analyse ?**
⚠️ **Ouvert.** Lié à Q101/Q156 ; à chiffrer avec des données réelles d'usage plutôt qu'estimé a priori.

**210. Quel temps maximal acceptable ?**
⚠️ **Ouvert.** Lié à Q156 ; même remarque.

---

## Synthèse des points ⚠️ nécessitant un arbitrage produit avant implémentation

- **Q21 / Q192** — liste d'outils MVP par catégorie.
- **Q86** — budget de contexte LLM par défaut (dépend du provider, Q94).
- **Q121** — liste des connectors supportés.
- **Q155 / Q194** — taille de repository/projet cible.
- **Q156 / Q209 / Q210** — cibles de temps et de budget d'analyse.
- **Q190** — API stable de plugin (à différer après stabilisation des interfaces internes).
- **Q193** — langages supportés au MVP (bloquant pour le choix d'outil de graph/complexité).
- **Q200** — critère de succès MVP (question de validation, pas de conception).
- **Q207 / Q208** — corpus de test/benchmark.

Ces points sont ceux où ce document propose délibérément de ne pas trancher seul : ils engagent soit un choix de coût/budget, soit une décision produit sur le public cible initial.
