# Méthodologie d'analyse technique d'Eliot — codification canonique (Session 05)

> **SSOT de la lecture technique d'Ichor** (ADR-113). Toute implémentation du
> module technique (service, section data_pool, indicateurs Pine, futur
> DimensionVote) dérive de CE document — jamais d'une autre source.
>
> **v1.1 (2026-06-12)** : v1.0 vérifiée par 6 agents adversariaux en contexte
> frais contre les sources brutes (37 findings : 1 bloquant, 10 majeurs) —
> TOUS pliés ici. Détail : SESSION_LOG du jour.
>
> **Sources primaires** (matériaux §9.2, fournis par l'owner 2026-06-12) :
>
> - `[T-P]` `transcript session ichor/analyse technique prioritaire.txt` — transcript pédagogique prioritaire (⚠ tronqué ~30 min par TurboScribe : la hiérarchie des origines s'arrête au début du niveau 2)
> - `[T-C]` `transcript session ichor/analyse technique complémentaire.txt` — stratégie complète (63 min, 2 juin)
> - `[T-B]` `transcript session ichor/backtest complet stratégie eliott technique.txt` — backtest live EUR/USD (Replay TradingView)
> - `[T-G]` `transcript session ichor/gestion de trades technique.txt` — gestion de trade/risque
> - `[T-F]` `transcript session ichor/transcript vidéo analyse fondamental et autres (connaissance).txt` — fondamental + fusion
> - `[HUB]` hub des réunions trading (`D:\Projects\reunion-trading` + `D:\Projects\ichor beta\IchorBeta\pages-site`) — doctrine vécue, leçons, gestion des incohérences
>
> **Conventions** : chaque règle porte sa source et sa confiance —
> **EXPLICITE** (dit dans la source ; les guillemets « » signalent du
> verbatim exact) ou **INFÉRÉE** (déduite du contexte, à ne pas durcir sans
> validation). Les ambiguïtés irréductibles sont marquées `[TBD owner]` et
> listées en §13. **Interdiction d'inventer** : ce qui n'est pas dans les
> sources n'est pas dans ce document.
>
> **Frontière contractuelle (ADR-017, intacte)** : Ichor lit, explique,
> probabilise et anticipe. Ichor n'émet JAMAIS de signal d'ordre, de niveau
> d'exécution prescriptif ni d'instruction de gestion de position. Les
> sections §9 et §10 sont codifiées comme **logique de fusion et contexte de
> lecture** — jamais rendues comme règles de prise de position. L'exécution
> reste Eliot.

---

## 0. Périmètre & vigilance anti-scam

- La méthodologie d'Eliot est **volontairement minimaliste** : « Order Blocks,
  Fair Value Gaps, etc. ne sont que des renommages complexifiés des origines
  acheteuses/vendeuses » `[T-P]` EXPLICITE. Le module technique n'encode PAS
  le jargon SMC/ICT anglophone (BOS, CHoCH, FVG interdits dans les rendus —
  convention hub `[HUB]` EXPLICITE ; « sweep » toléré comme langue commune).
- Anti-indicateurs : « les indicateurs ne savent pas comment est le marché »
  `[T-B]` EXPLICITE. Le chart d'Eliot ne porte quasi aucun indicateur (EMA
  retirée) ; seuls outils : sessions visualisées (carrés bleus 13h-20h) et
  No Gap Candles `[T-C]` EXPLICITE (effet exact sur la lecture des bougies
  vs barres TimescaleDB : `[TBD owner]`, §13.10).
- Anti-surcharge : « plus vous avez de niveaux, plus vous avez de friction
  d'analyse » `[T-B]` EXPLICITE ; analyses « guerre des étoiles » rejetées
  `[T-F]` EXPLICITE. Tracer uniquement ce que voit le marché.
- Filtre de validité : « quand vous arrivez à faire de l'argent constamment
  avec votre stratégie, vous l'appelez comme vous voulez » `[T-P]` — le
  critère est la récurrence démontrée, pas le vocabulaire. Toute extension du
  module au-delà de ce document = sur-engineering à refuser.
- Récence des patterns : plus on s'éloigne dans le temps, moins les patterns
  et les drivers de marché restent valides (mandats, régimes) → toute
  calibration/backtest des seuils se fait sur des données récentes `[T-B]`
  EXPLICITE.

## 1. Univers & cadre temporel

| Élément                        | Valeur                                                                                                                                                                                                 | Source                                                                                                                                               |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Actifs tradés                  | 5 : EUR/USD, GBP/USD, XAU/USD, SPX500, NAS100                                                                                                                                                          | `[T-C]` EXPLICITE (T-P n'en nomme que 3 ; le document owner « pourquoi ces 5 actifs » manque, §13.11)                                                |
| Arbitrage inter-actifs         | Éviter les actifs « pas sur de bons points », valoriser les setups les plus propres parmi les 5 — il y a presque toujours une opportunité quelque part                                                 | `[T-B]` EXPLICITE                                                                                                                                    |
| DXY                            | Jamais tradé. « Pilier » : driver/catalyseur, confirmation de corrélation                                                                                                                              | `[T-P]`,`[HUB]` EXPLICITE                                                                                                                            |
| Corrélations DXY (indicatives) | EURUSD −0,9/−0,95 · GBPUSD −0,8/−0,9 · XAUUSD −0,6/−0,85                                                                                                                                               | `[T-P]` EXPLICITE (valeurs « en moyenne », non sourcées — à recalculer en continu côté Ichor, jamais figées ; as-built : `services/correlations.py`) |
| Analyse quotidienne            | 12h-13h Paris (« chaque jour est une nouvelle analyse »)                                                                                                                                               | `[T-P]` EXPLICITE                                                                                                                                    |
| Fenêtre d'exécution            | 13h-16h Paris (overlap Londres/NY) `[T-P]`,`[T-C]` EXPLICITE ; pic de qualité valorisé 14h-16h `[T-B]` EXPLICITE ; courbe de volume `[T-C]` : pic absolu à l'open US 15h-15h30, déclin à partir de 17h | réconciliation §13.3                                                                                                                                 |
| Entrées tardives               | Jamais à 17h+ (« moins de volatilité, plus de manipulation »)                                                                                                                                          | `[T-C]`,`[T-B]` EXPLICITE                                                                                                                            |
| Gestion de trade               | 16h-20h : laisser tourner, placer des BE, « potentiellement reprendre des positions »                                                                                                                  | `[T-P]` EXPLICITE — tension avec T-C/T-G (journée finie après 17h sur BE) : §13.12                                                                   |
| Coupure                        | 20h Paris, inconditionnelle, quel que soit le R (« même en RR de 8 ») ; jamais d'overnight                                                                                                             | `[T-P]`,`[T-C]`,`[T-B]`,`[T-G]` EXPLICITE (règle la plus répétée du corpus)                                                                          |
| Session asiatique              | Non tradée : pas de volume → consolidation/manipulation                                                                                                                                                | `[T-C]` EXPLICITE                                                                                                                                    |
| Heures                         | Heure de Paris, été/hiver à surveiller (réglage LuxAlgo manuel)                                                                                                                                        | `[T-C]` EXPLICITE                                                                                                                                    |

**Pourquoi ces fenêtres** : le volume de transactions fait la volatilité et le
momentum ; l'overlap Londres/NY concentre le plus gros volume mondial ; les
annonces éco réagissent le plus sur la session NY `[T-C]` EXPLICITE.

## 2. La logique (dimension 1/5)

Toute l'analyse technique se réduit à **deux questions** `[T-P]` EXPLICITE :

1. **Dans quel élan/tendance est mon marché ?** — et la suivre. Jamais de
   contre-tendance (sans support fondamental `[T-B]`).
2. **Le prix s'approche-t-il d'origines acheteuses ou vendeuses ?**

« Un point, c'est tout. » Le reste est du contexte au service de ces deux
questions.

Principes logiques structurants :

- **Volume = volatilité = institutions** : sans gros volume directionnel, le
  marché consolide ou manipule `[T-C]` EXPLICITE.
- **Patterns récurrents / prix psychologique** : les acteurs qui ont profité
  sur un niveau y replacent leurs ordres (analogie de la pomme 3€→7€) — c'est
  le fondement comportemental des origines `[T-P]` EXPLICITE.
- **S'adapter, pas anticiper** : « le but ce n'est pas d'anticiper, c'est
  s'adapter » `[T-B]` EXPLICITE. On pose des scénarios, le marché choisit, on
  réagit aux confirmations.
- **L'objet unique tradé = le momentum de session NY** : mouvement direct et
  décidé à l'open NY ; si le prix revient au point d'entrée, la thèse momentum
  est morte `[T-B]` EXPLICITE.

## 3. Les critères (dimension 2/5)

Checklist des critères de qualification (tous EXPLICITES sauf mention) :

- **Bougie pleine** : corps > somme des deux mèches `[T-C]` — signature de
  poussée/momentum.
- **Bougie d'incertitude** : mèches dominantes, petit corps — équilibre des
  camps ; tolérée uniquement en début/fin de poussée `[T-C]`.
- **Poussée** : mouvement net, linéaire, bougies pleines quasi exclusivement
  dans le sens `[T-C]`.
- **Correction** : structurée, méchée, accumulation de bougies (« combat
  acheteurs/vendeurs ») `[T-C]`.
- **Cassure = clôture de bougie, jamais une mèche** (« une mèche n'est pas une
  cassure ») `[HUB]` EXPLICITE.
- **Tendance baissière** : plus bas ET plus hauts de plus en plus bas `[T-C]`.
- **Structure pré-session** : no-trade **par défaut** — « plus le marché est
  structuré avant votre session, plus le momentum à l'open sera net »
  `[T-B]`,`[HUB]` ; « moi je reste hors du marché souvent quand j'ai ce
  délire-là » `[T-B]` EXPLICITE. **Dérogation** `[T-B]` EXPLICITE : structure
  faible → position quand même possible à risque réduit, en s'appuyant
  beaucoup plus sur l'analyse fondamentale.
- **Proximité des zones** : la zone la plus proche du prix actuel prime ;
  une origine lointaine « n'a plus vraiment de sens » `[T-C]`,`[T-B]`.
- **Mouvement consommé** : si Londres a déjà fait le mouvement attendu, on ne
  le court pas après en NY `[T-B]`,`[HUB]`.

## 4. Les déclencheurs (dimension 3/5)

Séquence de déclenchement d'exécution (UT : 15m, idéalement 5m `[T-B]`
EXPLICITE) — codifiée ici comme **séquence de validation de scénario** pour
Ichor (jamais émise comme instruction d'ordre) :

1. **Retour du prix dans l'origine** — retest valide = la moitié de la zone
   **côté approche du prix** (division en 3 tiers `[T-B]` EXPLICITE,
   démontrée sur une origine ACHETEUSE : « entre le haut et le milieu de ma
   zone, pas entre le bas et le milieu » ; miroir pour une zone vendeuse =
   INFÉRÉE, §13.13).
2. **Rejet** : mèche de rejet sous/sur la structure (ex. tentative de nouveau
   plus bas rejetée) `[T-C]`.
3. **Pattern de confirmation** : avalement haussier/baissier (bougie qui
   englobe la précédente — lecture volumique : N×15 min de marché englouties
   `[T-B]`) OU étoile du matin/du soir (sens fort → incertitude → sens inverse
   net = « 100 % vendeurs → 50-50 → 100 % acheteurs ») `[T-C]` EXPLICITE.
4. **Validation à la clôture** de la bougie de confirmation — jamais en cours
   de bougie `[T-C]`.
5. **Séquence en deux temps sur zone** : bougie d'incertitude qui rejette
   (= intérêt pour la zone) PUIS bougie de décision dans le sens — on n'agit
   pas au simple toucher de zone `[T-G]` EXPLICITE.

Signal H1 de plus forte valeur : bougie H1 (notamment la clôture 12h-13h) qui
mèche fortement dans la zone ET clôture au-dessus/en-dessous de la structure —
« ça veut presque tout dire » `[T-C]` EXPLICITE.

## 5. La lecture du prix (dimension 4/5)

### 5.1 Grammaire poussée/correction

Le marché alterne poussées (entrée d'un gros volume directionnel) et
corrections (sortie du volume → combat) `[T-C]`. **Détecteur de retournement
principal — l'anomalie de rôle** : une correction qui devient nette/en
momentum (alors qu'elle devrait être structurée) signale la bascule du camp
dominant `[T-C]`,`[HUB]` EXPLICITE.

Signaux complémentaires (EXPLICITES) :

- Poussées dans le sens de la tendance de moins en moins fortes/grandes +
  poussées contraires de plus en plus fortes/grandes `[T-P]`,`[T-C]`.
- Échec de création d'un nouveau plus bas/haut, rejeté par mèches (= entrée
  de volume opposé) `[T-C]`.
- 3 bougies de momentum décroissantes à l'approche d'une origine opposée →
  basculer en mode retournement `[T-B]`.
- **Fin de correction → manipulation accrue attendue** (plus de mèches, plus
  d'incertitude — comportement normal, lecture, pas signal) `[T-B]`
  EXPLICITE.

### 5.2 La mèche du plongeur (concept signature)

« Avant d'aller dans son sens final, le marché crée dans la plupart des cas
une mèche dans le sens inverse — comme un plongeur prend une grande
respiration avant l'apnée » `[T-P]` EXPLICITE, valable sur toute UT.

Application quotidienne (EXPLICITE, répétée sur chaque trade du backtest) :

- Ce sont les sessions **asiatique + Londres (minuit-midi)** qui construisent
  la mèche inverse ; **NY fait le sens final**.
- SI à midi Asie+Londres ont fait le mouvement inverse du biais → confirmation
  supplémentaire (la respiration est faite) `[T-P]`.
- SI l'open part directement dans le sens attendu sans mèche contraire →
  suspect, rejet probable `[T-B]`,`[HUB]`. **Exception calibrée hub** : une
  surprise de donnée largement hors consensus (~2×) produit un mouvement
  direct SANS piège ; la vraie manipulation peut s'être jouée AVANT, sur
  Londres `[HUB]` EXPLICITE (nuance 05/06).
- **Exceptions (sous tension inter-sources, §13.14)** : T-P/T-C — réjection
  déjà marquée dans le sens visé, ou clôture daily en forte poussée
  directionnelle (continuation) → pas de mèche requise. MAIS contre-évidence
  `[T-B]` EXPLICITE : face à une clôture daily fortement baissière, Eliot
  attend la continuité ET exige quand même la mèche contraire avant la
  continuation NY. Slice-1 traite la mèche comme TOUJOURS informative et
  rapporte son statut sans la désactiver les jours de continuation.
- Une bougie qui a énormément manipulé → la suivante prend normalement le
  momentum (« ça ne peut pas arriver deux fois ») `[T-B]` EXPLICITE.

### 5.3 Lecture Daily

On ne regarde QUE la dernière bougie clôturée — surtout COMMENT elle s'est
clôturée (mèches, rejets) `[T-P]` EXPLICITE. Daily = contexte, jamais
direction globale `[T-C]`. Bougie pleine → continuation attendue ; bougie
d'incertitude après poussée → fin de momentum/début de correction `[T-B]`.
Lecture interne d'une incertitude : le camp qui a rejeté dicte la suite (deux
incertitudes de même forme ne se lisent pas pareil) `[T-B]` EXPLICITE.
**Clôture daily du chart d'Eliot : 22h-23h Paris** (« il est exactement 22h,
donc on est à la clôture journalière en daily ») `[T-P]` EXPLICITE — pas
minuit ; heure exacte faisant foi : §13.15.

### 5.4 Rôles des UT (top-down strict)

| UT     | Rôle                                                                                                                                                               | Source          |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------- |
| Daily  | Contexte de la dernière bougie clôturée + règle de la mèche                                                                                                        | `[T-P]`,`[T-C]` |
| H4     | « Je ne fais rien dessus » — contexte léger, correction structurée vs momentum                                                                                     | `[T-P]`,`[T-C]` |
| H1     | **Cœur de l'analyse** : zones/origines, canaux et switch (§13.16 — concept nommé, jamais défini formellement dans les sources), structure, scénario + invalidation | `[T-P]`,`[T-C]` |
| 15m/5m | Structure fine + déclencheurs d'exécution                                                                                                                          | `[T-B]`,`[T-C]` |

Trendlines : purement visuelles (matérialiser les canaux), on ne trade jamais
dessus `[T-P]` EXPLICITE.

## 6. Le raisonnement complet (dimension 5/5) — séquence quotidienne

Séquence observée à l'identique sur chaque journée du backtest `[T-B]` :

1. **Daily après la clôture 22h-23h** : lire la dernière bougie clôturée
   (pleine / incertitude / réjection) → poser le contexte du jour.
2. **Structure récente daily** : poussée/correction + golden zone Fibonacci.
3. **Attendre/vérifier la mèche contraire** (Asie/Londres) selon §5.2.
4. **H1** : identifier LA zone d'origine pertinente (§7) + structure +
   poser scénario principal ET invalidation chiffrée (« une prévision sans
   invalidation ne vaut rien » `[HUB]`).
5. **12h-13h** : clôture H1 de midi = signal-clé de confirmation `[T-C]`.
6. **15m/5m dans la fenêtre 13h-16h** : séquence de déclenchement (§4).
7. **Post-16h** : gestion uniquement selon T-C/T-G (T-P évoque des reprises
   de position 16h-20h — tension §13.12) ; 20h : la thèse du jour expire.

Filtres no-trade (EXPLICITES) : **jour férié US/UK (bank holiday) → pas de
volume institutionnel → no-trade a priori** `[T-B]` · pas de structure
lisible (défaut ; dérogation §3) · zone pertinente trop lointaine · mouvement
déjà consommé par Londres · session en range · contre-tendance sans support
fondamental · (en réel) fondamental non corrélé au technique. « Tous les
jours ne sont pas un jour de trade » `[T-B]`.

## 7. Les zones : origines acheteuses/vendeuses

**Définition** : niveau où un gros volume de transactions est entré (ou sorti)
et a créé le départ d'un mouvement — « c'est l'origine de la vente/l'achat »
`[T-P]` EXPLICITE. Tracées en **H1**, **aux clôtures de bougies** (très
souvent) et aux mèches `[T-C]` EXPLICITE. Pratique de tracé `[T-B]`
EXPLICITE : borne posée à la clôture de bougie, extension possible jusqu'au
haut de la mèche (« les vendeurs et le volume de transactions se sont faits
sur toute cette zone-là »), avec préférence pour une zone précise/étroite.

**Hiérarchie** — les AOI ne sont placées QUE sur deux niveaux (« les AOI, je
les place sur deux... une de niveau 1 ou une de niveau 2 ») `[T-C]`
EXPLICITE :

- **Niveau 1** : origine d'un grand mouvement créé **pendant la session NY**
  (fenêtre 13h-16h, volume d'ouverture US) — « le plus haut niveau » ; en
  pratique backtest : l'origine du momentum de la session NY **précédente**
  prime `[T-P]`,`[T-C]`,`[T-B]` EXPLICITE. Peut aussi être la 2e poussée d'une
  séquence poussée-correction-poussée (ré-entrée de volume) `[T-G]` EXPLICITE.
- **Niveau 2** : point de **sortie** d'un gros volume — momentum stoppé en
  début de session NY qui repart en sens inverse (les institutions « ne
  sortent pas du marché comme ça, juste par prise de tête » `[T-C]`
  EXPLICITE). Polarité inversée : la sortie des acheteurs devient origine
  vendeuse de niveau 2.
- **Niveau 3** : mentionné dans T-P (tronqué) mais jamais défini ; T-C borne
  les zones placées à deux niveaux → non implémenté (`[TBD owner]` §13.1).

**Critère discriminant** : une origine valide est l'origine d'un **momentum
réel** — pas la simple fin d'un mouvement adverse `[T-B]` EXPLICITE.

**Mécanique du retest** : toute grande zone est divisée en **3 tiers** ;
retest valide = **la moitié de la zone côté approche du prix** — démontré
`[T-B]` EXPLICITE sur une origine ACHETEUSE (« un retest entre le haut et le
milieu de ma zone, pas entre le bas et le milieu ») ; généralisation miroir
au cas vendeur (entre le bas et le milieu) = INFÉRÉE, à valider (§13.13).

**Priorisation** : proximité > taille (§3). Zone unique trop lointaine = pas
d'intérêt aujourd'hui.

**Usage en cours de trade (lecture)** : les origines adverses tracées en H1
servent à EXPLIQUER le comportement du prix (un range sur origine adverse est
NORMAL et attendu) — usage psychologique, pas signal `[T-G]` EXPLICITE.

## 8. Fibonacci : la golden zone

Seuls niveaux utilisés : **0,5 et 0,618** (« golden zone », chiffre d'or)
`[T-C]`,`[T-B]` EXPLICITE. Après une poussée forte, la correction revient très
souvent s'y terminer. Ancrage observé `[T-G]` : du plus haut au plus bas du
mouvement en 15m (en H1 sur la poussée pour l'analyse `[T-P]` INFÉRÉE — bornes
exactes du tirage `[TBD owner]` §13.6). Confluence golden zone + origine =
zone de retournement de haute qualité `[T-G]` EXPLICITE.

## 9. Fusion fondamental ↔ technique (doctrine vécue, hub)

> **Frontière** : cette section codifie la **logique de fusion** (comment le
> verdict d'Ichor pondère lecture technique et conviction fondamentale) et le
> vocabulaire de l'arbitrage ex post. Comme §4 et §10, elle n'est JAMAIS
> rendue comme règle de prise de position — elle gouverne le poids du vote
> technique dans le verdict (Chantier C), pas une permission d'exécution.

Architecture du système complet : **~80 % fondamental / ~20 % technique**
`[T-B]` EXPLICITE (« on a 80 % de notre analyse qui est faite par l'analyse
fondamentale ») ; version qualitative `[T-C]` EXPLICITE : stratégie reposant
« beaucoup » sur le fondamental, technique = adaptation + compréhension de
marché + recherche d'origines. « L'analyse technique seule n'a aucun pouvoir
prédictif » — la direction vient du courant (macro), le technique donne le OÙ
(origines H1) et le QUAND (fenêtre NY) `[T-F]` EXPLICITE.

Doctrine d'incohérence (hub, EXPLICITE — la règle cardinale) :

- **Désaccord technique ↔ fondamental → abstention par défaut** (« on
  n'invente pas : on reste à l'écart »), **levable en séance** uniquement si
  une annonce tranche le désaccord ET que les déclencheurs valident ensuite
  le scénario (« attendre que les annonces tranchent (ADP, ISM) et n'entrer
  que si les déclencheurs valident MON scénario »). L'incohérence est NOMMÉE
  le matin (« incohérence assumée »), trackée par actif, arbitrée ex post au
  bilan (QUI avait raison — en documentant le **driver réel vs annoncé** :
  « bonne cible, mauvaise histoire » ne compte pas comme raison pleine).
- **Le fondamental ne déclenche jamais seul** (« on ne prend une position que
  si elle respecte le système ») — garde-fou qui confirme ou retient.
- **La conviction module l'exigence de confirmation** : conviction tiède →
  extra-confirmation 15m exigée. Exception unique calibrée (02/06, vérifiée) :
  le vote technique ne peut l'emporter contre la conviction fondamentale que
  si TROIS conditions se cumulent — conviction faible (~56 %) ET
  **mono-déclencheur** ET structure technique très propre `[HUB]` EXPLICITE.
  Seuil dur « jamais contre ≥70 % » : INFÉRÉE (contrefactuel unique : « Si
  Ichor avait donné 70 % de hausse et qu'on vendait, il y aurait un
  problème »).
- **Toute prévision porte une invalidation chiffrée** (« une prévision sans
  invalidation ne vaut rien ») ; clôture H1 = arbitre.
- Échelle de conviction : 50 % = pile ou face · 60 % = ça penche · ≥70 % =
  forte conviction. **Plafonnement volontaire** quand les drivers s'opposent
  (55 % le 26/05, 52-60 % le 08/06) `[HUB]` EXPLICITE — une conviction
  « tiède » peut signifier « drivers opposés », pas « absence de vue ».

Leçons récurrentes du hub à encoder comme garde-fous de lecture (EXPLICITES) :

1. Or-refuge : en régime dollar fort + taux réels élevés, le canal taux bat le
   réflexe refuge — « on n'achète pas l'or sur une headline de guerre »
   (répétée 4× en 2 semaines, promue Conviction numérotée).
2. Direction >> magnitude : force du corpus = la direction, faiblesse
   chronique = l'échelle (« le sens ne suffit pas, il faut l'échelle », bilan
   09/06). Correctif opérationnel : cibles bornées à l'ADR de la fenêtre NY
   (~50 pips) quand le contexte est « trop large » `[HUB]` EXPLICITE.
3. Ne pas chasser le faux momentum à l'open (manipulation 15h30 → prise de
   liquidité → vrai mouvement).
4. DXY = pivot ET maillon faible : une lecture DXY inversée propage l'erreur
   aux 5 actifs.
5. Process > outcome : 0 trade « à raison » = victoire ; verdict Ichor et
   décision de trade jugés séparément.
6. **Manipulation/prise de liquidité = le signal le plus fiablement anticipé
   du corpus** (4 occurrences datées vérifiées : hunt 1,1656 du 27/05, sweep
   pré-PCE 28/05, sweep 16h45 du 03/06 « presque à la lettre », sweep 11h30 +
   purge open Nasdaq 08/06) `[HUB]` EXPLICITE — à pondérer en conséquence
   dans la probabilisation.

## 10. Gestion de trade — contexte de lecture UNIQUEMENT (frontière ADR-017)

> Codifié pour qu'Ichor comprenne ce qui confirme/invalide une thèse en cours
> de session. Jamais rendu comme instruction d'ordre. Le shaping descriptif
> RR existe déjà côté repo (`services/rr_analysis.py` : RR 3, BE à 1R, 90 % à
> RR 3 — cohérent avec les transcripts).

- Invalidation structurelle (placement conceptuel du stop) : juste au-dessus
  de la mèche du dernier plus haut local (15m) — « c'est la dernière mèche
  qui crée mon plus haut avant le boom donc gros retournement » `[T-G]`
  EXPLICITE — PAS sous la zone, PAS au plus haut structurel lointain (l'objet
  tradé est un momentum direct) `[T-C]`,`[T-B]`.
- Cible ≈ RR 3 (transcription « RR2.3 »/« RR23 » ambiguë — §13.2 ; la lecture
  RR 3 est corroborée par l'usage réel du hub : « courir jusqu'à R+3, couper
  l'essentiel à R+3 », débrief 06-09 `[HUB]`) ; BE à 1R (légèrement positif,
  spread/commissions) `[T-B]`,`[T-G]` EXPLICITE — **à 1R : passage à BE
  uniquement, AUCUNE clôture partielle avant la cible** `[T-G]` EXPLICITE ;
  90 % clôturés à la cible, 10 % courent jusqu'à 20h `[T-C]`,`[T-G]`.
- Dynamique binaire NY : « soit un tout droit vers le TP, soit c'est un range
  et on se fait SL » `[T-G]` EXPLICITE ; un retour au point d'entrée = marché
  structuré, thèse momentum morte `[T-B]`.
- **Exposition unique** : un seul risque ouvert à la fois (« un risque ouvert
  par jour et un SL par jour ») ; deux trades simultanés tolérés seulement si
  l'autre est déjà sécurisé à BE (« c'est comme si j'avais une seule
  position ») `[T-G]` EXPLICITE.
- BE n'invalide pas la thèse (re-lecture sur structure : réjection H1 +
  avalement, nouveau plus bas 15m + sortie de canal, golden zone + origine) ;
  BE avant 16h → re-entrée possible ; après 17h → journée finie ; SL → journée
  finie, anti-revenge absolu (« un SL par jour ») `[T-C]`,`[T-G]` EXPLICITE.
- Invalidation temporelle : à 20h la thèse du jour EXPIRE (volume mort →
  correction lente/range de dizaines d'heures) `[T-G]` EXPLICITE.
- Risque : 0,5 % par position en prop firm, fixe, sans modulation
  discrétionnaire `[T-G]` EXPLICITE (contexte ; hors périmètre Ichor).

## 11. Vocabulaire canonique

**Vocabulaire de rendu** (sections data_pool, frontend — FR, jargon SMC
interdit, jamais de token d'ordre) :
origine acheteuse/vendeuse · zone d'intérêt · poussée · correction
(structurée) · bougie pleine · bougie d'incertitude · mèche du plongeur /
mèche contraire · sens final · manipulation / prise de liquidité / se faire
chasser · momentum de session · carrés bleus (fenêtre NY) · l'overlap ·
golden zone · switch de canal · rejet/réjection · avalement · étoile du
matin/du soir · compréhension de marché · suite de confirmations · prix
psychologique · invalidation (chiffrée) · « sweep » (toléré, langue commune).

**Vocabulaire de compréhension** (lecture des sources et logique interne —
JAMAIS rendu dans un output d'Ichor, incompatible avec le filtre ADR-017) :
BE / SL à BE · RR de X · TP/SL · re-entrée · risque ouvert · prop firm.

## 12. Mapping vers l'implémentation (Chantier E)

| Élément méthodo                                                                        | Implémentation                                                                    | Statut                                                 |
| -------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------ |
| Grammaire bougies (pleine/incertitude, corps vs mèches)                                | `services/technical_analysis.py` pure core (+ `daily_candle_classifier` existant) | slice-1                                                |
| Poussée/correction + anomalie de rôle (H1)                                             | `technical_analysis.py`                                                           | slice-1                                                |
| Mèche du plongeur (statut quotidien Asie/Londres — toujours rapporté, cf. §5.2)        | `technical_analysis.py`                                                           | slice-1                                                |
| Origines H1 N1/N2 (+ tiers, retest, proximité)                                         | `technical_analysis.py`                                                           | slice-1 — provisional (cf. §13.1/§13.13, seuils §13.7) |
| Golden zone 0,5-0,618 sur dernière poussée H1                                          | `technical_analysis.py`                                                           | slice-1 — provisional (ancrage INFÉRÉE, cf. §13.6)     |
| Rendu Pass-2                                                                           | `_section_technical_methodology` (data_pool)                                      | slice-1                                                |
| Indicateur Pine (aide à la lecture d'Ichor)                                            | `docs/pine/ichor_lecture_technique.pine` + witness tradingview-cdp                | slice-1                                                |
| Corrélations DXY recalculées en continu                                                | as-built : `services/correlations.py` + `cross_asset` sections                    | déjà LIVE                                              |
| Séquence quotidienne complète (§6) + filtres no-trade + scénario/invalidation chiffrée | orchestration verdict (Chantier C/S06) — la section slice-1 fournit les briques   | différé                                                |
| Signal H1 clôture 12h-13h (§4)                                                         | nécessite lecture event-driven à 13h                                              | slice-2                                                |
| Déclencheurs 15m/5m (avalement, étoiles, 2-temps)                                      | slice-2 (agrégation 15m/5m + calibration)                                         | différé                                                |
| Canaux / switch de canal (§5.4)                                                        | non défini par les sources — bloqué sur §13.16                                    | différé                                                |
| DimensionVote technique (sign allowed)                                                 | post-Chantier C slice-1 (contrat figé, fusion intouchée)                          | différé                                                |
| Doctrine incohérence/conviction (fusion §9)                                            | Chantier C (fusion layer)                                                         | différé                                                |

Note de calibration (§0 récence) : tout backtest/calibration des seuils
provisoires se fait sur données récentes — les patterns se périment `[T-B]`.

## 13. Questions ouvertes `[TBD owner]` — à trancher par Eliot

1. **Hiérarchie origines : fin du niveau 2 + niveau 3** : T-P tronqué à
   ~30 min (TurboScribe gratuit). Indice `[T-C]` : les AOI ne sont placées
   que sur 2 niveaux → le niveau 3 n'est peut-être pas opérationnel. →
   Fournir la fin de la vidéo ou confirmer.
2. **Cible : « RR de 3 » ou « RR 2,3 » ?** (transcription ambiguë, 4
   occurrences). Évidence en faveur de RR 3 : « un RR de 1 ou un RR de 2 ou
   un RR de 6, de 12 » `[T-C]` + usage hub « couper l'essentiel à R+3 »
   (débrief 06-09). À confirmer.
3. **Fenêtre d'exécution : 13h-16h ou 14h-16h ?** T-P ET T-C disent 13h-16h
   (exécution) ; T-B valorise 14h-16h comme pic de qualité ; courbe de volume
   T-C : pic absolu à l'open US 15h-15h30, déclin dès 17h. Lecture probable :
   fenêtre = 13h-16h, qualité maximale 14h-16h. À confirmer.
4. **Seuil BE fin de journée : 17h ou 18h30 ?** (les deux sont dits, T-C).
5. **Bornes exactes des zones** : pratique T-B codifiée §7 (clôture →
   extension mèche, zone précise) — reste à trancher : quelle clôture
   exactement, largeur maximale, quand une zone est consommée/invalidée.
6. **Ancrage précis du Fibonacci** (quels swing high/low, quelle UT par
   défaut pour l'analyse vs l'exécution).
7. **Seuils quantitatifs** : « fort rejet » (ratio mèche/corps ?), « poussée
   de plus en plus grande » (mesure ?), « aux alentours » de la golden zone
   (tolérance ?). Slice-1 utilise des seuils provisoires DOCUMENTÉS dans le
   code (`technical_analysis.py`, constantes PROVISIONAL) — à calibrer.
8. **Indicateur de sessions** : paramétrage exact LuxAlgo (vidéo de référence
   non fournie).
9. **Re-entrées post-BE** : plafond exact (« pas 40 positions / 39 BE »).
10. **No Gap Candles** : réglage exact et impact sur la classification des
    bougies — les barres TimescaleDB d'Ichor peuvent diverger du chart no-gap
    d'Eliot (gaps week-end/illiquidité).
11. **Document « pourquoi ces 5 actifs / cette fenêtre »** : référencé par
    T-P, non fourni.
12. **Vidéo « compréhension de marché »** : dépendance explicite de la
    stratégie (T-P « on s'en sert beaucoup »), non fournie — les exemples
    codifiés en §5.1 en proviennent indirectement.
13. **Polarité du retest pour une zone vendeuse** : T-B ne démontre que le
    cas acheteur (« entre le haut et le milieu ») ; le miroir vendeur (entre
    le bas et le milieu, côté approche) est INFÉRÉE. À confirmer.
14. **Mèche du plongeur en continuation** : T-P/T-C disent « pas de mèche
    requise » en continuation ; T-B montre Eliot l'exiger quand même sur une
    continuation baissière. Laquelle prime ?
15. **Heure de clôture daily faisant foi** : 22h ou 23h Paris (DST), et
    quelle convention pour le module (le chart d'Eliot clôture 22h-23h, pas
    minuit).
16. **Canaux / switch de canal** : nommés comme partie du cœur H1, jamais
    définis formellement (qu'est-ce qui valide un switch ?). → Définir ou
    pointer la vidéo qui le couvre.

---

_Codifié 2026-06-12 (Session 05 / Chantier E, ADR-113). v1.1 : vérifié contre
les sources brutes par 6 agents adversariaux en contexte frais — 37 findings
pliés (détail : SESSION_LOG du jour). Toute évolution = nouvelle passe sur
les sources + mise à jour ici._
