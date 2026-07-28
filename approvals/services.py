import os

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from approvals.models import ApprovalDecision, ApprovalRequest, ApprovalRequestApprover
from auditlog.services import create_audit_log


def _build_decision_snapshot(decision, user, approval_request):
    """
    Congela nome, ordine di fase e firma visiva dell'utente al momento
    della decisione (TASK-029): un cambio successivo di nome/ruolo/firma
    non deve alterare lo storico già registrato.
    """
    from accounts.models import UserSignature

    decision.snapshot_approver_display_name = user.get_full_name() or user.username

    slot = approval_request.approvers.filter(approver=user).first()
    decision.snapshot_approver_order = slot.order if slot else None

    try:
        profile = user.signature_profile
    except UserSignature.DoesNotExist:
        profile = None

    if profile is not None and profile.image:
        decision.snapshot_signature_mode = ApprovalDecision.SignatureMode.TEXT_AND_IMAGE
        with profile.image.open('rb') as fh:
            decision.snapshot_signature_image.save(
                os.path.basename(profile.image.name), ContentFile(fh.read()), save=False,
            )
    else:
        decision.snapshot_signature_mode = ApprovalDecision.SignatureMode.TEXT_ONLY

    decision.save(update_fields=[
        'snapshot_approver_display_name',
        'snapshot_approver_order',
        'snapshot_signature_mode',
        'snapshot_signature_image',
    ])


def create_approval_request_attachment(approval_request, uploaded_file, uploaded_by, attachment_type='signature_template'):
    import hashlib
    import mimetypes
    import os

    from approvals.models import ApprovalRequestAttachment

    sha256 = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        sha256.update(chunk)
    uploaded_file.seek(0)

    name = uploaded_file.name
    ext = os.path.splitext(name)[1].lstrip('.').lower()
    mime = getattr(uploaded_file, 'content_type', None) or mimetypes.guess_type(name)[0] or ''

    attachment = ApprovalRequestAttachment.objects.create(
        approval_request=approval_request,
        file=uploaded_file,
        attachment_type=attachment_type,
        original_filename=name,
        extension=ext,
        size=uploaded_file.size,
        mime_type=mime,
        sha256_hash=sha256.hexdigest(),
        uploaded_by=uploaded_by,
    )

    create_audit_log(
        user=uploaded_by,
        action='ATTACHMENT_UPLOADED',
        instance=attachment,
        new_values={'attachment_type': attachment_type, 'filename': name},
        document=approval_request.document_version.document,
        document_version=approval_request.document_version,
    )

    return attachment


def approve_version(approval_request, approved_by, comment="", send_notifications=True):
    from documents.models import DocumentVersion

    Policy = ApprovalRequest.Policy
    ApproverStatus = ApprovalRequestApprover.ApproverStatus

    # 1. Assegnazione: deve essere approvatore assegnato oppure superuser
    is_assigned = approval_request.approvers.filter(approver=approved_by).exists()
    if not is_assigned and not approved_by.is_superuser:
        raise PermissionDenied("L'utente non è tra gli approvatori assegnati.")

    # 2. La richiesta deve essere pending
    if approval_request.status != ApprovalRequest.Status.PENDING:
        raise ValidationError(
            f"La richiesta non è in attesa. Stato attuale: {approval_request.get_status_display()}"
        )

    # 3. La versione deve essere in approvazione
    version = approval_request.document_version
    if version.status != DocumentVersion.Status.IN_APPROVAL:
        raise ValidationError(
            f"La revisione non è in approvazione. Stato attuale: {version.get_status_display()}"
        )

    # 4. Nessuna decisione precedente dello stesso utente
    if ApprovalDecision.objects.filter(
        approval_request=approval_request, approver=approved_by
    ).exists():
        raise ValidationError("Hai già espresso una decisione per questa richiesta.")

    # 5. Policy SEQUENTIAL: solo il prossimo approvatore in ordine può approvare
    policy = approval_request.approval_policy
    if policy == Policy.SEQUENTIAL and not approved_by.is_superuser:
        next_slot = (
            approval_request.approvers
            .filter(status=ApproverStatus.PENDING)
            .order_by('order')
            .first()
        )
        if next_slot is None or next_slot.approver_id != approved_by.pk:
            raise ValidationError(
                "Non è ancora il tuo turno: aspetta che l'approvatore precedente abbia approvato."
            )

    with transaction.atomic():
        now = timezone.now()

        decision = ApprovalDecision.objects.create(
            approval_request=approval_request,
            approver=approved_by,
            decision=ApprovalDecision.Decision.APPROVED,
            notes=comment,
        )
        _build_decision_snapshot(decision, approved_by, approval_request)

        # Aggiorna stato per-approvatore (solo se è assegnato)
        if is_assigned:
            ApprovalRequestApprover.objects.filter(
                approval_request=approval_request,
                approver=approved_by,
            ).update(status=ApproverStatus.APPROVED, decided_at=now)

        # Determina se è approvazione finale
        is_final = _is_final_approval(approval_request, approved_by, policy, ApproverStatus)

        if is_final:
            _finalize_approval(approval_request, version, approved_by, now)
        else:
            create_audit_log(
                user=approved_by,
                action='PARTIAL_APPROVAL',
                instance=version,
                old_values={'status': DocumentVersion.Status.IN_APPROVAL},
                new_values={'partial_approval_by': approved_by.pk},
                document=version.document,
                document_version=version,
            )

    # Generazione del PDF approvato: solo se questa specifica revisione è
    # effettivamente passata dal gate PDF all'invio (version.representation_pdf
    # esiste solo in quel caso — TASK-033). Non si rilegge qui il flag
    # corrente del documento: la richiesta si conclude secondo le regole che
    # gli approvatori hanno effettivamente seguito, non secondo un'eventuale
    # policy cambiata nel frattempo. Se il flusso PDF non era richiesto,
    # nessun tentativo viene fatto: nessun artefatto, nessun errore.
    if is_final and version.representation_pdf_id is not None:
        # Fuori dalla transazione che ha già finalizzato l'approvazione: un
        # errore qui non deve annullare un'approvazione già registrata
        # correttamente — resta solo un ApprovedPDFArtifact in stato FAILED,
        # rigenerabile.
        from documents.pdf_generation import generate_approved_pdf
        try:
            generate_approved_pdf(version, actor=approved_by)
        except Exception:
            pass

    if is_final:
        # Chiusura automatica dell'ECN collegato — standard o semplice
        # (requisito aziendale del 2026-07-28, generalizza AREA 3 che
        # limitava la chiusura automatica al solo flusso semplice). Fuori
        # dalla transazione che ha finalizzato l'approvazione: un errore
        # qui non deve mai invalidare un'approvazione già registrata
        # correttamente.
        try:
            from ecn.services import auto_close_executed_ecn_if_ready
            auto_close_executed_ecn_if_ready(version, approved_by)
        except Exception:
            pass

    if not send_notifications:
        return approval_request

    if is_final:
        from notifications.services import send_version_approved_email
        send_version_approved_email(approval_request)
        try:
            from notifications.inbox import notify_version_approved
            notify_version_approved(approval_request)
        except Exception:
            pass
    elif policy == Policy.SEQUENTIAL:
        # SEQUENTIAL e non finale: notifica il prossimo approvatore pending
        next_slot = (
            approval_request.approvers
            .filter(status=ApproverStatus.PENDING)
            .order_by('order')
            .first()
        )
        if next_slot:
            from notifications.services import send_approval_request_email
            send_approval_request_email(approval_request, next_slot.approver)
            try:
                from notifications.inbox import notify_approval_requested
                notify_approval_requested(approval_request, next_slot.approver)
            except Exception:
                pass

    return approval_request


def _is_final_approval(approval_request, approved_by, policy, ApproverStatus):
    """Restituisce True se questa approvazione chiude definitivamente la richiesta."""
    # Superuser: override finale incondizionato
    if approved_by.is_superuser:
        return True

    Policy = ApprovalRequest.Policy

    if policy == Policy.ANY:
        return True

    # ALL e SEQUENTIAL: finale solo se non restano approvatori pending
    remaining = approval_request.approvers.filter(
        status=ApproverStatus.PENDING
    ).count()
    return remaining == 0


def _finalize_approval(approval_request, version, approved_by, now):
    """Chiude definitivamente la richiesta e promuove la versione ad approved/current."""
    from documents.models import DocumentVersion

    approval_request.status = ApprovalRequest.Status.APPROVED
    approval_request.completed_at = now
    approval_request.save(update_fields=['status', 'completed_at'])

    document = version.document
    old_current = document.current_version

    if old_current is not None and old_current.pk != version.pk:
        DocumentVersion.objects.filter(pk=old_current.pk).update(
            status=DocumentVersion.Status.SUPERSEDED,
            is_current=False,
        )
        create_audit_log(
            user=approved_by,
            action='SUPERSEDED',
            instance=old_current,
            old_values={'status': old_current.status, 'is_current': True},
            new_values={'status': DocumentVersion.Status.SUPERSEDED, 'is_current': False},
            document=document,
            document_version=old_current,
        )

    version.status = DocumentVersion.Status.APPROVED
    version.is_current = True
    version.approved_at = now
    version.approved_by = approved_by
    version.save(update_fields=['status', 'is_current', 'approved_at', 'approved_by'])

    document.current_version = version
    document.save(update_fields=['current_version'])

    create_audit_log(
        user=approved_by,
        action='APPROVED',
        instance=version,
        old_values={'status': DocumentVersion.Status.IN_APPROVAL},
        new_values={
            'status': DocumentVersion.Status.APPROVED,
            'is_current': True,
            'approved_by_id': approved_by.pk,
        },
        document=document,
        document_version=version,
    )


def reject_version(approval_request, rejected_by, rejection_reason, comment="", send_notifications=True):
    from documents.models import DocumentVersion

    if not rejection_reason or not rejection_reason.strip():
        raise ValidationError("Il motivo del rifiuto è obbligatorio.")

    is_assigned = approval_request.approvers.filter(approver=rejected_by).exists()
    if not is_assigned and not rejected_by.is_superuser:
        raise PermissionDenied("L'utente non è tra gli approvatori assegnati.")

    if approval_request.status != ApprovalRequest.Status.PENDING:
        raise ValidationError(
            f"La richiesta non è in attesa. Stato attuale: {approval_request.get_status_display()}"
        )

    version = approval_request.document_version
    if version.status != DocumentVersion.Status.IN_APPROVAL:
        raise ValidationError(
            f"La revisione non è in approvazione. Stato attuale: {version.get_status_display()}"
        )

    # Nessuna decisione precedente dello stesso utente
    if ApprovalDecision.objects.filter(
        approval_request=approval_request, approver=rejected_by
    ).exists():
        raise ValidationError("Hai già espresso una decisione per questa richiesta.")

    with transaction.atomic():
        now = timezone.now()

        decision = ApprovalDecision.objects.create(
            approval_request=approval_request,
            approver=rejected_by,
            decision=ApprovalDecision.Decision.REJECTED,
            notes=comment,
        )
        _build_decision_snapshot(decision, rejected_by, approval_request)

        if is_assigned:
            ApprovalRequestApprover.objects.filter(
                approval_request=approval_request,
                approver=rejected_by,
            ).update(
                status=ApprovalRequestApprover.ApproverStatus.REJECTED,
                decided_at=now,
            )

        approval_request.status = ApprovalRequest.Status.REJECTED
        approval_request.completed_at = now
        approval_request.save(update_fields=['status', 'completed_at'])

        version.status = DocumentVersion.Status.REJECTED
        version.rejected_at = now
        version.rejection_reason = rejection_reason
        version.save(update_fields=['status', 'rejected_at', 'rejection_reason'])

        create_audit_log(
            user=rejected_by,
            action='REJECTED',
            instance=version,
            old_values={'status': DocumentVersion.Status.IN_APPROVAL},
            new_values={
                'status': DocumentVersion.Status.REJECTED,
                'rejection_reason': rejection_reason,
            },
            document=version.document,
            document_version=version,
        )

    # Notifica fuori dalla transazione.
    # In modalità sanatoria le notifiche sono soppresse.
    if not send_notifications:
        return approval_request

    from notifications.services import send_version_rejected_email
    send_version_rejected_email(approval_request, rejection_reason)
    try:
        from notifications.inbox import notify_version_rejected
        notify_version_rejected(approval_request)
    except Exception:
        pass

    return approval_request
