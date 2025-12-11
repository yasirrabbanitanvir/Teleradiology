from django.db import models
from django.contrib.auth.models import User, Group
from django.utils import timezone
from django.core.exceptions import ValidationError
from PIL import Image
from io import BytesIO
from django.core.files.base import ContentFile


class Center(models.Model):
    institute_name = models.CharField("Institute Name", max_length=100, null=True, blank=True)
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True)
    is_default = models.BooleanField(default=True)

    def __str__(self):
        return self.institute_name or "Unnamed Center"
    
class CenterName(models.Model):
    center = models.ForeignKey(Center, on_delete=models.CASCADE, related_name='center_names')
    name = models.CharField("Center Name", max_length=100)

    def __str__(self):
        return self.name

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True)
    center = models.ForeignKey(Center, on_delete=models.SET_NULL, null=True, blank=True)


    full_name = models.CharField(max_length=255, blank=True, null=True)
    designation = models.CharField(max_length=255, blank=True, null=True)
    qualification = models.CharField(max_length=255, blank=True, null=True)
    contact_number = models.CharField(max_length=20, blank=True, null=True)
    bmdc_reg_no = models.CharField("BMDC Reg. No", max_length=100, blank=True, null=True)
    signature = models.ImageField(upload_to='signatures/', blank=True, null=True)
    biometric_scan = models.FileField(upload_to='biometrics/', blank=True, null=True)
    
    
    def save(self, *args, **kwargs):
        if self.signature:
            img = Image.open(self.signature)
            
            
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            
            
            max_width = 140
            max_height = 60
            
            
            img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
            
            
            output = BytesIO()
            img.save(output, format='PNG', quality=95, optimize=True)
            output.seek(0)
            
            self.signature.save(
                self.signature.name,
                ContentFile(output.read()),
                save=False
            )
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.role.name if self.role else 'No Role'}"
    
    def clean(self):
        
        if self.role and self.role.name.lower() == 'doctor':
            required_fields = ['full_name', 'designation', 'qualification', 'contact_number', 'bmdc_reg_no']
            errors = {}
            
            for field in required_fields:
                if not getattr(self, field):
                    field_name = field.replace('_', ' ').title()
                    errors[field] = f"{field_name} is required for doctors."
            
            if errors:
                raise ValidationError(errors)


class Patient(models.Model):
    name = models.CharField(max_length=255)
    patient_id = models.CharField(max_length=10, unique=True, blank=True)
    age = models.IntegerField()
    sex = models.CharField(max_length=1, choices=[('M', 'Male'), ('F', 'Female')])
    body_part = models.CharField(max_length=255)
    modality = models.CharField(max_length=255)
    center = models.CharField(max_length=255, blank=True)
    institute_name = models.CharField(max_length=255, blank=True)
    scan_datetime = models.DateTimeField()
    locked = models.BooleanField(default=False)
    group = models.CharField(max_length=255, blank=True)  
    reported_by = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-scan_datetime']

    def save(self, *args, **kwargs):
        if not self.patient_id:
            last_patient = Patient.objects.order_by('-patient_id').first()
            if last_patient and last_patient.patient_id.isdigit():
                new_id = int(last_patient.patient_id) + 1
            else:
                new_id = 1001
            self.patient_id = str(new_id)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.patient_id})"

class DoctorUpload(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='uploads')
    dicom_file = models.FileField(upload_to='dicom_files/', blank=True, null=True)
    report_pdf = models.FileField(upload_to='reports/', blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('Not Assigned', 'Not Assigned'),
            ('Unreported', 'Unreported'), 
            ('Draft', 'Draft'),
            ('Reviewed', 'Reviewed'),
            ('Reported', 'Reported')
        ],
        default='Not Assigned'
    )

    def __str__(self):
        return f"Upload for {self.patient.name} at {self.uploaded_at}"

class DICOMImage(models.Model):

    report_file = models.FileField(upload_to='reports/', null=True, blank=True)
    report_content = models.TextField(blank=True, null=True)
    
    center_name = models.CharField(max_length=200, blank=False, default='', db_index=True,
                                  help_text="Name of the imaging center")
    patient_name = models.CharField(max_length=200, blank=True, default='')
    patient_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    patient_birth_date = models.CharField(max_length=8, blank=True, null=True)  
    patient_sex = models.CharField(max_length=10, blank=True, default='')
    study_instance_uid = models.CharField(max_length=64, blank=True, default='', db_index=True)
    study_date = models.CharField(max_length=8, blank=True, null=True)  
    study_time = models.CharField(max_length=14, blank=True, null=True)  
    study_description = models.CharField(max_length=200, blank=True, default='')
    referring_physician = models.CharField(max_length=200, blank=True, default='')
    series_instance_uid = models.CharField(max_length=64, blank=True, default='', db_index=True)
    series_number = models.CharField(max_length=12, blank=True, null=True)
    series_description = models.CharField(max_length=200, blank=True, default='')
    modality = models.CharField(max_length=16, blank=True, default='', db_index=True)
    sop_instance_uid = models.CharField(max_length=64, unique=True, db_index=True)
    instance_number = models.CharField(max_length=12, blank=True, null=True)
    file_path = models.CharField(max_length=500)
    file_size = models.BigIntegerField(default=0)
    image_orientation = models.TextField(blank=True, default='')  
    image_position = models.TextField(blank=True, default='')     
    pixel_spacing = models.TextField(blank=True, default='')      
    slice_thickness = models.FloatField(blank=True, null=True)
    assigned_doctors = models.CharField(max_length=500, blank=True, default='') 
    status = models.CharField(
        max_length=20,
        choices=[
            ('Not Assigned', 'Not Assigned'),
            ('Unreported', 'Unreported'),
            ('Draft', 'Draft'),
            ('Reviewed', 'Reviewed'),
            ('Reported', 'Reported')
        ],
        default='Not Assigned',
        db_index=True
    )
    reported_by = models.CharField(max_length=200, blank=True, default='')
    is_emergency = models.BooleanField(default=False, db_index=True)
    
    
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'dicom_images'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['center_name']),
            models.Index(fields=['center_name', 'patient_id']),
            models.Index(fields=['center_name', 'study_instance_uid']),
            models.Index(fields=['patient_id', 'study_instance_uid']),
            models.Index(fields=['study_instance_uid', 'series_instance_uid']),
            models.Index(fields=['modality', 'study_date']),
            models.Index(fields=['status', 'assigned_doctors']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"[{self.center_name}] {self.patient_name} - {self.study_description} ({self.modality})"
    
    @property
    def file_size_mb(self):
        return round(self.file_size / (1024 * 1024), 2) if self.file_size else 0
    
    @property
    def study_datetime(self):
        if self.study_date and self.study_time:
            return f"{self.study_date} {self.study_time}"
        return self.study_date or ''
    
    @property
    def assigned_doctors_list(self):
        if not self.assigned_doctors:
            return []
        return [doctor.strip() for doctor in self.assigned_doctors.split(',') if doctor.strip()]
    
    def assign_doctor(self, doctor_name):
        current_doctors = self.assigned_doctors_list
        if doctor_name not in current_doctors:
            current_doctors.append(doctor_name)
            self.assigned_doctors = ', '.join(current_doctors)
            if self.status == 'Not Assigned':
                self.status = 'Unreported'
            self.save()
    
    def remove_doctor(self, doctor_name):
        current_doctors = self.assigned_doctors_list
        if doctor_name in current_doctors:
            current_doctors.remove(doctor_name)
            self.assigned_doctors = ', '.join(current_doctors)
            if not current_doctors:
                self.status = 'Not Assigned'
            self.save()
    
    @classmethod
    def get_centers(cls):
        from django.db.models import Count
        return cls.objects.values('center_name').annotate(
            image_count=Count('id')
        ).order_by('center_name')
    
    @classmethod
    def get_center_stats(cls, center_name):
        from django.db.models import Count, Sum
        center_images = cls.objects.filter(center_name=center_name)
        
        stats = center_images.aggregate(
            total_images=Count('id'),
            total_patients=Count('patient_id', distinct=True),
            total_studies=Count('study_instance_uid', distinct=True),
            total_size=Sum('file_size')
        )
        
        return {
            'center_name': center_name,
            'total_images': stats['total_images'] or 0,
            'total_patients': stats['total_patients'] or 0,
            'total_studies': stats['total_studies'] or 0,
            'total_size_bytes': stats['total_size'] or 0,
            'total_size_mb': round((stats['total_size'] or 0) / (1024 * 1024), 2)
        }

class ReportTemplate(models.Model):
    body_part = models.CharField("Body Part", max_length=100)
    template_name = models.CharField("Template Name", max_length=200)
    content = models.TextField("Template Content")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField("Active", default=True)
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='report_templates'
    )
    
    class Meta:
        ordering = ['body_part', 'template_name']
        verbose_name = "Report Template"
        verbose_name_plural = "Report Templates"
    
    def __str__(self):
        return f"{self.body_part} - {self.template_name}"
    
    @property
    def is_admin_template(self):
        if not self.created_by:
            return True
        try:
            profile = UserProfile.objects.filter(user=self.created_by).first()
            return profile and profile.role and profile.role.name == 'Admin'
        except:
            return self.created_by.is_superuser