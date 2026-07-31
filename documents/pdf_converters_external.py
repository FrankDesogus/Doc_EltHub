"""
Convertitore esterno via LibreOffice headless per formati Office (TASK-044).

Isolato da documents/pdf_converters.py perché introduce una dipendenza di
sistema (binario `soffice`/LibreOffice) e invoca un processo esterno —
pdf_converters.py resta dichiaratamente pure-Python, nessuna dipendenza di
sistema.

Usato solo quando `is_libreoffice_available()` è vero, cioè quando
`settings.LIBREOFFICE_CONVERSION_ENABLED` è vero E il binario è realmente
presente sul PATH. Il chiamante (documents/pdf_pipeline.py) verifica questo
prima di selezionare PDFConverter.OFFICE_LIBREOFFICE in
documents/pdf_strategy.py — questo modulo non decide la policy, esegue
solo la conversione quando gli viene richiesta esplicitamente.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings

_CONVERT_TIMEOUT_SECONDS = 60


def _binary_name():
    return getattr(settings, 'LIBREOFFICE_BINARY', 'soffice')


def is_libreoffice_available():
    """
    True se la conversione via LibreOffice è sia abilitata via settings sia
    concretamente disponibile (binario presente sul PATH) in questo
    ambiente. Unico punto del sistema che fa questo controllo di I/O.
    """
    if not getattr(settings, 'LIBREOFFICE_CONVERSION_ENABLED', False):
        return False
    return shutil.which(_binary_name()) is not None


def render_office_to_pdf_bytes(source_bytes, extension):
    """
    Converte un file Office/OpenDocument (bytes grezzi + estensione, senza
    punto iniziale) in PDF invocando LibreOffice headless.

    Solleva RuntimeError con un messaggio chiaro se il binario non è
    disponibile, la conversione va in timeout, termina con codice diverso
    da zero o non produce un file di output — il chiamante
    (documents/pdf_pipeline.py) traduce questa eccezione in stato
    CONVERSION_FAILED, stesso pattern già usato per i convertitori
    pure-Python.
    """
    binary = shutil.which(_binary_name())
    if binary is None:
        raise RuntimeError(
            f"Binario LibreOffice ('{_binary_name()}') non trovato sul PATH."
        )

    with tempfile.TemporaryDirectory(prefix='docconv-work-') as work_dir, \
            tempfile.TemporaryDirectory(prefix='docconv-profile-') as profile_dir:
        work_path = Path(work_dir)
        input_path = work_path / f'source.{extension}'
        input_path.write_bytes(source_bytes)

        try:
            result = subprocess.run(
                [
                    binary,
                    '--headless',
                    '--norestore',
                    '--nolockcheck',
                    '--nodefault',
                    '--nofirststartwizard',
                    f'-env:UserInstallation=file://{profile_dir}',
                    '--convert-to', 'pdf',
                    '--outdir', str(work_path),
                    str(input_path),
                ],
                capture_output=True,
                timeout=_CONVERT_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Conversione LibreOffice interrotta per timeout "
                f"({_CONVERT_TIMEOUT_SECONDS}s)."
            ) from exc
        except OSError as exc:
            raise RuntimeError(f"Impossibile avviare LibreOffice: {exc}") from exc

        output_path = work_path / 'source.pdf'
        if result.returncode != 0 or not output_path.exists():
            stderr = result.stderr.decode('utf-8', errors='replace').strip()
            raise RuntimeError(
                f"Conversione LibreOffice fallita (codice {result.returncode}): "
                f"{stderr or 'nessun dettaglio disponibile'}"
            )
        return output_path.read_bytes()
