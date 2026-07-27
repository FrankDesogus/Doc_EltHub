"""
Generazione del PDF approvato (TASK-030).

Quando una ApprovalRequest raggiunge l'esito APPROVED, il sistema genera un
nuovo artefatto separato: il PDF di rappresentazione congelato + una pagina
finale con il registro delle approvazioni (nome, ruolo, decisione,
timestamp, eventuale firma visiva, nota sull'assenza di firma digitale).

Non modifica mai il PDF di rappresentazione né il file sorgente. Non va mai
generato per richieste REJECTED (il chiamante in approvals/services.py lo
invoca solo nel ramo di approvazione finale). Va chiamata fuori dalla
transazione che finalizza l'approvazione: un errore qui non deve annullare
un'approvazione già registrata correttamente — resta solo un
ApprovedPDFArtifact in stato FAILED, rigenerabile.
"""

import io

from django.core.files.base import ContentFile
from django.utils import timezone
from pypdf import PdfReader, PdfWriter
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
        registry_bytes = _build_registry_page(version)
        merged_bytes = _merge_pdfs(rep.file.path, registry_bytes)
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


def _merge_pdfs(representation_pdf_path, registry_page_bytes):
    reader = PdfReader(representation_pdf_path)
    registry_reader = PdfReader(io.BytesIO(registry_page_bytes))

    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    for page in registry_reader.pages:
        writer.add_page(page)

    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _build_registry_page(version):
    document = version.document
    approval_request = (
        version.approval_requests.filter(status='APPROVED').order_by('-completed_at').first()
    )

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

    decisions = []
    if approval_request:
        decisions = list(
            approval_request.decisions
            .filter(decision='APPROVED')
            .order_by('snapshot_approver_order', 'decided_at')
        )

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
        line(f"  {name} — {role} — {decision.get_decision_display()} — {decided_at}", size=9)

        if decision.snapshot_signature_image:
            try:
                img = ImageReader(decision.snapshot_signature_image.path)
                pdf.drawImage(
                    img, margin + 4 * mm, state['y'] - 10 * mm,
                    width=30 * mm, height=10 * mm,
                    mask='auto', preserveAspectRatio=True,
                )
                state['y'] -= 12 * mm
            except Exception:
                pass

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
