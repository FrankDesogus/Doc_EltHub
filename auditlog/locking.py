"""
Lock applicativo "un utente alla volta" per le pagine d'azione dei
flussi di approvazione (documento) ed ECN (dossier istruttorio, voto
CCB). Opera per duck-typing su qualunque model con i campi
locked_by/locked_at (ChangeNotice, ApprovalRequest) — nessun
ContentType/GenericForeignKey, solo 2 modelli coinvolti.

Il lock scade automaticamente dopo LOCK_TIMEOUT di inattività (nessuna
azione di sblocco manuale in questa fase): un lock scaduto è
equivalente a "nessun lock" agli occhi di lock_holder/acquire_lock.
"""
from datetime import timedelta

from django.utils import timezone

LOCK_TIMEOUT = timedelta(minutes=20)


def lock_holder(obj):
    """Restituisce l'utente che detiene un lock valido (non scaduto) su `obj`, o None."""
    if obj.locked_by_id and obj.locked_at and timezone.now() - obj.locked_at <= LOCK_TIMEOUT:
        return obj.locked_by
    return None


def acquire_lock(obj, user):
    """
    Prova ad acquisire il lock su `obj` per `user`.
    Restituisce True se acquisito (o già detenuto da `user`: rinnova il
    timestamp), False se detenuto da un altro utente con lock non scaduto
    (in tal caso non modifica nulla).
    """
    holder = lock_holder(obj)
    if holder is not None and holder.pk != user.pk:
        return False
    obj.locked_by = user
    obj.locked_at = timezone.now()
    obj.save(update_fields=['locked_by', 'locked_at'])
    return True


def release_lock(obj, user):
    """Rilascia il lock su `obj` solo se detenuto da `user` (anche se già scaduto)."""
    if obj.locked_by_id == user.pk:
        obj.locked_by = None
        obj.locked_at = None
        obj.save(update_fields=['locked_by', 'locked_at'])
