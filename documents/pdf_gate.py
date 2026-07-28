"""
Gate di invio in approvazione (TASK-026, reso opzionale in TASK-033).

Una DocumentVersion può restare in bozza senza alcun PDF di
rappresentazione, ma non può essere inviata in approvazione finché non ne
esiste uno valido, aggiornato rispetto al file sorgente corrente e (quando
la policy lo richiede) confermato dall'autore. Questo è l'unico punto in
cui il vincolo diventa bloccante: la bozza stessa non è mai bloccata.

L'intero gate si applica **solo** ai documenti con
`document.requires_approved_pdf=True` (TASK-033): per gli altri documenti
il workflow di approvazione continua invariato, senza alcun gate PDF. Il
valore è letto dal vivo al momento dell'invio — è proprio questa lettura,
combinata con l'immutabilità della DocumentVersion dopo l'invio (lo stato
non è più DRAFT/REJECTED), a "congelare" implicitamente il comportamento
per quella specifica richiesta di approvazione, senza bisogno di un campo
di snapshot dedicato.

Il gate riguarda inoltre specificamente il file sorgente e la sua
rappresentazione PDF: una DocumentVersion senza alcun file operativo
(`version.file is None`) resta una fattispecie preesistente e indipendente
da questa funzionalità (il campo è nullable da prima di questo lavoro) e
non viene bloccata qui.
"""

from django.core.exceptions import ValidationError


def get_pdf_submission_status(version):
    """
    Stato strutturato del PDF di rappresentazione rispetto all'invio in
    approvazione — unica fonte di verità, usata sia da assert_ready_for_submission
    (che solleva un'eccezione) sia dalla pagina di invio (che deve poter
    mostrare un campo di caricamento contestuale quando il PDF manca o non
    è valido, non solo un messaggio d'errore — AREA B, verifica manuale
    2026-07-28: il gate bloccava correttamente l'invio ma non offriva alcun
    percorso per risolvere il problema sulla stessa pagina).

    Restituisce (pronto: bool, motivo: str, rep: RepresentationPDF | None).
    `motivo` è vuoto se pronto. `rep` è l'eventuale rappresentazione PDF
    esistente (anche quando non ancora pronta, es. STALE o da confermare),
    utile alla UI per mostrare stato/errore/link di download.
    """
    from documents.models import RepresentationPDF

    if not version.document.requires_approved_pdf:
        return True, '', None

    if version.file_id is None:
        return True, '', None

    rep = version.representation_pdf
    if rep is None:
        return False, (
            "Nessun PDF di rappresentazione presente. Caricare o generare il PDF "
            "di rappresentazione prima di inviare in approvazione."
        ), None
    if rep.status == RepresentationPDF.Status.STALE:
        return False, (
            "Il PDF di rappresentazione non è aggiornato rispetto al file sorgente "
            "corrente. Ricaricare o rigenerare il PDF prima di inviare in approvazione."
        ), rep
    if rep.status == RepresentationPDF.Status.CONVERSION_FAILED:
        return False, (
            "La conversione automatica del PDF di rappresentazione è fallita. "
            "Caricare manualmente il PDF prima di inviare in approvazione."
        ), rep
    if rep.status == RepresentationPDF.Status.MANUAL_UPLOAD_REQUIRED:
        return False, (
            "Il formato del file sorgente richiede il caricamento manuale del PDF "
            "di rappresentazione prima di inviare in approvazione."
        ), rep
    if rep.requires_confirmation and rep.confirmed_at is None:
        return False, (
            "Confermare che il PDF di rappresentazione rappresenta correttamente il "
            "file sorgente prima di inviare in approvazione."
        ), rep

    return True, '', rep


def assert_ready_for_submission(version):
    """Solleva ValidationError con un motivo esplicito se non si può inviare."""
    ready, reason, _rep = get_pdf_submission_status(version)
    if not ready:
        raise ValidationError(reason)
