"""
Orchestrazione del PDF di rappresentazione (TASK-025).

Collega la policy centralizzata (documents.pdf_strategy), i convertitori
pure-Python (documents.pdf_converters) e il modello RepresentationPDF al
ciclo di vita di una DocumentVersion in bozza:

  - sync_representation_pdf_for_new_source(version): da chiamare ogni volta
    che il file sorgente viene assegnato o sostituito (create_new_revision /
    update_draft_version). Invalida (STALE) l'eventuale rappresentazione
    precedente e tenta una nuova conversione secondo la policy.
  - upload_manual_representation_pdf(version, uploaded_file, user): l'autore
    carica lui stesso il PDF di rappresentazione (bozza).
  - confirm_representation_pdf(version, user): l'autore dichiara che il PDF
    di rappresentazione rappresenta correttamente il file sorgente inviato.

Nessuna di queste funzioni invoca programmi esterni: la conversione fallita
o non disponibile lascia sempre una via di caricamento manuale.
"""

import os

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils import timezone

from documents.pdf_converters import render_image_to_pdf_bytes, render_text_to_pdf_bytes
from documents.pdf_strategy import PDFConverter, PDFStrategy, determine_pdf_strategy_for_file

_PDF_MAGIC = b'%PDF-'


def sync_representation_pdf_for_new_source(version):
    """
    Da chiamare subito dopo che version.file è stato assegnato/sostituito
    con un DocumentFile persistito. Determina la strategia PDF per il nuovo
    sorgente e tenta la conversione quando la policy lo prevede.
    """
    from documents.models import RepresentationPDF

    _invalidate_previous(version)

    source_file = version.file
    if source_file is None:
        version.representation_pdf = None
        version.save(update_fields=['representation_pdf'])
        return None

    decision = determine_pdf_strategy_for_file(source_file)
    rep = RepresentationPDF(
        strategy=decision.strategy,
        converter=decision.converter,
        requires_confirmation=decision.requires_confirmation,
        source_file_hash_at_generation=source_file.sha256_hash,
        created_by=version.created_by,
    )

    if decision.strategy == PDFStrategy.NATIVE_PDF:
        raw = _read_source_bytes(source_file)
        rep.file.save(_pdf_filename(source_file), ContentFile(raw), save=False)
        rep.status = RepresentationPDF.Status.READY
    elif decision.strategy == PDFStrategy.AUTO_RELIABLE:
        try:
            raw = _read_source_bytes(source_file)
            pdf_bytes = _convert(decision.converter, raw)
            rep.file.save(_pdf_filename(source_file), ContentFile(pdf_bytes), save=False)
            rep.status = RepresentationPDF.Status.READY
        except Exception as exc:
            rep.status = RepresentationPDF.Status.CONVERSION_FAILED
            rep.error_message = str(exc)
    else:
        rep.status = RepresentationPDF.Status.MANUAL_UPLOAD_REQUIRED
        rep.error_message = decision.reason

    rep.save()
    version.representation_pdf = rep
    version.save(update_fields=['representation_pdf'])
    return rep


def upload_manual_representation_pdf(version, uploaded_file, user):
    """L'autore carica manualmente il PDF di rappresentazione per una bozza."""
    from documents.models import DocumentVersion, RepresentationPDF

    if version.status not in (DocumentVersion.Status.DRAFT, DocumentVersion.Status.REJECTED):
        raise ValidationError(
            "Il PDF di rappresentazione può essere caricato manualmente solo su una bozza "
            "o su una revisione rifiutata."
        )

    _validate_pdf_upload(uploaded_file)
    _invalidate_previous(version)

    strategy = PDFStrategy.MANUAL_REQUIRED
    if version.file is not None:
        strategy = determine_pdf_strategy_for_file(version.file).strategy

    rep = RepresentationPDF(
        strategy=strategy,
        converter=PDFConverter.NONE,
        requires_confirmation=True,
        status=RepresentationPDF.Status.MANUAL_UPLOADED,
        created_by=user,
    )
    if version.file is not None:
        rep.source_file_hash_at_generation = version.file.sha256_hash
    rep.file.save(uploaded_file.name, ContentFile(uploaded_file.read()), save=False)
    rep.save()

    version.representation_pdf = rep
    version.save(update_fields=['representation_pdf'])
    return rep


def confirm_representation_pdf(version, user):
    """L'autore dichiara che il PDF di rappresentazione rappresenta correttamente il sorgente."""
    from documents.models import RepresentationPDF

    rep = version.representation_pdf
    if rep is None:
        raise ValidationError("Nessun PDF di rappresentazione da confermare.")
    if rep.status not in (RepresentationPDF.Status.READY, RepresentationPDF.Status.MANUAL_UPLOADED):
        raise ValidationError(
            f"Il PDF di rappresentazione non è in uno stato confermabile "
            f"(stato attuale: {rep.get_status_display()})."
        )

    rep.status = RepresentationPDF.Status.CONFIRMED
    rep.confirmed_by = user
    rep.confirmed_at = timezone.now()
    rep.save(update_fields=['status', 'confirmed_by', 'confirmed_at', 'updated_at'])
    return rep


def _invalidate_previous(version):
    from documents.models import RepresentationPDF

    previous = version.representation_pdf
    if previous is not None and previous.status != RepresentationPDF.Status.STALE:
        previous.status = RepresentationPDF.Status.STALE
        previous.save(update_fields=['status', 'updated_at'])


def _convert(converter, raw_bytes):
    if converter == PDFConverter.TEXT_RENDERER:
        return render_text_to_pdf_bytes(raw_bytes)
    if converter == PDFConverter.IMAGE_TO_PDF:
        return render_image_to_pdf_bytes(raw_bytes)
    raise ValueError(f"Convertitore sconosciuto: {converter!r}")


def _read_source_bytes(document_file):
    document_file.file.open('rb')
    try:
        return document_file.file.read()
    finally:
        document_file.file.close()


def _pdf_filename(document_file):
    base = document_file.original_filename or 'documento'
    stem = base.rsplit('.', 1)[0] if '.' in base else base
    return f"{stem}.pdf"


def _validate_pdf_upload(uploaded_file):
    name = getattr(uploaded_file, 'name', '') or ''
    if os.path.splitext(name)[1].lower() != '.pdf':
        raise ValidationError("Il file caricato deve essere un PDF (estensione .pdf).")
    head = uploaded_file.read(len(_PDF_MAGIC))
    uploaded_file.seek(0)
    if head != _PDF_MAGIC:
        raise ValidationError("Il file caricato non sembra un PDF valido.")
