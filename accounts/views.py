import base64

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from accounts.forms import UserSignatureForm
from accounts.models import UserSignature


@login_required
def signature_settings(request):
    signature, _ = UserSignature.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        if request.POST.get('remove') == '1':
            if signature.image:
                signature.image.delete(save=False)
                signature.image = None
                signature.save(update_fields=['image', 'updated_at'])
            messages.success(request, 'Firma visiva rimossa. Verrà usato solo il nome testuale.')
            return redirect('signature_settings')

        form = UserSignatureForm(request.POST, request.FILES, instance=signature)
        if form.is_valid():
            form.save()
            messages.success(request, 'Firma visiva aggiornata.')
            return redirect('signature_settings')
    else:
        form = UserSignatureForm(instance=signature)

    signature_data_uri = None
    if signature.image:
        with signature.image.open('rb') as fh:
            encoded = base64.b64encode(fh.read()).decode('ascii')
        signature_data_uri = f'data:image/png;base64,{encoded}'

    return render(request, 'accounts/signature_settings.html', {
        'form': form,
        'signature': signature,
        'signature_data_uri': signature_data_uri,
    })
