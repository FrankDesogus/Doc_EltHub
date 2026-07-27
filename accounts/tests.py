import io
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from accounts.forms import MAX_SIGNATURE_BYTES, MAX_SIGNATURE_WIDTH, UserSignatureForm
from accounts.models import UserSignature


def _make_png_bytes(size=(10, 10), mode='RGBA', color=(255, 0, 0, 128)):
    buf = io.BytesIO()
    Image.new(mode, size, color).save(buf, format='PNG')
    return buf.getvalue()


class UserSignatureModelTests(TestCase):

    def test_signature_created_without_image(self):
        user = User.objects.create_user('sigmodel-1', password='pw')
        sig = UserSignature.objects.create(user=user)
        self.assertFalse(sig.image)

    def test_str_uses_full_name_or_username(self):
        user = User.objects.create_user('sigmodel-2', password='pw', first_name='Maria', last_name='Rossi')
        sig = UserSignature.objects.create(user=user)
        self.assertIn('Maria Rossi', str(sig))


class UserSignatureFormTests(TestCase):

    def test_valid_png_accepted(self):
        upload = SimpleUploadedFile('firma.png', _make_png_bytes(), content_type='image/png')
        form = UserSignatureForm(data={}, files={'image': upload})
        self.assertTrue(form.is_valid(), form.errors)

    def test_non_image_rejected(self):
        upload = SimpleUploadedFile('firma.png', b'non e\' un\'immagine', content_type='image/png')
        form = UserSignatureForm(data={}, files={'image': upload})
        self.assertFalse(form.is_valid())

    def test_non_png_image_rejected(self):
        buf = io.BytesIO()
        Image.new('RGB', (10, 10), (0, 0, 0)).save(buf, format='JPEG')
        upload = SimpleUploadedFile('firma.jpg', buf.getvalue(), content_type='image/jpeg')
        form = UserSignatureForm(data={}, files={'image': upload})
        self.assertFalse(form.is_valid())
        self.assertIn('image', form.errors)

    def test_oversized_dimensions_rejected(self):
        upload = SimpleUploadedFile(
            'firma.png',
            _make_png_bytes(size=(MAX_SIGNATURE_WIDTH + 1, 50)),
            content_type='image/png',
        )
        form = UserSignatureForm(data={}, files={'image': upload})
        self.assertFalse(form.is_valid())

    def test_oversized_bytes_rejected(self):
        oversized_content = b'\x00' * (MAX_SIGNATURE_BYTES + 1)
        upload = SimpleUploadedFile('firma.png', oversized_content, content_type='image/png')
        form = UserSignatureForm(data={}, files={'image': upload})
        self.assertFalse(form.is_valid())

    def test_empty_image_is_valid_text_only_fallback(self):
        form = UserSignatureForm(data={}, files={})
        self.assertTrue(form.is_valid(), form.errors)


class SignatureSettingsViewTests(TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.temp_media = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_media, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user('sigview-1', password='pw')

    def test_requires_login(self):
        response = self.client.get(reverse('signature_settings'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_get_creates_signature_profile_on_demand(self):
        self.client.login(username='sigview-1', password='pw')
        self.assertFalse(UserSignature.objects.filter(user=self.user).exists())
        response = self.client.get(reverse('signature_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(UserSignature.objects.filter(user=self.user).exists())

    def test_upload_valid_signature(self):
        self.client.login(username='sigview-1', password='pw')
        upload = SimpleUploadedFile('firma.png', _make_png_bytes(), content_type='image/png')
        with self.settings(MEDIA_ROOT=self.temp_media):
            response = self.client.post(reverse('signature_settings'), {'image': upload})
            self.assertRedirects(response, reverse('signature_settings'))
        sig = UserSignature.objects.get(user=self.user)
        self.assertTrue(sig.image)

    def test_remove_signature(self):
        self.client.login(username='sigview-1', password='pw')
        upload = SimpleUploadedFile('firma.png', _make_png_bytes(), content_type='image/png')
        with self.settings(MEDIA_ROOT=self.temp_media):
            self.client.post(reverse('signature_settings'), {'image': upload})
            response = self.client.post(reverse('signature_settings'), {'remove': '1'})
        self.assertRedirects(response, reverse('signature_settings'))
        sig = UserSignature.objects.get(user=self.user)
        self.assertFalse(sig.image)

    def test_signature_not_publicly_exposed_via_media_url(self):
        """Nessuna URL pubblica: /media/... non deve essere raggiungibile senza login."""
        self.client.login(username='sigview-1', password='pw')
        upload = SimpleUploadedFile('firma.png', _make_png_bytes(), content_type='image/png')
        with self.settings(MEDIA_ROOT=self.temp_media):
            self.client.post(reverse('signature_settings'), {'image': upload})
            sig = UserSignature.objects.get(user=self.user)
            self.client.logout()
            response = self.client.get('/media/' + sig.image.name)
        self.assertNotEqual(response.status_code, 200)
