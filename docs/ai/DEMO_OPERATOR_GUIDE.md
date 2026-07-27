# Guida operatore — Demo Documentale (TASK-018)

Runbook breve e pratico per preparare, avviare e presentare la demo
locale. Per il dettaglio della validazione tecnica vedi
`docs/ai/DEMO_FLOW_VALIDATION.md` (TASK-017).

---

## Scopo della demo

Mostrare il flusso completo del Documentale — progetto, documento,
revisione, approvazione, ECN, audit — usando **un solo account
superuser**, senza bisogno di più utenti o permessi differenziati.

---

## Prerequisiti

- Repository Station con `projects/documentale-workcopy`.
- Venv già presente: `projects/documentale-workcopy/.venv`
  (`pip install -r requirements.txt` già fatto).
- Nessun `.env` necessario per la demo (le demo settings usano valori
  fittizi via variabile d'ambiente, stesso principio dei test).

---

## 1. Creare/ricreare il DB demo isolato

```bash
cd projects/documentale-workcopy
source .venv/bin/activate
python manage.py migrate --settings=config.demo_settings
```

Crea (o aggiorna) `.demo/db.sqlite3` — **file isolato**, mai il DB di
sviluppo/produzione. Rieseguibile in sicurezza in qualunque momento.

---

## 2. Popolare i dati demo

```bash
python manage.py demo_full --reset --no-email --settings=config.demo_settings
```

- `--reset` svuota e ricrea tutto da zero (usare quando si vuole uno
  stato pulito prima di una presentazione).
- Senza `--reset`, il comando è **idempotente**: rieseguirlo non crea
  duplicati (ogni scenario verifica se esiste già).
- Crea: utenti, gruppi, cartelle, progetti, documenti in tutti gli
  stati, ECN nei 6 stati, uno snapshot di progetto (`ProjectRevision`),
  record storici sanatoria.

---

## 3. Creare/garantire l'account demo

`demo_full` crea già `supervisor_demo` e `admin_demo`. Per un account
con credenziali esplicite dedicate (`demo_admin`), eseguire una volta:

```bash
python manage.py shell --settings=config.demo_settings -c "
from django.contrib.auth.models import User
u, _ = User.objects.get_or_create(username='demo_admin', defaults={
    'email': 'demo_admin@example.local', 'is_superuser': True, 'is_staff': True,
})
u.set_password('demo_admin_change_me')
u.is_superuser = True
u.is_staff = True
u.save()
"
```

Comando idempotente (`get_or_create` + reimpostazione password):
rieseguibile in sicurezza.

### Credenziali demo previste

| Username | Password | Note |
|----------|----------|------|
| `demo_admin` | `demo_admin_change_me` | Account dedicato per questa guida, superuser puro |
| `supervisor_demo` | `demo1234` | Creato da `demo_full`, pensato per presentazioni; con `DOCUMENTALE_DEMO_MODE=true` può anche autoselezionarsi come approvatore/CCB |
| `admin_demo` | `admin1234` | Creato da `demo_full`, pensato per Django Admin |

**Tutte locali, solo nel DB demo isolato — mai credenziali reali.**

---

## 4. Avviare il server demo

```bash
python manage.py runserver 127.0.0.1:8765 --settings=config.demo_settings
```

Aprire `http://127.0.0.1:8765/accounts/login/` e accedere con una delle
credenziali sopra. **Mai avviare su `0.0.0.0` o esporre in rete.**

---

## 5. Percorso demo consigliato (passo-passo)

1. **Login** come `demo_admin` (o `supervisor_demo`).
2. **Dashboard** (`/`) — panoramica.
3. **Progetti** (`/projects/`) → aprire `PRJ-DEMO-001` →
   sezione "Storico progetto": mostra lo snapshot revisione emesso
   (vedi §9 sotto per il chiarimento sul meccanismo).
4. **Documenti** (`/documents/`) → aprire `DEMO-MULTI-001`: mostra 3
   revisioni (storico completo, versioni superate).
5. **Documento con approvazione in corso**: aprire `DEMO-POL-ANY` o
   `DEMO-POL-SEQ` per mostrare le policy di approvazione (basta un
   approvatore vs sequenza ordinata).
6. **ECN** (`/ecn/`) → dashboard con ECN in tutti e 6 gli stati
   (draft, in istruttoria CCB, in revisione, approvata, rifiutata,
   chiusa). Aprire `DEMO-ECN-EXEC` per mostrare l'ECN che ha originato
   una revisione (link visibile in `version_detail`).
7. **ECN semplice (TASK-022)**: aprire `DEMO-ECN-SIMPLE-001` — la
   Rev. 01 è stata creata tramite un ECN semplice autoapprovato
   (`ECN-S-<anno>-0001`, visibile nella card "Ultimo ECN / Variante" e
   nello storico completo in Archivio), senza istruttoria né CCB. Vedi
   `docs/ai/SIMPLE_ECN_FLOW.md` per il dettaglio del flusso.
8. **Audit/storico**: dal dettaglio di un documento o versione, sezione
   "Storico eventi" — mostra le voci di audit trail generate da ogni
   azione.

---

## 6. Fermare il server

`Ctrl+C` nel terminale dove gira `runserver`, oppure se avviato in
background:

```bash
pkill -f "runserver 127.0.0.1:8765"
```

---

## 7. Pulire i dati demo (opzionale, sicuro)

I dati demo sono **completamente isolati** in `.demo/` e `.demo-media/`
(entrambi in `.gitignore`, mai committati). Per ripartire da zero:

```bash
rm -rf projects/documentale-workcopy/.demo projects/documentale-workcopy/.demo-media
python manage.py migrate --settings=config.demo_settings
python manage.py demo_full --reset --no-email --settings=config.demo_settings
```

Questo **non tocca mai** `media/` reale, `db.sqlite3` di sviluppo, né
alcun dato al di fuori delle due cartelle isolate.

---

## 8. Progetto revisionabile tramite `ProjectRevision` — chiarimento

I progetti **sono revisionabili**, ma con un meccanismo diverso dai
documenti:

- **Documenti**: ciclo `DRAFT → IN_APPROVAL → APPROVED/REJECTED`.
- **Progetti**: `ProjectRevision` è uno **snapshot immutabile**
  (tipo `version` o `revision`) dei metadati e documenti correnti del
  progetto in un dato momento. Non c'è un ciclo di approvazione per lo
  snapshot: una volta emesso (`issued`), diventa immutabile.

In demo: `demo_full` (dopo TASK-018) crea automaticamente uno snapshot
revisione per `PRJ-DEMO-001`, visibile in "Storico progetto" —
**non più vuoto** come rilevato in TASK-017.

---

## 9. ECN semplice vs "revisione senza ECN" (legacy) — chiarimento

Dopo TASK-022, ogni nuovo documento richiede sempre un ECN per le
revisioni successive alla prima approvazione (`requires_ecn_for_revision`
default `True`, non più derogabile da UI). Per i casi a basso impatto
esiste l'**ECN semplice** (`ecn:ecn_create_simple`): autoapprovato,
nessuna CCB, stesso audit trail di un ECN standard — vedi
`docs/ai/SIMPLE_ECN_FLOW.md` per il dettaglio completo.

La vecchia modalità "revisione senza ECN" (`requires_ecn_for_revision=False`)
resta supportata solo per **compatibilità con documenti già esistenti**
con quel flag, non è più proposta come percorso nella creazione di un
nuovo documento.

---

## 10. Cosa NON è oggetto di questa demo

- Deploy reale o PostgreSQL (vedi `docs/ai/DEPLOY_REHEARSAL_PLAN.md`
  per una prova di deploy separata, su VM isolata).
- Permessi cartella granulari multiutente (`FolderPermissionGrant`,
  `ProjectFolderMembership`) — la demo usa il bypass superuser, non
  rappresentativo di un utente con ruolo limitato.
- Migrazione permessi legacy / refactor `can_view_ecn` (fuori scope,
  vedi `docs/ai/PERMISSIONS_AUDIT.md`).
- Firma digitale (non presente per design, vedi `CLAUDE.md`).
- Invio email reale (demo usa sempre `--no-email`, backend `locmem`).

---

## 11. Troubleshooting minimo

| Sintomo | Causa probabile | Soluzione |
|---------|-----------------|-----------|
| `manage.py` si lamenta di dipendenze mancanti | Venv non attiva | `source .venv/bin/activate` prima di ogni comando |
| Errore "già esistente" durante `demo_full` senza `--reset` | Comportamento atteso (idempotenza) | Usare `--reset` per ripartire da zero |
| Pagina 500 dopo `migrate` | DB demo corrotto/incompleto | Cancellare `.demo/` e rifare `migrate` + `demo_full --reset` |
| Login fallisce | Password errata o utente non ancora creato | Rieseguire il comando di creazione `demo_admin` (§3) |
| Server non raggiungibile | Porta occupata o server non avviato | Verificare `ps aux | grep runserver`, cambiare porta se necessario |
| Windows: `UnicodeEncodeError: 'charmap' codec can't encode character...` durante `demo_full` (o altri comandi `manage.py` con output non-ASCII, es. `→`) | Console Windows di default usa il codepage cp1252, non UTF-8 | Impostare `PYTHONIOENCODING=utf-8` come variabile d'ambiente prima del comando (es. `set PYTHONIOENCODING=utf-8` in PowerShell/cmd, `export PYTHONIOENCODING=utf-8` in Git Bash). Non serve su Linux/macOS. |

---

## Riferimenti

- `docs/ai/DEMO_FLOW_VALIDATION.md` — validazione tecnica dettagliata
  (TASK-017), azioni verificate passo-passo.
- `documents/management/commands/demo_full.py` — comando demo
  completo (esteso in TASK-018 con lo scenario `ProjectRevision`).
- `config/demo_settings.py` — isolamento DB/media per la demo.
