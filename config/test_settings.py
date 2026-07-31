"""
Impostazioni Django sicure per controlli automatizzati (scripts/test.sh).

- Nessun .env richiesto: SECRET_KEY fittizia impostata prima dell'import.
- Database SQLite in memoria (:memory:), mai file persistente.
- Email in memoria (locmem), nessun SMTP reale.
- Upload file (FileField/ImageField) isolati in .test-media/, mai nella
  media/ reale: senza questo override i test che caricano file scrivono
  nella cartella media/ di sviluppo, inquinandola in modo permanente
  (scoperto in TASK-011/TASK-012 — vedi docs/ai/TESTING_STATUS.md).
"""

import os

# Valori minimi in ambiente così config.settings importa senza .env reale.
os.environ['SECRET_KEY'] = 'test-secret-key-not-for-production-use-only'
os.environ.setdefault('DEBUG', 'True')
os.environ.setdefault('ALLOWED_HOSTS', 'testserver,localhost,127.0.0.1')

from config.settings import *  # noqa: E402, F403

SECRET_KEY = 'test-secret-key-not-for-production-use-only'
DEBUG = True

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
        'TEST': {
            'NAME': ':memory:',
        },
    }
}

EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# Isolamento upload di test: mai nella media/ reale (BASE_DIR / 'media').
MEDIA_ROOT = BASE_DIR / '.test-media'

# La suite non deve dipendere dalla presenza di LibreOffice sulla macchina
# che esegue i test (TASK-044): disabilitato esplicitamente, indipendente
# dal default di produzione in config/settings.py. I test che verificano
# la conversione via LibreOffice si abilitano puntualmente con
# @override_settings e restano comunque skippati se il binario non è
# realmente installato (unittest.skipUnless(shutil.which(...))).
LIBREOFFICE_CONVERSION_ENABLED = False
