"""
Generazione del PDF approvato (TASK-030, firma in calce corretta — verifica
manuale del 2026-07-27; TASK-040 Fase 3, posizionamento libero firma
disegnato realmente sul PDF).

Quando una ApprovalRequest raggiunge l'esito APPROVED, il sistema genera un
nuovo artefatto separato: il PDF di rappresentazione congelato + il registro
delle approvazioni (nome, ruolo, decisione, timestamp, eventuale firma
visiva, nota sull'assenza di firma digitale).

Posizionamento libero della firma (TASK-040/040-2/040-3): un `ApprovalDecision`
può avere `signature_page`/`signature_x`/`signature_y` valorizzati (coordinate
normalizzate 0.0-1.0, X da sinistra, Y dall'alto, scelte dall'approvatore nel
widget di trascinamento). Quando il posizionamento è valido — pagina in
range, immagine firma realmente presente sul disco — la firma viene
disegnata direttamente in quel punto della pagina indicata, **al posto**
della riga con immagine nel registro "in calce"/pagina dedicata (che per
quella decisione resta solo testuale, con una nota sulla pagina). Se il
posizionamento non è valido per qualunque motivo (pagina fuori range,
immagine mancante su disco, errore di lettura), la decisione ricade
silenziosamente sul comportamento automatico preesistente (immagine nel
registro) — mai una firma persa, mai un errore di generazione per questo.

Collocazione del registro — strategia ibrida:

  - Strategia primaria ("in calce"): l'ultima pagina del PDF di
    rappresentazione viene resa più alta (si estende il suo stesso
    MediaBox), il contenuto originale viene traslato verso l'alto per
    liberare un'area realmente vuota in fondo, e il registro viene
    stampato in quello spazio nuovo. Non c'è mai sovrapposizione con il
    contenuto esistente perché lo spazio è creato ex novo, non "indovinato"
    sopra al contenuto — verificato visivamente anche su una pagina
    completamente piena fino in fondo (nessuno spazio libero preesistente).
  - Fallback (pagina dedicata): se il registro risultasse troppo alto per
    un footer ragionevole (molti approvatori) o se l'estensione del canvas
    fallisse per qualunque motivo tecnico, il registro viene invece
    stampato su una pagina finale separata (comportamento originale) — mai
    un errore di generazione per questo.

Non modifica mai il PDF di rappresentazione né il file sorgente (si lavora
su una copia in memoria). Non va mai generato per richieste REJECTED (il
chiamante in approvals/services.py lo invoca solo nel ramo di approvazione
finale). Va chiamata fuori dalla transazione che finalizza l'approvazione:
un errore qui non deve annullare un'approvazione già registrata
correttamente — resta solo un ApprovedPDFArtifact in stato FAILED,
rigenerabile.
"""

import io
import os

from django.core.files.base import ContentFile
from django.utils import timezone
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import RectangleObject
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from auditlog.services import create_audit_log

DISCLAIMER = (
    "Le firme riprodotte rappresentano graficamente le approvazioni registrate "
    "nel sistema documentale e non costituiscono firma digitale o firma "
    "elettronica qualificata."
)

# Altezza massima ragionevole per un footer "in calce" (in punti). Oltre
# questa soglia (tipicamente con molti approvatori) si passa alla pagina
# finale dedicata: un footer più alto di così non si leggerebbe più come
# "in calce", ma come un'appendice travestita da footer.
_MAX_FOOTER_HEIGHT_PT = 130 * mm

_MARGIN = 12 * mm
_ROW_HEIGHT_TEXT_ONLY = 6 * mm
_ROW_HEIGHT_WITH_IMAGE = 16 * mm
_SIGNATURE_IMG_WIDTH = 26 * mm
_SIGNATURE_IMG_HEIGHT = 9 * mm

# Dimensioni della firma disegnata nel punto scelto liberamente sulla pagina
# (TASK-040 Fase 3) — più grande della miniatura del registro "in calce",
# pensata per essere leggibile come una vera firma apposta sul documento.
_MANUAL_SIGNATURE_WIDTH = 40 * mm
_MANUAL_SIGNATURE_HEIGHT = 16 * mm


def generate_approved_pdf(version, actor=None, force=False):
    """
    Genera (o rigenera) il PDF approvato per una DocumentVersion APPROVED.

    Idempotente: se esiste già un artefatto GENERATED per la stessa
    rappresentazione congelata e force=False, restituisce quell'artefatto
    senza rigenerare né duplicare.
    """
    from documents.models import ApprovedPDFArtifact, DocumentVersion

    if version.status != DocumentVersion.Status.APPROVED:
        raise ValueError("Il PDF approvato si genera solo per revisioni APPROVED.")

    rep = version.representation_pdf
    if rep is None or not rep.file:
        artifact = _get_or_create_artifact(version)
        artifact.status = ApprovedPDFArtifact.Status.FAILED
        artifact.error_message = (
            "Nessun PDF di rappresentazione disponibile per generare il PDF approvato."
        )
        artifact.save(update_fields=['status', 'error_message', 'updated_at'])
        _link(version, artifact)
        _log(version, actor, 'APPROVED_PDF_GENERATION_FAILED', {'reason': artifact.error_message})
        return artifact

    existing = version.approved_pdf
    if (
        not force
        and existing is not None
        and existing.status == ApprovedPDFArtifact.Status.GENERATED
        and existing.source_representation_pdf_id == rep.pk
    ):
        return existing

    artifact = _get_or_create_artifact(version)
    try:
        decisions = _final_decisions(version)
        merged_bytes = _build_approved_pdf_bytes(version, rep.file.path, decisions)
        artifact.file.save(_approved_filename(version), ContentFile(merged_bytes), save=False)
        artifact.status = ApprovedPDFArtifact.Status.GENERATED
        artifact.source_representation_pdf_id = rep.pk
        artifact.generated_at = timezone.now()
        artifact.error_message = ''
        artifact.save()
        _log(version, actor, 'APPROVED_PDF_GENERATED', {'artifact_id': artifact.pk})
    except Exception as exc:
        artifact.status = ApprovedPDFArtifact.Status.FAILED
        artifact.error_message = str(exc)
        artifact.save(update_fields=['status', 'error_message', 'updated_at'])
        _log(version, actor, 'APPROVED_PDF_GENERATION_FAILED', {'reason': str(exc)})

    _link(version, artifact)
    return artifact


def _link(version, artifact):
    version.approved_pdf = artifact
    version.save(update_fields=['approved_pdf'])


def _get_or_create_artifact(version):
    from documents.models import ApprovedPDFArtifact
    if version.approved_pdf_id:
        return version.approved_pdf
    return ApprovedPDFArtifact.objects.create()


def _final_decisions(version):
    approval_request = (
        version.approval_requests.filter(status='APPROVED').order_by('-completed_at').first()
    )
    if not approval_request:
        return approval_request, []
    decisions = list(
        approval_request.decisions
        .filter(decision='APPROVED')
        .order_by('snapshot_approver_order', 'decided_at')
    )
    return approval_request, decisions


def _build_approved_pdf_bytes(version, representation_pdf_path, decisions_tuple):
    approval_request, decisions = decisions_tuple
    reader = PdfReader(representation_pdf_path)
    n_pages = len(reader.pages)
    manual_by_page, manual_ids = _decisions_with_valid_manual_placement(decisions, n_pages)

    footer_height = _estimate_footer_height(decisions, manual_ids)
    if footer_height <= _MAX_FOOTER_HEIGHT_PT:
        try:
            return _stamp_footer_on_last_page(
                reader, version, approval_request, decisions, footer_height,
                manual_by_page, manual_ids,
            )
        except Exception:
            pass  # ripiego sulla pagina finale dedicata, mai un errore di generazione per questo

    registry_bytes = _build_registry_standalone_page(version, approval_request, decisions, manual_ids)
    return _append_page(representation_pdf_path, registry_bytes, manual_by_page)


def _decisions_with_valid_manual_placement(decisions, n_pages):
    """
    Seleziona le decisioni con posizionamento libero della firma (TASK-040)
    davvero utilizzabile: pagina/coordinate tutte presenti, pagina nel range
    del PDF, immagine firma realmente leggibile su disco. Qualunque di questi
    controlli fallisca, la decisione resta fuori da entrambi i risultati e
    ricade sul comportamento automatico (riga con immagine nel registro) —
    mai un errore di generazione, mai una firma silenziosamente persa.

    Ritorna (manual_by_page: {numero_pagina_1based: [decisioni]}, manual_ids: {pk}).
    """
    manual_by_page = {}
    manual_ids = set()
    for d in decisions:
        if d.signature_page is None or d.signature_x is None or d.signature_y is None:
            continue
        if not d.snapshot_signature_image:
            continue
        if not (1 <= d.signature_page <= n_pages):
            continue
        try:
            if not os.path.exists(d.snapshot_signature_image.path):
                continue
        except Exception:
            continue
        manual_by_page.setdefault(d.signature_page, []).append(d)
        manual_ids.add(d.pk)
    return manual_by_page, manual_ids


def _estimate_footer_height(decisions, manual_ids):
    header_block = 22 * mm  # titolo registro + riga stato/codice/revisione + riga policy/data
    rows = sum(
        _ROW_HEIGHT_TEXT_ONLY if d.pk in manual_ids
        else (_ROW_HEIGHT_WITH_IMAGE if d.snapshot_signature_image else _ROW_HEIGHT_TEXT_ONLY)
        for d in decisions
    ) or _ROW_HEIGHT_TEXT_ONLY
    disclaimer_block = 10 * mm
    return header_block + rows + disclaimer_block + 2 * _MARGIN


def _stamp_footer_on_last_page(
    reader, version, approval_request, decisions, footer_height, manual_by_page, manual_ids,
):
    writer = PdfWriter()
    n_pages = len(reader.pages)

    for i, page in enumerate(reader.pages):
        page_number = i + 1
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        y_offset = 0.0

        if i == n_pages - 1:
            footer_bytes = _build_footer_overlay(
                version, approval_request, decisions, width, footer_height, manual_ids,
            )
            footer_page = PdfReader(io.BytesIO(footer_bytes)).pages[0]

            # Sposta il contenuto originale verso l'alto per liberare, in fondo,
            # un'area realmente vuota (mai "indovinata" sopra al contenuto).
            page.add_transformation(Transformation().translate(tx=0, ty=footer_height))
            page.mediabox = RectangleObject([0, 0, width, height + footer_height])
            if page.cropbox is not None:
                page.cropbox = RectangleObject([0, 0, width, height + footer_height])
            # L'area [0, footer_height] è vuota per costruzione: nessuna sovrapposizione.
            page.merge_page(footer_page)
            y_offset = footer_height

        placements = manual_by_page.get(page_number)
        if placements:
            # Coordinate calcolate sulla pagina ORIGINALE (larghezza invariata,
            # mai estesa); y_offset le trasla verso l'alto esattamente come il
            # contenuto originale, solo per l'ultima pagina (unica estesa).
            overlay_bytes = _build_signature_placements_overlay(placements, width, height, y_offset)
            page.merge_page(PdfReader(io.BytesIO(overlay_bytes)).pages[0])

        writer.add_page(page)

    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _clamp_center(raw, dimension, half_size):
    """Vincola il centro di un riquadro di lato 2*half_size a restare
    interamente dentro [0, dimension]; se il riquadro non ci sta proprio
    (pagina più piccola della firma), lo centra semplicemente."""
    if dimension <= half_size * 2:
        return dimension / 2
    return min(max(raw, half_size), dimension - half_size)


def _build_signature_placements_overlay(placements, orig_width, orig_height, y_offset):
    """
    Overlay con le firme posizionate liberamente su questa pagina (TASK-040
    Fase 3). Disegnato nel sistema di coordinate della pagina ORIGINALE
    (larghezza invariata, mai estesa dal footer) e poi traslato di y_offset
    se questa stessa pagina ha ricevuto anche l'estensione per il footer
    "in calce" (solo l'ultima pagina, mai le altre) — così la firma resta
    visivamente nello stesso punto scelto dall'approvatore rispetto al
    contenuto originale, che ha subito la stessa traslazione.
    """
    canvas_height = orig_height + y_offset
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(orig_width, canvas_height))
    half_w = _MANUAL_SIGNATURE_WIDTH / 2
    half_h = _MANUAL_SIGNATURE_HEIGHT / 2

    for decision in placements:
        px = _clamp_center(decision.signature_x * orig_width, orig_width, half_w)
        py = _clamp_center(orig_height - decision.signature_y * orig_height, orig_height, half_h)
        py += y_offset
        try:
            img = ImageReader(decision.snapshot_signature_image.path)
            pdf.drawImage(
                img, px - half_w, py - half_h,
                width=_MANUAL_SIGNATURE_WIDTH, height=_MANUAL_SIGNATURE_HEIGHT,
                mask='auto', preserveAspectRatio=True,
            )
        except Exception:
            continue  # già filtrate a monte da _decisions_with_valid_manual_placement, difensivo

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _build_footer_overlay(version, approval_request, decisions, width, footer_height, manual_ids):
    """Registro compatto, disegnato con origine (0,0) in basso a sinistra,
    pensato per essere incollato esattamente nell'area liberata in calce."""
    document = version.document
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(width, footer_height))

    y = footer_height - _MARGIN
    pdf.setLineWidth(0.5)
    pdf.line(_MARGIN, y, width - _MARGIN, y)
    y -= 6 * mm

    pdf.setFont('Helvetica-Bold', 11)
    pdf.drawString(_MARGIN, y, "REGISTRO DI APPROVAZIONE")
    y -= 6 * mm

    pdf.setFont('Helvetica', 8.5)
    policy = approval_request.get_approval_policy_display() if approval_request else '—'
    completed = (
        timezone.localtime(approval_request.completed_at).strftime('%d/%m/%Y %H:%M')
        if approval_request and approval_request.completed_at else '—'
    )
    pdf.drawString(
        _MARGIN, y,
        f"APPROVATO — {document.code} rev.{version.revision_label} — "
        f"{policy} — concluso il {completed}",
    )
    y -= 6 * mm

    for decision in decisions:
        name = (
            decision.snapshot_approver_display_name
            or decision.approver.get_full_name()
            or decision.approver.username
        )
        role = (
            "Approvatore"
            if decision.snapshot_approver_order is None
            else f"Approvatore (fase {decision.snapshot_approver_order})"
        )
        decided_at = timezone.localtime(decision.decided_at).strftime('%d/%m/%Y %H:%M')

        pdf.setFont('Helvetica', 9)
        if decision.pk not in manual_ids and decision.snapshot_signature_image:
            try:
                img = ImageReader(decision.snapshot_signature_image.path)
                pdf.drawImage(
                    img, _MARGIN, y - _SIGNATURE_IMG_HEIGHT,
                    width=_SIGNATURE_IMG_WIDTH, height=_SIGNATURE_IMG_HEIGHT,
                    mask='auto', preserveAspectRatio=True,
                )
                pdf.drawString(
                    _MARGIN + _SIGNATURE_IMG_WIDTH + 4 * mm,
                    y - _SIGNATURE_IMG_HEIGHT / 2 - 1 * mm,
                    f"{name} — {role} — {decision.get_decision_display()} — {decided_at}",
                )
                y -= _ROW_HEIGHT_WITH_IMAGE
                continue
            except Exception:
                pass
        label = f"{name} — {role} — {decision.get_decision_display()} — {decided_at}"
        if decision.pk in manual_ids:
            label += f" (firma apposta a pag. {decision.signature_page})"
        pdf.drawString(_MARGIN, y, label)
        y -= _ROW_HEIGHT_TEXT_ONLY

    pdf.setFont('Helvetica-Oblique', 6.5)
    text_obj = pdf.beginText(_MARGIN, max(y - 2 * mm, _MARGIN / 2))
    for wrapped_line in _wrap(DISCLAIMER, 140):
        text_obj.textLine(wrapped_line)
    pdf.drawText(text_obj)

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _append_page(representation_pdf_path, registry_page_bytes, manual_by_page):
    reader = PdfReader(representation_pdf_path)
    registry_reader = PdfReader(io.BytesIO(registry_page_bytes))

    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        # Pagina dedicata di fallback: le pagine di contenuto originali non
        # vengono mai estese/traslate (a differenza della strategia "in
        # calce"), quindi le firme posizionate liberamente si disegnano
        # sempre senza alcun offset verticale.
        placements = manual_by_page.get(i + 1)
        if placements:
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            overlay_bytes = _build_signature_placements_overlay(placements, width, height, 0.0)
            page.merge_page(PdfReader(io.BytesIO(overlay_bytes)).pages[0])
        writer.add_page(page)
    for page in registry_reader.pages:
        writer.add_page(page)

    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _build_registry_standalone_page(version, approval_request, decisions, manual_ids):
    """Fallback: pagina finale dedicata (usata solo quando il footer 'in
    calce' risulterebbe troppo alto, o se l'estensione della pagina fallisce
    per un motivo tecnico)."""
    document = version.document

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 20 * mm
    state = {'y': height - margin}

    def line(text, size=10, gap=6 * mm, bold=False):
        pdf.setFont('Helvetica-Bold' if bold else 'Helvetica', size)
        pdf.drawString(margin, state['y'], text)
        state['y'] -= gap

    line("REGISTRO DI APPROVAZIONE", size=14, bold=True, gap=10 * mm)
    line("Stato: APPROVATO", bold=True)
    line(f"Codice documento: {document.code}")
    line(f"Titolo: {document.title}")
    line(f"Revisione: {version.revision_label}")

    if approval_request:
        line(f"Modalità approvazione: {approval_request.get_approval_policy_display()}")
        if approval_request.completed_at:
            completed = timezone.localtime(approval_request.completed_at).strftime('%d/%m/%Y %H:%M')
            line(f"Data conclusione: {completed}")

    state['y'] -= 4 * mm
    line("Approvatori:", bold=True)

    for decision in decisions:
        name = (
            decision.snapshot_approver_display_name
            or decision.approver.get_full_name()
            or decision.approver.username
        )
        role = (
            "Approvatore"
            if decision.snapshot_approver_order is None
            else f"Approvatore (fase {decision.snapshot_approver_order})"
        )
        decided_at = timezone.localtime(decision.decided_at).strftime('%d/%m/%Y %H:%M')
        row_top = state['y']
        label = f"{name} — {role} — {decision.get_decision_display()} — {decided_at}"
        if decision.pk in manual_ids:
            label += f" (firma apposta a pag. {decision.signature_page})"
        pdf.setFont('Helvetica', 9)
        pdf.drawString(margin + 2 * mm, row_top, label)

        if decision.pk not in manual_ids and decision.snapshot_signature_image:
            try:
                img = ImageReader(decision.snapshot_signature_image.path)
                img_y = row_top - 4 * mm - _SIGNATURE_IMG_HEIGHT
                pdf.drawImage(
                    img, margin + 4 * mm, img_y,
                    width=_SIGNATURE_IMG_WIDTH, height=_SIGNATURE_IMG_HEIGHT,
                    mask='auto', preserveAspectRatio=True,
                )
                state['y'] = img_y - 4 * mm
            except Exception:
                state['y'] = row_top - _ROW_HEIGHT_TEXT_ONLY
        else:
            state['y'] = row_top - _ROW_HEIGHT_TEXT_ONLY

    state['y'] -= 8 * mm
    pdf.setFont('Helvetica-Oblique', 8)
    text_obj = pdf.beginText(margin, state['y'])
    for wrapped_line in _wrap(DISCLAIMER, 100):
        text_obj.textLine(wrapped_line)
    pdf.drawText(text_obj)

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _wrap(text, max_len):
    words = text.split()
    lines = []
    current = ''
    for word in words:
        candidate = (current + ' ' + word).strip()
        if len(candidate) > max_len:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _approved_filename(version):
    return f"{version.document.code}_rev{version.revision_label}_approvato.pdf"


def _log(version, actor, action, metadata):
    create_audit_log(
        user=actor,
        action=action,
        instance=version,
        document=version.document,
        document_version=version,
        metadata=metadata,
    )
