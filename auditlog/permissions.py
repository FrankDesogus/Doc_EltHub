"""
Permessi per la sanatoria storica.

Regole fondamentali:
  can_use_sanatoria          → richiede SEMPRE DOCUMENTALE_DEMO_MODE=true, più
                               almeno una di:
                                 - is_demo_supervisor(user) (account demo storico
                                   'supervisor_demo', percorso legacy)
                                 - permesso individuale 'auditlog.can_use_sanatoria'
                                   (assegnabile per singolo utente da Django Admin;
                                   automaticamente vero per i superuser, come ogni
                                   altro permesso Django)
  can_view_historical_records → chiunque possa usare la sanatoria, più
                               superuser, QM, DM, DA
  can_verify_historical_records → Quality Manager, superuser

Con DOCUMENTALE_DEMO_MODE=false:
  - can_use_sanatoria restituisce sempre False, qualunque permesso abbia l'utente
  - la UI non mostra checkbox né campi storici
  - i POST con sanatoria=true vengono rifiutati
"""


def can_use_sanatoria(user) -> bool:
    """
    True se DOCUMENTALE_DEMO_MODE è attivo E (l'utente è il supervisore demo
    legacy OPPURE ha il permesso individuale 'auditlog.can_use_sanatoria').
    """
    from django.conf import settings

    if not getattr(user, 'is_authenticated', False):
        return False
    if not getattr(settings, 'DOCUMENTALE_DEMO_MODE', False):
        return False

    from config.demo_utils import is_demo_supervisor
    if is_demo_supervisor(user):
        return True
    return user.has_perm('auditlog.can_use_sanatoria')


def can_view_historical_records(user) -> bool:
    """
    True per: chiunque possa usare la sanatoria (can_use_sanatoria), superuser,
    Quality Manager, Document Manager, Document Auditor.
    """
    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return True
    if can_use_sanatoria(user):
        return True
    from documents.permissions import (
        GROUP_QUALITY_MANAGER,
        GROUP_MANAGERS,
        GROUP_AUDITORS,
    )
    return user.groups.filter(
        name__in=[GROUP_QUALITY_MANAGER, GROUP_MANAGERS, GROUP_AUDITORS]
    ).exists()


def can_verify_historical_records(user) -> bool:
    """
    True per: Quality Manager, superuser.
    """
    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return True
    from documents.permissions import GROUP_QUALITY_MANAGER
    return user.groups.filter(name=GROUP_QUALITY_MANAGER).exists()
