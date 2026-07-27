# Flusso ECN semplice (TASK-022)

Guida di riferimento al flusso "ECN semplice", introdotto per sostituire
la vecchia modalità "revisione senza ECN" come percorso demo principale.

---

## Perché esiste

Prima di TASK-022, un documento poteva essere configurato con
`requires_ecn_for_revision=False` ("revisione senza ECN"): le revisioni
successive alla prima approvazione non richiedevano alcun ECN, solo il
normale ciclo di approvazione (DRAFT → IN_APPROVAL → APPROVED).

La nuova regola di prodotto è: **ogni revisione deve essere collegata a
un ECN**. Per non appesantire i casi a basso impatto con l'intero
processo di istruttoria/CCB, esistono ora **due flussi ECN**:

| | ECN standard | ECN semplice |
|---|---|---|
| Istruttoria/dossier CCB | Sì | No |
| Convocazione CCB | Sì (se necessaria) | No |
| Approvatori multipli | Sì (ANY/ALL/SEQUENTIAL) | No |
| Stato dopo la creazione | `DRAFT` | `APPROVED` (immediato) |
| Chiusura Qualità | Sì (`close_change_notice`) | No (resta `APPROVED`) |
| Codice | `ECN-NNNN` | `ECN-S-<anno>-NNNN` |
| Traccia audit/storico | Sì | Sì (identica) |

## Quando usare quale

- **ECN standard**: variante che richiede valutazione tecnica formale,
  impatto significativo, coinvolgimento CCB, o classificazione
  Classe 1/Classe 2.
- **ECN semplice**: revisione rapida, basso impatto, nessuna necessità
  di istruttoria collegiale (es. correzione refuso, aggiunta campo,
  chiarimento redazionale).

La scelta è lasciata all'operatore al momento della revisione — non
c'è un criterio automatico che impone l'uno o l'altro.

## Come viene generato il codice

`ecn/services.py::_generate_simple_ecn_code()` genera
`ECN-S-<anno corrente>-NNNN` (es. `ECN-S-2026-0001`), contando gli ECN
semplici già creati nell'anno corrente più un ciclo anti-collisione —
stesso principio di `_generate_ecn_code()` (usato per gli ECN
standard, formato `ECN-NNNN`), solo con prefisso diverso per
distinguerli a colpo d'occhio in ogni lista/storico.

Nota: gli ECN demo `ECN-S-01`…`ECN-S-06` creati da
`_scenario_ecn_all_states` in `demo_full.py` sono codici manuali
preesistenti (scenario "stati ECN"), non generati da questa funzione —
coincidenza di prefisso, nessuna collisione reale (formato diverso:
`ECN-S-01` vs `ECN-S-2026-0001`).

## Cosa significa "autoapprovazione"

`create_simple_ecn(document, proposed_by, title, description='', ...)`
crea il `ChangeNotice` **direttamente in stato `APPROVED`**
(`flow_type=SIMPLE`), impostando `ccb_reviewed_by`/`ccb_reviewed_at`
come marcatore di chi/quando ha autoapprovato, senza passare da
`DRAFT` → `CCB_PREPARATION` → `UNDER_REVIEW`. Non viene creato alcun
`ChangeNoticeApprover`/`ChangeNoticeDecision`: non c'è nessuna CCB da
votare.

L'ECN semplice non viene mai chiuso (`close_change_notice`): resta
`APPROVED` in modo permanente — per design, "approvato" è già lo stato
finale equivalente per questo flusso (non c'è verifica qualità di
chiusura da fare).

## Come si collega alla revisione documento

**Nessuna modifica è stata fatta a `create_new_revision`.** Il gate
esistente (`documents/services.py`) controlla solo:

1. `ecn.document_id == document.pk`
2. `ecn.status == ChangeNotice.Status.APPROVED`
3. `ecn.executed_version_id is None` (non ancora usato)

Un ECN semplice approvato soddisfa queste tre condizioni esattamente
come un ECN standard approvato dalla CCB — si passa `ecn=<simple_ecn>`
a `create_new_revision` senza `_bypass_ecn_check`, e la funzione
collega automaticamente `executed_version`/`executed_at` come sempre.

### Flusso UI (due step)

1. Da `document_detail.html`, pulsante **"+ Crea ECN semplice"** →
   form minimo (titolo + descrizione) → creazione e autoapprovazione
   immediata, redirect a `document_detail` con messaggio di successo.
2. L'ECN semplice compare automaticamente tra gli "ECN approvati
   disponibili" in `new_revision.html` (nessuna modifica alla query
   `available_ecns`, già filtrata per `APPROVED` + non eseguito) —
   badge "Semplice" nella colonna Tipo per distinguerlo da uno
   standard. L'utente clicca "Usa questo ECN" come già oggi.

Il pulsante **"+ Richiedi ECN standard"** resta disponibile accanto,
per chi ha bisogno del flusso CCB completo.

## Permessi

Nessun permesso nuovo introdotto. `ecn_create_simple` riusa
`can_create_ecn(user, document)`, identico alla view standard
`ecn_create`.

## Cosa si vede nello storico

- **Dettaglio compatto** (`document_detail.html`, fuori Archivio):
  card "Ultimo ECN / Variante" — se l'ECN semplice è il più recente,
  compaiono qui i suoi dettagli (codice, titolo, stato, proponente,
  data), esattamente come per un ECN standard.
- **Archivio** (`archive_document_detail.html`): tabella "ECN /
  Varianti collegate" completa, include tutti gli ECN semplici e
  standard del documento, senza distinzione di visibilità.

## La vecchia modalità "revisione senza ECN" (legacy)

`Document.requires_ecn_for_revision` e il form field `ecn_exemption`
**non sono stati rimossi** dal modello/form (per non rischiare
migrazioni o rompere test esistenti). Sono stati **rimossi solo dalla
UI di creazione documento** (`new_document.html`): i nuovi documenti
creati da interfaccia hanno sempre `requires_ecn_for_revision=True`
(già il default).

I documenti **esistenti** con `requires_ecn_for_revision=False`
continuano a funzionare esattamente come prima (percorso "+ Nuova
revisione" diretto, badge "approvazione diretta senza ECN") — nessuna
migrazione dati, nessuna rottura.

## Dati demo

`demo_full.py`, scenario `_scenario_simple_ecn` (documento
`DEMO-ECN-SIMPLE-001`, ex `DEMO-NOSCOPE-001`): prima revisione diretta
(bootstrap, nessuna versione corrente ancora), poi un vero ECN
semplice (`create_simple_ecn`, non un bypass) autorizza la seconda
revisione. Dimostra il flusso reale, non un mock.

Gli scenari `_scenario_multi_revision`, `_scenario_rejected_revision`
e `_scenario_approval_policies` continuano a usare
`_bypass_ecn_check=True` internamente per costruire rapidamente dati
demo non collegati a questa funzionalità (multi-revisione, rifiuto,
policy di approvazione) — non mostrano il bypass come feature
all'utente, quindi non sono stati convertiti (fuori scope, per non
fare refactor ampi non richiesti).

## Backlog / fuori scope

- Rimozione definitiva di `requires_ecn_for_revision`/`ecn_exemption`
  dal modello, una volta che tutti i documenti reali siano migrati a
  richiedere sempre un ECN.
- Badge "Tipo" (Standard/Semplice) in `ecn_list.html`/`ecn_detail.html`
  — oggi il prefisso del codice (`ECN-S-...` vs `ECN-...`) è già
  sufficiente a distinguerli a colpo d'occhio; aggiunta rimandata per
  costo/beneficio marginale.
- Permessi dedicati per l'ECN semplice (oggi riusa `can_create_ecn`
  senza distinzioni) — da valutare se in futuro serve limitare chi
  può creare ECN semplici rispetto a chi crea ECN standard.
