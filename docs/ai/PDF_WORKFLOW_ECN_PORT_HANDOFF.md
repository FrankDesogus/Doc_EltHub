# Handoff — portare il flusso ECN semplice + Archivio progetti su task/documentale-pdf-workflow

Data: 2026-07-29. Contesto precedente troppo pieno per continuare nella stessa
finestra — riprendere da qui in una nuova conversazione.

## STATO ESATTO ALL'INTERRUZIONE (leggere per primo)

**Aggiornamento 2026-07-29 (stessa data, nuova finestra):** la correzione
TASK-026 nel worktree `pdf-ecn-integration` è ora **committata** —
commit [`ddc77dd`](#) `Align project archive permissions to TASK-026
(Archivio progetti)`, in cima al branch
`task/documentale-pdf-ecn-integration` di quel worktree (sopra `46c8528`).
`git status` nel worktree è pulito.

Il primo tentativo di lanciare `manage.py test projects --keepdb` era
**fallito** (5 errori, tutti in `AuditUIProjectDetailTests`): quella classe
di test non era stata aggiornata insieme al resto — asseriva ancora sulle
chiavi di contesto `show_audit`/`audit_logs` in `project_detail`, rimosse
dalla stessa correzione TASK-026 (spostate in `archive_project_detail`).
Corretta riscrivendo i 5 test per verificare `can_view_project_archive` e il
link "Vedi storico completo" al posto di quelle chiavi — stesso schema di
ruoli coperto (manager/document-manager, auditor globale, folder-auditor,
reader). Il commit finale copre anche altri aggiustamenti minori ad
`ArchiveProjectListViewTests`/`ProjectHistoryViewTests` e alle classi
correlate elencate nel messaggio di commit.

Suite `projects` completa: **429/429 OK** (confermato dopo la correzione;
nota: la prima esecuzione via tool in background veniva uccisa al cap di
10 minuti del tool anche con `run_in_background`, perché la suite reale
richiede ~35-37 minuti — è stata infine lanciata come processo Windows
staccato via `Start-Process` per sopravvivere oltre quel limite. Se serve
rilanciarla in una sessione futura, usare lo stesso approccio invece di
`run_in_background` diretto).

`manage.py check` e `manage.py makemigrations --check --dry-run`: puliti.

Non è stato ancora fatto **nessun cherry-pick** sul branch
`task/documentale-pdf-workflow` — il lavoro lì è ancora zero, tutto il resto
di questo documento descrive cosa fare. Questo resta il prossimo passo
(sezione "Come procedere nella nuova finestra", punto 3 in poi — i punti 1
e 2 sono ora completati).

⚠️ **Attenzione branch nel worktree principale**: durante questa sessione il
worktree principale (`Ai-Station`) è stato trovato checked out su `main`
(HEAD `6290813`, 9 commit avanti a `origin/main`, con lavoro recente non
correlato — TASK-019/020/021 "Archivio" lato documenti, fix Windows), non
più su `task/documentale-pdf-workflow` (che resta intatto a `949b224`,
invariato). Non è stato toccato né modificato nulla su `main` in questa
sessione. Prima di fare qualunque cherry-pick, verificare con `git status`
e fare `git checkout task/documentale-pdf-workflow` nel worktree
principale — probabilmente è stato usato in parallelo per altro lavoro,
non è un errore di questa sessione ma va controllato prima di procedere.

## Situazione

Due branch fratelli nello stesso repo monorepo (Ai-Station), **stessa base
comune**, nessun problema di storie non correlate:

```
git merge-base task/documentale-pdf-workflow task/documentale-pdf-ecn-integration
→ 949b224   (= HEAD attuale di task/documentale-pdf-workflow)
```

- **`task/documentale-pdf-workflow`** (branch di lavoro attuale, worktree
  principale `C:\Users\riccardo.dibiagio\PycharmProjects\AI-Station-documentale\Ai-Station`,
  cartella progetto `projects/documentale-workcopy`): contiene il flusso PDF
  di rappresentazione / PDF approvato / firma visiva (TASK-023→035). **Non ha
  nessun concetto di "ECN a flusso semplice"** — solo il vecchio
  `requires_ecn_for_revision` (esenzione totale da ECN, ECNPOL-1).
- **`task/documentale-pdf-ecn-integration`** (worktree secondario
  `C:\Users\riccardo.dibiagio\AppData\Local\Temp\pdf-ecn-integration\projects\documentale-workcopy`):
  branchato dalla stessa punta (949b224), aggiunge sopra: il flusso ECN
  semplice (TASK-022), il flag per vietarlo per documento (AREA A), upload
  PDF inline nel gate approvazione (AREA B), generalizzazione auto-chiusura
  ECN, fix vari, e una sezione "Archivio progetti" (TASK 2/TASK-026).

## Perché serve un port e non un semplice merge

L'utente ha chiesto **solo un sottoinsieme** delle modifiche presenti su
`pdf-ecn-integration`, non tutto il branch (niente TASK 3 design doc, niente
handoff doc dell'altro lato). Un merge secco porterebbe anche cose non
volute. Va fatto un **cherry-pick ordinato** dei soli commit richiesti.

Poiché `pdf-ecn-integration` è stato branchato ESATTAMENTE dalla punta
attuale di `pdf-workflow`, i cherry-pick in ordine cronologico dovrebbero
applicarsi **senza conflitti** (il tree di partenza coincide).

## Scope deciso con l'operatore

1. **Flusso ECN semplice + divieto per documento** (approvato, "Minimo + fix
   correlati ECN/PDF"):
   - `7a5417f` Define TASK-022: simple/automatic ECN flow
   - `ace08aa` TASK-022: flusso ECN semplice per revisioni rapide
   - `7346ae9` Merge branch 'task/documentale-simple-ecn-flow' (merge commit —
     va cherry-pickato con `-m 1` oppure ricreato applicando i singoli commit
     del branch `task/documentale-simple-ecn-flow` se il cherry-pick del merge
     dà problemi; verificare `git log --oneline 949b224..task/documentale-simple-ecn-flow`
     per l'elenco preciso se serve il fallback)
   - `d48a142` Fix ECN closure lifecycle contradiction e auto-close flusso semplice (AREA 3)
   - `85599f2` Generalizza auto-chiusura ECN al flusso standard + notifica CCB
   - `eeec327` Add Document.allow_simple_ecn: vieta ECN a flusso semplice per documento (AREA A)
   - `1044a54` Upload PDF inline nel gate di invio in approvazione (AREA B)
   - `6b14963` Rinomina label stato ECN "In Revisione CCB" → "In Valutazione CCB"
   - `9e43310` Fix PDF workflow discoverability gaps
   - `c91bca3` Fix link /media/ rotto nella pagina admin UserSignature
   - `4abd306` Estendi demo_full con firme visive e flusso PDF approvato
   - `b0a62d1` Restrict allow_simple_ecn editing a superuser/demo-supervisor
     dopo la creazione (decisione operatore già presa e discussa)

   Commit **doc-only, opzionali** (portarli è innocuo ma non necessario):
   `b8004d2`, `d15e253`, `ead325b` (aggiornano `docs/ai/TASKS.md` nell'altro
   worktree — se portati, andranno probabilmente adattati al `TASKS.md` di
   questo branch invece che copiati alla cieca).

   **Da NON portare**: `46c8528` (handoff doc dell'altro lato, non pertinente
   qui), `ce2f75f` (design doc TASK 3 permessi granulari — fuori scope,
   chiedere all'operatore se interessa separatamente).

2. **Sezione "Archivio progetti"** (richiesta dall'operatore in un secondo
   momento, "anche la sezione archivi... la devi importare da un altro
   branch"): **non usare il commit originale `766d859`** (ha permessi
   sbagliati — stessa visibilità debole di `project_detail` invece del
   permesso più alto coerente con `can_view_audit`). È stato corretto e
   **committato** nel worktree `pdf-ecn-integration`: commit `ddc77dd`
   `Align project archive permissions to TASK-026 (Archivio progetti)`,
   sopra `46c8528`. Suite `projects` completa 429/429 OK dopo la correzione
   (vedi nota sopra su `AuditUIProjectDetailTests`).
   **Cherry-pickare `766d859` seguito da `ddc77dd`**, oppure,
   se il cherry-pick di `766d859` da solo desse conflitti (perché la sua
   diff presuppone tutti i commit precedenti dell'elenco sopra già
   applicati — motivo per cui l'ordine cronologico va rispettato), applicare
   prima tutta la sequenza del punto 1 e solo dopo questi due.

   Riepilogo della correzione (committata in `ddc77dd`):
   - `projects/permissions.py`: nuova `can_view_archived_project(user, project)`
     → `can_view_audit(user, folder=project.root_folder)`.
   - `projects/views.py`: `project_history` rinominato `archive_project_detail`,
     gate `can_view_archived_project(...)` + `raise Http404` (non più
     `_assert_can_view_project`/`PermissionDenied`); `archive_project_list`
     riscritto con `can_view_archive(request.user)` + `Http404` (non più
     filtro per-progetto su `get_project_visible_folder_ids`);
     `project_revision_detail` aggiornato a `can_view_archived_project(...)`
     + `PermissionDenied` (non `Http404` — qui l'oggetto esiste già come URL
     noto, quindi 403 non 404); `project_detail` ora calcola
     `current_baseline = project.revisions.filter(is_current=True,
     snapshot_type='revision').select_related('issued_by').first()` invece di
     `snapshot_count`/`latest_snapshot`, e passa `can_view_project_archive`
     al context (non più `show_audit`/`audit_logs`/`save_version_url`/
     `save_revision_url`, tutti confinati nella vista archivio).
   - `config/urls.py`: `archive_project_detail` registrato direttamente
     (come `archive_document_detail`) su `archivio-progetti/<int:project_id>/`,
     rimosso da `projects/project_urls.py` (`<int:project_id>/history/`).
   - Template: `project_history.html` → `archive_project_detail.html`
     (contenuto allineato al riferimento, con l'aggiunta della sezione
     ECN/Varianti collegate già presente in questa sessione, assente nel
     riferimento); `project_detail.html` sostituita la sezione "Storico
     progetto" con una card "Ultima revisione salvata"
     (Revisione/Stato/Emessa il/Emessa da), link "Vedi storico completo"
     condizionato da `can_view_project_archive`; `archive_project_list.html`
     arricchita con colonne Versione/Revisione dal riferimento;
     `base.html` — bug corretto: il link "Archivio progetti" in sidebar era
     **fuori** dal blocco `{% if sb_can_archive %}` (visibile a chiunque),
     ora dentro insieme al link "Archivio documenti".
   - `projects/tests.py`: `ProjectHistoryViewTests`/`ArchiveProjectListViewTests`
     e i test in `ProjectRevisionViewTests`/`BaselineComparisonTests`/
     `SaveFolderPermissionModularTests`/VH-3 aggiornati per il nuovo nome
     URL e i nuovi permessi (alcuni test con solo `read_published`/
     `view_projects` ora si aspettano **404** invece di 403, perché il
     permesso di Archivio è strutturalmente più alto — non raggiungibile
     nemmeno con permessi "normali" di visualizzazione progetto).

## Come procedere nella nuova finestra

1. ✅ **Fatto.** Entrambi i worktree presenti, nessuna modifica non
   committata persa.
2. ✅ **Fatto.** `pdf-ecn-integration` ha la correzione TASK-026 committata
   in `ddc77dd` (vedi sopra), suite `projects` 429/429 OK.
3. **Prossimo passo.** Sul branch `task/documentale-pdf-workflow` (worktree
   principale),
   eseguire i cherry-pick nell'ordine cronologico elencato sopra (punto 1,
   poi punto 2). Es.:
   ```powershell
   git cherry-pick 7a5417f ace08aa
   git cherry-pick -m 1 7346ae9   # se serve, altrimenti singoli commit del branch simple-ecn-flow
   git cherry-pick d48a142 85599f2 eeec327 1044a54 6b14963 9e43310 c91bca3 4abd306 b0a62d1
   git cherry-pick 766d859 ddc77dd
   ```
   Risolvere eventuali conflitti (dovrebbero essere minimi/assenti, vista la
   base comune) confrontando con l'intento descritto sopra, non accettando
   ciecamente una versione.
4. Dopo ogni blocco di cherry-pick: `manage.py check`,
   `manage.py makemigrations --check --dry-run` (occhio: questi commit
   introducono modelli nuovi — `Document.allow_simple_ecn`,
   `UserSignature` già presente da pdf-workflow — verificare che le
   migrazioni generate dai due branch non collidano su nomi/numeri file;
   potrebbe servire rinumerare una migrazione se entrambi i branch hanno
   creato una migration con lo stesso numero progressivo per app diversa
   ragione).
5. Eseguire test mirati (`ecn`, `documents`, `projects`, `accounts`) con
   `--keepdb`, poi la suite combinata prima di considerare il lavoro
   concluso. Politica del progetto: non lanciare suite complete per piccoli
   cambi, ma questo è un port sostanzioso — giustifica una suite ampia a
   fine lavoro.
6. Riavviare il server dev (`manage.py runserver`, `DOCUMENTALE_DEMO_MODE`
   già `true` in `.env`) e verificare a mano: form creazione documento
   mostra il checkbox "vieta ECN semplice"; sezione "Archivio progetti" in
   sidebar visibile solo a Manager/Auditor/Quality Manager o utenti con
   grant `view_history`.
7. Non pushare automaticamente — chiedere conferma prima di
   `git push` su `documentale-new` o altrove (regola permanente di questo
   progetto).

## Cose da NON fare

- Non forzare un merge `--allow-unrelated-histories` da nessuna parte — non
  serve qui, i due branch condividono la base.
- Non copiare/incollare alla cieca `docs/ai/TASKS.md` dall'altro worktree:
  ha una numerazione/roadmap diversa da quella di questo branch — se si
  vogliono portare le voci doc-only, riscriverle adattate.
- Non eliminare il worktree `pdf-ecn-integration` finché il port non è
  verificato e magari già committato: resta la fonte di riferimento in
  caso di conflitti da risolvere.
