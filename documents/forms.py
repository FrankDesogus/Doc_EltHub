from django import forms
from django.contrib.auth.models import User

from auditlog.historical_forms import SanatoriaFieldsMixin
from documents.document_types import (
    CATEGORY_BY_DOCUMENT_TYPE_VALUE,
    DOCUMENT_TYPE_CHOICES,
    is_valid_document_type_for_category,
)
from documents.models import Document
from documents.versioning import SequenceScheme, normalize_sequence_value, validate_sequence_value
from projects.models import ProjectFolder


class DocumentTypeSelect(forms.Select):
    """Select con data-category per opzione, per il filtro a cascata via JS
    in new_document.html (vedi TASK-020)."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        category = CATEGORY_BY_DOCUMENT_TYPE_VALUE.get(str(value), '')
        if category:
            option['attrs']['data-category'] = category
        return option


class FolderChoiceField(forms.ModelChoiceField):
    """
    ModelChoiceField che mostra il percorso gerarchico completo nell'etichetta
    di ogni opzione (es. "Ingegneria › PRJ-DEMO-001 — Amplificatore RF Demo"),
    invece del solo codice/nome della cartella foglia.

    Con molte cartelle annidate, una tendina piatta rende difficile capire
    dove si trova ciascuna voce nell'albero (segnalato dagli operatori).
    Mostrare il percorso completo, unito a un campo di ricerca lato client
    (vedi new_document.html) che filtra il testo delle opzioni, risolve il
    problema senza sostituire il controllo nativo con un widget custom.

    folder_names_by_pk va popolato dal form prima del rendering (nome di
    ogni cartella per pk, per risolvere gli antenati dal materialized path
    senza una query per opzione).
    """
    folder_names_by_pk: dict = {}

    def label_from_instance(self, obj):
        if not obj.path:
            return f"{obj.code} — {obj.name}"
        ancestor_pks = [int(p) for p in obj.path.split('/') if p][:-1]
        crumbs = [self.folder_names_by_pk.get(pk, '?') for pk in ancestor_pks]
        crumbs.append(f"{obj.code} — {obj.name}")
        return ' › '.join(crumbs)


class DocumentCreateForm(SanatoriaFieldsMixin, forms.Form):
    code = forms.CharField(
        max_length=50,
        required=False,
        label='Codice documento',
        help_text=(
            'Lasciare vuoto: il codice viene generato automaticamente secondo la '
            'procedura aziendale. Compilare solo in modalità sanatoria (codice storico '
            'reale del documento) o per categoria "Altro" (documenti fuori procedura).'
        ),
    )
    title = forms.CharField(max_length=255, label='Titolo')
    description = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
        label='Descrizione',
    )
    category = forms.ChoiceField(
        choices=list(Document.Category.choices) + [('OTHER', 'Altro')],
        label='Categoria',
    )
    category_other = forms.CharField(
        max_length=50,
        required=False,
        label='Specifica categoria',
        help_text='Obbligatorio se la categoria è "Altro": diventa la categoria effettiva del documento.',
    )
    document_type = forms.ChoiceField(
        choices=[('', '— seleziona prima la categoria —')] + DOCUMENT_TYPE_CHOICES,
        required=False,
        label='Tipo documento',
        help_text=(
            'Le opzioni disponibili dipendono dalla Categoria selezionata sopra. '
            'Obbligatorio: determina il codice documento generato automaticamente '
            '(non richiesto per categoria "Altro" o in modalità sanatoria).'
        ),
        widget=DocumentTypeSelect,
    )
    document_type_other = forms.CharField(
        max_length=100,
        required=False,
        label='Specifica tipo documento',
        help_text='Obbligatorio se la categoria è "Altro".',
    )
    project_folder = FolderChoiceField(
        queryset=ProjectFolder.objects.none(),
        required=True,
        label='Cartella',
        empty_label='— seleziona cartella —',
        help_text='La cartella determina dove il documento viene archiviato e quali utenti possono accedervi.',
    )
    revision_scheme = forms.ChoiceField(
        choices=SequenceScheme.choices,
        initial=SequenceScheme.NUMERIC,
        label='Schema revisione',
        help_text='Numerica (00, 01…) o Alfabetica (A, B…). Applicato alle revisioni future.',
    )
    revision_label = forms.CharField(
        max_length=20,
        initial='00',
        label='Etichetta prima revisione',
        help_text='Numerica: 00. Alfabetica: A.',
    )
    change_summary = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
        label='Sommario modifiche',
    )
    ecn_exemption = forms.BooleanField(
        required=False,
        initial=False,
        label='Consenti revisioni senza ECN obbligatorio',
        help_text=(
            'Se spuntato, le revisioni successive potranno essere create senza un ECN approvato. '
            'Il normale ciclo di approvazione rimane obbligatorio.'
        ),
    )
    allow_simple_ecn = forms.BooleanField(
        required=False,
        initial=True,
        label='Consenti ECN a flusso semplice per questo documento',
        help_text=(
            'Se disattivato, per questo documento sarà possibile creare solo ECN '
            'standard (con istruttoria e votazione CCB): l\'ECN a flusso semplice '
            '(autoapprovato, senza CCB) non sarà proponibile. L\'ECN standard resta '
            'sempre disponibile in ogni caso. Modificabile in seguito dai metadati '
            'del documento.'
        ),
    )
    requires_approved_pdf = forms.BooleanField(
        required=False,
        initial=False,
        label='Richiede copia PDF approvata con registro delle approvazioni',
        help_text=(
            'Se attivo: prima di ogni invio in approvazione sarà richiesto un PDF che '
            'rappresenti il file sorgente (prodotto automaticamente quando possibile, '
            'altrimenti caricato dall\'autore); al termine dell\'approvazione verrà '
            'generata una copia PDF con il registro delle approvazioni ed eventuali '
            'firme visive. Le firme non costituiscono firma digitale. '
            'Modificabile in seguito dai metadati del documento — vale solo per le '
            'revisioni non ancora inviate in approvazione.'
        ),
    )
    file = forms.FileField(required=False, label='File operativo')

    def __init__(self, *args, user=None, initial_folder=None, current_user=None, **kwargs):
        """
        initial_folder: cartella suggerita dal contesto di provenienza
        (cartella o progetto di partenza) — è solo una preselezione, non
        un vincolo: il queryset resta sempre l'intero elenco delle cartelle
        scrivibili dall'utente, che può scegliere liberamente un'altra
        destinazione prima di salvare.
        """
        super().__init__(*args, current_user=current_user, **kwargs)
        if user is not None and (user.is_superuser or user.is_staff):
            qs = ProjectFolder.objects.filter(status='active').order_by('code')
            self.fields['project_folder'].queryset = qs
        elif user is not None:
            from projects.permissions import get_writable_folder_ids
            writable_ids = get_writable_folder_ids(user)
            qs = ProjectFolder.objects.filter(pk__in=writable_ids, status='active').order_by('code')
            self.fields['project_folder'].queryset = qs

        if initial_folder is not None:
            self.fields['project_folder'].initial = initial_folder

        # Nomi di tutte le cartelle per risolvere il percorso gerarchico
        # (FolderChoiceField.label_from_instance) senza una query per opzione.
        self.fields['project_folder'].folder_names_by_pk = dict(
            ProjectFolder.objects.values_list('pk', 'name')
        )

    def clean(self):
        cleaned = super().clean()
        scheme = cleaned.get('revision_scheme', SequenceScheme.NUMERIC)
        label = cleaned.get('revision_label', '')
        if label:
            try:
                label = normalize_sequence_value(label, scheme)
                validate_sequence_value(label, scheme)
                cleaned['revision_label'] = label
            except Exception as exc:
                self.add_error('revision_label', str(exc))

        category = cleaned.get('category', '')
        document_type = cleaned.get('document_type', '')
        is_other_category = (category == 'OTHER')

        if is_other_category:
            category_other = cleaned.get('category_other', '').strip()
            if not category_other:
                self.add_error('category_other', 'Specifica la categoria per un documento "Altro".')
            cleaned['category'] = category_other

            document_type_other = cleaned.get('document_type_other', '').strip()
            if not document_type_other:
                self.add_error('document_type_other', 'Specifica il tipo di documento per un documento "Altro".')
            document_type = document_type_other
            cleaned['document_type'] = document_type_other
        elif document_type and not is_valid_document_type_for_category(document_type, category):
            self.add_error(
                'document_type',
                'Il tipo selezionato non è valido per la categoria scelta.',
            )

        # Codice documento: automatico salvo modalità sanatoria (codice storico)
        # o categoria "Altro" (documento fuori procedura) — inserito manualmente
        # in entrambi i casi. Vedi documents.services.generate_document_code
        # per il percorso automatico.
        sanatoria = cleaned.get('sanatoria', False)
        code = cleaned.get('code', '').strip()
        if sanatoria or is_other_category:
            if not code:
                self.add_error(
                    'code',
                    'In modalità sanatoria il codice documento storico è obbligatorio.'
                    if sanatoria else
                    'Per un documento di categoria "Altro" il codice va inserito manualmente.',
                )
            elif Document.objects.filter(code=code).exists():
                self.add_error('code', f'Un documento con codice "{code}" esiste già.')
            cleaned['code'] = code
        else:
            cleaned['code'] = ''
            if not document_type:
                self.add_error(
                    'document_type',
                    'Il tipo documento è obbligatorio per generare automaticamente il codice.',
                )

        return cleaned


class DocumentRevisionCreateForm(SanatoriaFieldsMixin, forms.Form):
    revision_label = forms.CharField(max_length=20, label='Etichetta revisione')
    change_summary = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
        label='Sommario modifiche',
    )
    file = forms.FileField(required=False, label='File operativo')

    def __init__(self, *args, revision_scheme=None, current_user=None, **kwargs):
        super().__init__(*args, current_user=current_user, **kwargs)
        self._revision_scheme = revision_scheme

    def clean_revision_label(self):
        label = self.cleaned_data.get('revision_label', '')
        if self._revision_scheme and label:
            from django.core.exceptions import ValidationError as DjVE
            try:
                label = normalize_sequence_value(label, self._revision_scheme)
                validate_sequence_value(label, self._revision_scheme)
            except DjVE as exc:
                raise forms.ValidationError(str(exc))
        return label


class DocumentVersionEditForm(forms.Form):
    revision_label = forms.CharField(max_length=20, label='Etichetta revisione')
    change_summary = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
        label='Sommario modifiche',
    )
    file = forms.FileField(
        required=False,
        label='Sostituisci file operativo',
        help_text='Lascia vuoto per mantenere il file esistente.',
    )

    def __init__(self, *args, revision_scheme=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._revision_scheme = revision_scheme

    def clean_revision_label(self):
        label = self.cleaned_data.get('revision_label', '')
        if self._revision_scheme and label:
            from django.core.exceptions import ValidationError as DjVE
            try:
                label = normalize_sequence_value(label, self._revision_scheme)
                validate_sequence_value(label, self._revision_scheme)
            except DjVE as exc:
                raise forms.ValidationError(str(exc))
        return label


class DocumentMetadataEditForm(forms.ModelForm):
    revision_scheme = forms.ChoiceField(
        choices=SequenceScheme.choices,
        label='Schema revisione',
        help_text=(
            'Il cambio dello schema non modifica le revisioni storiche. '
            'La prima revisione successiva dovrà essere inserita manualmente.'
        ),
    )

    class Meta:
        model = Document
        fields = ['title', 'description', 'revision_scheme', 'requires_approved_pdf']
        labels = {
            'title': 'Titolo',
            'description': 'Descrizione',
            'requires_approved_pdf': 'Richiede copia PDF approvata con registro delle approvazioni',
        }
        help_texts = {
            'requires_approved_pdf': (
                'Vale solo per le revisioni non ancora inviate in approvazione: le '
                'revisioni storiche e i workflow già in corso non cambiano. Se esiste '
                'già una bozza senza PDF e questa opzione viene attivata, sarà '
                'necessario fornire un PDF prima di poterla inviare in approvazione.'
            ),
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, current_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Allineamento 2026-07-28 alla decisione presa per allow_simple_ecn:
        # solo superuser o supervisor_demo (demo mode) possono cambiare questa
        # configurazione DOPO la creazione del documento — non autori/manager,
        # che pure possono modificare titolo/descrizione/schema/PDF. L'autore
        # può comunque impostarla liberamente in fase di creazione documento
        # (DocumentCreateForm, invariato). Il campo non viene aggiunto affatto
        # al form per chi non è autorizzato: un tentativo di POST grezzo con
        # allow_simple_ecn=on viene ignorato (nessun campo, nessun cleaned_data),
        # non solo nascosto lato client.
        from documents.permissions import can_edit_simple_ecn_flag
        if current_user is not None and can_edit_simple_ecn_flag(current_user):
            self.fields['allow_simple_ecn'] = forms.BooleanField(
                required=False,
                initial=self.instance.allow_simple_ecn if self.instance else True,
                label='Consenti ECN a flusso semplice per questo documento',
                help_text=(
                    'Se disattivato, per i prossimi ECN di questo documento sarà possibile '
                    'usare solo il flusso standard (istruttoria e votazione CCB): il flusso '
                    'semplice (autoapprovato) non sarà proponibile. L\'ECN standard resta '
                    'sempre disponibile. Vale solo per gli ECN non ancora creati: gli ECN '
                    'già esistenti e i workflow già in corso non cambiano.'
                ),
            )


class ApproverRowForm(forms.Form):
    approver = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('last_name', 'first_name', 'username'),
        label='Approvatore',
        empty_label='— seleziona utente —',
        required=False,
    )

    def __init__(self, *args, current_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from config.demo_utils import is_demo_supervisor
        if current_user and is_demo_supervisor(current_user):
            # Demo mode: l'unico approvatore selezionabile è il supervisore stesso
            self.fields['approver'].queryset = User.objects.filter(pk=current_user.pk)
        else:
            self.fields['approver'].queryset = User.objects.filter(
                is_active=True
            ).order_by('last_name', 'first_name', 'username')


class BaseApproverFormSet(forms.BaseFormSet):
    def __init__(self, *args, current_user=None, **kwargs):
        self.current_user = current_user
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs['current_user'] = self.current_user
        return kwargs

    def clean(self):
        if any(self.errors):
            return
        selected = []
        for form in self.forms:
            if form.cleaned_data and form.cleaned_data.get('approver'):
                approver = form.cleaned_data['approver']
                if approver in selected:
                    raise forms.ValidationError(
                        f"L'utente '{approver}' è selezionato più di una volta."
                    )
                selected.append(approver)
        if not selected:
            raise forms.ValidationError("Devi selezionare almeno un approvatore.")


ApproverFormSet = forms.formset_factory(
    ApproverRowForm,
    formset=BaseApproverFormSet,
    extra=0,
)


class SubmitForApprovalForm(SanatoriaFieldsMixin, forms.Form):
    approval_policy = forms.ChoiceField(
        choices=[
            ('any', 'Basta un approvatore'),
            ('all', 'Devono approvare tutti'),
            ('sequential', 'Approvazione sequenziale'),
        ],
        initial='all',
        label='Modalità approvazione',
    )
    due_date = forms.DateField(
        required=False,
        label='Scadenza approvazione',
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    signature_template_file = forms.FileField(
        required=False,
        label='Modello da firmare',
        help_text='Allegato opzionale consultabile dagli approvatori.',
    )
