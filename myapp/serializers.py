from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Patient, DoctorUpload, Center, CenterName, UserProfile, DICOMImage, ReportTemplate

class CenterSerializer(serializers.ModelSerializer):
    center_names = serializers.SerializerMethodField()
    
    class Meta:
        model = Center
        fields = ['id', 'institute_name', 'center_names', 'is_default', 'user']
    
    def get_center_names(self, obj):
        return [cn.name for cn in obj.center_names.all()]

class UserProfileSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source='role.name', read_only=True)
    center_name = serializers.SerializerMethodField(read_only=True)
    institute_name = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = UserProfile
        fields = ['role', 'center', 'role_name', 'center_name', 'institute_name', 
                  'full_name', 'designation', 'qualification', 'contact_number', 'bmdc_reg_no']
    
    def get_center_name(self, obj):
        if obj.center:
            center_name_obj = obj.center.center_names.first()
            return center_name_obj.name if center_name_obj else obj.center.institute_name
        return None
    
    def get_institute_name(self, obj):
        if obj.center:
            return obj.center.institute_name
        return None

class PatientSerializer(serializers.ModelSerializer):
    uploads = serializers.SerializerMethodField()

    class Meta:
        model = Patient
        fields = '__all__'

    def get_uploads(self, obj):
        uploads = DoctorUpload.objects.filter(patient=obj)
        return DoctorUploadSerializer(uploads, many=True).data

class DoctorUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = DoctorUpload
        fields = '__all__'

class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'profile']

class ReportSerializer(serializers.Serializer):
    patient_name = serializers.CharField(max_length=100)
    patient_id = serializers.CharField(max_length=50)
    patient_age = serializers.CharField(max_length=10)
    patient_gender = serializers.ChoiceField(choices=[("M", "Male"), ("F", "Female"), ("O", "Other")])
    exam_date = serializers.DateField()
    referring_doctor = serializers.CharField(max_length=100)
    modality = serializers.CharField(max_length=50)
    exam_type = serializers.CharField(max_length=200)
    report_body = serializers.CharField()
    impression = serializers.CharField()
    doctor_name = serializers.CharField(max_length=100)
    doctor_degree = serializers.CharField(max_length=200)
    doctor_designation = serializers.CharField(max_length=200)
    doctor_institution = serializers.CharField(max_length=200)
    doctor_reg = serializers.CharField(max_length=50)

class DICOMImageSerializer(serializers.ModelSerializer):
    file_size_mb = serializers.SerializerMethodField()
    study_datetime = serializers.SerializerMethodField()
    assigned_doctors_list = serializers.SerializerMethodField()
    age = serializers.SerializerMethodField()
    institute_name = serializers.SerializerMethodField()
    
    class Meta:
        model = DICOMImage
        fields = '__all__' 

    def get_file_size_mb(self, obj):
        return obj.file_size_mb

    def get_study_datetime(self, obj):
        return obj.study_datetime

    def get_assigned_doctors_list(self, obj):
        return obj.assigned_doctors_list
    
    def get_age(self, obj):
        if not obj.patient_birth_date:
            return 0
        
        try:
            from datetime import datetime
            birth_date = datetime.strptime(obj.patient_birth_date, '%Y%m%d')
            today = datetime.now()
            age = today.year - birth_date.year
            if today.month < birth_date.month or (today.month == birth_date.month and today.day < birth_date.day):
                age -= 1
            return max(0, age)
        except (ValueError, TypeError):
            return 0
    
    def get_institute_name(self, obj):
        try:
            center_name_obj = CenterName.objects.filter(name=obj.center_name).first()
            if center_name_obj and center_name_obj.center:
                return center_name_obj.center.institute_name
            
            center = Center.objects.filter(center_names__name=obj.center_name).first()
            if center:
                return center.institute_name
            
            return obj.center_name
        except Exception:
            return obj.center_name

class DICOMImageListSerializer(serializers.ModelSerializer):
    file_size_mb = serializers.SerializerMethodField()
    assigned_doctors_list = serializers.SerializerMethodField()
    age = serializers.SerializerMethodField()
    formatted_study_date = serializers.SerializerMethodField()
    institute_name = serializers.SerializerMethodField()
    
    class Meta:
        model = DICOMImage
        fields = [
            'id', 'center_name', 'institute_name', 'patient_name', 'patient_id', 'patient_sex',
            'study_description', 'series_description', 'modality', 'file_path',
            'file_size_mb', 'assigned_doctors', 'assigned_doctors_list',
            'status', 'reported_by', 'is_emergency', 'age',
            'formatted_study_date', 'created_at'
        ]

    def get_file_size_mb(self, obj):
        return obj.file_size_mb

    def get_assigned_doctors_list(self, obj):
        return obj.assigned_doctors_list
    
    def get_age(self, obj):
        if not obj.patient_birth_date:
            return 0
        
        try:
            from datetime import datetime
            birth_date = datetime.strptime(obj.patient_birth_date, '%Y%m%d')
            today = datetime.now()
            age = today.year - birth_date.year
            if today.month < birth_date.month or (today.month == birth_date.month and today.day < birth_date.day):
                age -= 1
            return max(0, age)
        except (ValueError, TypeError):
            return 0
    
    def get_formatted_study_date(self, obj):
        if not obj.study_date:
            return ''
        
        try:
            from datetime import datetime
            date_obj = datetime.strptime(obj.study_date, '%Y%m%d')
            return date_obj.strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            return obj.study_date
    
    def get_institute_name(self, obj):
        try:
            center_name_obj = CenterName.objects.filter(name=obj.center_name).first()
            if center_name_obj and center_name_obj.center:
                return center_name_obj.center.institute_name
            
            center = Center.objects.filter(center_names__name=obj.center_name).first()
            if center:
                return center.institute_name
            
            return obj.center_name
        except Exception:
            return obj.center_name

class DICOMAssignmentSerializer(serializers.Serializer):
    image_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        help_text="List of DICOM image IDs to assign doctors to"
    )
    doctor_names = serializers.ListField(
        child=serializers.CharField(max_length=200),
        min_length=1,
        help_text="List of doctor names to assign"
    )
    
    def validate_image_ids(self, value):
        existing_ids = set(DICOMImage.objects.filter(id__in=value).values_list('id', flat=True))
        invalid_ids = set(value) - existing_ids
        
        if invalid_ids:
            raise serializers.ValidationError(f"Invalid image IDs: {list(invalid_ids)}")
        
        return value

class DICOMStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[
            ('Not Assigned', 'Not Assigned'),
            ('Unreported', 'Unreported'),
            ('Draft', 'Draft'),
            ('Reviewed', 'Reviewed'),
            ('Reported', 'Reported')
        ],
        help_text="New status for the DICOM image"
    )
    reported_by = serializers.CharField(
        max_length=200,
        required=False,
        allow_blank=True,
        help_text="Name of the doctor who reported"
    )
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Additional notes for the status update"
    )

class ReportTemplateSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    is_admin_template = serializers.SerializerMethodField()
    created_by = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=False,
        allow_null=True
    )
    
    class Meta:
        model = ReportTemplate
        fields = '__all__'
    
    def get_is_admin_template(self, obj):
        return obj.is_admin_template