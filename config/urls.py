from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from accounts.views import signature_settings
from projects.views import archive_project_list
from documents.views import (
    archive_document_detail,
    archive_document_list,
    confirm_representation_pdf_view,
    dashboard,
    download_approved_pdf,
    download_representation_pdf,
    download_version_file,
    edit_version,
    my_drafts,
    regenerate_approved_pdf_view,
    submit_for_approval,
    upload_representation_pdf_view,
    version_detail,
    workspace_my_work,
    workspace_quality,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', dashboard, name='dashboard'),
    path('archivio/', archive_document_list, name='archive_document_list'),
    path('archivio/<int:document_id>/', archive_document_detail, name='archive_document_detail'),
    path('archivio-progetti/', archive_project_list, name='archive_project_list'),
    path('workspace/my-work/', workspace_my_work, name='workspace_my_work'),
    path('workspace/quality/', workspace_quality, name='workspace_quality'),
    path('documents/', include('documents.urls')),
    path('my-drafts/', my_drafts, name='my_drafts'),
    path('versions/<int:version_id>/', version_detail, name='version_detail'),
    path('versions/<int:version_id>/submit/', submit_for_approval, name='version_submit'),
    path('versions/<int:version_id>/edit/', edit_version, name='version_edit'),
    path('versions/<int:version_id>/download/', download_version_file, name='version_download'),
    path('versions/<int:version_id>/pdf/upload/', upload_representation_pdf_view, name='version_pdf_upload'),
    path('versions/<int:version_id>/pdf/confirm/', confirm_representation_pdf_view, name='version_pdf_confirm'),
    path('versions/<int:version_id>/pdf/representation/download/', download_representation_pdf, name='version_representation_pdf_download'),
    path('versions/<int:version_id>/pdf/approved/download/', download_approved_pdf, name='version_approved_pdf_download'),
    path('versions/<int:version_id>/pdf/approved/regenerate/', regenerate_approved_pdf_view, name='version_approved_pdf_regenerate'),
    path('folders/', include('projects.urls')),
    path('projects/', include('projects.project_urls')),
    path('project-revisions/', include('projects.revision_urls')),
    path('approvals/', include('approvals.urls')),
    path('ecn/', include('ecn.urls')),
    path('notifications/', include('notifications.urls', namespace='notifications')),
    path('accounts/login/', auth_views.LoginView.as_view(), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('accounts/signature/', signature_settings, name='signature_settings'),
]
