from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.db import models


class UserSignature(models.Model):
    """
    Firma visiva opzionale (TASK-028): rappresentazione grafica interna
    usata nel registro di approvazione del PDF approvato.

    Non è una firma digitale crittografica o una firma elettronica
    qualificata: è solo un'immagine PNG (facoltativa) associata all'utente.
    Se assente, il registro di approvazione mostra solo il nome testuale.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='signature_profile',
        verbose_name='Utente',
    )
    image = models.ImageField(
        upload_to='user_signatures/%Y/%m/',
        null=True,
        blank=True,
        verbose_name='Immagine firma (PNG)',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Firma utente'
        verbose_name_plural = 'Firme utente'

    def __str__(self):
        return f"Firma di {self.user.get_full_name() or self.user.username}"


class OperatorCode(models.Model):
    """
    Codice operatore a 2 cifre (00-99), assegnato da un amministratore alla
    creazione dell'account. Compone il codice documento generato
    automaticamente (procedura aziendale ELTHUB "Gestione delle Informazioni
    Documentate", 230201161SYSP Rev. C, §2.1.1: yymmdd + progressivo + codice
    operatore + tipo documento — vedi documents.services.generate_document_code).

    Un utente senza questo record non può creare documenti fuori dalla
    modalità sanatoria (dove il codice è storico, inserito manualmente).
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='operator_code',
        verbose_name='Utente',
    )
    code = models.CharField(
        max_length=2,
        unique=True,
        verbose_name='Codice operatore',
        validators=[RegexValidator(r'^\d{2}$', 'Il codice operatore deve essere di 2 cifre numeriche (es. 04).')],
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Codice operatore'
        verbose_name_plural = 'Codici operatore'

    def __str__(self):
        return f"{self.code} — {self.user.get_full_name() or self.user.username}"
