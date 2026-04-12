# Message pour Léa — Activer le pipeline Closing

## Objectif
Obtenir une attribution parfaite VSL vs Follow sur chaque vente, sans rajouter de travail aux closers (juste 1 clic par call au lieu d'une form EOD plus longue).

## Le workflow

Le pipeline **"Closing"** existe déjà dans ton GHL avec les stages :
R1 Planifié → R1 No show → R2 Planifié → Follow Up → Gagné → Perdu → Annulé

### Ce qui change
1. **Automation GHL** : quand un call est booké sur l'un de tes 2 calendriers (VSL ou Follow), une carte est créée automatiquement dans le pipeline Closing avec :
   - Nom du contact
   - Source Funnel (tag "VSL" ou "Follow" selon le calendrier de booking)
   - Closer assigné
   - Date du RDV

2. **Les closers** (Anaïs, Audrey, Mary) : après chaque call, ils déplacent la carte vers :
   - **Gagné** si vente + ils remplissent le montant dans "Valeur de l'opportunité"
   - **R2 Planifié** si 2e RDV
   - **Follow Up** si à relancer
   - **Perdu** si passé
   - **Annulé** si no-show

   → C'est **1 clic par call** dans l'app GHL. Moins long que leur form EOD actuelle.

3. **Data auto** : chaque nuit je pull les cartes "Gagné" → j'ai :
   - Contact exact
   - Source funnel (VSL ou Follow)
   - Montant (pour distinguer cash contracté vs collecté plus tard)
   - Closer
   - Date

## Ce qu'on gagne

- **Attribution parfaite** VSL vs Follow sur chaque vente (plus d'ambiguïté)
- **Pipeline live** visible pour Léa (combien de deals en cours, où ils sont coincés)
- **Follow-ups trackés** (aujourd'hui perdus dans nature)
- **Historique par contact** conservé à vie
- **Form EOD simplifiée** ou supprimée si le pipeline couvre tout

## Ce qu'il faut

1. ✅ Pipeline Closing existe déjà
2. **À faire** : créer l'automation "Call booked → Create Opportunity" (5 min dans GHL Workflows)
3. **À faire** : message Loom de 2 min aux closers pour leur montrer le nouveau flow
4. **À faire** : décider si on garde ou supprime la form EOD

## Historique

Pour mars-avril (avant ce process) : on utilise ce qui existe déjà (form EOD + data manuelle du vieux dashboard). 99% des ventes historiques = Follow (VSL vient de lancer). Pas de data perdue.
