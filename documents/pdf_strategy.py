"""
Politica centralizzata per il PDF di rappresentazione (TASK-023).

Qualunque punto del codice che deve sapere "questo file sorgente può essere
convertito automaticamente in PDF, in questo ambiente?" deve interrogare
`determine_pdf_strategy(extension)` — non deve mai decidere da solo con un
`if estensione == ...` locale.

Strategie possibili:
  NATIVE_PDF      — il sorgente è già un PDF: la rappresentazione è una
                     copia identica, nessuna conversione, nessuna conferma.
  AUTO_RELIABLE   — conversione automatica con librerie Python pure
                     (nessuna dipendenza di sistema): testo semplice via
                     reportlab, immagini via Pillow. Richiede comunque la
                     conferma dell'autore (non è una copia byte-per-byte).
  MANUAL_REQUIRED — il PDF deve essere caricato dall'autore. Il motivo
                     (`reason`) distingue tre casi concreti:
                       - formato Office/documentale (docx, xlsx, ppt, odt...)
                         per cui una conversione fedele richiederebbe uno
                         strumento esterno (es. LibreOffice) non collegato
                         in questa versione del sistema;
                       - formato esplicitamente a rischio (archivi, CAD,
                         eseguibili...) per cui una conversione automatica
                         sarebbe comunque inaffidabile o priva di senso;
                       - estensione sconosciuta al sistema.

Il registro è un insieme di frozenset per estensione, non una catena di
`if`: aggiungere un formato è aggiungere l'estensione all'insieme giusto.
Nessun binario esterno viene invocato da questo modulo.
"""

from dataclasses import dataclass


class PDFStrategy:
    NATIVE_PDF = 'native_pdf'
    AUTO_RELIABLE = 'auto_reliable'
    MANUAL_REQUIRED = 'manual_required'

    CHOICES = (
        (NATIVE_PDF, 'Sorgente già PDF'),
        (AUTO_RELIABLE, 'Conversione automatica affidabile'),
        (MANUAL_REQUIRED, 'PDF da caricare manualmente'),
    )


class PDFConverter:
    IDENTITY = 'identity'
    TEXT_RENDERER = 'text_renderer'
    IMAGE_TO_PDF = 'image_to_pdf'
    NONE = ''


@dataclass(frozen=True)
class PDFStrategyDecision:
    strategy: str
    converter: str
    requires_confirmation: bool
    reason: str


# ---------------------------------------------------------------------------
# Registro delle estensioni. Estendere qui, non altrove.
# ---------------------------------------------------------------------------

_NATIVE_PDF_EXTENSIONS = frozenset({'pdf'})

_AUTO_RELIABLE_TEXT_EXTENSIONS = frozenset({'txt', 'md', 'csv'})
_AUTO_RELIABLE_IMAGE_EXTENSIONS = frozenset({
    'png', 'jpg', 'jpeg', 'bmp', 'tiff', 'tif', 'gif',
})

# Formati per cui una conversione fedele richiederebbe uno strumento esterno
# (es. LibreOffice headless) non collegato in questa versione del sistema:
# restano manuali, ma con un motivo distinto da "estensione sconosciuta",
# così che in futuro si possa registrare un converter reale per queste
# estensioni senza dover ridisegnare la policy.
_OFFICE_LIKE_MANUAL_EXTENSIONS = frozenset({
    'docx', 'doc', 'docm', 'odt', 'rtf',
    'xlsx', 'xls', 'xlsm', 'ods',
    'pptx', 'ppt', 'pptm', 'odp',
})

# Formati esplicitamente a rischio (archivi, CAD, eseguibili...): una
# conversione automatica non avrebbe comunque senso o sarebbe inaffidabile.
_RISKY_MANUAL_EXTENSIONS = frozenset({
    'zip', 'rar', '7z', 'tar', 'gz',
    'dwg', 'dxf',
    'exe', 'msi', 'dmg', 'bat', 'sh', 'cmd',
})

_REASON_OFFICE_UNAVAILABLE = (
    'Formato documentale (Office/OpenDocument): la conversione automatica '
    'non è disponibile in questo ambiente (nessun convertitore collegato). '
    'Caricare il PDF corrispondente prima dell\'invio in approvazione.'
)
_REASON_RISKY_FORMAT = (
    'Formato non adatto a una conversione automatica affidabile (rischio di '
    'fedeltà o contenuto non rappresentabile in PDF). Caricare il PDF '
    'corrispondente prima dell\'invio in approvazione.'
)
_REASON_UNKNOWN_EXTENSION = (
    'Estensione non riconosciuta dal sistema per la conversione automatica. '
    'Caricare il PDF corrispondente prima dell\'invio in approvazione.'
)


def normalize_extension(extension):
    """Normalizza un'estensione (con o senza punto iniziale) in minuscolo."""
    return (extension or '').strip().lstrip('.').lower()


def determine_pdf_strategy(extension):
    """
    Restituisce la PDFStrategyDecision per l'estensione indicata (senza
    punto iniziale, es. 'pdf', 'docx', 'png' — case-insensitive).

    Funzione pura: nessun accesso a filesystem, rete o modelli Django.
    """
    ext = normalize_extension(extension)

    if ext in _NATIVE_PDF_EXTENSIONS:
        return PDFStrategyDecision(
            strategy=PDFStrategy.NATIVE_PDF,
            converter=PDFConverter.IDENTITY,
            requires_confirmation=False,
            reason='Il file sorgente è già un PDF: nessuna conversione necessaria.',
        )

    if ext in _AUTO_RELIABLE_TEXT_EXTENSIONS:
        return PDFStrategyDecision(
            strategy=PDFStrategy.AUTO_RELIABLE,
            converter=PDFConverter.TEXT_RENDERER,
            requires_confirmation=True,
            reason='Testo semplice: conversione automatica disponibile, richiede conferma.',
        )

    if ext in _AUTO_RELIABLE_IMAGE_EXTENSIONS:
        return PDFStrategyDecision(
            strategy=PDFStrategy.AUTO_RELIABLE,
            converter=PDFConverter.IMAGE_TO_PDF,
            requires_confirmation=True,
            reason='Immagine: conversione automatica disponibile, richiede conferma.',
        )

    if ext in _OFFICE_LIKE_MANUAL_EXTENSIONS:
        return PDFStrategyDecision(
            strategy=PDFStrategy.MANUAL_REQUIRED,
            converter=PDFConverter.NONE,
            requires_confirmation=True,
            reason=_REASON_OFFICE_UNAVAILABLE,
        )

    if ext in _RISKY_MANUAL_EXTENSIONS:
        return PDFStrategyDecision(
            strategy=PDFStrategy.MANUAL_REQUIRED,
            converter=PDFConverter.NONE,
            requires_confirmation=True,
            reason=_REASON_RISKY_FORMAT,
        )

    return PDFStrategyDecision(
        strategy=PDFStrategy.MANUAL_REQUIRED,
        converter=PDFConverter.NONE,
        requires_confirmation=True,
        reason=_REASON_UNKNOWN_EXTENSION,
    )


def determine_pdf_strategy_for_file(document_file):
    """Scorciatoia: legge l'estensione da un'istanza DocumentFile."""
    return determine_pdf_strategy(document_file.extension)
