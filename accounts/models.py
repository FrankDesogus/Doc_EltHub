from django.contrib.auth.models import User
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
