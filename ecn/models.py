from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models


class ChangeNotice(models.Model):
    """Richiesta di modifica controllata (ECN / Variante) per un documento emesso."""

    # Lunghezza minima del dettaglio quando l'applicabilità è "limitata":
    # soglia semplice e non arbitraria per scartare risposte palesemente non
    # informative (es. "-", "n/a") senza introdurre valutazioni linguistiche
    # o AI, come richiesto dalla specifica della funzionalità.
    APPLICABILITY_DETAIL_MIN_LENGTH = 10

    class Status(models.TextChoices):
        DRAFT           = 'draft',           'Bozza'
        CCB_PREPARATION = 'ccb_preparation', 'Istruttoria CCB'
        UNDER_REVIEW    = 'under_review',    'In Valutazione CCB'
        APPROVED        = 'approved',        'Approvata'
        REJECTED        = 'rejected',        'Rifiutata'
        CLOSED          = 'closed',          'Chiusa'

    class Motivation(models.TextChoices):
        IMPROVEMENT    = 'improvement',    'Miglioramento tecnico'
        CUSTOMER       = 'customer',       'Richiesta cliente'
        NON_CONFORMITY = 'non_conformity', 'Non conformità'
        DESIGN         = 'design',         'Ottimizzazione progettuale'
        REGULATORY     = 'regulatory',     'Adeguamento normativo'
        OTHER          = 'other',          'Altro'

    class CCBClass(models.TextChoices):
        CLASS1 = 'class1', 'Classe 1'
        CLASS2 = 'class2', 'Classe 2'

    class CCBPolicy(models.TextChoices):
        ANY        = 'any',        'Qualsiasi approvatore (ANY)'
        ALL        = 'all',        'Tutti gli approvatori (ALL)'
        SEQUENTIAL = 'sequential', 'Sequenziale (SEQUENTIAL)'

    class FlowType(models.TextChoices):
        STANDARD = 'standard', 'Standard (CCB)'
        SIMPLE   = 'simple',   'Semplice (automatico)'

    class Applicability(models.TextChoices):
        """Campo di applicazione della modifica, valutato dalla CCB nel
        dossier istruttorio (obbligatorio prima dell'invio al voto per ogni
        ECN standard) — non una dichiarazione del proponente.

        Informazione strutturata e dichiarativa: NON seleziona automaticamente
        quale DocumentVersion viene mostrata a un progetto (resta
        Document.current_version, invariato) — vedi applicability_scope_notice.
        """
        GENERAL = 'general', 'Applicazione generale'
        FUTURE  = 'future',  'Applicazione futura'
        LIMITED = 'limited', 'Applicazione limitata'

    # Descrizioni sintetiche mostrate in UI ed email accanto all'etichetta —
    # unica fonte per evitare testo duplicato/divergente nei template.
    APPLICABILITY_DESCRIPTIONS = {
        Applicability.GENERAL: (
            'La modifica è destinata a tutti i progetti e alle realizzazioni interessate.'
        ),
        Applicability.FUTURE: (
            'La modifica è destinata alle nuove commesse o ai nuovi progetti. '
            "L'applicazione ai progetti già esistenti deve essere valutata separatamente."
        ),
        Applicability.LIMITED: (
            'La modifica si applica soltanto ai casi specificati nel dettaglio '
            "dell'applicabilità."
        ),
    }

    # Classe CSS badge per categoria — centralizzata qui, mai duplicata nei
    # template (vedi src/css/main.css: .badge-applicability-*).
    APPLICABILITY_BADGE_CLASSES = {
        Applicability.GENERAL: 'badge-applicability-general',
        Applicability.FUTURE:  'badge-applicability-future',
        Applicability.LIMITED: 'badge-applicability-limited',
    }

    # ------------------------------------------------------------------
    # Identificazione
    # ------------------------------------------------------------------
    code  = models.CharField(max_length=50, unique=True, verbose_name='Codice ECN')
    title = models.CharField(max_length=255, verbose_name='Titolo')

    # ------------------------------------------------------------------
    # Descrizioni proposta
    # ------------------------------------------------------------------
    description = models.TextField(
        blank=True,
        verbose_name='Descrizione modifica proposta',
    )
    motivation = models.CharField(
        max_length=30,
        choices=Motivation.choices,
        verbose_name='Categoria motivazione',
    )
    motivation_detail = models.TextField(
        blank=True,
        verbose_name='Motivazione (dettaglio)',
        help_text='Descrizione estesa della motivazione della variante.',
    )
    commessa = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Commessa / ordine',
    )

    # ------------------------------------------------------------------
    # Applicabilità — campo di applicazione della modifica.
    #
    # È una valutazione della CCB, compilata nel dossier istruttorio
    # (ecn.services.update_ccb_dossier) dal responsabile istruttoria —
    # NON una dichiarazione del proponente al momento della richiesta
    # (TASK-037, correzione rispetto all'impostazione iniziale TASK-036,
    # che la chiedeva per errore già in create_change_notice/ChangeNoticeForm).
    #
    # Nullable perché resta senza valore per due motivi legittimi, non solo
    # uno:
    #   - ECN standard non ancora arrivato in istruttoria CCB (DRAFT/appena
    #     creato), o storico antecedente a questa funzionalità — NON va
    #     inventato retroattivamente;
    #   - ECN a flusso semplice (TASK-022): nessuna CCB si riunisce mai in
    #     quel flusso, quindi l'applicabilità non viene mai richiesta né
    #     decisa (decisione esplicita, non un'omissione).
    #
    # Obbligatoria applicativamente solo per l'ECN standard, solo prima
    # dell'invio al voto quando si parte da CCB_PREPARATION (vedi
    # ecn.services.submit_change_notice) e di nuovo, in difesa, al momento
    # dell'approvazione finale (ecn.services.approve_change_notice) — mai
    # al momento della creazione. Diventa immutabile appena l'ECN lascia
    # CCB_PREPARATION (update_ccb_dossier non è più chiamabile).
    #
    # Distinto da:
    #   - project/commessa: riferimento/contesto dell'ECN, non il suo campo
    #     di applicazione;
    #   - ccb_other_impact: impatti collaterali valutati in istruttoria CCB,
    #     non l'ambito di applicazione della modifica;
    #   - description/motivation: cosa cambia e perché, non a chi si applica.
    # ------------------------------------------------------------------
    applicability_category = models.CharField(
        max_length=20,
        choices=Applicability.choices,
        null=True,
        blank=True,
        verbose_name='Applicabilità',
        help_text=(
            'Ambito di applicazione della modifica, valutato dalla CCB nel dossier '
            'istruttorio. Nullo prima dell\'istruttoria, per gli ECN a flusso semplice '
            '(nessuna CCB) e per gli ECN storici antecedenti a questa funzionalità.'
        ),
    )
    applicability_detail = models.TextField(
        blank=True,
        verbose_name="Dettaglio dell'applicabilità",
        help_text=(
            'Obbligatorio per "Applicazione limitata": specifica progetti, commesse, '
            'configurazioni, prodotti, unità, condizioni o eccezioni interessate. '
            'Facoltativo per le altre due categorie.'
        ),
    )

    # ------------------------------------------------------------------
    # Riferimenti a documento, versione e progetto
    # FK a stringa per evitare dipendenze circolari con le altre app
    # ------------------------------------------------------------------
    document = models.ForeignKey(
        'documents.Document',
        on_delete=models.PROTECT,
        related_name='ecns',
        verbose_name='Documento',
    )
    # Snapshot della versione corrente al momento della proposta ECN.
    # Serve per tracciare su quale revisione si è basata la variante.
    document_version = models.ForeignKey(
        'documents.DocumentVersion',
        on_delete=models.PROTECT,
        related_name='ecns_as_baseline',
        verbose_name='Revisione di riferimento',
        help_text='Versione del documento corrente al momento della proposta.',
    )
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ecns',
        verbose_name='Progetto',
    )

    # ------------------------------------------------------------------
    # Proponente e stato
    # ------------------------------------------------------------------
    proposed_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='proposed_ecns',
        verbose_name='Proponente',
    )
    proposed_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Proposto il',
    )
    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Inviato a CCB il',
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name='Stato',
    )
    flow_type = models.CharField(
        max_length=20,
        choices=FlowType.choices,
        default=FlowType.STANDARD,
        verbose_name='Tipo di flusso',
        help_text=(
            'Standard: passa da istruttoria/CCB. '
            'Semplice: autoapprovato, nessuna CCB (TASK-022).'
        ),
    )

    # ------------------------------------------------------------------
    # Politica di approvazione CCB
    # ------------------------------------------------------------------
    ccb_policy = models.CharField(
        max_length=20,
        choices=CCBPolicy.choices,
        default=CCBPolicy.ALL,
        verbose_name='Politica approvazione CCB',
        help_text='ANY: basta un approvatore; ALL: tutti; SEQUENTIAL: in ordine.',
    )

    # ------------------------------------------------------------------
    # Responsabile istruttoria CCB
    # Compilazione del dossier prima dell'invio ai votanti.
    # ------------------------------------------------------------------
    ccb_coordinator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='coordinating_ecns',
        verbose_name='Responsabile istruttoria CCB',
        help_text='Utente incaricato di compilare il dossier istruttorio prima dell\'invio ai votanti CCB.',
    )

    # ------------------------------------------------------------------
    # Dossier istruttorio CCB
    # Compilato dal responsabile istruttoria prima dell'invio ai votanti.
    # ------------------------------------------------------------------
    ccb_class = models.CharField(
        max_length=10,
        choices=CCBClass.choices,
        null=True,
        blank=True,
        verbose_name='Classe variante',
    )
    ccb_requirements = models.TextField(
        blank=True,
        verbose_name='Analisi requisiti',
        help_text='Conformità ai requisiti tecnici e normativi.',
    )
    ccb_technical_impact = models.TextField(
        blank=True,
        verbose_name='Impatto tecnico',
    )
    ccb_cost_impact = models.TextField(
        blank=True,
        verbose_name='Impatto costi',
    )
    ccb_time_impact = models.TextField(
        blank=True,
        verbose_name='Impatto tempi',
    )
    ccb_quality_impact = models.TextField(
        blank=True,
        verbose_name='Impatto qualità',
    )
    ccb_other_impact = models.TextField(
        blank=True,
        verbose_name='Impatto su altri documenti / parti',
    )
    ccb_notes = models.TextField(
        blank=True,
        verbose_name='Note CCB',
        help_text='Note aggiuntive del revisore CCB, incluse le motivazioni del rifiuto.',
    )
    ccb_reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_ecns',
        verbose_name='Revisore CCB',
    )
    ccb_reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Revisionato il',
    )

    # ------------------------------------------------------------------
    # Esecuzione: nuova revisione del documento collegata all'ECN
    # Popolato quando l'autore/esecutore crea la nuova bozza a valle
    # dell'ECN approvato.
    # ------------------------------------------------------------------
    executed_version = models.ForeignKey(
        'documents.DocumentVersion',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ecns_executed',
        verbose_name='Revisione eseguita',
    )
    executed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Eseguita il',
    )

    # ------------------------------------------------------------------
    # Chiusura: verificata dal Responsabile Qualità
    # ------------------------------------------------------------------
    close_notes = models.TextField(
        blank=True,
        verbose_name='Note chiusura qualità',
        help_text='Note del Responsabile Qualità a chiusura della variante.',
    )
    closed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='closed_ecns',
        verbose_name='Chiuso da',
    )
    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Chiuso il',
    )

    # ------------------------------------------------------------------
    # Metadati
    # ------------------------------------------------------------------
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_ecns',
        verbose_name='Creato da',
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Aggiornato il',
    )
    locked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='locked_ecns',
        verbose_name='In lavorazione da',
        help_text='Utente che sta compilando il dossier o votando in questo momento (lock temporaneo).',
    )
    locked_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='In lavorazione dal',
    )

    class Meta:
        verbose_name        = 'ECN / Variante'
        verbose_name_plural = 'ECN / Varianti'
        ordering            = ['-proposed_at']

    def __str__(self):
        return f"{self.code} — {self.title} [{self.get_status_display()}]"

    # ------------------------------------------------------------------
    # Applicabilità — helper centralizzati (validazione + presentazione)
    # ------------------------------------------------------------------
    @property
    def applicability_is_registered(self):
        """
        False quando il valore è nullo — non ancora deciso dalla CCB
        (istruttoria non completata), ECN a flusso semplice (nessuna CCB
        si riunisce mai), o ECN storico antecedente a questa funzionalità.
        """
        return bool(self.applicability_category)

    @property
    def applicability_display(self):
        """Etichetta leggibile, incluso il caso non ancora deciso/non applicabile."""
        if not self.applicability_category:
            return 'Applicabilità non specificata'
        return self.get_applicability_category_display()

    @property
    def applicability_short_description(self):
        """Descrizione sintetica della categoria (vuota se non registrata)."""
        if not self.applicability_category:
            return ''
        return self.APPLICABILITY_DESCRIPTIONS.get(self.applicability_category, '')

    @property
    def applicability_badge_class(self):
        """Classe CSS badge centralizzata (vedi src/css/main.css)."""
        if not self.applicability_category:
            return 'badge-applicability-unset'
        return self.APPLICABILITY_BADGE_CLASSES.get(
            self.applicability_category, 'badge-applicability-unset',
        )

    @property
    def applicability_shows_scope_notice(self):
        """
        True per "Applicazione futura" e "Applicazione limitata": in questi
        casi la UI deve mostrare l'avviso che l'applicabilità è
        un'informazione dichiarativa e non assegna automaticamente revisioni
        differenti ai singoli progetti (Document.current_version resta unico
        e invariato — nessun resolver per-progetto introdotto da questo campo).
        """
        return self.applicability_category in (
            self.Applicability.FUTURE, self.Applicability.LIMITED,
        )

    @classmethod
    def validate_applicability(cls, category, detail):
        """
        Validazione centralizzata server-side, riusata da form e service
        (mai bypassabile inviando direttamente al service saltando il form).

        Ritorna (category, detail_pulito). Solleva ValidationError con un
        error_dict {'applicability_category': ..., 'applicability_detail': ...}
        così form.clean() può smistare i messaggi sul campo giusto.
        """
        errors = {}

        if category not in cls.Applicability.values:
            errors['applicability_category'] = (
                "Seleziona una categoria di applicabilità valida "
                "(Applicazione generale / futura / limitata)."
            )

        detail = (detail or '').strip()
        if category == cls.Applicability.LIMITED:
            if not detail:
                errors['applicability_detail'] = (
                    'Il dettaglio è obbligatorio per "Applicazione limitata": specifica '
                    'progetti, commesse, configurazioni, prodotti, unità, condizioni o '
                    'eccezioni a cui la modifica si applica o non si applica.'
                )
            elif len(detail) < cls.APPLICABILITY_DETAIL_MIN_LENGTH:
                errors['applicability_detail'] = (
                    'Il dettaglio inserito è troppo breve per essere informativo '
                    f'(minimo {cls.APPLICABILITY_DETAIL_MIN_LENGTH} caratteri). '
                    'Specifica concretamente progetti, commesse o condizioni interessate.'
                )

        if errors:
            raise ValidationError(errors)

        return category, detail


class ChangeNoticeApprover(models.Model):
    """Approvatore CCB assegnato a un ECN."""

    change_notice = models.ForeignKey(
        ChangeNotice,
        on_delete=models.CASCADE,
        related_name='approvers',
        verbose_name='ECN',
    )
    user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='ecn_approver_roles',
        verbose_name='Approvatore',
    )
    order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name='Ordine',
        help_text='Usato per la politica SEQUENTIAL.',
    )
    is_required = models.BooleanField(
        default=True,
        verbose_name='Approvazione obbligatoria',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Approvatore CCB'
        verbose_name_plural = 'Approvatori CCB'
        unique_together     = [['change_notice', 'user']]
        ordering            = ['order', 'id']

    def __str__(self):
        return f"{self.change_notice.code} — {self.user.username}"


class ChangeNoticeDecision(models.Model):
    """Decisione individuale di un approvatore CCB su un ECN."""

    class Decision(models.TextChoices):
        APPROVE = 'approve', 'Approvato'
        REJECT  = 'reject',  'Rifiutato'

    change_notice = models.ForeignKey(
        ChangeNotice,
        on_delete=models.CASCADE,
        related_name='decisions',
        verbose_name='ECN',
    )
    approver = models.ForeignKey(
        ChangeNoticeApprover,
        on_delete=models.PROTECT,
        related_name='decisions',
        verbose_name='Approvatore',
    )
    user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='ecn_decisions',
        verbose_name='Utente',
    )
    decision = models.CharField(
        max_length=10,
        choices=Decision.choices,
        verbose_name='Decisione',
    )
    comment = models.TextField(
        blank=True,
        verbose_name='Commento',
    )
    decided_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Deciso il',
    )

    class Meta:
        verbose_name        = 'Decisione CCB'
        verbose_name_plural = 'Decisioni CCB'
        unique_together     = [['change_notice', 'approver']]
        ordering            = ['decided_at', 'id']

    def __str__(self):
        return (
            f"{self.change_notice.code} — {self.user.username}: "
            f"{self.get_decision_display()}"
        )


class ChangeNoticeAttachment(models.Model):
    """File allegato a un ECN (specifiche tecniche, disegni, analisi, ecc.)."""

    change_notice = models.ForeignKey(
        ChangeNotice,
        on_delete=models.CASCADE,
        related_name='attachments',
        verbose_name='ECN',
    )
    file = models.FileField(
        upload_to='ecn/attachments/%Y/%m/',
        verbose_name='File',
    )
    # original_filename: nome del file al momento del caricamento,
    # necessario per i download (FileResponse filename) — coerente con
    # ApprovalRequestAttachment e DocumentFile già presenti nel progetto.
    original_filename = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Nome file originale',
    )
    title = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Titolo',
    )
    description = models.TextField(
        blank=True,
        verbose_name='Descrizione',
    )
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='uploaded_ecn_attachments',
        verbose_name='Caricato da',
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Caricato il',
    )
    size = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        verbose_name='Dimensione (byte)',
    )
    extension = models.CharField(
        max_length=20,
        blank=True,
        verbose_name='Estensione',
    )

    class Meta:
        verbose_name        = 'Allegato ECN'
        verbose_name_plural = 'Allegati ECN'
        ordering            = ['uploaded_at']

    def __str__(self):
        name = self.original_filename or self.title or '—'
        return f"{self.change_notice.code} — {name}"
