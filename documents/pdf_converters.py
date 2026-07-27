"""
Convertitori pure-Python per il PDF di rappresentazione (TASK-025).

Ogni funzione riceve i byte del file sorgente e restituisce i byte di un
PDF equivalente. Nessun accesso a filesystem/rete/modelli Django: chi
chiama (documents/pdf_pipeline.py) si occupa di leggere/scrivere file e di
tradurre un'eccezione qui sollevata in stato CONVERSION_FAILED.

Nessuna dipendenza da programmi esterni (niente LibreOffice/soffice): solo
reportlab (testo) e Pillow (immagini), entrambe librerie Python pure.
"""

import io

from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

_MARGIN = 15 * mm
_LINE_HEIGHT = 4.5 * mm
_FONT_NAME = 'Courier'
_FONT_SIZE = 9
_MAX_CHARS_PER_LINE = 100


def render_text_to_pdf_bytes(source_bytes):
    """Converte testo semplice (.txt/.md/.csv) in un PDF paginato monospace."""
    text = _decode_text(source_bytes)
    lines = _wrap_lines(text)

    buffer = io.BytesIO()
    page_width, page_height = A4
    usable_height = page_height - 2 * _MARGIN
    lines_per_page = max(1, int(usable_height // _LINE_HEIGHT))

    pdf = canvas.Canvas(buffer, pagesize=A4)
    for start in range(0, len(lines), lines_per_page):
        page_lines = lines[start:start + lines_per_page]
        pdf.setFont(_FONT_NAME, _FONT_SIZE)
        y = page_height - _MARGIN
        for line in page_lines:
            pdf.drawString(_MARGIN, y, line)
            y -= _LINE_HEIGHT
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def render_image_to_pdf_bytes(source_bytes):
    """Converte un'immagine (png/jpg/bmp/tiff/gif) in un PDF di una pagina."""
    with Image.open(io.BytesIO(source_bytes)) as img:
        img.load()
        flattened = _flatten_to_rgb(img)
        buffer = io.BytesIO()
        flattened.save(buffer, format='PDF')
        return buffer.getvalue()


def _flatten_to_rgb(img):
    has_alpha = img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)
    if not has_alpha:
        return img.convert('RGB')
    rgba = img.convert('RGBA')
    background = Image.new('RGB', img.size, (255, 255, 255))
    background.paste(rgba, mask=rgba.split()[-1])
    return background


def _decode_text(source_bytes):
    for encoding in ('utf-8', 'latin-1'):
        try:
            return source_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return source_bytes.decode('utf-8', errors='replace')


def _wrap_lines(text):
    wrapped = []
    raw_lines = text.splitlines() or ['']
    for raw_line in raw_lines:
        if not raw_line:
            wrapped.append('')
            continue
        while len(raw_line) > _MAX_CHARS_PER_LINE:
            wrapped.append(raw_line[:_MAX_CHARS_PER_LINE])
            raw_line = raw_line[_MAX_CHARS_PER_LINE:]
        wrapped.append(raw_line)
    return wrapped
