# Run Log

Registro delle esecuzioni dei cicli AI su questo progetto.

---

## Template

### Run — YYYY-MM-DD HH:MM — Titolo del task

**Agente:** Claude Code | Codex | Cursor | Altro
**Task:** <!-- riferimento a TASKS.md, es. #ID Titolo -->
**Branch:** <!-- nome del branch usato -->

**Operazioni eseguite:**
<!-- Cosa ha fatto l'agente, in ordine -->

1.

**Esito test (`scripts/test.sh`):**

```
# incolla qui l'output
```

**Problemi riscontrati:**
<!-- Errori, ambiguità, stop forzati. Vuoto se nessuno. -->

-

**Prossimo passo per l'operatore umano:**
<!-- Cosa deve fare l'operatore ora: approvare, correggere, committare, altro -->

---

<!-- Aggiungi i run qui sotto in ordine cronologico -->

### Run — 2026-07-05 — TASK-001 Analisi iniziale progetto Documentale

**Agente:** Cursor Agent
**Task:** TASK-001 — Analisi iniziale progetto Documentale
**Branch:** task/onboard-documentale-workcopy

**Operazioni eseguite:**

1. Letti `docs/ai/TASKS.md`, `AGENTS.md`, `scripts/test.sh` (obbligatori pre-modifica).
2. Analisi read-only di documentazione e codebase: `CLAUDE.md`, `README.md`, `AI_CONTEXT.md`, `PROJECT_HANDOFF.md`, `DEPLOY.md`, `requirements.txt`, `package.json`, `config/`, app Django, migrazioni, template.
3. Creato `docs/ai/PROJECT_ANALYSIS.md` con tutte le sezioni richieste (panoramica, stack, struttura, entry point, dipendenze, comandi, deploy, file sensibili, rischi, problemi, roadmap TASK-002…, raccomandazione).
4. Nessun file applicativo modificato; `scripts/test.sh` non toccato.
5. Nessun commit eseguito.

**Esito test (`scripts/test.sh`):**

```
== Test: documentale-workcopy ==
Nessun test ancora configurato per questo progetto.
Sostituire questo script con il comando di test reale (pytest, npm test, ...).
Exit code: 0
```

Verifica: script placeholder invariato (`exit 0` esplicito). L'operatore può riconfermare con:
`cd projects/documentale-workcopy && ./scripts/test.sh`

**Problemi riscontrati:**

- Nessuno bloccante. Shell non eseguibile dall'agente in questa sessione; esito dedotto da contenuto statico dello script (placeholder Station, exit 0 garantito).

**Prossimo passo per l'operatore umano:**

1. Leggere `docs/ai/PROJECT_ANALYSIS.md`.
2. Trascrivere nel Backlog di `docs/ai/TASKS.md` la roadmap proposta (TASK-002…).
3. Spostare TASK-001 in Completati dopo review positiva.
4. Avviare **TASK-002** (collegare `scripts/test.sh` alla suite Django) — raccomandazione esplicita nel report.

---

### Run — 2026-07-05 — TASK-002 Collegare test reali Django

**Agente:** Cursor Agent (implementazione) + Claude Code (fix + verifica esecuzione)
**Task:** TASK-002 — Collegare test reali Django
**Branch:** task/documentale-test-bootstrap

**Operazioni eseguite:**

1. Cursor Agent ha sostituito il placeholder `scripts/test.sh` con controlli
   reali: verifica dipendenze `requirements.txt`, `python -m compileall`,
   `manage.py check`, `manage.py test` (SQLite `:memory:`, no `.env`, no
   server, no migrazioni reali).
2. Cursor Agent ha creato `config/test_settings.py`: SECRET_KEY fittizia
   impostata via env var prima dell'import di `config.settings` (evita
   `UndefinedValueError` di `python-decouple` senza `.env`), poi override di
   `DATABASES` (SQLite `:memory:`) ed `EMAIL_BACKEND` (`locmem`).
3. Cursor Agent non ha potuto eseguire `bash`/`python3` nella propria
   sessione (shell disabilitata) e non ha aggiornato questo log, per non
   dichiarare un esito non verificato — comportamento corretto.
4. **Claude Code (reviewer)** ha eseguito `ai-cycle.sh --run`, che ha
   correttamente fermato il ciclo allo STEP 5 (`Test falliti`): bug reale di
   sintassi bash in `scripts/test.sh` riga 55
   (`pkg="${pkg%%[*"` — parentesi non chiusa, causava `EOF non atteso`).
5. Bug corretto (una riga: `pkg="${pkg%%\[*}"`), sintassi verificata
   (`bash -n`), script rieseguito manualmente.
6. Corretta anche una discrepanza di formattazione `shfmt` (`< "${FILE}"` →
   `<"${FILE}"`).

**Esito test (`scripts/test.sh`):**

```
== Test: documentale-workcopy ==
Root progetto: /home/frank/AI-Software-Station/projects/documentale-workcopy
Python: Python 3.14.5
Settings di test: config.test_settings

== 0/3 — Verifica dipendenze Python (requirements.txt) ==
Dipendenze mancanti:
  - asgiref (import asgiref)
  - Django (import django)
  - django-filter (import django_filters)
  - djangorestframework (import rest_framework)
  - gunicorn (import gunicorn)
  - psycopg (import psycopg)
  - python-decouple (import decouple)
  - sqlparse (import sqlparse)
  - tzdata (import tzdata)
ERRORE: Impossibile eseguire controlli Django reali. Installare le dipendenze da requirements.txt (fuori da questo script).
Exit code: 1
```

Questo è l'esito **atteso e corretto** in questo ambiente: la AI Software
Station non ha un virtualenv con le dipendenze del Documentale installate
(per design — nessuna installazione automatica di pacchetti), quindi lo
script fallisce onestamente invece di dare un falso `exit 0`. `shellcheck` e
`shfmt` puliti; `bash -n` e `python -m py_compile config/test_settings.py`
OK.

**Problemi riscontrati:**

- Bug di sintassi bash introdotto dall'implementazione (vedi sopra), corretto
  in review prima del commit.
- Ambiente Station privo delle dipendenze Python del Documentale: lo script
  non può eseguire i controlli Django reali qui. Non bloccante per il merge
  di questo task (lo script è corretto e sicuro), ma la suite Django
  completa (~1100+ test) resta da eseguire in un ambiente con
  `pip install -r requirements.txt` (venv dedicato, non creato in questo
  task per non violare il guardrail "nessuna installazione di pacchetti").

**Prossimo passo per l'operatore umano:**

1. Per validare i controlli Django reali: creare un virtualenv locale (fuori
   da questo workflow automatico) con `pip install -r requirements.txt` ed
   eseguire `./scripts/test.sh` per confermare che compile/check/test
   passino sul codice reale.
2. Spostare TASK-002 in Completati dopo review positiva.
3. Procedere con i task successivi della roadmap (`PROJECT_ANALYSIS.md`):
   TASK-003 bootstrap ambiente dev, TASK-004 migrazione permessi cartella, ecc.

---

### Run — 2026-07-05 — TASK-003 Preparare ambiente test dedicato Documentale

**Agente:** Claude Code (con autorizzazione esplicita dell'operatore per
installare pacchetti solo in una venv dedicata alla copia)
**Task:** TASK-003 — Preparare ambiente test dedicato Documentale
**Branch:** task/documentale-test-env

**Operazioni eseguite:**

1. Creata venv dedicata: `projects/documentale-workcopy/.venv` (Python
   3.14.5, pip 26.1.1). Già coperta da `.gitignore` esistente (`.venv/`),
   mai committata.
2. Installate le dipendenze con `.venv/bin/pip install -r requirements.txt`
   — solo in questa venv, nessun pacchetto globale, nessun `sudo`.
3. Eseguito `scripts/test.sh` con la venv attivata.
4. Aggiornati `docs/ai/TESTING_STATUS.md` (esito reale) e `docs/ai/TASKS.md`
   (TASK-003 → Completati, checklist spuntata).
5. Nessuna modifica alla logica applicativa. Nessun `.env` letto, nessun
   database reale toccato, nessun server avviato, nessuna migrazione su
   database reale (solo SQLite `:memory:` interno al test runner Django).
6. Nessun commit eseguito in questo step (fatto separatamente via
   `commit-if-approved.sh` dopo review).

**Esito test (`scripts/test.sh`, con venv `.venv` attiva):**

```
== 0/3 — Verifica dipendenze Python (requirements.txt) ==
OK — dipendenze di requirements.txt importabili.

== 1/3 — Compilazione e sintassi Python ==
OK — compilazione/sintassi Python superata.
(1 SyntaxWarning non bloccante in documents/versioning.py:9)

== 2/3 — Django manage.py check (settings di test, no .env) ==
System check identified no issues (0 silenced).
OK — manage.py check superato.

== 3/3 — Django manage.py test (SQLite :memory:, no migrate/runserver) ==
Ran 1207 tests in 489.755s
OK
Found 1207 test(s).
System check identified no issues (0 silenced).
OK — manage.py test superato.

Tutti i controlli completati con successo.
Exit code: 0
```

**Problemi riscontrati:**

- `documents/versioning.py:9` — `SyntaxWarning` cosmetico (escape sequence
  `\d` non raw string). Non bloccante, tutti i test passano comunque. Non
  corretto in questo task (è codice applicativo, fuori scope di TASK-003).
- Molti messaggi informativi "Email non inviata: ... senza indirizzo email"
  e un messaggio "Errore durante apply: Errore simulato in test atomicità"
  durante l'esecuzione: comportamento atteso di test che verificano
  rollback/notifiche, non fallimenti.

**Prossimo passo per l'operatore umano:**

1. Ricordare che la venv `.venv` è locale a questa macchina/sessione: va
   ricreata (`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`)
   da chiunque riprenda il lavoro, e i cicli `ai-cycle.sh --run` futuri
   NON la attivano automaticamente.
2. Valutare se aprire un piccolo task dedicato per correggere il
   `SyntaxWarning` in `documents/versioning.py:9`.
3. Procedere con i task successivi della roadmap in
   `docs/ai/PROJECT_ANALYSIS.md` (es. migrazione permessi cartella, pulizia
   dipendenze inutilizzate, allineamento documentazione).

---

### Run — 2026-07-06 — TASK-004 Correggere SyntaxWarning in versioning

**Agente:** Claude Code (fix diretto come orchestratore, task di una riga —
autorizzato esplicitamente dall'operatore per micro-fix di questa entità)
**Task:** TASK-004 — Correggere SyntaxWarning in versioning
**Branch:** task/documentale-fix-versioning-warning

**Operazioni eseguite:**

1. Analizzato `documents/versioning.py`: il `SyntaxWarning` proviene dal
   docstring di modulo (riga 1-13, stringa non raw contenente `\d` come
   testo descrittivo), non dalla regex compilata `_RE_NUMERIC` (riga 20,
   già `r'^\d+$'` corretta).
2. Fix applicato: `"""` → `r"""` sul docstring di apertura. Nessun'altra
   modifica.
3. Verificato con `ast.parse` + `python -W error::SyntaxWarning`: nessun
   warning residuo.
4. Eseguita la suite Django completa con la venv `.venv` attivata:
   1206/1207 test PASS, 1 fallimento
   (`test_document_list_shows_approval_date`).
5. **Verifica di indipendenza (test di controllo A/B):** ripristinato
   temporaneamente `documents/versioning.py` alla versione originale
   (`git stash`) e rieseguito il test isolato: fallisce **identicamente**.
   Confermato che il fallimento è pre-esistente e indipendente dal fix.
   Fix ripristinato (`git stash pop`).
6. Causa del fallimento identificata: bug di fuso orario nel test stesso
   (confronta `strftime` su datetime UTC non convertito con il rendering
   del template, localizzato in Europe/Rome — vicino alla mezzanotte
   CEST/UTC le due date possono differire di un giorno). Non è una
   regressione, non è collegato al fix, non è codice applicativo di
   produzione (il template localizza correttamente).
7. Aggiornati `docs/ai/TESTING_STATUS.md` e `docs/ai/TASKS.md` con
   entrambi gli esiti, documentati onestamente.

**Esito test (`scripts/test.sh`, con venv `.venv` attiva):**

```
== 1/3 == OK — compilazione/sintassi Python superata. (nessun SyntaxWarning)
== 2/3 == System check identified no issues (0 silenced).
== 3/3 == Ran 1207 tests in 480.905s — FAILED (failures=1)
```

Test isolato di controllo (stesso test, file originale ripristinato):
FAILED identicamente — fallimento confermato indipendente dal fix.

**Problemi riscontrati:**

- 1 test fragile su confine di fuso orario, pre-esistente, non corretto
  (fuori scope di TASK-004): vedi `docs/ai/TESTING_STATUS.md`.

**Prossimo passo per l'operatore umano:**

1. Valutare un piccolo task dedicato per correggere
   `test_document_list_shows_approval_date` in `documents/tests.py`
   (usare `timezone.localtime()` nell'assert).
2. Procedere con i task della roadmap in `docs/ai/PROJECT_ANALYSIS.md`.

---

### Run — 2026-07-06 — TASK-005 Correggere test approval date timezone

**Agente:** Claude Code (fix diretto come orchestratore, task di una riga)
**Task:** TASK-005 — Correggere test approval date timezone
**Branch:** task/documentale-fix-approval-date-test

**Operazioni eseguite:**

1. Analizzata la causa esatta: `approved_at` impostato con `timezone.now()`
   in `approvals/services.py` (datetime UTC-aware); il template
   `templates/documents/document_list.html` lo renderizza con
   `|date:"d/m/Y"`, che converte automaticamente in `Europe/Rome`; il test
   confrontava invece con `strftime` diretto sul datetime UTC (nessuna
   conversione) — mismatch possibile vicino alla mezzanotte CEST.
2. Fix applicato in `documents/tests.py`,
   `test_document_list_shows_approval_date`:
   `v.approved_at.strftime('%d/%m/%Y')` →
   `timezone.localtime(v.approved_at).strftime('%d/%m/%Y')`
   (`timezone` già importato). Nessuna altra modifica.
3. Test mirato isolato: PASS.
4. Suite Django completa (venv `.venv` attiva): **1207/1207 PASS**, 0
   warning, `manage.py check` pulito.
5. Aggiornati `docs/ai/TESTING_STATUS.md` e `docs/ai/TASKS.md`.
6. Nessuna modifica a view, modelli, template o migrazioni. Nessun file
   del progetto sorgente originale toccato.

**Esito test (`scripts/test.sh`, con venv `.venv` attiva):**

```
Ran 1207 tests in 502.104s
OK
Tutti i controlli completati con successo.
Exit code: 0
```

**Problemi riscontrati:**

- Nessuno. Suite completamente verde, nessun warning residuo.

**Prossimo passo per l'operatore umano:**

1. Procedere con i task della roadmap in `docs/ai/PROJECT_ANALYSIS.md`
   (es. migrazione permessi cartella, pulizia dipendenze inutilizzate,
   allineamento documentazione).

---

### Run — 2026-07-06 — Organizzazione backlog operativo roadmap

**Agente:** Claude Code (solo documentazione, nessun codice applicativo)
**Task:** N/A — riorganizzazione `docs/ai/TASKS.md`
**Branch:** task/documentale-roadmap-backlog

**Operazioni eseguite:**

1. Letti `PROJECT_ANALYSIS.md`, `TESTING_STATUS.md`, `TASKS.md`,
   `RUN_LOG.md` per ricostruire lo stato reale (TASK-001..005 completati,
   suite 1207/1207 PASS, nessun problema noto residuo).
2. Trasformata la roadmap di `PROJECT_ANALYSIS.md` in Backlog operativo in
   `docs/ai/TASKS.md`: TASK-006 (audit permessi, solo analisi), TASK-007
   (migrazione permessi, dipende da TASK-006), TASK-008 (audit dipendenze),
   TASK-009 (pulizia dipendenze, dipende da TASK-008), TASK-010
   (allineamento documentazione), TASK-011 (review deployment),
   TASK-012 (hardening config test) — ciascuno con dettaglio operativo
   completo (obiettivo, scope, file coinvolti, acceptance criteria, test,
   guardrail, note).
3. Nota aggiunta in `PROJECT_ANALYSIS.md`: roadmap operativa trasferita in
   `TASKS.md`.
4. Nessuna modifica a codice applicativo.

**Esito test (`scripts/test.sh`, con venv `.venv` attiva):**

Suite Django reale confermata 1207/1207 PASS (nessuna modifica applicativa
in questo lavoro).

**Prossimo passo per l'operatore umano:**

1. Eseguire **TASK-006** (audit permessi cartella/documenti, solo analisi)
   con `./scripts/ai-cycle.sh --project documentale-workcopy --task TASK-006 --run`.

---

### Run — 2026-07-06 — TASK-006 Audit permessi cartella/documenti

**Agente:** Cursor Agent
**Task:** TASK-006 — Audit permessi cartella/documenti
**Branch:** task/documentale-permissions-audit

**Operazioni eseguite:**

1. Letti `docs/ai/TASKS.md`, `AGENTS.md`, `scripts/test.sh` (obbligatori pre-modifica).
2. Analisi read-only del sistema permessi: `projects/models.py`,
   `projects/resolver.py`, `projects/permissions.py`,
   `documents/permissions.py`, `projects/views.py`, `ecn/permissions.py`,
   management command `backfill_folder_permission_grants` e
   `compare_folder_permissions`, sezioni permessi in `projects/tests.py`,
   `docs/ai/PROJECT_ANALYSIS.md` (rischio #4).
3. Creato `docs/ai/PERMISSIONS_AUDIT.md` con: modello dati legacy vs modulare,
   tre mapping distinti (runtime / backfill / compare), punti fallback,
   comandi migrazione, inventario test, gap, rischi, sequenza proposta TASK-007,
   raccomandazioni esercizio sicuro su SQLite `:memory:`.
4. Nessuna modifica applicativa. Nessun commit.

**Esito test (`scripts/test.sh`):**

```
NON ESEGUITO in questa sessione — invocazioni shell rifiutate dall'ambiente
prima dell'avvio dello script (compileall/check/test non lanciati).

Baseline documentata (TASK-005, 2026-07-06): 1207/1207 PASS.
L'operatore deve riconfermare con:
  cd projects/documentale-workcopy && source .venv/bin/activate && ./scripts/test.sh
prima di considerare TASK-006 chiuso in TASKS.md.
```

**Problemi riscontrati:**

- Impossibilità tecnica di eseguire `./scripts/test.sh` in questa sessione agente
  (shell bloccata). Il task non introduce codice applicativo; l'assenza di
  regressione attesa non sostituisce la verifica manuale.

**Prossimo passo per l'operatore umano:**

1. Leggere `docs/ai/PERMISSIONS_AUDIT.md`.
2. Eseguire `./scripts/test.sh` e confermare 1207/1207 PASS.
3. Review del report; poi spostare TASK-006 in Completati e avviare TASK-007
   solo dopo review esplicita del gap mapping backfill vs runtime.

---

### Run — 2026-07-07 — TASK-007 / Fase 1 Allineamento mapping permessi

**Agente:** Cursor Agent (implementazione) + Claude Code (verifica test,
scope, review — Cursor Agent non aveva shell disponibile per eseguire i
test nella propria sessione, come già in TASK-006)
**Task:** TASK-007 / Fase 1 — Allineamento mapping permessi
**Branch:** task/documentale-permissions-mapping-alignment

**Operazioni eseguite:**

1. `projects/management/commands/backfill_folder_permission_grants.py`:
   `BACKFILL_ROLE_PERMISSIONS` ora derivato da `_LEGACY_ROLE_PERMISSIONS`
   (importato da `projects.resolver`) meno il nuovo insieme nominato
   `BACKFILL_EXCLUDED_PERMISSIONS` (i 6 permission code esclusi,
   documentati con rimando a `PERMISSIONS_AUDIT.md`). Valori risultanti
   verificati identici a quelli precedenti (nessun cambio di comportamento
   del backfill).
2. `projects/management/commands/compare_folder_permissions.py`:
   `_legacy_allows()` e il loop principale usano ora
   `_LEGACY_ROLE_PERMISSIONS` (mapping completo) invece di
   `BACKFILL_ROLE_PERMISSIONS` (sottoinsieme) — il confronto è ora onesto
   sull'intero comportamento legacy, non solo sul sottoinsieme backfillato.
3. `projects/tests.py` (`CompareFolderPermissionsTests`): aggiornati
   `test_no_divergences_exit_code_0`, `test_user_id_filter`,
   `test_folder_id_filter` per riflettere la nuova semantica (divergenze
   attese sui permission code esclusi dal backfill, non più "0 divergenze
   dopo backfill"); aggiunto nuovo test di regressione
   `test_backfill_gap_detected_for_all_roles` (gap G1/G2 dell'audit): per
   ciascuno dei 5 ruoli, confronta che le divergenze rilevate dopo backfill
   coincidano **esattamente** con `BACKFILL_EXCLUDED_PERMISSIONS ∩
   _LEGACY_ROLE_PERMISSIONS[ruolo]`.
4. Nessuna modifica a `ecn/permissions.py`, `resolver.py`, modelli, view,
   template, migrazioni, settings. Nessun tocco a `include_legacy_fallback`
   in nessun punto (verificato con `git diff` esplicito). Nessuna migrazione
   dati, nessun `--apply` su dati reali (non esistono in questa copia).
5. **Claude Code (reviewer)** ha eseguito i test mirati
   (`CompareFolderPermissionsTests`, `BackfillFolderPermissionGrantsTests`)
   e la suite completa con `.venv` attiva, dato che Cursor Agent non poteva
   verificarlo nella propria sessione.

**Esito test (con venv `.venv` attiva):**

```
CompareFolderPermissionsTests: 7/7 PASS (incluso il nuovo test di regressione)
BackfillFolderPermissionGrantsTests: 15/15 PASS
Suite completa: Ran 1208 tests — OK (1207 + 1 nuovo test)
System check identified no issues (0 silenced).
Exit code: 0
```

**Problemi riscontrati:**

- Nessuno. Refactor comportamentalmente neutro sul backfill, estensione
  onesta sul compare, copertura test aggiornata e ampliata.

**Prossimo passo per l'operatore umano:**

1. Spostare TASK-007/Fase 1 in Completati dopo review.
2. Pianificare Fase 2 (backfill esteso reale in ambiente di test) come task
   separato, solo dopo revisione esplicita di questa Fase 1.
3. Fase 3 (refactor `ecn/permissions.py`) e Fase 4 (rimozione fallback)
   restano bloccate finché Fase 2 non è completa e verde.

---

### Run — 2026-07-07 — TASK-007 / Fase 2 Backfill esteso permessi

**Agente:** Cursor Agent (implementazione, via `ai-cycle.sh --run`) +
Claude Code (spec, verifica scope/test, fix mirato, review — stesso pattern
di Fase 1: Cursor Agent non ha shell disponibile per verificare da sé)
**Task:** TASK-007-2 (TASK-007 / Fase 2 — Backfill esteso permessi)
**Branch:** task/documentale-permissions-backfill-extended

**Operazioni eseguite:**

1. Analisi preliminare (Claude Code, per grep mirato su tutto il progetto,
   non solo lettura): dei 6 permission code esclusi dal backfill
   conservativo (`view_projects`, `view_folder_ecns`,
   `view_obsolete_documents`, `manage_rejected_drafts`,
   `manage_project_documents`, `request_ecn`), nessuno ha motivazione
   tecnica residua per restare escluso. `view_projects` è l'unico
   consumato attivamente via resolver in `projects/permissions.py` e
   `projects/views.py` (con `include_legacy_fallback=True`); gli altri 5
   non sono consumati da nessun path applicativo tramite il resolver —
   `ecn/permissions.py` bypassa completamente `FolderPermissionGrant`
   usando `get_folder_role()` diretto. Spec scritta in
   `docs/ai/TASKS.md` (sezione `TASK-007-2`).
2. `projects/management/commands/backfill_folder_permission_grants.py`
   (Cursor Agent): `BACKFILL_EXCLUDED_PERMISSIONS` svuotato
   (`frozenset()`), mantenuto come costante/punto di estensione futuro con
   commento aggiornato; `BACKFILL_ROLE_PERMISSIONS` ora identico a
   `_LEGACY_ROLE_PERMISSIONS` per tutti e 5 i ruoli. Docstring del comando
   aggiornato di conseguenza.
3. `projects/tests.py` (Cursor Agent): `test_mapping_manager_conservative`
   rinominato `test_mapping_manager_full` (verifica tutti i 12 permission
   code + grant `allow` espliciti); `test_no_divergences_exit_code_0` e
   `test_backfill_gap_detected_for_all_roles` (rinominato
   `test_no_gap_after_extended_backfill_for_all_roles`) aggiornati per
   aspettarsi **zero divergenze** dopo il backfill esteso (il gap G1/G2
   dell'audit è ora chiuso).
4. **Regressione trovata e corretta da Claude Code** (non prevista dalla
   spec): `test_user_id_filter` e `test_folder_id_filter` fallivano perché
   asserivano la presenza di username/codice cartella nell'output del
   `compare` — testo che il comando stampa solo nelle righe di divergenza.
   Con il backfill esteso il ruolo `reader` non produce più divergenze,
   quindi quel testo non compare più indipendentemente dal filtro. Fix:
   le due asserzioni ora verificano il conteggio
   `Combinazioni analizzate : N` (dipendente da
   `len(_LEGACY_ROLE_PERMISSIONS['reader'])`), che dimostra il filtro
   indipendentemente dalla presenza di divergenze.
5. Nessuna modifica a `compare_folder_permissions.py`, `resolver.py`,
   `ecn/permissions.py`, modelli, migrazioni, view, template, settings.
   Nessun tocco a `include_legacy_fallback` in nessun punto applicativo
   (verificato con `git diff main -- <file codice> | grep
   include_legacy_fallback` → vuoto). Nessuna migrazione dati, nessun
   `--apply` su dati reali (gli `--apply` eseguiti sono tutti dentro test
   Django su SQLite `:memory:`).
6. `ai-cycle.sh --run` ha segnalato "ERROR: Cursor Agent fallito o
   timeout" (limite 300s) ma le modifiche risultavano già scritte
   correttamente sul disco — stesso pattern già osservato in TASK-007
   Fase 1: verificato riga per riga con `git diff` prima di procedere,
   legittimo e in scope.

**Esito test (con venv `.venv` attiva):**

```
BackfillFolderPermissionGrantsTests: 15/15 PASS
CompareFolderPermissionsTests: 7/7 PASS (incluso il fix su user/folder filter)
FolderPermissionResolverTests + StepEFolderPermissionsIntegrationTests +
  StepFProjectIntegrationTests + BulkResolverTests: 86/86 PASS
Suite completa: Ran 1208 tests — OK
System check identified no issues (0 silenced).
Exit code: 0
```

**Problemi riscontrati:**

- Spec Fase 2 indicava (erroneamente) di non toccare `test_user_id_filter`
  e `test_folder_id_filter`: chiudere il gap per il ruolo `reader` ha
  eliminato l'unico canale (testo di divergenza) da cui quei test
  leggevano l'evidenza del filtro. Corretto da Claude Code, vedi punto 4.

**Prossimo passo per l'operatore umano:**

1. Spostare TASK-007-2 in Completati dopo review.
2. Fase 3 (refactor `ecn/permissions.py` su resolver, prioritario per
   `view_folder_ecns`/`request_ecn` ora backfillati ma ancora inutilizzati
   a runtime) resta task futuro separato.
3. Fase 4 (rimozione fallback) resta bloccata finché Fase 3 non è
   completa e verde.

---

### Run — 2026-07-07 — TASK-008 Audit dipendenze requirements

**Agente:** Cursor Agent
**Task:** TASK-008 — Audit dipendenze requirements
**Branch:** task/documentale-dependencies-audit

**Operazioni eseguite:**

1. Letti `docs/ai/TASKS.md`, `AGENTS.md`, `scripts/test.sh` (obbligatori pre-modifica).
2. Analisi read-only: `requirements.txt` (11 pacchetti), `config/settings.py`,
   `config/test_settings.py`, `config/wsgi.py`, `config/asgi.py`, `.env.example`,
   `DEPLOY.md`, `manage.py`, grep import su tutto il codebase Python.
3. Creato `docs/ai/DEPENDENCIES_AUDIT.md` con classificazione per ciascuna
   dipendenza, evidenze grep/file, sezioni dedicate per dubbie/inutilizzate,
   rischi di rimozione, proposta TASK-009 e test pre/post rimozione.
4. Riverificati esplicitamente `djangorestframework` e `django-filter`: ancora
   assenti da `INSTALLED_APPS` e da qualsiasi import Python — conferma
   problema #2 di `PROJECT_ANALYSIS.md`.
5. Scoperto caso aggiuntivo non documentato in PROJECT_ANALYSIS: `pillow`
   pinato ma nessun `ImageField`/`PIL` nel codebase (solo `FileField`).
6. Nessuna modifica a `requirements.txt`, settings, codice applicativo,
   `TASKS.md`, `PROJECT_ANALYSIS.md`. Nessun commit.

**Esito test (`scripts/test.sh`):**

```
Non eseguito in questa sessione agente — esecuzione shell/Python bloccata
(Rejected). Task di sola analisi: nessun file applicativo modificato;
esito atteso invariato rispetto a TASK-007-2 (1208/1208 PASS).

Conferma richiesta all'operatore:
  source projects/documentale-workcopy/.venv/bin/activate
  projects/documentale-workcopy/scripts/test.sh
```

**Problemi riscontrati:**

- Shell agente non disponibile per `./scripts/test.sh` in questa sessione
  (stesso pattern già osservato in TASK-006/007). Audit completato via
  grep/lettura; verifica suite delegata all'operatore.

**Prossimo passo per l'operatore umano:**

1. Rieseguire `./scripts/test.sh` con venv attiva (conferma formale verde).
2. Leggere `docs/ai/DEPENDENCIES_AUDIT.md`.
3. Spostare TASK-008 in Completati dopo review; avviare **TASK-009**
   (rimozione `django-filter`, `djangorestframework`, valutare `pillow`).

---

### Run — 2026-07-07 — TASK-009 Step A: rimozione django-filter

**Agente:** Claude Code (esecuzione diretta, nessuna delega a Cursor Agent
per questo task — rimozione dipendenza a basso rischio, incrementale)
**Task:** TASK-009 Step A
**Branch:** task/documentale-clean-unused-dependencies

**Operazioni eseguite:**

1. Riverificata assenza d'uso: `rg -i "django_filters|django-filter|FilterSet|DjangoFilterBackend|filter_backends"` su tutto il codebase Python (esclusi migrations) → nessun match. `INSTALLED_APPS` in `config/settings.py` non contiene `django_filters`.
2. Rimossa riga `django-filter==25.2` da `requirements.txt`.
3. `pip uninstall -y django-filter` nella venv locale `projects/documentale-workcopy/.venv` (nessun pacchetto globale toccato).
4. Eseguita suite completa con venv attiva.

**Esito test (`scripts/test.sh`):**

```
Ran 1208 tests in 482.281s
OK
System check identified no issues (0 silenced).
OK — manage.py test superato.
Tutti i controlli completati con successo.
```

**Problemi riscontrati:**

- Nessuno.

**Prossimo passo per l'operatore umano:**

1. Procedere con Step B (`djangorestframework`) dopo review/commit di Step A.

---

### Run — 2026-07-07 — TASK-009 Step B: rimozione djangorestframework

**Agente:** Claude Code (esecuzione diretta)
**Task:** TASK-009 Step B
**Branch:** task/documentale-clean-unused-dependencies

**Operazioni eseguite:**

1. Riverificata assenza d'uso con pattern mirati (evitando falsi positivi
   sul generico `response` dei test client): nessun `import rest_framework`,
   nessun `APIView`/`ViewSet`/`ModelSerializer`/`DefaultRouter`/
   `DjangoFilterBackend`, nessun `rest_framework.response/serializers/
   views/viewsets/routers/generics`. `INSTALLED_APPS` non contiene
   `rest_framework`. Nessun router DRF in alcun `urls.py`.
2. Rimossa riga `djangorestframework==3.17.1` da `requirements.txt`.
3. `pip uninstall -y djangorestframework` nella venv locale (nessun
   pacchetto globale toccato).
4. Eseguita suite completa con venv attiva.

**Esito test (`scripts/test.sh`):**

```
Ran 1208 tests in 485.471s
OK
System check identified no issues (0 silenced).
OK — manage.py test superato.
Tutti i controlli completati con successo.
```

**Problemi riscontrati:**

- Nessuno.

**Prossimo passo per l'operatore umano:**

1. Procedere con Step C (`pillow`, dubbia — verifica approfondita prima
   di decidere) dopo review/commit di Step B.

---

### Run — 2026-07-07 — TASK-009 Step C: rimozione pillow

**Agente:** Claude Code (esecuzione diretta)
**Task:** TASK-009 Step C
**Branch:** task/documentale-clean-unused-dependencies

**Operazioni eseguite:**

1. Verifica approfondita (dipendenza "dubbia", cautela maggiore):
   nessun `import PIL`/`from PIL`, nessun `ImageField` (né in modelli né
   in form), nessun riferimento a `thumbnail`/`preview`/`immagine` nel
   codice Python, nessun `<img>`/`thumbnail` nei template, nessun
   validator specifico immagine (`FileExtensionValidator` con estensioni
   immagine, `ImageFileValidator`). Tutti gli upload nel progetto usano
   `models.FileField`/`forms.FileField` (documenti/allegati PDF), mai
   `ImageField` — Django richiede Pillow solo per `ImageField`. Nessuna
   menzione di piani futuri per campi immagine in `PROJECT_HANDOFF.md`,
   `DEPLOY.md`, `AI_CONTEXT.md`, `CLAUDE.md`. **Nessun dubbio reale
   emerso**: rimozione confermata sicura.
2. Rimossa riga `pillow==12.2.0` da `requirements.txt`.
3. `pip uninstall -y pillow` nella venv locale (nessun pacchetto globale
   toccato).
4. Eseguita suite completa con venv attiva.

**Esito test (`scripts/test.sh`):**

```
Ran 1208 tests in 480.204s
OK
System check identified no issues (0 silenced).
OK — manage.py test superato.
Tutti i controlli completati con successo.
```

**Problemi riscontrati:**

- Nessuno.

**Prossimo passo per l'operatore umano:**

1. TASK-009 completo (Step A/B/C tutti verdi). Eseguire verifiche finali
   (suite completa, regressioni Station, `requirements.txt` coerente con
   la venv) e review finale prima del merge.

---

### Run — 2026-07-07 — TASK-010 Allineamento documentazione progetto

**Agente:** Claude Code (esecuzione diretta, solo documentazione)
**Task:** TASK-010
**Branch:** task/documentale-docs-alignment

**Operazioni eseguite:**

1. Audit di `AI_CONTEXT.md`, `PROJECT_HANDOFF.md`, `DEPLOY.md`,
   `README.md`, `docs/ai/PROJECT_ANALYSIS.md`, `docs/ai/TESTING_STATUS.md`,
   `docs/ai/DEPENDENCIES_AUDIT.md`, `docs/ai/PERMISSIONS_AUDIT.md`.
2. `README.md`: era **corrotto** (UTF-16LE senza BOM, illeggibile in
   qualunque strumento che assume UTF-8) — decodificato con `iconv` e
   riscritto in UTF-8 pulito, contenuto originale preservato + nota
   Station aggiunta.
3. `AI_CONTEXT.md`: aggiunta nota Station (chiarisce che descrive il
   progetto originale, non la workcopy) + **corretta la tabella gruppi**,
   disallineata dal codice reale (`readers`/`authors`/... minuscoli senza
   prefisso vs le vere costanti `GROUP_READERS = 'Document Readers'` ecc.
   in `documents/permissions.py`/`ecn/permissions.py`).
4. `PROJECT_HANDOFF.md`: aggiunta nota Station (chiarisce che i
   riferimenti a PowerShell/push su `origin/main` riguardano il repo
   originale, non questa workcopy senza remote) senza riscrivere lo
   storico originale.
5. `DEPLOY.md`: **corretto bug reale** nel comando bootstrap gruppi —
   `'Quality Managers'` (plurale, sbagliato) → `'Quality Manager'`
   (singolare, come da codice); un nome errato avrebbe creato un gruppo
   Django inutilizzato senza concedere alcun permesso. Elenco gruppi
   completato con tutti e 10 quelli reali del codice.
6. `docs/ai/PROJECT_ANALYSIS.md`: aggiunta nota di stato aggiornato sopra
   la tabella "Problemi evidenti" (verbale storico non riscritto) —
   problemi #1/#2 risolti (TASK-002/003, TASK-009), #3/#4/#5 allineati
   in questo task, #6 chiarito (fallback attivo per design, non un bug).
7. `docs/ai/TESTING_STATUS.md`: conteggio test aggiornato da 1207/1207 a
   **1208/1208 PASS**, aggiunta sezione riassuntiva TASK-006→TASK-009,
   sezione "Prossimo passo" aggiornata.
8. `docs/ai/PERMISSIONS_AUDIT.md`: aggiunta nota di aggiornamento — Fase
   1/2 di TASK-007 completate, fallback legacy ancora attivo, Fase 3/4
   restano future.
9. `docs/ai/TASKS.md`: TASK-010 spostato in Completati, "Prossimo task
   consigliato" aggiornato a TASK-011.
10. Nessuna modifica a codice applicativo, `requirements.txt`, settings,
    test Python.

**Esito test (`scripts/test.sh`):**

```
1208/1208 PASS (invariato — nessuna modifica applicativa in questo task)
pip check: No broken requirements found.
```

**Problemi riscontrati:**

- `README.md` corrotto (encoding) — non era nell'elenco dei problemi noti
  di `PROJECT_ANALYSIS.md`, scoperto durante l'audit di questo task.
  Corretto.

**Prossimo passo per l'operatore umano:**

1. Procedere con TASK-011 (review deployment locale/VM, solo
   analisi/dry-run) dopo review/commit di questo task.

---

### Run — 2026-07-08 — TASK-011 Review deployment locale/VM

**Agente:** Claude Code (esecuzione diretta, solo audit/dry-run sicuri)
**Task:** TASK-011
**Branch:** task/documentale-deployment-readiness

**Operazioni eseguite:**

1. Audit di `DEPLOY.md`, `README.md`, `AI_CONTEXT.md`,
   `PROJECT_HANDOFF.md`, `manage.py`, `config/settings.py`,
   `config/test_settings.py`, `config/wsgi.py`, `config/asgi.py`,
   `.env.example` (solo chiavi), `requirements.txt`, `package.json`,
   `tailwind.config.js`.
2. Dry-run sicuri: `manage.py check` (0 problemi) e
   `manage.py check --deploy` (6 warning, tutti attesi in ambiente di
   test) con `config.test_settings` — nessun segreto reale coinvolto.
3. Verificata esistenza di tutti i comandi citati in `DEPLOY.md`
   (`migrate`, `collectstatic`, `createsuperuser`, `shell`) via
   `manage.py help`, senza eseguirli.
4. **Scoperto** comando custom `setup_document_groups`
   (`documents/management/commands/setup_document_groups.py`),
   idempotente, legge i 10 nomi gruppo dalle costanti `GROUP_*` del
   codice — non documentato in `DEPLOY.md`, che usava invece uno snippet
   Python manuale (già corretto in TASK-010, ma comunque più fragile).
5. **Corretto `DEPLOY.md` §5**: sostituito lo snippet manuale con
   `python manage.py setup_document_groups`.
6. Verificata coerenza `.env.example` ↔ `config/settings.py`: tutte le
   26 chiavi lette da `config()` sono presenti in `.env.example`,
   nessuna mancante o extra.
7. Verificata assenza di `db.sqlite3`, `staticfiles/`, `.env` in questa
   workcopy (nessun deploy/collectstatic/migrate mai eseguito).
8. `media/` locale: contati 501 file (**nessun contenuto letto**);
   lettura della sola nota `.gitkeep-note.txt`, che dichiara che il
   contenuto reale originale (235 file) fu rimosso in onboarding e non
   va mai letto da un agente AI — segnalato in
   `docs/ai/DEPLOYMENT_READINESS.md` come osservazione, nessuna azione.
9. Creato `docs/ai/DEPLOYMENT_READINESS.md` (report completo: stack,
   comandi, variabili richieste, checklist VM locale e pre-deploy,
   rischi, errori documentali, cosa verificato/non eseguito,
   raccomandazioni TASK-012, acceptance criteria per una prova deploy
   futura controllata).
10. Nessun deploy reale, nessun server avviato, nessuna migrazione
    eseguita, nessun segreto letto, nessuna modifica a codice
    applicativo o `requirements.txt`.

**Esito test (`scripts/test.sh`):**

```
1208/1208 PASS (invariato)
pip check: No broken requirements found.
manage.py check: 0 problemi
manage.py check --deploy: 6 warning attesi (ambiente di test)
```

**Problemi riscontrati:**

- Nessuno bloccante. Vedi `docs/ai/DEPLOYMENT_READINESS.md` §7 per i
  rischi non bloccanti individuati (compatibilità PostgreSQL mai
  verificata, procedura mai eseguita end-to-end).

**Prossimo passo per l'operatore umano:**

1. Procedere con TASK-012 (hardening configurazione test, facoltativo)
   o, se prioritario, pianificare una prova di deploy controllata su VM
   isolata seguendo `docs/ai/DEPLOYMENT_READINESS.md` §12.

---

### Run — 2026-07-08 — TASK-012 Hardening configurazione test (isolamento media)

**Agente:** Claude Code (esecuzione diretta)
**Task:** TASK-012
**Branch:** task/documentale-test-hardening

**Operazioni eseguite:**

1. **Verifica sicura `media/` reale** (pre-merge TASK-011, richiesta
   esplicita operatore): `git ls-files -- media` vuoto (nessun file
   tracciato), `git status --ignored` conferma l'intera cartella
   ignorata, 521 file su disco tutti non tracciati/ignorati. Nessun
   contenuto aperto. Bonificati con lista generata da
   `git ls-files --others --ignored --exclude-standard` +
   rimozione mirata (**mai `git clean`**), preservata la nota di
   sicurezza `.gitkeep-note.txt`.
2. Merge fast-forward di `task/documentale-deployment-readiness` su
   `main` (dopo verifica media positiva).
3. **Causa radice identificata**: `config/test_settings.py` non
   sovrascriveva `MEDIA_ROOT`, quindi ogni test con upload file scriveva
   nella `media/` reale — confermato empiricamente rieseguendo la suite
   subito dopo la bonifica: **20 nuovi file** scritti nella `media/`
   reale in un solo run (da 1 a 21).
4. **Fix**: `config/test_settings.py` — aggiunto
   `MEDIA_ROOT = BASE_DIR / '.test-media'` (isolata). `.gitignore` —
   aggiunta voce `.test-media/`. `scripts/test.sh` — stampa il path di
   `MEDIA_ROOT` di test, pulisce `.test-media/` prima di ogni run e di
   nuovo dopo un run riuscito (mai tocca `media/` reale — verificato con
   `shellcheck`/`shfmt` puliti).
5. **Verifica del fix**: suite completa rieseguita — `media/` reale
   rimasta a **21 file (invariata, 0 nuove scritture)**, `.test-media/`
   creata durante il run e correttamente rimossa a fine run riuscito.
6. Bonifica finale dei 20 file residui pre-fix rimasti in `media/`
   (stesso metodo sicuro del punto 1).
7. Nessuna modifica a codice applicativo, view, modelli, migrazioni,
   logica funzionale — solo `config/test_settings.py` (1 riga + commento),
   `scripts/test.sh` (path/pulizia), `.gitignore` (1 voce), docs AI.

**Esito test (`scripts/test.sh`):**

```
Ran 1208 tests in 483.313s
OK
System check identified no issues (0 silenced).
OK — manage.py test superato.
media/ reale: 21 file prima e dopo (invariata)
.test-media/: assente dopo il run (ripulita)
```

**Problemi riscontrati:**

- Bug pre-esistente scoperto in TASK-011 (non introdotto da questo
  task): i test scrivevano nella `media/` reale da quando esiste
  `config/test_settings.py` (TASK-003). Corretto qui.

**Prossimo passo per l'operatore umano:**

1. Backlog operativo TASK-001→TASK-012 esaurito. Pianificare come nuovo
   task dedicato: Fase 3 di TASK-007 (refactor `ecn/permissions.py`) o
   una prova di deploy controllata (`docs/ai/DEPLOYMENT_READINESS.md`
   §12), quando prioritari.

---

### Run — 2026-07-08 — TASK-013 Audit ECN permissions resolver bypass

**Agente:** Cursor Agent (via `ai-cycle.sh --run`) + Claude Code (spec,
verifica accuratezza, review)
**Task:** TASK-013
**Branch:** task/documentale-ecn-permissions-resolver

**Operazioni eseguite:**

1. Spec scritta da Claude Code in `docs/ai/TASKS.md` con analisi
   preliminare già verificata (lettura diretta `ecn/permissions.py`,
   `projects/permissions.py`, `projects/resolver.py`): solo 2 delle 13
   funzioni pubbliche di `ecn/permissions.py` toccano permessi cartella
   (`can_view_ecn`, `can_create_ecn`), entrambe via `get_folder_role`
   (solo legacy).
2. Cursor Agent ha prodotto `docs/ai/ECN_PERMISSIONS_AUDIT.md` (420
   righe): conferma esatta dell'analisi preliminare, con righe di codice
   precise (89-93, 116-121), tabelle di equivalenza verificate contro
   `_LEGACY_ROLE_PERMISSIONS` — `request_ecn` = `WRITE_ROLES` esatto
   (match 1:1), `view_folder_ecns` ⊋ `AUDIT_ROLES` (nessun match,
   rischio escalation se migrato ingenuamente).
3. Claude Code ha verificato a campione (non solo letto) le righe di
   codice citate e il mapping `_LEGACY_ROLE_PERMISSIONS` via grep —
   confermato accurato al 100%.
4. Nessuna modifica applicativa (solo il nuovo file docs).

**Esito test (`ai-cycle.sh` STEP 5):**

```
Ran 1208 tests in 481.136s — OK
System check identified no issues (0 silenced).
```

**Problemi riscontrati:** nessuno.

---

### Run — 2026-07-08 — TASK-014 Refactor minimo ECN permissions verso resolver modulare

**Agente:** Claude Code (esecuzione diretta — modifica chirurgica di 2
righe, permessi-critica, precisione preferita a delega)
**Task:** TASK-014
**Branch:** task/documentale-ecn-permissions-resolver

**Operazioni eseguite:**

1. `ecn/permissions.py`, `can_create_ecn`: sostituito
   `get_folder_role(user, folder) in WRITE_ROLES` con
   `has_folder_permission(user, folder, 'request_ecn',
   include_legacy_fallback=True)` (import da `projects.resolver`).
   **`can_view_ecn` non toccato**, come da acceptance criteria TASK-013.
2. `ecn/tests.py`: import `FolderPermissionGrant` aggiunto; 2 nuovi test
   (oltre il minimo richiesto):
   `test_folder_grant_request_ecn_can_create_without_membership` (grant
   modulare senza membership legacy → può creare ECN) e
   `test_folder_grant_deny_request_ecn_blocks_legacy_author` (deny
   modulare blocca anche con membership legacy author — precedenza del
   grant sul fallback).
3. Guardrail verificati esplicitamente con `git diff | grep`:
   `include_legacy_fallback` — unica occorrenza è la nuova riga con
   `=True` esplicito, nessuna disattivazione; `ProjectFolderMembership`
   — solo import riordinato (aggiunta `FolderPermissionGrant`), ancora
   importato e usato; nessuna migrazione, nessun template, nessun
   `.env` toccato.
4. Test eseguiti in ordine crescente di scope: `ECNPermissionsTests`
   (42/42), app `ecn` completa (317/317), suite completa
   (1210/1210 = 1208 + 2 nuovi).

**Esito test (con venv `.venv` attiva):**

```
ecn.tests.ECNPermissionsTests: 42/42 PASS
App ecn completa: 317/317 PASS
Suite completa: Ran 1210 tests — OK (1208 + 2 nuovi)
System check identified no issues (0 silenced).
pip check: No broken requirements found.
```

**Problemi riscontrati:** nessuno. Nessun rollback necessario.

---

### Run — 2026-07-08 — TASK-015 Consolidamento documentazione permessi

**Agente:** Claude Code (esecuzione diretta, solo documentazione)
**Task:** TASK-015
**Branch:** task/documentale-ecn-permissions-resolver

**Operazioni eseguite:**

1. `docs/ai/PERMISSIONS_AUDIT.md`: aggiunta nota di aggiornamento
   TASK-013/014 (gap G3 parzialmente chiuso: `can_create_ecn` migrata,
   `can_view_ecn` deliberatamente non migrata per assenza di permission
   code equivalente); riga G3 nella tabella gap aggiornata da "Media" a
   "Parzialmente risolto (TASK-014)".
2. `docs/ai/TASKS.md`: TASK-013/014/015 spostati in Completati, backlog
   svuotato con nota esplicita sul perché `can_view_ecn` non è stata
   migrata (decisione di prodotto, non task tecnico).
3. `docs/ai/TESTING_STATUS.md`: non modificato in questo task (il
   conteggio test 1210 è già documentato nell'entry TASK-014 di questo
   RUN_LOG; nessuna sezione dedicata necessaria per un incremento di 2
   test con causa già chiara).
4. Nessuna modifica a codice applicativo.

**Esito test:** invariato rispetto a TASK-014 (1210/1210 PASS, nessuna
modifica applicativa in questo task).

**Problemi riscontrati:** nessuno.

**Prossimo passo per l'operatore umano:**

1. Backlog operativo `documentale-workcopy` (TASK-001→TASK-015) esaurito
   di nuovo. `can_view_ecn` resta un bypass legacy intenzionale, non un
   difetto da correggere senza decisione di prodotto.
2. Candidato successivo: prova di deploy controllata su VM isolata
   (`docs/ai/DEPLOYMENT_READINESS.md` §12), da pianificare come nuovo
   task dedicato quando prioritario.

---

### Run — 2026-07-08 — TASK-016 Piano prova deploy controllata

**Agente:** Claude Code (esecuzione diretta, solo documentazione +
dry-run sicuri)
**Task:** TASK-016
**Branch:** task/documentale-deploy-rehearsal-plan

**Operazioni eseguite:**

1. Riverificati (non solo riletti) `requirements.txt` (8 pacchetti,
   coerente con TASK-009), chiavi `.env.example` (26, coerenti con
   `config/settings.py`), presenza `static/css/tailwind.css` (58 KB),
   assenza `db.sqlite3`/`staticfiles/`/`.env` nella workcopy.
2. Dry-run sicuri: `manage.py check` (0 problemi),
   `manage.py check --deploy` (6 warning attesi in ambiente di test,
   invariati rispetto a TASK-011), `manage.py help
   setup_document_groups` (comando confermato disponibile e idempotente).
3. Creato `docs/ai/DEPLOY_REHEARSAL_PLAN.md` (20 sezioni): scopo, cosa
   NON viene fatto, ambiente consigliato (VM isolata, DB/media vuoti,
   `.env` di prova creato **solo** dall'operatore umano), prerequisiti,
   checklist pre-flight, procedura dry-run locale, procedura VM isolata,
   comandi da eseguire manualmente, comandi vietati per un agente AI,
   verifiche post-installazione, bootstrap gruppi
   (`setup_document_groups`), static/Tailwind, database/migrazioni
   (solo DB vuoto isolato), media/privacy (richiamo TASK-012), account
   demo/test, criteri di successo/stop, rollback/cleanup, rischi
   residui, prossimo task suggerito.
4. Aggiunta nota di rimando in `docs/ai/DEPLOYMENT_READINESS.md` §12
   verso il nuovo piano.
5. Nessuna modifica a codice applicativo. `can_view_ecn` non toccata
   (non pertinente a questo task). Nessun `.env` creato/letto, nessun
   server avviato, nessuna migrazione, nessun segreto letto.

**Esito test (`scripts/test.sh`):**

```
Ran 1210 tests in 489.684s — OK
System check identified no issues (0 silenced).
pip check: No broken requirements found.
media/ reale: invariata (1 file, solo la nota) prima e dopo la suite
.test-media/: assente dopo il run (ripulita)
```

**Problemi riscontrati:** nessuno.

**Prossimo passo per l'operatore umano:**

1. Backlog operativo `documentale-workcopy` (TASK-001→TASK-016) esaurito
   di nuovo.
2. Se prioritario: eseguire manualmente la prova di deploy pianificata
   in `docs/ai/DEPLOY_REHEARSAL_PLAN.md`, in una VM/container isolato —
   richiede azione umana diretta (creazione `.env`, `createsuperuser`),
   non delegabile a un agente AI.
3. `can_view_ecn` resta aperta come decisione di prodotto (nuovo
   permission code o accettazione esplicita del comportamento attuale),
   non un task tecnico Station.

---

### Run — 2026-07-09 — TASK-017 Validazione flusso DEMO end-to-end

**Agente:** Claude Code (esecuzione diretta, solo demo isolata)
**Task:** TASK-017
**Branch:** task/documentale-demo-flow-validation

**Cambio di priorità dell'operatore:** focus su presentabilità demo,
non su permessi fini/deploy/PostgreSQL/refactor `can_view_ecn`.

**Operazioni eseguite:**

1. Analisi: scoperto che esiste già un'infrastruttura demo completa
   (`documents/management/commands/demo_company.py`,
   `demo_full.py`) con un utente `supervisor_demo` **progettato
   esplicitamente per presentazioni a singolo accesso** (docstring del
   comando). Nessuna nuova fixture necessaria.
2. Creato `config/demo_settings.py` (isolato: DB SQLite file in
   `.demo/db.sqlite3`, media in `.demo-media/`, nessun `.env`), sul
   modello di `config/test_settings.py`. `.gitignore` aggiornato.
3. Eseguito `migrate` + `demo_full --reset --no-email` sul DB demo
   isolato: 2 progetti, 8 cartelle, 13 documenti, 19 versioni, 18
   richieste approvazione, 8 ECN (tutti e 6 gli stati), 86 voci audit
   log.
4. Creato `demo_admin` (superuser, credenziali fornite
   dall'operatore) in aggiunta a `supervisor_demo`/`admin_demo` già
   esistenti.
5. **Validazione con azioni reali** (non solo lettura codice) via
   `manage.py shell`: `demo_admin` (nessun gruppo, nessuna membership
   cartella) ha creato un documento, una revisione, inviato in
   approvazione assegnando sé stesso, approvato (bypass superuser in
   `approvals/services.py`), verificato `can_create_ecn`/`can_view_ecn`
   (entrambi `True` via bypass superuser), creato/popolato/emesso uno
   snapshot `ProjectRevision`. Tutte le azioni hanno generato voci
   `AuditLog` corrette.
6. **Gap scoperto**: `demo_full` non crea `ProjectRevision` di esempio
   — colmato manualmente in validazione, segnalato come miglioria non
   bloccante nel report.
7. Avviato `runserver 127.0.0.1:8765 --settings=config.demo_settings`
   (solo loopback), verificate con `curl` le pagine principali
   (login, dashboard, documents, projects, ecn — tutte 200 dopo login,
   nessun 500), **fermato subito dopo**.
8. Creato `docs/ai/DEMO_FLOW_VALIDATION.md` (20 sezioni). Nessuna
   modifica a `ecn/permissions.py` (`can_view_ecn` inclusa), modelli,
   migrazioni.

**Esito test (`scripts/test.sh`, `config.test_settings` — non toccato
dal lavoro demo):**

```
Ran 1210 tests in 488.201s — OK
System check identified no issues (0 silenced).
pip check: No broken requirements found.
media/ reale: invariata (1 file) — il lavoro demo usa .demo-media/, mai media/
.test-media/: assente dopo il run (ripulita)
```

**Problemi riscontrati:** nessun bug bloccante per la demo. Unico gap:
`demo_full` non esercita `ProjectRevision` (non bloccante, colmato
manualmente).

**Prossimo passo per l'operatore umano:**

1. Demo verificata presentabile con un singolo account superuser
   (`demo_admin` o `supervisor_demo`) — nessuna azione Station
   aggiuntiva necessaria prima di una presentazione.
2. Migliorie facoltative non bloccanti in
   `docs/ai/DEMO_FLOW_VALIDATION.md` §19.

---

### Run — 2026-07-09 — TASK-018 Kit operativo demo ripetibile

**Agente:** Claude Code (esecuzione diretta)
**Task:** TASK-018
**Branch:** task/documentale-demo-operator-kit

**Operazioni eseguite:**

1. Merge fast-forward di `task/documentale-demo-flow-validation`
   (TASK-017) su `main` (627d6d5), confermato con regressioni
   Station + suite completa (1210/1210 PASS) prima di procedere.
2. Colmato il gap segnalato in TASK-017: aggiunto
   `_scenario_project_snapshot` a
   `documents/management/commands/demo_full.py` (unico file di codice
   applicativo toccato) — crea/popola/emette uno snapshot
   `ProjectRevision` per `PRJ-DEMO-001`, stesso pattern idempotente
   degli altri scenari del comando. Verificato: nessun test esistente
   copre `demo_full` (solo `demo_company`), rischio di regressione
   minimo.
3. Verificato con esecuzione reale: `demo_full --reset --no-email` crea
   lo snapshot senza errori; rieseguito senza `--reset` → scenario
   correttamente saltato (idempotenza confermata).
4. Creato `docs/ai/DEMO_OPERATOR_GUIDE.md`: runbook breve e pratico
   (creazione DB demo, creazione account, popolamento dati, avvio/stop
   server, percorso demo passo-passo, chiarimenti progetto/ECN, cosa
   non è oggetto della demo, troubleshooting).
5. Nessuna modifica a `can_view_ecn`, permessi avanzati, modelli,
   migrazioni, `config/demo_settings.py` (già corretto in TASK-017).
   Nessuna nuova dipendenza.

**Esito test (`scripts/test.sh`, `config.test_settings` — non toccato
dal lavoro demo):**

```
Ran 1210 tests in 487.301s — OK (invariato)
System check identified no issues (0 silenced).
pip check: No broken requirements found.
media/ reale: invariata (1 file)
.test-media/: assente
.demo/: correttamente ignorata da git
nessun server rimasto attivo
```

**Problemi riscontrati:** nessuno.

**Prossimo passo per l'operatore umano:**

1. Demo ripetibile e documentata (`docs/ai/DEMO_OPERATOR_GUIDE.md`),
   nessuna azione Station bloccante residua.
2. Task tecnici già rinviati (refactor `can_view_ecn`, permessi
   avanzati, deploy reale) restano backlog futuro, non urgenti.

---

### Run — 2026-07-09 15:36 — TASK-019 Stub pagina "Archivio" + voce sidebar

**Agente:** Cursor Agent (via `ai-cycle.sh --run`) + Claude Code (review)
**Task:** TASK-019 — Stub pagina "Archivio" + voce sidebar (collaudo flusso Station)
**Branch:** task/documentale-workcopy-archivio-stub

**Operazioni eseguite:**

1. Primo collaudo end-to-end del flusso Station su Windows: intake →
   `station-next-task.sh` → prompt via `cursor-prompt.sh` → Cursor
   Agent CLI (`agent.cmd`, autenticato) → test reali → review Claude
   Code → commit gated.
2. Cursor Agent ha implementato lo stub esattamente nello scope
   previsto: nuova view `archive_placeholder` (`documents/views.py`,
   `@login_required`, nessuna logica), nuovo URL `archivio/`
   (`config/urls.py`), nuovo template
   `templates/documents/archive_placeholder.html`, nuova sezione
   sidebar "Prossimamente" con singola voce "Archivio (in arrivo)"
   (`templates/base.html`, sezione "Archivio" esistente invariata),
   2 nuovi test in `documents/tests.py`
   (`ArchivePlaceholderTests`: redirect anonimo, 200 per utente
   autenticato).
3. Nessun file fuori scope toccato (verificato con
   `git diff --stat`: solo i 4 file previsti + 1 nuovo template).
4. Nota infrastrutturale: la prima esecuzione di `ai-cycle.sh --run`
   è fallita allo STEP 4 per mancata autenticazione di Cursor CLI
   (`agent login` eseguito dall'operatore) e un'altra per un gap di
   integrazione Windows (STEP 5 non trovava le dipendenze perché
   `scripts/test.sh` risolve `python`/`python3` dal PATH ambientale,
   non da un venv dedicato) — verificato manualmente attivando
   `AI-Station-documentale/.venv` sul PATH. Corretto separatamente
   anche un fallback `agent` → `agent.cmd` in `ai-cycle.sh` (Cursor
   CLI su Windows espone solo il wrapper `.cmd`, non risolvibile da
   Git Bash come comando nudo).

**Esito test (`scripts/test.sh`, con `AI-Station-documentale/.venv` sul PATH):**

```
Ran 1212 tests in 4010.353s — OK (1210 esistenti + 2 nuovi)
System check identified no issues (0 silenced).
```

**Problemi riscontrati:**

- Suite completa ~67 minuti su questa macchina (hardware mobile,
  Intel Core Ultra 7 265U) contro i ~40 minuti osservati in
  precedenza — attribuito a differenza hardware/throttling termico
  sotto carico prolungato, non a una regressione: nessun test
  modificato tra le due run a parità di codice applicativo.
- `scripts/test.sh` non individua automaticamente un venv locale:
  richiede attivazione manuale o PATH esplicito prima
  dell'esecuzione, sia in locale che da `ai-cycle.sh --run`. Non
  corretto in questo task (fuori scope): candidato per un piccolo
  task dedicato futuro.

**Prossimo passo per l'operatore umano:**

1. Review Claude Code completata, verdetto approvato — procedere con
   `commit-if-approved.sh`.
2. Valutare un task dedicato per far rilevare a `scripts/test.sh` un
   venv locale del progetto automaticamente (evita di dover
   ricordarsi il PATH ad ogni esecuzione, anche da `ai-cycle.sh`).
3. Collaudo Station→Windows riuscito: il ciclo può considerarsi
   validato per un secondo task reale.

---

### Run — 2026-07-09 17:10 — TASK-020 Tipo Documento come vocabolario controllato

**Agente:** Claude Code (implementazione diretta, non via Cursor Agent)
**Task:** TASK-020 — Tipo Documento come menu a cascata (dipendente da
Categoria) + suffisso di riferimento
**Branch:** task/documentale-workcopy-tipo-documento

**Operazioni eseguite:**

1. Letti due allegati dell'operatore (elenco acronimi "documenti di
   sistema", 35 tipi; elenco "documenti di progetto", 44 tipi) e
   verificato che corrispondano esattamente a `Document.Category`
   (QUALITY/PROJECT) già esistente, senza sovrapposizioni.
2. Chiarite con l'operatore 3 decisioni prima di implementare: cascata
   per categoria (sì), suffisso nel codice documento rimandato a task
   futuro (solo riferimento visivo per ora), normalizzazione delle 2
   anomalie nei dati sorgente (SCTY duplicato mantenuto come due voci
   con lo stesso acronimo, SDD__ normalizzato a SDD_).
3. Creato `documents/document_types.py` (liste di tuple, non
   `TextChoices`, per supportare il duplicato SCTY e valori che
   iniziano con cifra come `3DPD`/`3DAD`).
4. `Document.document_type` con `choices=` (migrazione
   `0006_alter_document_document_type`, solo metadata Django, nessun
   impatto sullo schema DB).
5. `DocumentCreateForm.document_type` da `CharField` a `ChoiceField`
   con widget custom `DocumentTypeSelect` (annota `data-category` per
   opzione) + validazione incrociata categoria/tipo in `clean()`.
6. `new_document.html`: select ripopolato via JS vanilla in base alla
   categoria scelta (nessuna libreria nuova).
7. Nuova classe CSS `.badge-doctype` (+ variante dark), Tailwind
   ricompilato (`npm install` + `npm run build`, node_modules non
   presente inizialmente).
8. `document_detail.html` e `document_list.html`: badge acronimo
   visibile in header/riga tabella; filtro lista da testo libero a
   select con optgroup per categoria; `views.py` filtro `doc_type` da
   `icontains` a match esatto.
9. 7 comandi demo (`demo_workflow.py`, `demo_company.py`,
   `demo_full.py`) aggiornati dai vecchi valori liberi italiani ai
   nuovi acronimi validi, coerenti con la categoria di ciascun
   documento demo.
10. Verifica manuale completa nel browser (demo server già attivo):
    cascata categoria→tipo confermata via DOM (37 opzioni per QUALITY,
    45 per PROJECT), badge visibili in lista e dettaglio, creazione
    reale di un documento (`TEST-TIPO-001`, tipo `CNTY`) confermata via
    shell Django.

**Esito test (`manage.py test documents --keepdb --failfast`, non la suite globale su richiesta operatore):**

```
Ran 362 tests in 977.590s
OK
System check identified no issues (0 silenced).
```

**Problemi riscontrati:**

- Nessuno bloccante. `node_modules/` non presente per il build
  Tailwind: risolto con `npm install` (già documentato come step
  standard in `README.md`).

**Prossimo passo per l'operatore umano:**

1. Review Claude Code + commit gated (`commit-if-approved.sh`).
2. Valutare se estendere il badge Tipo Documento anche agli altri
   template che elencano documenti (`approvals/`, `ecn/`, `projects/`,
   `workspace/`) — non incluso in questo task su decisione esplicita
   di scope.
3. Suffisso del tipo nel codice documento: da valutare in un task
   futuro separato, ora che il campo è in uso reale.

---

### Run — 2026-07-10 — TASK-021 Archivio: storico completo + dettaglio compatto

**Agente:** Claude Code (implementazione diretta, non via Cursor Agent)
**Task:** TASK-021 — Archivio: storico completo documenti (permesso
`view_history`) + dettaglio compatto altrove
**Branch:** task/documentale-workcopy-archivio-storico

**Operazioni eseguite:**

1. Analizzato il codice esistente prima di scrivere qualunque riga:
   `can_view_document`/`can_view_version` già implementano la regola
   "bozze/rifiutati privati solo autore+superuser, nessuna deroga" e il
   pattern `view_history` per-cartella con fallback legacy — riusati,
   non reinventati.
2. Chiarite con l'operatore 2 decisioni prima di iniziare: chi accede
   ad Archivio (stesso permesso di `can_view_audit`, non aperto a
   tutti) e ambito della lista (tutti gli stati documento, bozze
   private altrui sempre escluse).
3. Nuove funzioni permesso: `can_view_archive`,
   `can_view_archived_document` (`documents/permissions.py`),
   `get_history_visible_folder_ids` (`projects/permissions.py`),
   `user_can_view_archive` (nav tag).
4. Nuove view `archive_document_list`/`archive_document_detail`
   (sostituiscono lo stub `archive_placeholder` di TASK-019) + 2 nuovi
   template. `document_detail` ridotto: via tabella revisioni e
   storico eventi, ECN da tabella completa a card "Ultimo ECN".
   Aggiunto link "Vedi storico completo" condizionale.
5. Sidebar: sezione "Storico" (nome scelto per evitare collisione con
   la sezione "Archivio" già esistente per Documenti/Cartelle/Progetti),
   visibile solo con permesso.
6. Aggiornati 3 test esistenti + riscritta un'intera classe
   (`AuditUIDocumentDetailTests` → `AuditUIArchiveDetailTests`) che
   testava la funzionalità ora spostata; 1 assert aggiornato in
   `ecn/tests.py`. Aggiunti 22 nuovi test sui permessi e sul contenuto
   delle nuove viste.
7. Verifica manuale completa nel browser (demo server già attivo):
   lista Archivio con tutti gli stati, dettaglio con storico completo,
   vista compatta senza storico, 404 diretto su `/archivio/` per
   utente senza permesso.

**Esito test (`manage.py test documents ecn --keepdb --failfast`):**

```
Ran 700 tests in 58788.902s (PC sospeso a metà esecuzione, poi ripreso)
OK
System check identified no issues (0 silenced).
```

**Problemi riscontrati:**

- Nessuno bloccante. Il PC è stato sospeso (sleep) a metà della corsa
  test per esigenza dell'operatore: il processo è ripreso
  automaticamente al risveglio senza reimpostare nulla, confermando
  che la sospensione (non lo spegnimento) è sicura per processi in
  background su questa macchina.

**Prossimo passo per l'operatore umano:**

1. Review Claude Code + commit gated (`commit-if-approved.sh`).
2. Valutare se estendere lo stesso pattern "storico confinato in
   Archivio" anche a `projects/project_detail.html` (ha una sua
   sezione "Storico eventi" separata, non toccata in questo task).
3. Suffisso del tipo nel codice documento (rimandato da TASK-020):
   ancora da valutare.

---

### Run — 2026-07-10 — TASK-022 Flusso ECN semplice per revisioni rapide

**Agente:** Claude Code (implementazione diretta, non via Cursor Agent)
**Task:** TASK-022 — Flusso ECN semplice per revisioni rapide
(sostituisce "revisione senza ECN" come percorso demo principale)
**Branch:** task/documentale-simple-ecn-flow (creato da `main` dopo
fast-forward delle 4 branch precedenti: station-windows-portability,
documentale-workcopy-archivio-stub, documentale-workcopy-tipo-documento,
documentale-workcopy-archivio-storico — tutte confermate pulite,
lineari, senza conflitti, con suite completa verde prima del merge).

**Operazioni eseguite:**

1. **FASE 0**: verificato stato git, ricostruita la pila lineare delle
   4 branch precedenti non ancora su `main`. Trovate 3 regressioni
   Station pre-esistenti (0% overlap coi task pendenti, confermato via
   `git diff --stat`): `python3` non su PATH Windows
   (`ai-cycle-dogfood/scripts/test.sh`,
   `log-analyzer/scripts/test.sh`) e backslash Windows che rompeva un
   test su path (`cursor-prompt-builder/prompt_builder.py`). Corrette
   su richiesta esplicita dell'operatore (fermato e chiesto conferma
   prima di procedere, come previsto da FASE 0.4). Suite completa
   `documentale-workcopy` verde prima del merge → fast-forward di
   `main` alle 4 branch, poi creato `task/documentale-simple-ecn-flow`.
2. **FASE 2**: audit riga-per-riga del flusso ECN/CCB esistente
   (`ecn/services.py`, `documents/services.py`,
   `documents/models.py`), documentato in dettaglio in `TASKS.md`.
   Individuato il punto chiave: il gate di `create_new_revision` è
   agnostico rispetto a *come* un ECN sia diventato `APPROVED` — questo
   ha reso possibile un'implementazione interamente additiva.
3. **FASE 3-4**: aggiunto `ChangeNotice.flow_type`
   (`STANDARD`/`SIMPLE`) + migrazione; `create_simple_ecn` +
   `_generate_simple_ecn_code` (`ECN-S-<anno>-NNNN`); vista
   `ecn_create_simple` (riusa `can_create_ecn`, nessun permesso nuovo);
   `document_detail.html` con due pulsanti distinti (ECN semplice /
   ECN standard); `new_revision.html` con badge tipo ECN nella tabella.
4. **FASE 5**: `requires_ecn_for_revision`/`ecn_exemption` lasciati nel
   modello/form per compatibilità dati; rimossa solo la checkbox dalla
   UI di creazione documento.
5. **FASE 6**: scenario `demo_full.py` convertito da bypass a esercizio
   reale di `create_simple_ecn` (`DEMO-ECN-SIMPLE-001`); verificato con
   run reale (`--reset --no-email --settings=config.demo_settings`).
6. **FASE 7**: 14 nuovi test in `ecn/tests.py`, 3 in `documents/tests.py`
   (incl. verifica esplicita che il percorso legacy resti invariato per
   i documenti esistenti).
7. **FASE 8**: creato `docs/ai/SIMPLE_ECN_FLOW.md`; aggiornato
   `docs/ai/DEMO_OPERATOR_GUIDE.md` (punto 7 + sezione 9).
8. **FASE 9**: suite mirata e suite completa eseguite (vedi sotto),
   `pip check`, regressioni Station rieseguite, verificati
   `.test-media/`/`media/`/`.demo/`/`.demo-media/`, nessun server
   residuo.

**Esito test:**

```
manage.py test documents ecn --keepdb --failfast: Ran 718 tests — OK
scripts/test.sh (tutte le app): Ran 1261 tests in 4585.449s — OK
manage.py check: nessun problema (0 silenced)
pip check: nessuna dipendenza rotta
Regressioni Station (cursor-prompt-builder, log-analyzer,
ai-cycle-dogfood): tutte verdi
```

**Problemi riscontrati:**

- 3 regressioni Station pre-esistenti (non causate da questo task),
  vedi FASE 0 sopra — corrette su richiesta esplicita dell'operatore.
- 1 fix durante la scrittura dei test: `test_post_creates_approved_ecn_and_redirects`
  falliva perché `assertRedirects` segue il redirect e richiede che
  l'utente possa anche **vedere** il documento (`can_view_document`),
  non solo crearne l'ECN (`can_create_ecn` basta l'appartenenza globale
  al gruppo Authors) — risolto aggiungendo l'appartenenza alla cartella
  nel `setUp()` del test.
- Suite completa ha richiesto ~76 minuti (1261 test, incl. 63 minuti
  solo per la parte `documents ecn`); nessun timeout, nessun processo
  bloccato.

**Prossimo passo per l'operatore umano:**

1. Review Claude Code + commit gated (`commit-if-approved.sh`) — solo
   locale, nessun push, nessun merge di questa branch su `main` senza
   conferma esplicita.
2. Valutare il backlog residuo (vedi `docs/ai/SIMPLE_ECN_FLOW.md`):
   rimozione definitiva di `requires_ecn_for_revision`/`ecn_exemption`,
   badge "Tipo" in `ecn_list.html`/`ecn_detail.html`, permessi dedicati
   per ECN semplice.
3. Merge finale di `task/documentale-simple-ecn-flow` su `main`: **non
   eseguito**, in attesa di conferma esplicita dell'operatore.
