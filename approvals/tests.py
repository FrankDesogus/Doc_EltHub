import datetime
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from approvals.models import ApprovalRequest
from approvals.services import approve_version, reject_version
from documents.models import Document, DocumentVersion
from documents.services import create_document_file, create_new_revision, submit_version_for_approval

LOCMEM = 'django.core.mail.backends.locmem.EmailBackend'


def make_document(code='DOC-001', owner=None, requires_approved_pdf=False):
    return Document.objects.create(
        code=code,
        title='Documento di test',
        category=Document.Category.QUALITY,
        owner=owner,
        created_by=owner,
        requires_approved_pdf=requires_approved_pdf,
    )


@override_settings(EMAIL_BACKEND=LOCMEM)
class ApproveVersionTests(TestCase):

    def setUp(self):
        self.author = User.objects.create_user('author', password='pw')
        self.approver = User.objects.create_user('approver', password='pw')
        self.other = User.objects.create_user('other', password='pw')
        self.document = make_document(owner=self.author)

    def _make_in_approval(self, label, number):
        # _bypass_ecn_check=True: questi test verificano il flusso di approvazione,
        # non il gate ECN (che ha test dedicati in ecn/tests.py).
        version = create_new_revision(self.document, self.author, label, number, _bypass_ecn_check=True)
        req = submit_version_for_approval(version, self.author, [self.approver])
        return version, req

    def test_first_approval_sets_current_version(self):
        version, req = self._make_in_approval('A', 1)
        approve_version(req, self.approver)

        version.refresh_from_db()
        self.document.refresh_from_db()

        self.assertEqual(version.status, DocumentVersion.Status.APPROVED)
        self.assertTrue(version.is_current)
        self.assertEqual(self.document.current_version, version)

    def test_subsequent_approval_supersedes_previous(self):
        v1, req1 = self._make_in_approval('A', 1)
        approve_version(req1, self.approver)

        v2, req2 = self._make_in_approval('B', 2)
        approve_version(req2, self.approver)

        v1.refresh_from_db()
        v2.refresh_from_db()
        self.document.refresh_from_db()

        self.assertEqual(v1.status, DocumentVersion.Status.SUPERSEDED)
        self.assertFalse(v1.is_current)
        self.assertEqual(v2.status, DocumentVersion.Status.APPROVED)
        self.assertTrue(v2.is_current)
        self.assertEqual(self.document.current_version, v2)

        current_count = DocumentVersion.objects.filter(
            document=self.document, is_current=True
        ).count()
        self.assertEqual(current_count, 1)

    def test_non_approver_cannot_approve(self):
        _, req = self._make_in_approval('A', 1)
        with self.assertRaises(PermissionDenied):
            approve_version(req, self.other)

    def test_superuser_can_approve(self):
        superuser = User.objects.create_superuser('admin', password='pw')
        _, req = self._make_in_approval('A', 1)
        approve_version(req, superuser)
        req.refresh_from_db()
        self.assertEqual(req.status, ApprovalRequest.Status.APPROVED)

    def test_due_date_saved_on_approval_request(self):
        version = create_new_revision(self.document, self.author, 'C', 3)
        scadenza = datetime.date(2026, 6, 30)
        req = submit_version_for_approval(version, self.author, [self.approver], due_date=scadenza)
        self.assertEqual(req.due_date, scadenza)

    def test_due_date_none_by_default(self):
        version = create_new_revision(self.document, self.author, 'D', 4)
        req = submit_version_for_approval(version, self.author, [self.approver])
        self.assertIsNone(req.due_date)


class ApprovalDecisionSnapshotTests(TestCase):
    """TASK-029 — snapshot congelato su ApprovalDecision al momento della decisione."""

    def setUp(self):
        self.author = User.objects.create_user('snap-author', password='pw')
        self.approver = User.objects.create_user(
            'snap-approver', password='pw', first_name='Maria', last_name='Bianchi',
        )
        self.document = make_document(code='SNAP-001', owner=self.author)

    def _make_in_approval(self, label='A', number=1, approvers=None, policy='all'):
        version = create_new_revision(self.document, self.author, label, number, _bypass_ecn_check=True)
        req = submit_version_for_approval(version, self.author, approvers or [self.approver], approval_policy=policy)
        return version, req

    def test_snapshot_display_name_and_order_captured_on_approve(self):
        _, req = self._make_in_approval()
        approve_version(req, self.approver)
        decision = req.decisions.get(approver=self.approver)
        self.assertEqual(decision.snapshot_approver_display_name, 'Maria Bianchi')
        self.assertEqual(decision.snapshot_approver_order, 1)

    def test_snapshot_text_only_when_no_signature_profile(self):
        from approvals.models import ApprovalDecision
        _, req = self._make_in_approval()
        approve_version(req, self.approver)
        decision = req.decisions.get(approver=self.approver)
        self.assertEqual(decision.snapshot_signature_mode, ApprovalDecision.SignatureMode.TEXT_ONLY)
        self.assertFalse(decision.snapshot_signature_image)

    def test_snapshot_includes_image_when_signature_profile_has_one(self):
        import io
        from accounts.models import UserSignature
        from approvals.models import ApprovalDecision
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buf = io.BytesIO()
        Image.new('RGBA', (10, 10), (0, 0, 255, 255)).save(buf, format='PNG')
        sig = UserSignature.objects.create(user=self.approver)
        sig.image.save('firma.png', SimpleUploadedFile('firma.png', buf.getvalue()), save=True)

        _, req = self._make_in_approval()
        approve_version(req, self.approver)
        decision = req.decisions.get(approver=self.approver)
        self.assertEqual(decision.snapshot_signature_mode, ApprovalDecision.SignatureMode.TEXT_AND_IMAGE)
        self.assertTrue(decision.snapshot_signature_image)

    def test_snapshot_unaffected_by_later_profile_change(self):
        """Se l'utente cambia nome o firma dopo la decisione, lo storico non cambia."""
        import io
        from accounts.models import UserSignature
        from approvals.models import ApprovalDecision
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buf = io.BytesIO()
        Image.new('RGBA', (10, 10), (0, 255, 0, 255)).save(buf, format='PNG')
        sig = UserSignature.objects.create(user=self.approver)
        sig.image.save('vecchia.png', SimpleUploadedFile('vecchia.png', buf.getvalue()), save=True)

        _, req = self._make_in_approval()
        approve_version(req, self.approver)
        decision = req.decisions.get(approver=self.approver)
        old_display_name = decision.snapshot_approver_display_name
        old_signature_name = decision.snapshot_signature_image.name

        # L'utente cambia nome e rimuove la firma dopo la decisione.
        self.approver.first_name = 'Cambiato'
        self.approver.last_name = 'Dopo'
        self.approver.save()
        sig.image.delete(save=False)
        sig.image = None
        sig.save(update_fields=['image'])

        decision.refresh_from_db()
        self.assertEqual(decision.snapshot_approver_display_name, old_display_name)
        self.assertEqual(decision.snapshot_signature_image.name, old_signature_name)
        self.assertEqual(decision.snapshot_signature_mode, ApprovalDecision.SignatureMode.TEXT_AND_IMAGE)

    def test_snapshot_order_none_for_unassigned_superuser_override(self):
        superuser = User.objects.create_superuser('snap-admin', password='pw')
        _, req = self._make_in_approval()
        approve_version(req, superuser)
        decision = req.decisions.get(approver=superuser)
        self.assertIsNone(decision.snapshot_approver_order)

    def test_snapshot_captured_on_reject_too(self):
        _, req = self._make_in_approval()
        reject_version(req, self.approver, rejection_reason='Non conforme')
        decision = req.decisions.get(approver=self.approver)
        self.assertEqual(decision.snapshot_approver_display_name, 'Maria Bianchi')
        self.assertEqual(decision.snapshot_approver_order, 1)


@override_settings(EMAIL_BACKEND=LOCMEM)
class ApprovedPDFAutoGenerationTests(TestCase):
    """TASK-030 — generazione automatica del PDF approvato via approve_version/reject_version."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.temp_media = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_media, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.author = User.objects.create_user('pdfgen-author', password='pw')
        self.approver1 = User.objects.create_user('pdfgen-approver1', password='pw', first_name='Anna', last_name='Verdi')
        self.approver2 = User.objects.create_user('pdfgen-approver2', password='pw', first_name='Marco', last_name='Neri')
        self.document = make_document(code='PDFGEN-001', owner=self.author, requires_approved_pdf=True)

    @staticmethod
    def _real_pdf_bytes(text='Contenuto di prova'):
        import io
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        buf = io.BytesIO()
        pdf = canvas.Canvas(buf, pagesize=A4)
        pdf.drawString(50, 800, text)
        pdf.showPage()
        pdf.save()
        return buf.getvalue()

    def _make_pending(self, approvers, policy='all', label='A', number=1):
        upload = SimpleUploadedFile(f'{label}.pdf', self._real_pdf_bytes(), content_type='application/pdf')
        source = create_document_file(upload, self.author)
        version = create_new_revision(self.document, self.author, label, number, file=source, _bypass_ecn_check=True)
        req = submit_version_for_approval(version, self.author, approvers, approval_policy=policy)
        return version, req

    def test_approved_pdf_generated_on_final_approval_any_policy(self):
        from documents.models import ApprovedPDFArtifact
        with self.settings(MEDIA_ROOT=self.temp_media):
            version, req = self._make_pending([self.approver1, self.approver2], policy='any')
            approve_version(req, self.approver1)
        version.refresh_from_db()
        self.assertIsNotNone(version.approved_pdf)
        self.assertEqual(version.approved_pdf.status, ApprovedPDFArtifact.Status.GENERATED)
        self.assertTrue(version.approved_pdf.file)

    def test_approved_pdf_content_includes_minimum_fields_any_policy(self):
        """Con policy ANY, solo la decisione effettivamente registrata compare nel registro."""
        from pypdf import PdfReader
        with self.settings(MEDIA_ROOT=self.temp_media):
            version, req = self._make_pending([self.approver1, self.approver2], policy='any')
            approve_version(req, self.approver1)
            version.refresh_from_db()
            text = "\n".join(page.extract_text() for page in PdfReader(version.approved_pdf.file.path).pages)
        self.assertIn('APPROVATO', text)
        self.assertIn(self.document.code, text)
        self.assertIn(version.revision_label, text)
        self.assertIn('Anna Verdi', text)
        self.assertNotIn('Marco Neri', text)  # non ha mai deciso: non deve comparire
        self.assertIn('firma digitale', text.lower())

    def test_approved_pdf_content_lists_all_approvers_for_all_policy(self):
        from pypdf import PdfReader
        with self.settings(MEDIA_ROOT=self.temp_media):
            version, req = self._make_pending([self.approver1, self.approver2], policy='all')
            approve_version(req, self.approver1)
            approve_version(req, self.approver2)
            version.refresh_from_db()
            text = "\n".join(page.extract_text() for page in PdfReader(version.approved_pdf.file.path).pages)
        self.assertIn('Anna Verdi', text)
        self.assertIn('Marco Neri', text)

    def test_approved_pdf_content_respects_sequential_order(self):
        from pypdf import PdfReader
        with self.settings(MEDIA_ROOT=self.temp_media):
            version, req = self._make_pending([self.approver1, self.approver2], policy='sequential')
            approve_version(req, self.approver1)
            approve_version(req, self.approver2)
            version.refresh_from_db()
            decisions = list(req.decisions.filter(decision='APPROVED').order_by('snapshot_approver_order'))
        self.assertEqual([d.approver_id for d in decisions], [self.approver1.pk, self.approver2.pk])

    def test_no_approved_pdf_generated_on_rejection(self):
        with self.settings(MEDIA_ROOT=self.temp_media):
            version, req = self._make_pending([self.approver1], policy='all')
            reject_version(req, self.approver1, rejection_reason='Non conforme')
        version.refresh_from_db()
        self.assertIsNone(version.approved_pdf)

    def test_no_approved_pdf_generated_on_partial_approval(self):
        with self.settings(MEDIA_ROOT=self.temp_media):
            version, req = self._make_pending([self.approver1, self.approver2], policy='all')
            approve_version(req, self.approver1)
        version.refresh_from_db()
        self.assertIsNone(version.approved_pdf)

    def test_regeneration_is_idempotent_no_duplicate_artifact(self):
        from documents.pdf_generation import generate_approved_pdf
        with self.settings(MEDIA_ROOT=self.temp_media):
            version, req = self._make_pending([self.approver1], policy='all')
            approve_version(req, self.approver1)
            version.refresh_from_db()
            first_artifact_id = version.approved_pdf_id
            second_artifact = generate_approved_pdf(version)
        self.assertEqual(second_artifact.pk, first_artifact_id)

    def test_generation_failure_is_recorded_and_retryable(self):
        from documents.models import ApprovedPDFArtifact
        from documents.pdf_generation import generate_approved_pdf
        with self.settings(MEDIA_ROOT=self.temp_media):
            version, req = self._make_pending([self.approver1], policy='all')
            approve_version(req, self.approver1)
            version.refresh_from_db()

            # Rompe deliberatamente il file di rappresentazione per indurre un fallimento.
            rep = version.representation_pdf
            rep.file.delete(save=False)
            rep.save(update_fields=['file'])
            version.refresh_from_db()

            artifact = generate_approved_pdf(version, force=True)
            self.assertEqual(artifact.status, ApprovedPDFArtifact.Status.FAILED)
            self.assertTrue(artifact.error_message)


@override_settings(EMAIL_BACKEND=LOCMEM)
class ApprovedPDFFooterPlacementTests(TestCase):
    """
    Verifica manuale del 2026-07-27 (AREA 2): il registro delle approvazioni
    deve comparire realmente "in calce" all'ultima pagina di contenuto
    quando è tecnicamente sicuro, senza mai sovrapporsi al contenuto
    esistente — con una pagina finale dedicata come fallback per i casi in
    cui il registro sarebbe troppo alto per un footer ragionevole.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.temp_media = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_media, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.author = User.objects.create_user('footer-author', password='pw')
        self.document = make_document(code='FOOTER-001', owner=self.author, requires_approved_pdf=True)

    @staticmethod
    def _content_pdf_bytes(n_pages=1, fill_bottom=False):
        import io
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        buf = io.BytesIO()
        pdf = canvas.Canvas(buf, pagesize=A4)
        width, height = A4
        for _ in range(n_pages):
            pdf.setFont('Helvetica', 11)
            y = height - 30
            floor = 10 if fill_bottom else 150
            while y > floor:
                pdf.drawString(30, y, "Riga di contenuto reale del documento sorgente")
                y -= 14
            pdf.showPage()
        pdf.save()
        return buf.getvalue()

    @staticmethod
    def _signature_png_bytes():
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new('RGBA', (300, 100), (0, 100, 200, 255)).save(buf, format='PNG')
        return buf.getvalue()

    def _approvers_with_signatures(self, n, signed=True):
        from accounts.models import UserSignature
        users = []
        for i in range(n):
            u = User.objects.create_user(f'footer-approver{i}', password='pw', first_name=f'Nome{i}', last_name='Cognome')
            if signed:
                sig = UserSignature.objects.create(user=u)
                sig.image.save(f'firma{i}.png', SimpleUploadedFile(f'firma{i}.png', self._signature_png_bytes()), save=True)
            users.append(u)
        return users

    def test_footer_used_for_single_approver_no_extra_page(self):
        from pypdf import PdfReader
        from approvals.services import approve_version
        with self.settings(MEDIA_ROOT=self.temp_media):
            approvers = self._approvers_with_signatures(1)
            source = create_document_file(
                SimpleUploadedFile('a.pdf', self._content_pdf_bytes(n_pages=1), content_type='application/pdf'),
                self.author,
            )
            version = create_new_revision(self.document, self.author, 'A', 1, file=source)
            req = submit_version_for_approval(version, self.author, approvers, approval_policy='all')
            approve_version(req, approvers[0])
            version.refresh_from_db()

            self.assertEqual(version.approved_pdf.status, 'generated')
            reader = PdfReader(version.approved_pdf.file.path)
            self.assertEqual(len(reader.pages), 1)  # footer in calce: nessuna pagina aggiunta
            text = reader.pages[0].extract_text()
        self.assertIn('REGISTRO DI APPROVAZIONE', text)
        self.assertIn('Riga di contenuto reale', text)  # contenuto originale ancora presente

    def test_no_overlap_when_last_page_completely_full(self):
        """Caso peggiore: pagina piena fino in fondo, nessuno spazio libero
        preesistente — la generazione deve comunque riuscire senza sovrapporsi."""
        from pypdf import PdfReader
        from approvals.services import approve_version
        with self.settings(MEDIA_ROOT=self.temp_media):
            approvers = self._approvers_with_signatures(2)
            source = create_document_file(
                SimpleUploadedFile('a.pdf', self._content_pdf_bytes(n_pages=2, fill_bottom=True), content_type='application/pdf'),
                self.author,
            )
            version = create_new_revision(self.document, self.author, 'A', 1, file=source)
            req = submit_version_for_approval(version, self.author, approvers, approval_policy='all')
            approve_version(req, approvers[0])
            approve_version(req, approvers[1])
            version.refresh_from_db()

            self.assertEqual(version.approved_pdf.status, 'generated')
            reader = PdfReader(version.approved_pdf.file.path)
            # Pagina estesa (footer in calce), non una pagina aggiuntiva.
            self.assertEqual(len(reader.pages), 2)

    def test_falls_back_to_dedicated_page_when_registry_too_tall(self):
        """Molti approvatori con firma -> il footer supererebbe l'altezza
        massima ragionevole: deve ricadere sulla pagina finale dedicata."""
        from pypdf import PdfReader
        from approvals.services import approve_version
        with self.settings(MEDIA_ROOT=self.temp_media):
            approvers = self._approvers_with_signatures(10)
            source = create_document_file(
                SimpleUploadedFile('a.pdf', self._content_pdf_bytes(n_pages=1), content_type='application/pdf'),
                self.author,
            )
            version = create_new_revision(self.document, self.author, 'A', 1, file=source)
            req = submit_version_for_approval(version, self.author, approvers, approval_policy='all')
            for u in approvers:
                approve_version(req, u)
            version.refresh_from_db()

            self.assertEqual(version.approved_pdf.status, 'generated')
            reader = PdfReader(version.approved_pdf.file.path)
            self.assertEqual(len(reader.pages), 2)  # pagina di contenuto + pagina registro dedicata
            registry_text = reader.pages[1].extract_text()
        self.assertIn('REGISTRO DI APPROVAZIONE', registry_text)
        for u in approvers:
            self.assertIn(u.get_full_name(), registry_text)

    def test_disclaimer_present_in_footer_variant(self):
        from pypdf import PdfReader
        from approvals.services import approve_version
        approvers = self._approvers_with_signatures(1, signed=False)
        with self.settings(MEDIA_ROOT=self.temp_media):
            source = create_document_file(
                SimpleUploadedFile('a.pdf', self._content_pdf_bytes(n_pages=1), content_type='application/pdf'),
                self.author,
            )
            version = create_new_revision(self.document, self.author, 'A', 1, file=source)
            req = submit_version_for_approval(version, self.author, approvers, approval_policy='all')
            approve_version(req, approvers[0])
            version.refresh_from_db()
            text = PdfReader(version.approved_pdf.file.path).pages[0].extract_text()
        self.assertIn('non costituiscono firma digitale', text)


@override_settings(EMAIL_BACKEND=LOCMEM)
class RejectVersionTests(TestCase):

    def setUp(self):
        self.author = User.objects.create_user('author', password='pw')
        self.approver = User.objects.create_user('approver', password='pw')
        self.other = User.objects.create_user('other', password='pw')
        self.document = make_document(owner=self.author)

    def _make_in_approval(self, label='A', number=1):
        version = create_new_revision(self.document, self.author, label, number)
        req = submit_version_for_approval(version, self.author, [self.approver])
        return version, req

    def test_reject_sets_rejected_status(self):
        version, req = self._make_in_approval()
        reject_version(req, self.approver, 'Non conforme')
        version.refresh_from_db()
        self.assertEqual(version.status, DocumentVersion.Status.REJECTED)

    def test_reject_stores_reason(self):
        version, req = self._make_in_approval()
        reject_version(req, self.approver, 'Non conforme ai requisiti')
        version.refresh_from_db()
        self.assertEqual(version.rejection_reason, 'Non conforme ai requisiti')

    def test_reject_does_not_change_current_version(self):
        v1 = create_new_revision(self.document, self.author, 'A', 1)
        req1 = submit_version_for_approval(v1, self.author, [self.approver])
        approve_version(req1, self.approver)

        v2 = create_new_revision(self.document, self.author, 'B', 2, _bypass_ecn_check=True)
        req2 = submit_version_for_approval(v2, self.author, [self.approver])
        reject_version(req2, self.approver, 'Non conforme')

        self.document.refresh_from_db()
        self.assertEqual(self.document.current_version, v1)

    def test_reject_requires_reason(self):
        _, req = self._make_in_approval()
        with self.assertRaises(ValidationError):
            reject_version(req, self.approver, '')

    def test_non_approver_cannot_reject(self):
        _, req = self._make_in_approval()
        with self.assertRaises(PermissionDenied):
            reject_version(req, self.other, 'qualsiasi motivo')


@override_settings(EMAIL_BACKEND=LOCMEM)
class ApprovalEmailTests(TestCase):
    """Verifica che approve_version e reject_version inviino email e creino NotificationLog."""

    def setUp(self):
        mail.outbox = []
        self.author = User.objects.create_user(
            'author', email='author@example.com', password='pw',
        )
        self.approver = User.objects.create_user(
            'approver', email='approver@example.com', password='pw',
        )
        self.document = make_document(owner=self.author)

    def _make_in_approval(self, label='A', number=1):
        version = create_new_revision(self.document, self.author, label, number)
        req = submit_version_for_approval(version, self.author, [self.approver])
        mail.outbox = []  # azzera dopo submit per isolare il test
        return version, req

    def test_approve_sends_email_to_author(self):
        _, req = self._make_in_approval()
        approve_version(req, self.approver)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.author.email, mail.outbox[0].to)

    def test_approve_email_contains_document_code(self):
        _, req = self._make_in_approval()
        approve_version(req, self.approver)
        self.assertIn(self.document.code, mail.outbox[0].body)

    def test_approve_creates_notification_log(self):
        from notifications.models import NotificationLog
        _, req = self._make_in_approval()
        approve_version(req, self.approver)
        self.assertTrue(NotificationLog.objects.filter(is_sent=True).exists())

    def test_reject_sends_email_to_author(self):
        _, req = self._make_in_approval()
        reject_version(req, self.approver, 'Sezione 3 incompleta')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.author.email, mail.outbox[0].to)

    def test_reject_email_contains_rejection_reason(self):
        _, req = self._make_in_approval()
        reject_version(req, self.approver, 'Sezione 3 incompleta')
        self.assertIn('Sezione 3 incompleta', mail.outbox[0].body)

    def test_reject_creates_notification_log(self):
        from notifications.models import NotificationLog
        _, req = self._make_in_approval()
        reject_version(req, self.approver, 'Sezione 3 incompleta')
        self.assertTrue(NotificationLog.objects.filter(is_sent=True).exists())


@override_settings(EMAIL_BACKEND=LOCMEM)
class ApprovalViewTests(TestCase):
    """Verifica le view di approvazione: accesso, azioni approve/reject."""

    def setUp(self):
        mail.outbox = []
        self.author = User.objects.create_user('author', email='a@t.com', password='pw')
        self.approver = User.objects.create_user('approver', email='ap@t.com', password='pw')
        self.other = User.objects.create_user('other', email='o@t.com', password='pw')
        self.document = make_document(owner=self.author)

    def _make_pending(self, label='A', number=1):
        version = create_new_revision(self.document, self.author, label, number)
        req = submit_version_for_approval(version, self.author, [self.approver])
        mail.outbox = []
        return version, req

    def test_approver_sees_assigned_request_in_queue(self):
        self._make_pending()
        self.client.login(username='approver', password='pw')
        response = self.client.get(reverse('approval_queue'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.document.code)

    def test_unassigned_user_gets_403_on_detail(self):
        _, req = self._make_pending()
        self.client.login(username='other', password='pw')
        response = self.client.get(reverse('approval_detail', args=[req.pk]))
        self.assertEqual(response.status_code, 403)

    def test_approve_from_ui_changes_status(self):
        _, req = self._make_pending()
        self.client.login(username='approver', password='pw')
        response = self.client.post(
            reverse('approval_detail', args=[req.pk]),
            {'action': 'approve', 'comment': ''},
        )
        self.assertRedirects(response, reverse('approval_queue'))
        req.refresh_from_db()
        self.assertEqual(req.status, ApprovalRequest.Status.APPROVED)

    def test_reject_from_ui_requires_reason(self):
        _, req = self._make_pending()
        self.client.login(username='approver', password='pw')
        response = self.client.post(
            reverse('approval_detail', args=[req.pk]),
            {'action': 'reject', 'rejection_reason': ''},
        )
        self.assertEqual(response.status_code, 200)  # resta sulla pagina
        req.refresh_from_db()
        self.assertEqual(req.status, ApprovalRequest.Status.PENDING)  # invariato

    def test_reject_from_ui_with_reason_changes_status(self):
        _, req = self._make_pending()
        self.client.login(username='approver', password='pw')
        response = self.client.post(
            reverse('approval_detail', args=[req.pk]),
            {'action': 'reject', 'rejection_reason': 'Documento incompleto'},
        )
        self.assertRedirects(response, reverse('approval_queue'))
        req.refresh_from_db()
        self.assertEqual(req.status, ApprovalRequest.Status.REJECTED)


@override_settings(EMAIL_BACKEND=LOCMEM)
class RepresentationPDFApproverViewTests(TestCase):
    """TASK-027 — l'approvatore vede/scarica il PDF di rappresentazione, distinto dal sorgente."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import tempfile
        cls.temp_media = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.temp_media, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from documents.services import create_document_file

        mail.outbox = []
        self.author = User.objects.create_user('reppdf-author', email='a@t.com', password='pw')
        self.approver = User.objects.create_user('reppdf-approver', email='ap@t.com', password='pw')
        self.other = User.objects.create_user('reppdf-other', email='o@t.com', password='pw')
        self.document = make_document(code='REPPDF-001', owner=self.author, requires_approved_pdf=True)
        with self.settings(MEDIA_ROOT=self.temp_media):
            upload = SimpleUploadedFile('sorgente.pdf', b'%PDF-1.4 vero', content_type='application/pdf')
            source = create_document_file(upload, self.author)
            self.version = create_new_revision(self.document, self.author, 'A', 1, file=source)
            self.req = submit_version_for_approval(self.version, self.author, [self.approver])

    def test_approval_detail_shows_representation_pdf_distinct_from_source(self):
        self.client.login(username='reppdf-approver', password='pw')
        response = self.client.get(reverse('approval_detail', args=[self.req.pk]))
        self.assertContains(response, 'PDF di rappresentazione')
        self.assertContains(response, 'File sorgente')

    def test_assigned_approver_can_download_representation_pdf(self):
        self.client.login(username='reppdf-approver', password='pw')
        with self.settings(MEDIA_ROOT=self.temp_media):
            response = self.client.get(reverse('version_representation_pdf_download', args=[self.version.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_unassigned_user_cannot_download_representation_pdf(self):
        self.client.login(username='reppdf-other', password='pw')
        with self.settings(MEDIA_ROOT=self.temp_media):
            response = self.client.get(reverse('version_representation_pdf_download', args=[self.version.pk]))
        self.assertEqual(response.status_code, 403)


# ---------------------------------------------------------------------------
# Policy-aware tests
# ---------------------------------------------------------------------------

@override_settings(EMAIL_BACKEND=LOCMEM)
class PolicyAnyTests(TestCase):
    """Policy ANY: basta un approvatore qualsiasi."""

    def setUp(self):
        self.author = User.objects.create_user('pa_author', password='pw')
        self.a1 = User.objects.create_user('pa_a1', password='pw')
        self.a2 = User.objects.create_user('pa_a2', password='pw')
        self.doc = make_document(code='PA-DOC', owner=self.author)

    def _make_pending(self):
        version = create_new_revision(self.doc, self.author, '00', 0)
        req = submit_version_for_approval(
            version, self.author, [self.a1, self.a2], approval_policy='any'
        )
        return version, req

    def test_first_approve_finalizes_immediately(self):
        version, req = self._make_pending()
        approve_version(req, self.a1)
        req.refresh_from_db()
        version.refresh_from_db()
        self.doc.refresh_from_db()
        self.assertEqual(req.status, ApprovalRequest.Status.APPROVED)
        self.assertEqual(version.status, DocumentVersion.Status.APPROVED)
        self.assertTrue(version.is_current)
        self.assertEqual(self.doc.current_version, version)

    def test_any_reject_sets_rejected(self):
        version, req = self._make_pending()
        reject_version(req, self.a2, 'Non conforme')
        req.refresh_from_db()
        version.refresh_from_db()
        self.assertEqual(req.status, ApprovalRequest.Status.REJECTED)
        self.assertEqual(version.status, DocumentVersion.Status.REJECTED)


@override_settings(EMAIL_BACKEND=LOCMEM)
class PolicyAllTests(TestCase):
    """Policy ALL: devono approvare tutti."""

    def setUp(self):
        self.author = User.objects.create_user('pl_author', password='pw')
        self.a1 = User.objects.create_user('pl_a1', password='pw')
        self.a2 = User.objects.create_user('pl_a2', password='pw')
        self.doc = make_document(code='PL-DOC', owner=self.author)

    def _make_pending(self):
        version = create_new_revision(self.doc, self.author, '00', 0)
        req = submit_version_for_approval(
            version, self.author, [self.a1, self.a2], approval_policy='all'
        )
        return version, req

    def test_first_approve_leaves_request_pending(self):
        version, req = self._make_pending()
        approve_version(req, self.a1)
        req.refresh_from_db()
        version.refresh_from_db()
        self.assertEqual(req.status, ApprovalRequest.Status.PENDING)
        self.assertEqual(version.status, DocumentVersion.Status.IN_APPROVAL)
        self.assertFalse(version.is_current)

    def test_first_approve_does_not_set_current_version(self):
        version, req = self._make_pending()
        approve_version(req, self.a1)
        self.doc.refresh_from_db()
        self.assertIsNone(self.doc.current_version)

    def test_all_approve_finalizes(self):
        version, req = self._make_pending()
        approve_version(req, self.a1)
        approve_version(req, self.a2)
        req.refresh_from_db()
        version.refresh_from_db()
        self.doc.refresh_from_db()
        self.assertEqual(req.status, ApprovalRequest.Status.APPROVED)
        self.assertEqual(version.status, DocumentVersion.Status.APPROVED)
        self.assertTrue(version.is_current)
        self.assertEqual(self.doc.current_version, version)

    def test_reject_by_first_approver_sets_rejected(self):
        version, req = self._make_pending()
        reject_version(req, self.a1, 'Non conforme')
        req.refresh_from_db()
        version.refresh_from_db()
        self.assertEqual(req.status, ApprovalRequest.Status.REJECTED)
        self.assertEqual(version.status, DocumentVersion.Status.REJECTED)

    def test_reject_does_not_change_current_version(self):
        # Approva una prima versione, poi crea e rifiuta una seconda
        v1 = create_new_revision(self.doc, self.author, '00', 0)
        req1 = submit_version_for_approval(v1, self.author, [self.a1], approval_policy='all')
        approve_version(req1, self.a1)

        # _bypass_ecn_check=True: test del flusso approvazione, non del gate ECN
        v2 = create_new_revision(self.doc, self.author, '01', 1, _bypass_ecn_check=True)
        req2 = submit_version_for_approval(v2, self.author, [self.a1, self.a2], approval_policy='all')
        reject_version(req2, self.a1, 'Non conforme')

        self.doc.refresh_from_db()
        self.assertEqual(self.doc.current_version, v1)


@override_settings(EMAIL_BACKEND=LOCMEM)
class PolicySequentialTests(TestCase):
    """Policy SEQUENTIAL: gli approvatori devono approvare nell'ordine definito."""

    def setUp(self):
        self.author = User.objects.create_user('ps_author', password='pw')
        self.a1 = User.objects.create_user('ps_a1', password='pw')
        self.a2 = User.objects.create_user('ps_a2', password='pw')
        self.doc = make_document(code='PS-DOC', owner=self.author)

    def _make_pending(self):
        # a1 ha order=0, a2 ha order=1 (nell'ordine della lista)
        version = create_new_revision(self.doc, self.author, '00', 0)
        req = submit_version_for_approval(
            version, self.author, [self.a1, self.a2], approval_policy='sequential'
        )
        return version, req

    def test_second_approver_cannot_approve_before_first(self):
        _, req = self._make_pending()
        with self.assertRaises(ValidationError):
            approve_version(req, self.a2)

    def test_first_approver_leaves_request_pending(self):
        version, req = self._make_pending()
        approve_version(req, self.a1)
        req.refresh_from_db()
        version.refresh_from_db()
        self.assertEqual(req.status, ApprovalRequest.Status.PENDING)
        self.assertEqual(version.status, DocumentVersion.Status.IN_APPROVAL)

    def test_both_approve_in_order_finalizes(self):
        version, req = self._make_pending()
        approve_version(req, self.a1)
        approve_version(req, self.a2)
        req.refresh_from_db()
        version.refresh_from_db()
        self.doc.refresh_from_db()
        self.assertEqual(req.status, ApprovalRequest.Status.APPROVED)
        self.assertEqual(version.status, DocumentVersion.Status.APPROVED)
        self.assertTrue(version.is_current)
        self.assertEqual(self.doc.current_version, version)

    def test_reject_in_sequential_sets_rejected(self):
        version, req = self._make_pending()
        reject_version(req, self.a1, 'Non conforme')
        req.refresh_from_db()
        version.refresh_from_db()
        self.assertEqual(req.status, ApprovalRequest.Status.REJECTED)
        self.assertEqual(version.status, DocumentVersion.Status.REJECTED)

    def test_later_approver_can_reject_out_of_order(self):
        """Un approvatore successivo può rifiutare anche prima del suo turno."""
        version, req = self._make_pending()
        reject_version(req, self.a2, 'Problema grave')
        req.refresh_from_db()
        self.assertEqual(req.status, ApprovalRequest.Status.REJECTED)


@override_settings(EMAIL_BACKEND=LOCMEM)
class DoubleDecisionTests(TestCase):
    """Lo stesso approvatore non può decidere due volte sulla stessa richiesta."""

    def setUp(self):
        self.author = User.objects.create_user('dd_author', password='pw')
        self.approver = User.objects.create_user('dd_approver', password='pw')
        self.a2 = User.objects.create_user('dd_a2', password='pw')
        self.doc = make_document(code='DD-DOC', owner=self.author)

    def test_double_approve_raises(self):
        version = create_new_revision(self.doc, self.author, '00', 0)
        req = submit_version_for_approval(
            version, self.author, [self.approver, self.a2], approval_policy='all'
        )
        approve_version(req, self.approver)
        with self.assertRaises(ValidationError):
            approve_version(req, self.approver)

    def test_double_reject_raises(self):
        version = create_new_revision(self.doc, self.author, '00', 0)
        req = submit_version_for_approval(
            version, self.author, [self.approver, self.a2], approval_policy='all'
        )
        reject_version(req, self.approver, 'Motivo')
        # La richiesta è già REJECTED, quindi la seconda chiamata solleva per stato
        with self.assertRaises(ValidationError):
            reject_version(req, self.approver, 'Altro motivo')

    def test_approve_then_reject_raises(self):
        """Un approvatore che ha già approvato non può poi rifiutare (decisione già registrata)."""
        version = create_new_revision(self.doc, self.author, '00', 0)
        req = submit_version_for_approval(
            version, self.author, [self.approver, self.a2], approval_policy='all'
        )
        approve_version(req, self.approver)
        # Il secondo reject solleva per decisione già presente
        with self.assertRaises(ValidationError):
            reject_version(req, self.approver, 'Ripensamento')


@override_settings(EMAIL_BACKEND=LOCMEM)
class SuperuserOverrideTests(TestCase):
    """Superuser può approvare/rifiutare anche se non assegnato; l'approvazione è sempre finale."""

    def setUp(self):
        self.author = User.objects.create_user('su_author', password='pw')
        self.approver = User.objects.create_user('su_approver', password='pw')
        self.superuser = User.objects.create_superuser('su_admin', password='pw')
        self.doc = make_document(code='SU-DOC', owner=self.author)

    def test_superuser_not_assigned_can_approve(self):
        version = create_new_revision(self.doc, self.author, '00', 0)
        req = submit_version_for_approval(
            version, self.author, [self.approver], approval_policy='all'
        )
        approve_version(req, self.superuser)
        req.refresh_from_db()
        self.assertEqual(req.status, ApprovalRequest.Status.APPROVED)

    def test_superuser_override_with_all_policy_multiple_approvers(self):
        """Superuser approva definitivamente anche con ALL e più approvatori non ancora decisi."""
        a2 = User.objects.create_user('su_a2', password='pw')
        version = create_new_revision(self.doc, self.author, '00', 0)
        req = submit_version_for_approval(
            version, self.author, [self.approver, a2], approval_policy='all'
        )
        approve_version(req, self.superuser)
        req.refresh_from_db()
        version.refresh_from_db()
        self.assertEqual(req.status, ApprovalRequest.Status.APPROVED)
        self.assertEqual(version.status, DocumentVersion.Status.APPROVED)


@override_settings(EMAIL_BACKEND=LOCMEM)
class PolicyUITests(TestCase):
    """Test UI: submit salva approval_policy; detail mostra messaggi approvazione parziale/finale."""

    def setUp(self):
        from django.contrib.auth.models import Group
        mail.outbox = []
        self.author = User.objects.create_user('ui_author', email='a@t.com', password='pw')
        self.a1 = User.objects.create_user('ui_a1', email='a1@t.com', password='pw')
        self.a2 = User.objects.create_user('ui_a2', email='a2@t.com', password='pw')
        Group.objects.get_or_create(name='Document Authors')[0].user_set.add(self.author)
        self.doc = make_document(code='UI-DOC', owner=self.author)

    def test_submit_form_saves_approval_policy(self):
        version = create_new_revision(self.doc, self.author, '00', 0)
        self.client.login(username='ui_author', password='pw')
        self.client.post(
            reverse('version_submit', args=[version.pk]),
            {
                'approver-TOTAL_FORMS': '2',
                'approver-INITIAL_FORMS': '0',
                'approver-MIN_NUM_FORMS': '0',
                'approver-MAX_NUM_FORMS': '1000',
                'approver-0-approver': str(self.a1.pk),
                'approver-1-approver': str(self.a2.pk),
                'approval_policy': 'any',
            },
        )
        from approvals.models import ApprovalRequest
        req = ApprovalRequest.objects.get(document_version=version)
        self.assertEqual(req.approval_policy, 'any')

    def test_partial_approval_message_shown(self):
        """Con policy ALL e due approvatori, dopo il primo approve il messaggio è 'ancora in attesa'."""
        version = create_new_revision(self.doc, self.author, '00', 0)
        req = submit_version_for_approval(
            version, self.author, [self.a1, self.a2], approval_policy='all'
        )
        self.client.login(username='ui_a1', password='pw')
        response = self.client.post(
            reverse('approval_detail', args=[req.pk]),
            {'action': 'approve', 'comment': ''},
            follow=True,
        )
        self.assertContains(response, 'ancora in attesa')

    def test_final_approval_message_shown(self):
        """Con policy ALL e un solo approvatore, dopo approve il messaggio è 'Documento approvato'."""
        version = create_new_revision(self.doc, self.author, '00', 0)
        req = submit_version_for_approval(
            version, self.author, [self.a1], approval_policy='all'
        )
        self.client.login(username='ui_a1', password='pw')
        response = self.client.post(
            reverse('approval_detail', args=[req.pk]),
            {'action': 'approve', 'comment': ''},
            follow=True,
        )
        self.assertContains(response, 'approvato')


@override_settings(EMAIL_BACKEND=LOCMEM)
class ApprovalAttachmentTests(TestCase):

    def setUp(self):
        mail.outbox = []
        from django.contrib.auth.models import Group
        self.author = User.objects.create_user('at_author', email='author@t.com', password='pw')
        self.approver = User.objects.create_user('at_approver', email='ap@t.com', password='pw')
        self.outsider = User.objects.create_user('at_outsider', email='out@t.com', password='pw')
        Group.objects.get_or_create(name='Document Authors')[0].user_set.add(self.author)
        self.doc = make_document(code='AT-DOC', owner=self.author)

    def _make_draft(self):
        return create_new_revision(self.doc, self.author, '01', 1)

    def _post_submit(self, version, sig_file=None):
        from django.core.files.uploadedfile import SimpleUploadedFile
        data = {
            'approver-TOTAL_FORMS': '1',
            'approver-INITIAL_FORMS': '0',
            'approver-MIN_NUM_FORMS': '0',
            'approver-MAX_NUM_FORMS': '1000',
            'approver-0-approver': str(self.approver.pk),
            'approval_policy': 'all',
        }
        files = {}
        if sig_file is not None:
            files['signature_template_file'] = sig_file
        self.client.login(username='at_author', password='pw')
        return self.client.post(reverse('version_submit', args=[version.pk]), {**data, **files})

    def test_submit_without_attachment_works(self):
        draft = self._make_draft()
        response = self._post_submit(draft)
        self.assertEqual(response.status_code, 302)
        from approvals.models import ApprovalRequest, ApprovalRequestAttachment
        ar = ApprovalRequest.objects.get(document_version=draft)
        self.assertEqual(ar.attachments.count(), 0)

    def test_submit_with_signature_template_creates_attachment(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        draft = self._make_draft()
        sig_file = SimpleUploadedFile('modello.pdf', b'%PDF dummy', content_type='application/pdf')
        response = self._post_submit(draft, sig_file=sig_file)
        self.assertEqual(response.status_code, 302)
        from approvals.models import ApprovalRequest, ApprovalRequestAttachment
        ar = ApprovalRequest.objects.get(document_version=draft)
        self.assertEqual(ar.attachments.count(), 1)
        att = ar.attachments.first()
        self.assertEqual(att.attachment_type, ApprovalRequestAttachment.AttachmentType.SIGNATURE_TEMPLATE)
        self.assertEqual(att.original_filename, 'modello.pdf')

    def test_attachment_does_not_replace_version_file(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from documents.services import create_document_file
        op_file = SimpleUploadedFile('operativo.pdf', b'%PDF op', content_type='application/pdf')
        doc_file = create_document_file(op_file, self.author)
        draft = create_new_revision(self.doc, self.author, '01', 1, file=doc_file)
        sig_file = SimpleUploadedFile('modello.pdf', b'%PDF sig', content_type='application/pdf')
        self._post_submit(draft, sig_file=sig_file)
        draft.refresh_from_db()
        self.assertIsNotNone(draft.file)
        self.assertEqual(draft.file.pk, doc_file.pk)

    def test_attachment_metadata_set(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        import hashlib
        content = b'%PDF-1.4 test content'
        expected_hash = hashlib.sha256(content).hexdigest()
        draft = self._make_draft()
        sig_file = SimpleUploadedFile('firma.pdf', content, content_type='application/pdf')
        self._post_submit(draft, sig_file=sig_file)
        from approvals.models import ApprovalRequest
        ar = ApprovalRequest.objects.get(document_version=draft)
        att = ar.attachments.first()
        self.assertEqual(att.original_filename, 'firma.pdf')
        self.assertEqual(att.sha256_hash, expected_hash)
        self.assertEqual(att.size, len(content))
        self.assertEqual(att.extension, 'pdf')

    def test_assigned_approver_can_download_attachment(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        draft = self._make_draft()
        sig_file = SimpleUploadedFile('modello.pdf', b'%PDF dummy', content_type='application/pdf')
        self._post_submit(draft, sig_file=sig_file)
        from approvals.models import ApprovalRequest
        ar = ApprovalRequest.objects.get(document_version=draft)
        att = ar.attachments.first()
        self.client.login(username='at_approver', password='pw')
        response = self.client.get(reverse('approval_attachment_download', args=[att.pk]))
        self.assertEqual(response.status_code, 200)

    def test_unassigned_user_cannot_download_attachment(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        draft = self._make_draft()
        sig_file = SimpleUploadedFile('modello.pdf', b'%PDF dummy', content_type='application/pdf')
        self._post_submit(draft, sig_file=sig_file)
        from approvals.models import ApprovalRequest
        ar = ApprovalRequest.objects.get(document_version=draft)
        att = ar.attachments.first()
        self.client.login(username='at_outsider', password='pw')
        response = self.client.get(reverse('approval_attachment_download', args=[att.pk]))
        self.assertEqual(response.status_code, 403)

    def test_approval_detail_shows_attachment_link(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        draft = self._make_draft()
        sig_file = SimpleUploadedFile('modello.pdf', b'%PDF dummy', content_type='application/pdf')
        self._post_submit(draft, sig_file=sig_file)
        from approvals.models import ApprovalRequest
        ar = ApprovalRequest.objects.get(document_version=draft)
        att = ar.attachments.first()
        self.client.login(username='at_approver', password='pw')
        response = self.client.get(reverse('approval_detail', args=[ar.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('approval_attachment_download', args=[att.pk]))
        self.assertContains(response, 'modello.pdf')

    def test_document_detail_shows_attachment_link_in_approval_section(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from approvals.services import approve_version as do_approve
        draft = self._make_draft()
        sig_file = SimpleUploadedFile('modello.pdf', b'%PDF dummy', content_type='application/pdf')
        self._post_submit(draft, sig_file=sig_file)
        from approvals.models import ApprovalRequest
        ar = ApprovalRequest.objects.get(document_version=draft)
        att = ar.attachments.first()
        do_approve(ar, self.approver)
        self.client.login(username='at_approver', password='pw')
        response = self.client.get(reverse('document_detail', args=[self.doc.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('approval_attachment_download', args=[att.pk]))
        self.assertContains(response, 'modello.pdf')


@override_settings(EMAIL_BACKEND=LOCMEM)
class PDFPolicyInFlightWorkflowTests(TestCase):
    """
    TASK-035 — workflow in corso: cambiare Document.requires_approved_pdf
    mentre una richiesta è già in approvazione non deve cambiare le regole
    applicate a quella specifica richiesta (self-freezing via
    representation_pdf_id, non tramite rilettura del flag al momento
    dell'approvazione — vedi approvals/services.py).
    """

    @staticmethod
    def _real_pdf_bytes(text='Contenuto'):
        import io
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        buf = io.BytesIO()
        pdf = canvas.Canvas(buf, pagesize=A4)
        pdf.drawString(50, 800, text)
        pdf.showPage()
        pdf.save()
        return buf.getvalue()

    def setUp(self):
        self.author = User.objects.create_user('inflight-author', password='pw')
        self.approver1 = User.objects.create_user('inflight-approver1', password='pw')
        self.approver2 = User.objects.create_user('inflight-approver2', password='pw')

    def test_flag_disabled_mid_approval_does_not_stop_generation_started_when_enabled(self):
        import shutil
        import tempfile
        temp_media = tempfile.mkdtemp()
        try:
            with self.settings(MEDIA_ROOT=temp_media):
                document = make_document(code='INFLIGHT-001', owner=self.author, requires_approved_pdf=True)
                upload = SimpleUploadedFile('a.pdf', self._real_pdf_bytes(), content_type='application/pdf')
                source = create_document_file(upload, self.author)
                version = create_new_revision(document, self.author, 'A', 1, file=source)
                req = submit_version_for_approval(version, self.author, [self.approver1], approval_policy='all')

                # La policy viene disattivata mentre la richiesta è già IN_APPROVAL.
                document.requires_approved_pdf = False
                document.save(update_fields=['requires_approved_pdf'])

                approve_version(req, self.approver1)
                version.refresh_from_db()
        finally:
            shutil.rmtree(temp_media, ignore_errors=True)

        self.assertIsNotNone(version.approved_pdf)
        self.assertEqual(version.approved_pdf.status, 'generated')

    def test_flag_enabled_mid_approval_does_not_trigger_generation_for_request_started_without_it(self):
        document = make_document(code='INFLIGHT-002', owner=self.author, requires_approved_pdf=False)
        version = create_new_revision(document, self.author, 'A', 1)
        req = submit_version_for_approval(version, self.author, [self.approver1], approval_policy='all')

        # La policy viene attivata mentre la richiesta è già IN_APPROVAL, senza
        # alcun PDF di rappresentazione collegato a questa specifica revisione.
        document.requires_approved_pdf = True
        document.save(update_fields=['requires_approved_pdf'])

        approve_version(req, self.approver1)
        version.refresh_from_db()
        self.assertIsNone(version.approved_pdf)

    def test_flag_toggle_mid_approval_consistent_after_rejection(self):
        document = make_document(code='INFLIGHT-003', owner=self.author, requires_approved_pdf=True)
        version = create_new_revision(document, self.author, 'A', 1, _bypass_ecn_check=True)
        # Nessun file sorgente: il gate non si applica (fuori scope), invio consentito.
        req = submit_version_for_approval(version, self.author, [self.approver1])

        document.requires_approved_pdf = False
        document.save(update_fields=['requires_approved_pdf'])

        reject_version(req, self.approver1, rejection_reason='Non conforme')
        version.refresh_from_db()
        self.assertIsNone(version.approved_pdf)
        self.assertEqual(version.status, DocumentVersion.Status.REJECTED)

    def test_self_freezing_holds_for_any_policy(self):
        import shutil
        import tempfile
        temp_media = tempfile.mkdtemp()
        try:
            with self.settings(MEDIA_ROOT=temp_media):
                document = make_document(code='INFLIGHT-004', owner=self.author, requires_approved_pdf=True)
                upload = SimpleUploadedFile('a.pdf', self._real_pdf_bytes(), content_type='application/pdf')
                source = create_document_file(upload, self.author)
                version = create_new_revision(document, self.author, 'A', 1, file=source)
                req = submit_version_for_approval(
                    version, self.author, [self.approver1, self.approver2], approval_policy='any',
                )

                document.requires_approved_pdf = False
                document.save(update_fields=['requires_approved_pdf'])

                approve_version(req, self.approver1)
                version.refresh_from_db()
        finally:
            shutil.rmtree(temp_media, ignore_errors=True)

        self.assertIsNotNone(version.approved_pdf)
        self.assertEqual(version.approved_pdf.status, 'generated')


@override_settings(EMAIL_BACKEND=LOCMEM)
class SimpleEcnAutoCloseEndToEndTests(TestCase):
    """
    Prova end-to-end (approve_version reale, non il service ECN diretto)
    che la chiusura automatica dell'ECN collegato — standard o semplice
    (requisito aziendale 2026-07-28, generalizza AREA 3) — è indipendente
    dalla policy PDF del documento.
    """

    def setUp(self):
        self.author = User.objects.create_user('e2e-author', password='pw')
        self.approver = User.objects.create_user('e2e-approver', password='pw')

    def _document_with_current_version(self, code, requires_approved_pdf):
        doc = make_document(code=code, owner=self.author, requires_approved_pdf=requires_approved_pdf)
        first_version = create_new_revision(doc, self.author, '00', 0, _bypass_ecn_check=True)
        req = submit_version_for_approval(first_version, self.author, [self.approver])
        approve_version(req, self.approver, send_notifications=False)
        doc.refresh_from_db()
        return doc

    def test_simple_ecn_closes_automatically_after_real_approval_pdf_disabled(self):
        from ecn.models import ChangeNotice
        from ecn.services import create_simple_ecn

        doc = self._document_with_current_version('E2E-ECN-001', requires_approved_pdf=False)
        ecn = create_simple_ecn(
            document=doc, proposed_by=self.author, title='Revisione rapida', send_notifications=False,
        )
        version = create_new_revision(doc, self.author, '01', 1, ecn=ecn, change_summary='Via ECN semplice')
        req = submit_version_for_approval(version, self.author, [self.approver])
        approve_version(req, self.approver, send_notifications=False)

        ecn.refresh_from_db()
        self.assertEqual(ecn.status, ChangeNotice.Status.CLOSED)

    def test_simple_ecn_closes_automatically_after_real_approval_pdf_enabled(self):
        """Stessa prova con il workflow PDF attivo sul documento: le due dimensioni restano indipendenti."""
        from ecn.models import ChangeNotice
        from ecn.services import create_simple_ecn

        doc = self._document_with_current_version('E2E-ECN-002', requires_approved_pdf=True)
        ecn = create_simple_ecn(
            document=doc, proposed_by=self.author, title='Revisione rapida', send_notifications=False,
        )
        version = create_new_revision(doc, self.author, '01', 1, ecn=ecn, change_summary='Via ECN semplice')
        req = submit_version_for_approval(version, self.author, [self.approver])
        # Nessun file sorgente: il gate PDF non si applica (fuori scope), invio consentito comunque.
        approve_version(req, self.approver, send_notifications=False)

        ecn.refresh_from_db()
        self.assertEqual(ecn.status, ChangeNotice.Status.CLOSED)

    def test_standard_ecn_closes_automatically_after_real_approval(self):
        from ecn.models import ChangeNotice
        from ecn.services import create_change_notice

        doc = self._document_with_current_version('E2E-ECN-003', requires_approved_pdf=False)
        ecn = create_change_notice(
            document=doc, proposed_by=self.author, title='ECN standard',
            motivation=ChangeNotice.Motivation.IMPROVEMENT, send_notifications=False,
        )
        ecn.status = ChangeNotice.Status.APPROVED
        ecn.save(update_fields=['status'])
        version = create_new_revision(doc, self.author, '01', 1, ecn=ecn, change_summary='Via ECN standard')
        req = submit_version_for_approval(version, self.author, [self.approver])
        approve_version(req, self.approver, send_notifications=False)

        ecn.refresh_from_db()
        self.assertEqual(ecn.status, ChangeNotice.Status.CLOSED)
        self.assertIn('Rev. 01', ecn.close_notes)

    def test_standard_ecn_closes_with_all_policy_only_on_final_approval(self):
        """La chiusura avviene solo quando la richiesta ALL è davvero completa."""
        from ecn.models import ChangeNotice
        from ecn.services import create_change_notice

        approver2 = User.objects.create_user('e2e-approver2', password='pw')
        doc = self._document_with_current_version('E2E-ECN-ALL', requires_approved_pdf=False)
        ecn = create_change_notice(
            document=doc, proposed_by=self.author, title='ECN standard ALL',
            motivation=ChangeNotice.Motivation.IMPROVEMENT, send_notifications=False,
        )
        ecn.status = ChangeNotice.Status.APPROVED
        ecn.save(update_fields=['status'])
        version = create_new_revision(doc, self.author, '01', 1, ecn=ecn, change_summary='Via ECN standard ALL')
        req = submit_version_for_approval(
            version, self.author, [self.approver, approver2], approval_policy='all',
        )

        approve_version(req, self.approver, send_notifications=False)
        ecn.refresh_from_db()
        self.assertEqual(ecn.status, ChangeNotice.Status.APPROVED)  # ancora in attesa del secondo voto

        approve_version(req, approver2, send_notifications=False)
        ecn.refresh_from_db()
        self.assertEqual(ecn.status, ChangeNotice.Status.CLOSED)

    def test_standard_ecn_closes_with_sequential_policy_only_on_final_approval(self):
        """La chiusura avviene solo quando l'ultimo approvatore SEQUENTIAL ha deciso."""
        from ecn.models import ChangeNotice
        from ecn.services import create_change_notice

        approver2 = User.objects.create_user('e2e-approver3', password='pw')
        doc = self._document_with_current_version('E2E-ECN-SEQ', requires_approved_pdf=False)
        ecn = create_change_notice(
            document=doc, proposed_by=self.author, title='ECN standard SEQUENTIAL',
            motivation=ChangeNotice.Motivation.IMPROVEMENT, send_notifications=False,
        )
        ecn.status = ChangeNotice.Status.APPROVED
        ecn.save(update_fields=['status'])
        version = create_new_revision(doc, self.author, '01', 1, ecn=ecn, change_summary='Via ECN standard SEQ')
        req = submit_version_for_approval(
            version, self.author, [self.approver, approver2], approval_policy='sequential',
        )

        approve_version(req, self.approver, send_notifications=False)
        ecn.refresh_from_db()
        self.assertEqual(ecn.status, ChangeNotice.Status.APPROVED)

        approve_version(req, approver2, send_notifications=False)
        ecn.refresh_from_db()
        self.assertEqual(ecn.status, ChangeNotice.Status.CLOSED)

    def test_standard_ecn_ccb_members_receive_closure_email(self):
        """
        Requisito: alla chiusura automatica dello standard, tutti i membri
        CCB assegnati a QUELLO specifico ECN ricevono l'email di chiusura —
        non un elenco globale di utenti.
        """
        from django.core import mail
        from ecn.models import ChangeNotice
        from ecn.services import configure_ccb, create_change_notice

        ccb_member1 = User.objects.create_user(
            'e2e-ccb1', password='pw', email='ccb1@example.test', first_name='Ccb', last_name='Uno',
        )
        ccb_member2 = User.objects.create_user(
            'e2e-ccb2', password='pw', email='ccb2@example.test', first_name='Ccb', last_name='Due',
        )
        # Utente estraneo: non deve mai ricevere l'email di chiusura di questo ECN.
        stranger = User.objects.create_user('e2e-stranger', password='pw', email='stranger@example.test')

        doc = self._document_with_current_version('E2E-ECN-CCB-MAIL', requires_approved_pdf=False)
        ecn = create_change_notice(
            document=doc, proposed_by=self.author, title='ECN standard con CCB',
            motivation=ChangeNotice.Motivation.IMPROVEMENT, send_notifications=False,
        )
        configure_ccb(ecn, actor=self.author, users=[ccb_member1, ccb_member2], policy='any',
                      send_notifications=False)
        ecn.status = ChangeNotice.Status.APPROVED
        ecn.save(update_fields=['status'])

        version = create_new_revision(doc, self.author, '01', 1, ecn=ecn, change_summary='Via ECN standard')
        req = submit_version_for_approval(version, self.author, [self.approver])

        mail.outbox = []
        approve_version(req, self.approver, send_notifications=False)

        ecn.refresh_from_db()
        self.assertEqual(ecn.status, ChangeNotice.Status.CLOSED)

        sent_to = {addr for m in mail.outbox for addr in m.to}
        self.assertIn(ccb_member1.email, sent_to)
        self.assertIn(ccb_member2.email, sent_to)
        self.assertNotIn(stranger.email, sent_to)

        closure_emails = [m for m in mail.outbox if m.subject == f'[ECN] Chiuso: {ecn.code}']
        self.assertTrue(closure_emails)
        self.assertIn('chiuso automaticamente', closure_emails[0].body.lower())
        self.assertIn('Rev. 01', closure_emails[0].body)
