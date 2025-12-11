from django.contrib import admin
from django.urls import path
from django.shortcuts import redirect
from django.utils.html import format_html
from django.http import HttpResponseRedirect
from .models import Center, Patient, DoctorUpload, UserProfile, DICOMImage, CenterName, ReportTemplate


admin.site.register(Patient)
admin.site.register(DoctorUpload)
admin.site.register(UserProfile)

class CenterNameInline(admin.TabularInline):
    model = CenterName
    extra = 3

@admin.register(Center)
class CenterAdmin(admin.ModelAdmin):
    list_display = ('institute_name', 'user', 'is_default')
    inlines = [CenterNameInline]

@admin.register(DICOMImage)
class DICOMImageAdmin(admin.ModelAdmin):
    list_display = (
        'center_name', 'patient_name', 'patient_id', 
        'modality', 'study_description', 'file_size_mb', 'created_at'
    )
    list_filter = ('center_name', 'modality', 'study_date', 'created_at')
    search_fields = ('center_name', 'patient_name', 'patient_id', 'study_instance_uid')
    ordering = ('-created_at',)

@admin.register(ReportTemplate)
class ReportTemplateAdmin(admin.ModelAdmin):
    
    def has_module_permission(self, request):
        return True
    
    def has_add_permission(self, request):
        return HttpResponseRedirect('/api/template-manager/')
    
    def has_change_permission(self, request, obj=None):
        return True
    
    def changelist_view(self, request, extra_context=None):
        return HttpResponseRedirect('/api/template-manager/')
    
    def add_view(self, request, form_url='', extra_context=None):
        return HttpResponseRedirect('/api/template-manager/')
    
    def change_view(self, request, object_id, form_url='', extra_context=None):
        return HttpResponseRedirect('/api/template-manager/')

admin.site.site_header = "Telerad PACS Administration"
admin.site.site_title = "PACS Admin"
admin.site.index_title = "DICOM Data Management"