# Project Intelligence — Design Questions

Ces questions servent à finaliser la spécification avant implémentation.

L'agent doit identifier les décisions nécessaires, proposer des options lorsque plusieurs solutions sont raisonnables, et signaler explicitement les décisions qui ont un impact architectural.

---

# A. Scope et modèle mental

1. Qu'est-ce qu'on appelle exactement un `Project` ?
2. Quelle différence formelle entre `Project`, `Repository`, `System` et `Environment` ?
3. Peut-on analyser plusieurs repositories simultanément ?
4. Comment déclare-t-on que plusieurs repositories appartiennent au même système ?
5. Un repository peut-il appartenir à plusieurs systèmes ?
6. Comment représente-t-on une source externe non disponible localement ?
7. Comment représente-t-on une information inconnue ?
8. Quelle granularité d'analyse doit être supportée : repository, directory, file, symbol, system ?
9. L'utilisateur peut-il limiter explicitement le scope ?
10. L'outil doit-il pouvoir fonctionner complètement offline ?

---

# B. Discovery

11. Comment détecte-t-on automatiquement les langages ?
12. Comment détecte-t-on les frameworks ?
13. Comment détecte-t-on les build systems ?
14. Comment détecte-t-on les package managers ?
15. Comment détecte-t-on les repositories Git ?
16. Comment détecte-t-on qu'une partie du système est probablement ailleurs ?
17. Comment détecte-t-on les fichiers d'IaC ?
18. Comment détecte-t-on Docker / Kubernetes / Helm / CI ?
19. Comment gère-t-on les technologies inconnues ?
20. Comment l'utilisateur peut-il ajouter manuellement une source ou un outil ?

---

# C. Existing tools / adapters

21. Quelle est la liste initiale des outils supportés ?
22. Quels outils sont considérés comme obligatoires pour le MVP ?
23. Quels outils sont optionnels ?
24. Comment un analyzer est-il déclaré ?
25. Comment son installation est-elle gérée ?
26. Peut-on utiliser un binaire externe ?
27. Peut-on utiliser Docker pour encapsuler un analyzer ?
28. Comment gère-t-on une version incompatible d'un outil ?
29. Comment gère-t-on l'absence d'un outil ?
30. Comment gère-t-on un analyzer qui échoue ?
31. Comment versionne-t-on les adapters ?
32. Comment testons-nous les adapters ?
33. Quel contrat de sortie impose-t-on à tous les adapters ?

---

# D. Normalized Facts

34. Quelle est la structure exacte d'un `Fact` ?
35. Quels types d'entités supportons-nous ?
36. Quels types de relations supportons-nous ?
37. Quelle structure pour une `Evidence` ?
38. Comment référence-t-on un fichier ?
39. Comment référence-t-on une ligne ?
40. Comment référence-t-on un symbole ?
41. Comment référence-t-on un commit ?
42. Comment référence-t-on une ressource externe ?
43. Comment représente-t-on la provenance d'une donnée ?
44. Comment représente-t-on la confiance ?
45. Comment distingue-t-on `observed`, `computed`, `inferred` et `hypothesis` ?
46. Les facts sont-ils immuables ?
47. Peut-on recalculer les insights à partir des facts sans relancer les analyzers ?
48. Les facts doivent-ils être persistés ?
49. Quel format de stockage : JSON, SQLite, graph DB, autre ?
50. Comment versionne-t-on le schema des facts ?

---

# E. Graph

51. Quelle partie du graph est fournie directement par des outils existants ?
52. Quelle partie est construite par Project Intelligence ?
53. Utilisons-nous Graphify directement ?
54. Quels autres graph providers devons-nous supporter ?
55. Comment normalisons-nous les différents graph formats ?
56. Quelles relations doivent être standards ?
57. Comment distingue-t-on une relation extraite d'une relation inférée ?
58. Comment gère-t-on les graphs énormes ?
59. Faut-il produire plusieurs niveaux de graph ?
60. Comment calcule-t-on les communautés ?
61. Comment calcule-t-on la centralité ?
62. Comment détecte-t-on les cycles ?
63. Quelle information doit être accessible au MCP ?

---

# F. Hotspots

64. Quelles métriques entrent dans le hotspot score ?
65. Le score doit-il être configurable ?
66. Les poids sont-ils fixes ou adaptatifs ?
67. Comment normalise-t-on les métriques entre projets ?
68. Comment évite-t-on qu'un énorme fichier domine artificiellement ?
69. Comment intègre-t-on Git churn ?
70. Comment intègre-t-on graph centrality ?
71. Comment intègre-t-on complexity ?
72. Comment intègre-t-on runtime data lorsqu'elle est disponible ?
73. Comment explique-t-on le score ?
74. Comment représente-t-on l'absence de données ?
75. Peut-on avoir plusieurs scores : code hotspot, architectural hotspot, Git hotspot, runtime hotspot ?

---

# G. Architecture interpretation

76. Qu'est-ce qu'une architecture "observée" ?
77. Qu'est-ce qu'une architecture "interprétée" ?
78. Quels patterns architecturaux cherchons-nous ?
79. Le LLM peut-il proposer un pattern architectural ?
80. Comment doit-il citer ses preuves ?
81. Comment évite-t-on les hallucinations architecturales ?
82. Peut-on avoir plusieurs hypothèses concurrentes ?
83. Comment exprime-t-on la confiance ?
84. Peut-on comparer architecture déclarée dans la documentation et architecture observée ?

---

# H. Domain understanding

85. Quels artefacts fournissons-nous au LLM ?
86. Combien de contexte LLM maximum ?
87. Comment sélectionnons-nous les fichiers importants ?
88. Comment sélectionnons-nous les tests importants ?
89. Comment identifions-nous les workflows candidats ?
90. Comment extrayons-nous les états ?
91. Comment extrayons-nous les événements ?
92. Comment conservons-nous les preuves ?
93. Comment évitons-nous d'envoyer tout le repository au LLM ?
94. Comment gère-t-on plusieurs LLM providers ?
95. Peut-on désactiver complètement le LLM ?

---

# I. LLM orchestration

96. Combien de passes LLM sont nécessaires ?
97. Peut-on réaliser le rapport avec un seul appel final ?
98. Quels agents spécialisés sont réellement nécessaires ?
99. Quels agents peuvent être remplacés par des analyzers déterministes ?
100. Comment limite-t-on les tokens ?
101. Comment impose-t-on un budget ?
102. Comment cache-t-on les résultats ?
103. Comment invalidons-nous un résultat après modification du code ?
104. Comment détecte-t-on les hallucinations ?
105. Le LLM doit-il obligatoirement produire des citations ?
106. Quel modèle de sortie doit-il respecter ?
107. Que se passe-t-il si le LLM échoue ?

---

# J. Git

108. Quelle profondeur d'historique analyse-t-on ?
109. Analyse-t-on toute l'histoire ou une fenêtre configurable ?
110. Comment calcule-t-on le churn ?
111. Comment calcule-t-on le co-change ?
112. Comment gère-t-on les renames ?
113. Comment gère-t-on les merge commits ?
114. Comment gère-t-on les monorepos ?
115. Comment détecte-t-on les hotspots historiques ?
116. Comment corrèle-t-on Git et code graph ?

---

# K. Infrastructure / external sources

117. Comment déclare-t-on qu'un IaC repository appartient au système ?
118. Peut-on analyser plusieurs repositories différents avec des adapters différents ?
119. Comment gère-t-on les repositories absents ?
120. Comment gère-t-on les sources accessibles uniquement via API ?
121. Quels connectors sont supportés ?
122. Comment gère-t-on les credentials ?
123. Le système doit-il fonctionner sans credentials ?
124. Comment sépare-t-on données locales et données sensibles ?
125. Quelles données ne doivent jamais être envoyées au LLM ?

---

# L. HTML report

126. Quelle structure exacte du rapport ?
127. Quelle navigation ?
128. Quels diagrammes ?
129. Mermaid ou autre moteur ?
130. Les diagrammes doivent-ils être générés à partir des facts ?
131. Peut-on cliquer sur un composant et voir ses preuves ?
132. Peut-on cliquer sur une relation et voir son origine ?
133. Peut-on rechercher un symbole ?
134. Peut-on filtrer le graph ?
135. Comment affiche-t-on les niveaux de confiance ?
136. Comment distingue-t-on fact / insight / hypothesis ?
137. Le rapport doit-il fonctionner totalement offline ?
138. Doit-il être un fichier HTML autonome ?
139. Peut-on exporter certaines vues ?
140. Le rapport doit-il être versionnable ?

---

# M. MCP

141. Quelles primitives MCP sont nécessaires ?
142. Le MCP expose-t-il les facts bruts ?
143. Le MCP expose-t-il les insights ?
144. Le MCP expose-t-il les evidence ?
145. Peut-on interroger un composant ?
146. Peut-on demander ses dépendances ?
147. Peut-on demander ses dépendants ?
148. Peut-on chercher un workflow ?
149. Peut-on demander les hotspots ?
150. Peut-on demander un chemin entre deux composants ?
151. Peut-on demander "où commencer pour comprendre X" ?
152. Comment éviter que le MCP retourne trop de données ?
153. Quels outils MCP sont read-only ?
154. Le MCP doit-il déclencher une nouvelle analyse à la demande ?

---

# N. Performance

155. Quelle taille de repository doit être supportée ?
156. Quel temps d'analyse cible ?
157. Quels analyzers peuvent tourner en parallèle ?
158. Comment gère-t-on les gros monorepos ?
159. Comment cache-t-on les résultats ?
160. Peut-on analyser uniquement les changements depuis une analyse précédente ?
161. Comment gère-t-on les limites mémoire ?
162. Quels résultats doivent être disponibles rapidement avant le reste ?

---

# O. Security / privacy

163. L'analyse doit-elle être locale par défaut ?
164. Quelles données peuvent sortir de l'environnement ?
165. Comment détecte-t-on les secrets avant appel LLM ?
166. Comment anonymise-t-on certaines informations ?
167. Comment gère-t-on les repositories clients confidentiels ?
168. Peut-on utiliser un LLM local ?
169. Peut-on désactiver certaines catégories d'analyse ?
170. Comment journalise-t-on les appels externes ?

---

# P. UX / CLI

171. Quelle commande lance l'analyse ?
172. Quelle configuration est nécessaire ?
173. Faut-il une configuration explicite ou une auto-discovery maximale ?
174. Comment affiche-t-on la progression ?
175. Peut-on relancer uniquement un analyzer ?
176. Peut-on lancer uniquement Git analysis ?
177. Peut-on lancer uniquement le LLM synthesis ?
178. Comment inspecte-t-on les facts ?
179. Comment debugge-t-on un adapter ?
180. Comment affiche-t-on les erreurs sans interrompre toute l'analyse ?

---

# Q. Extensibility

181. Comment ajouter un nouvel analyzer ?
182. Comment ajouter un nouveau langage ?
183. Comment ajouter un nouveau provider de graph ?
184. Comment ajouter un nouvel outil externe ?
185. Comment ajouter une nouvelle source externe ?
186. Comment ajouter une nouvelle métrique ?
187. Comment ajouter une nouvelle vue HTML ?
188. Comment ajouter une nouvelle primitive MCP ?
189. Le système doit-il avoir un plugin mechanism ?
190. Quelle API stable doit être fournie aux plugins ?

---

# R. MVP

191. Quelles capacités sont absolument nécessaires au premier release ?
192. Quels outils existants devons-nous intégrer en premier ?
193. Quels langages devons-nous supporter ?
194. Quelle taille de projet doit être supportée ?
195. Le MVP doit-il supporter plusieurs repositories ?
196. Le MVP doit-il supporter l'IaC externe ?
197. Le MVP doit-il inclure le MCP ?
198. Le MVP doit-il inclure le LLM ?
199. Quel niveau de rapport HTML est nécessaire ?
200. Quel résultat démontrerait que le MVP est réellement utile à un senior engineer ?

---

# S. Validation

201. Comment mesurer la qualité du rapport ?
202. Comment mesurer la précision des facts ?
203. Comment mesurer la pertinence des hotspots ?
204. Comment mesurer la qualité de l'onboarding path ?
205. Comment mesurer les hallucinations ?
206. Comment comparer une analyse avec l'expertise d'un engineer connaissant le projet ?
207. Quels repositories de test utiliser ?
208. Comment construire un benchmark multi-langage ?
209. Quel budget maximal d'analyse ?
210. Quel temps maximal acceptable ?