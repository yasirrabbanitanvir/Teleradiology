from rest_framework import viewsets, status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated, BasePermission, AllowAny
from rest_framework.decorators import action, api_view, permission_classes, authentication_classes
from rest_framework.pagination import PageNumberPagination
from django.contrib.auth import authenticate
from django.contrib.auth.models import User, Group
from django.contrib.auth.hashers import make_password
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from django.http import FileResponse, Http404, JsonResponse, HttpResponse
from django.shortcuts import render
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.db.models import Q, Count, Sum
from django_filters import rest_framework as filters
from pathlib import Path
import os
import mimetypes
import datetime
import logging
import json
import pydicom
from .models import (
    Patient, DoctorUpload, UserProfile, Center, DICOMImage, ReportTemplate
)
from .serializers import (
    PatientSerializer, DoctorUploadSerializer, UserSerializer, 
    CenterSerializer, ReportSerializer, DICOMImageSerializer, 
    ReportTemplateSerializer
)
from rest_framework import status

logger = logging.getLogger(__name__)


class RoleBasedPermission(BasePermission):
    allowed_roles = []

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        profile = UserProfile.objects.filter(user=request.user).first()
        if not profile:
            return request.user.is_superuser
        return profile.role.name in self.allowed_roles

class AdminPermission(RoleBasedPermission):
    allowed_roles = ['Admin']

class DoctorPermission(RoleBasedPermission):
    allowed_roles = ['Doctor']

class SubAdminPermission(RoleBasedPermission):
    allowed_roles = ['SubAdmin']

class CenterPermission(RoleBasedPermission):
    allowed_roles = ['Center']

class AdminOrSubAdminPermission(RoleBasedPermission):
    allowed_roles = ['Admin', 'SubAdmin']

class PatientViewSet(viewsets.ModelViewSet):
    queryset = Patient.objects.all()
    serializer_class = PatientSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def by_patient_id(self, request):
        patient_id = request.query_params.get('patient_id')
        if patient_id:
            patient = Patient.objects.filter(patient_id=patient_id).first()
            if patient:
                serializer = self.get_serializer(patient)
                return Response(serializer.data)
        return Response({"detail": "Patient not found"}, status=status.HTTP_404_NOT_FOUND)

class DoctorUploadViewSet(viewsets.ModelViewSet):
    queryset = DoctorUpload.objects.all()
    serializer_class = DoctorUploadSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, DoctorPermission | CenterPermission]

    def get_queryset(self):
        queryset = super().get_queryset()
        patient_id = self.request.query_params.get('patient')
        if patient_id:
            queryset = queryset.filter(patient_id=patient_id)
        return queryset

@method_decorator(csrf_exempt, name='dispatch')
class CustomLoginView(APIView):
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            token, created = Token.objects.get_or_create(user=user)
            profile = UserProfile.objects.filter(user=user).first()
            role = profile.role.name if profile else ('Admin' if user.is_superuser else 'Unknown')
            redirect_url = "/"
            center_name = None
            institute_name = None
            
            if role == 'Admin':
                redirect_url = "/admin/"
            elif role == 'SubAdmin':
                redirect_url = "/static/index.html"
            elif role == 'Center':
                redirect_url = "/static/institute.html"
                
                if profile and profile.center:
                    center_obj = profile.center
                    institute_name = center_obj.institute_name
                    center_name_obj = center_obj.center_names.first()
                    center_name = center_name_obj.name if center_name_obj else None
                else:
                    center = Center.objects.filter(user=user).first()
                    if center:
                        institute_name = center.institute_name
                        center_name_obj = center.center_names.first()
                        center_name = center_name_obj.name if center_name_obj else None
                        
                        if profile:
                            profile.center = center
                            profile.save()
                        
            elif role == 'Doctor':
                redirect_url = "/static/doctor.html"
                
            return Response({
                "token": token.key,
                "redirect": redirect_url,
                "role": role,
                "center_name": center_name,
                "institute_name": institute_name
            })
        return Response({"error": "Invalid credentials"}, status=401)

class UserViewSet(viewsets.ViewSet):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, AdminPermission]

    def list(self, request):
        users = User.objects.all()
        serializer = UserSerializer(users, many=True, context={'request': request})
        return Response(serializer.data)

    def create(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        role = request.data.get('role')
        center_id = request.data.get('center')

        if User.objects.filter(username=username).exists():
            return Response({"detail": "Username already exists"}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.create(
            username=username,
            password=make_password(password)
        )

        group = Group.objects.get(name=role)
        profile = UserProfile.objects.create(user=user, role=group)

        if role == 'Center' and center_id:
            center = Center.objects.get(id=center_id)
            profile.center = center
            profile.save()
            center.user = user
            center.save()

        return Response({"detail": "User created successfully"}, status=status.HTTP_201_CREATED)

    def destroy(self, request, pk=None):
        try:
            user = User.objects.get(pk=pk)
            user.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except User.DoesNotExist:
            return Response({"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND)

class CenterViewSet(viewsets.ModelViewSet):
    queryset = Center.objects.all()
    serializer_class = CenterSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, AdminPermission]


def serve_dicom(request, filename):
    file_path = os.path.join(settings.MEDIA_ROOT, filename)
    if not os.path.exists(file_path):
        raise Http404("DICOM file not found")

    response = FileResponse(open(file_path, "rb"), content_type="application/dicom")
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response['Access-Control-Max-Age'] = '1000'
    response['Access-Control-Allow-Headers'] = 'X-Requested-With, Content-Type'
    
    return response


def extract_dicom_metadata(ds):
    metadata = {}
    
    def safe_get_attr(ds, attr, default=''):
        try:
            if not hasattr(ds, attr):
                return default
                
            value = getattr(ds, attr)
            
            if value is None:
                return default
                
            if hasattr(value, 'original_string'):
                try:
                    return str(value)
                except UnicodeDecodeError:
                    for encoding in ['latin-1', 'iso-8859-1', 'cp1252', 'ascii']:
                        try:
                            if isinstance(value.original_string, bytes):
                                return value.original_string.decode(encoding, errors='replace')
                            return str(value)
                        except:
                            continue
                    return default
                except Exception:
                    return default
            
            if isinstance(value, (list, tuple)):
                try:
                    return [str(item) for item in value]
                except:
                    return default
            
            if hasattr(value, 'alphabetic'):
                try:
                    return str(value.alphabetic) if value.alphabetic else default
                except UnicodeDecodeError:
                    return value.alphabetic.decode('latin-1', errors='replace') if value.alphabetic else default
                except:
                    return default
                    
            if isinstance(value, bytes):
                if attr in ['PatientName', 'PatientID', 'StudyDescription', 'SeriesDescription']:
                    for encoding in ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252', 'ascii']:
                        try:
                            return value.decode(encoding, errors='replace')
                        except UnicodeDecodeError:
                            continue
                    return default
                else:
                    return default
            
            try:
                return str(value)
            except UnicodeDecodeError:
                if hasattr(value, 'encode'):
                    return value.encode('latin-1', errors='replace').decode('latin-1')
                return default
                
        except Exception as e:
            logger.warning(f"Error extracting {attr}: {str(e)}")
            return default
    
    metadata['patient_name'] = safe_get_attr(ds, 'PatientName', '')
    metadata['patient_id'] = safe_get_attr(ds, 'PatientID', '')
    metadata['patient_birth_date'] = safe_get_attr(ds, 'PatientBirthDate', '')
    metadata['patient_sex'] = safe_get_attr(ds, 'PatientSex', '')
    
    metadata['study_instance_uid'] = safe_get_attr(ds, 'StudyInstanceUID', '')
    metadata['study_date'] = safe_get_attr(ds, 'StudyDate', '')
    metadata['study_time'] = safe_get_attr(ds, 'StudyTime', '')
    metadata['study_description'] = safe_get_attr(ds, 'StudyDescription', '')
    metadata['referring_physician'] = safe_get_attr(ds, 'ReferringPhysicianName', '')
    
    metadata['series_instance_uid'] = safe_get_attr(ds, 'SeriesInstanceUID', '')
    metadata['series_number'] = safe_get_attr(ds, 'SeriesNumber', '')
    metadata['series_description'] = safe_get_attr(ds, 'SeriesDescription', '')
    metadata['modality'] = safe_get_attr(ds, 'Modality', '')
    
    metadata['sop_instance_uid'] = safe_get_attr(ds, 'SOPInstanceUID', '')
    metadata['instance_number'] = safe_get_attr(ds, 'InstanceNumber', '')
    
    
    try:
        if hasattr(ds, 'ImageOrientationPatient') and ds.ImageOrientationPatient:
            orient = ds.ImageOrientationPatient
            if hasattr(orient, '__iter__'):
                metadata['image_orientation'] = [float(x) for x in orient]
            else:
                metadata['image_orientation'] = str(orient)
    except:
        metadata['image_orientation'] = ''
        
    try:
        if hasattr(ds, 'ImagePositionPatient') and ds.ImagePositionPatient:
            pos = ds.ImagePositionPatient
            if hasattr(pos, '__iter__'):
                metadata['image_position'] = [float(x) for x in pos]
            else:
                metadata['image_position'] = str(pos)
    except:
        metadata['image_position'] = ''
        
    try:
        if hasattr(ds, 'PixelSpacing') and ds.PixelSpacing:
            spacing = ds.PixelSpacing
            if hasattr(spacing, '__iter__'):
                metadata['pixel_spacing'] = [float(x) for x in spacing]
            else:
                metadata['pixel_spacing'] = str(spacing)
    except:
        metadata['pixel_spacing'] = ''
        
    try:
        if hasattr(ds, 'SliceThickness') and ds.SliceThickness:
            metadata['slice_thickness'] = float(ds.SliceThickness)
    except:
        metadata['slice_thickness'] = None
        
    return metadata

@csrf_exempt
@require_http_methods(["POST"])
def receive_dicom_data(request):
    try:
        logger.info("Received DICOM data request")
        
        if 'dicom_file' not in request.FILES:
            logger.error("No DICOM file in request")
            return JsonResponse({
                'success': False,
                'error': 'No DICOM file provided'
            }, status=400)
        
        center_name = request.POST.get('center_name', '').strip()
        if not center_name:
            logger.error("No center name provided")
            return JsonResponse({
                'success': False,
                'error': 'Center name is required'
            }, status=400)
        
        dicom_file = request.FILES['dicom_file']
        
        try:
            file_content = dicom_file.read()
            ds = pydicom.dcmread(
                pydicom.filebase.DicomBytesIO(file_content),
                force=True
            )
            
            if not hasattr(ds, 'SpecificCharacterSet'):
                ds.SpecificCharacterSet = 'ISO_IR 100'
            
        except Exception as e:
            logger.error(f"Error reading DICOM file: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': f'Invalid DICOM file: {str(e)}'
            }, status=400)
        
        try:
            metadata = extract_dicom_metadata(ds)
        except Exception as e:
            logger.error(f"Error extracting metadata: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': f'Error processing DICOM metadata: {str(e)}'
            }, status=500)
        
        try:
            center_dir = center_name.replace(' ', '_').replace('/', '_').replace('\\', '_')
            filename = f"{center_dir}/{metadata.get('sop_instance_uid', 'unknown')}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.dcm"
            file_path = default_storage.save(filename, ContentFile(file_content))
            full_path = os.path.join(settings.MEDIA_ROOT, file_path)
        except Exception as e:
            logger.error(f"Error saving file: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': f'Error saving file: {str(e)}'
            }, status=500)
        
        try:
            dicom_image = DICOMImage.objects.create(
                center_name=center_name[:200],
                patient_name=metadata.get('patient_name', '')[:200],
                patient_id=metadata.get('patient_id', '')[:64],
                patient_birth_date=metadata.get('patient_birth_date', '') or None,
                patient_sex=metadata.get('patient_sex', '')[:10],
                study_instance_uid=metadata.get('study_instance_uid', '')[:64],
                study_date=metadata.get('study_date', '') or None,
                study_time=metadata.get('study_time', '') or None,
                study_description=metadata.get('study_description', '')[:200],
                referring_physician=metadata.get('referring_physician', '')[:200],
                series_instance_uid=metadata.get('series_instance_uid', '')[:64],
                series_number=metadata.get('series_number', '') or None,
                series_description=metadata.get('series_description', '')[:200],
                modality=metadata.get('modality', '')[:16],
                sop_instance_uid=metadata.get('sop_instance_uid', '')[:64],
                instance_number=metadata.get('instance_number', '') or None,
                file_path=file_path,
                file_size=len(file_content),
                image_orientation=json.dumps(metadata.get('image_orientation', [])) if metadata.get('image_orientation') else '',
                image_position=json.dumps(metadata.get('image_position', [])) if metadata.get('image_position') else '',
                pixel_spacing=json.dumps(metadata.get('pixel_spacing', [])) if metadata.get('pixel_spacing') else '',
                slice_thickness=metadata.get('slice_thickness'),
                status='Not Assigned',
                assigned_doctors='',
                reported_by='',
                is_emergency=False
            )
            
            logger.info(f"Successfully saved DICOM image for {center_name}: {dicom_image.id}")
            
        except Exception as e:
            logger.error(f"Error saving to database: {str(e)}")
            try:
                if os.path.exists(full_path):
                    os.remove(full_path)
            except:
                pass
            return JsonResponse({
                'success': False,
                'error': f'Error saving to database: {str(e)}'
            }, status=500)
        
        return JsonResponse({
            'success': True,
            'message': 'DICOM file processed successfully',
            'image_id': dicom_image.id,
            'filename': os.path.basename(filename),
            'center_name': center_name
        })
        
    except Exception as e:
        logger.error(f"Unexpected error in receive_dicom_data: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Server error: {str(e)}'
        }, status=500)

class PatientPagination:
    def __init__(self, page_size=10):
        self.page_size = page_size
    
    def paginate_patients(self, queryset, page):
        patients_dict = {}
        
        for image in queryset:
            patient_id = image.patient_id or 'Unknown'
            if patient_id not in patients_dict:
                patients_dict[patient_id] = {
                    'patient_id': patient_id,
                    'patient_name': image.patient_name,
                    'age': getattr(image, 'age', 0),
                    'patient_sex': image.patient_sex,
                    'images': [],
                    'latest_created_at': image.created_at
                }
            patients_dict[patient_id]['images'].append(image)
            if image.created_at and (not patients_dict[patient_id]['latest_created_at'] or 
                                    image.created_at > patients_dict[patient_id]['latest_created_at']):
                patients_dict[patient_id]['latest_created_at'] = image.created_at
        
        sorted_patients = sorted(
            patients_dict.values(), 
            key=lambda x: x['latest_created_at'] if x['latest_created_at'] else datetime.datetime.min.replace(tzinfo=datetime.timezone.utc),
            reverse=True
        )
        
        unique_patients = sorted_patients
        total_patients = len(unique_patients)
        total_pages = (total_patients + self.page_size - 1) // self.page_size
        
        start_idx = (page - 1) * self.page_size
        end_idx = start_idx + self.page_size
        current_page_patients = unique_patients[start_idx:end_idx]
        
        result_images = []
        for patient_data in current_page_patients:
            sorted_images = sorted(
                patient_data['images'], 
                key=lambda img: img.created_at if img.created_at else datetime.datetime.min.replace(tzinfo=datetime.timezone.utc),
                reverse=True
            )
            result_images.extend(sorted_images)
        
        return {
            'results': result_images,
            'count': total_patients,
            'total_pages': total_pages,
            'current_page': page,
            'patients_on_page': len(current_page_patients)
        }

class DICOMImageViewSet(viewsets.ModelViewSet):
    queryset = DICOMImage.objects.all()
    serializer_class = DICOMImageSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        center_name = self.request.query_params.get('center_name')
        if center_name:
            queryset = queryset.filter(center_name=center_name)
        return queryset.order_by('-created_at')

    def list(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 10))
        
        paginator = PatientPagination(page_size)
        paginated_data = paginator.paginate_patients(queryset, page)
        
        serializer = self.get_serializer(paginated_data['results'], many=True)
        
        return Response({
            'results': serializer.data,
            'count': paginated_data['count'],
            'total_pages': paginated_data['total_pages'],
            'current_page': paginated_data['current_page'],
            'patients_on_page': paginated_data['patients_on_page']
        })

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def assign_doctors(self, request):
        try:
            image_ids = request.data.get('image_ids', [])
            doctor_names = request.data.get('doctor_names', [])
            
            if not image_ids or not doctor_names:
                return Response({
                    'success': False,
                    'error': 'image_ids and doctor_names are required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            images = DICOMImage.objects.filter(id__in=image_ids)
            if len(images) != len(image_ids):
                return Response({
                    'success': False,
                    'error': 'Some image IDs not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            updated_count = 0
            for image in images:
                current_doctors = image.assigned_doctors_list
                
                for doctor_name in doctor_names:
                    if doctor_name not in current_doctors:
                        current_doctors.append(doctor_name)
                
                image.assigned_doctors = ', '.join(current_doctors)
                
                if image.status == 'Not Assigned':
                    image.status = 'Unreported'
                
                image.save()
                updated_count += 1
            
            return Response({
                'success': True,
                'message': f'Successfully assigned doctors to {updated_count} images',
                'updated_images': updated_count
            })
            
        except Exception as e:
            logger.error(f"Error assigning doctors: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['patch'], permission_classes=[IsAuthenticated])
    def update_status(self, request, pk=None):
        try:
            image = self.get_object()
            new_status = request.data.get('status')
            reported_by = request.data.get('reported_by', '')
            report_content = request.data.get('report_content', '')
            
            if not new_status:
                return Response({
                    'success': False,
                    'error': 'status is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            valid_statuses = ['Not Assigned', 'Unreported', 'Draft', 'Reviewed', 'Reported']
            if new_status not in valid_statuses:
                return Response({
                    'success': False,
                    'error': f'Invalid status. Valid options: {valid_statuses}'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            image.status = new_status
            if reported_by:
                image.reported_by = reported_by
            if report_content:
                image.report_content = report_content
            image.save()
            
            return Response({
                'success': True,
                'message': 'Status and report updated successfully',
                'image': DICOMImageSerializer(image).data
            })
            
        except Exception as e:
            logger.error(f"Error updating status: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], url_path='by_doctor', url_name='by_doctor')
    def by_doctor(self, request):
        doctor_name = request.query_params.get('doctor_name')
        if not doctor_name:
            return Response({
                'success': False,
                'error': 'doctor_name parameter is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        images = DICOMImage.objects.filter(
            assigned_doctors__icontains=doctor_name
        ).order_by('-created_at')
        
        serializer = self.get_serializer(images, many=True)
        return Response({
            'success': True,
            'images': serializer.data,
            'count': images.count()
        })
    

    @action(detail=False, methods=['post'])
    def remove_single_doctor(self, request):
        try:
            image_id = request.data.get('image_id')
            doctor_name = request.data.get('doctor_name')
            
            dicom_image = self.get_queryset().get(id=image_id)
            
            assigned_doctors = dicom_image.assigned_doctors.split(',') if dicom_image.assigned_doctors else []
            assigned_doctors = [d.strip() for d in assigned_doctors]
            
            if doctor_name in assigned_doctors:
                assigned_doctors.remove(doctor_name)
                dicom_image.assigned_doctors = ','.join(assigned_doctors)
                dicom_image.save()
                
                return Response({'success': True})
            else:
                return Response({'success': False, 'error': 'Doctor not found'}, status=400)
                
        except Exception as e:
            return Response({'success': False, 'error': str(e)}, status=500)

def get_studies(request):
    try:
        center_name = request.GET.get('center_name', '')
        queryset = DICOMImage.objects.all()
        
        if center_name:
            queryset = queryset.filter(center_name=center_name)
        
        studies = queryset.values(
            'study_instance_uid',
            'patient_name', 
            'patient_id',
            'study_date',
            'study_description',
            'modality',
            'center_name',
            'status',
            'assigned_doctors',
            'is_emergency'
        ).annotate(image_count=Count('id')).distinct('study_instance_uid')
        
        return JsonResponse({
            'success': True,
            'studies': list(studies)
        })
    except Exception as e:
        logger.error(f"Error getting studies: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@csrf_exempt
def get_studies_grouped(request):
    try:
        center_name = request.GET.get('center_name', '')
        patient_name = request.GET.get('patient_name', '')
        patient_id = request.GET.get('patient_id', '')
        
        queryset = DICOMImage.objects.all()
        
        if center_name:
            queryset = queryset.filter(center_name=center_name)
        if patient_name:
            queryset = queryset.filter(patient_name__icontains=patient_name)
        if patient_id:
            queryset = queryset.filter(patient_id__icontains=patient_id)
        
        studies_dict = {}
        for image in queryset.order_by('study_instance_uid', 'series_number', 'instance_number'):
            study_uid = image.study_instance_uid
            if study_uid not in studies_dict:
                studies_dict[study_uid] = {
                    'study_instance_uid': study_uid,
                    'patient_name': image.patient_name,
                    'patient_id': image.patient_id,
                    'patient_birth_date': image.patient_birth_date,
                    'patient_sex': image.patient_sex,
                    'study_date': image.study_date,
                    'study_description': image.study_description,
                    'modality': image.modality,
                    'center_name': image.center_name,
                    'status': image.status,
                    'assigned_doctors': image.assigned_doctors,
                    'is_emergency': image.is_emergency,
                    'images': [],
                    'image_count': 0
                }
            
            studies_dict[study_uid]['images'].append({
                'id': image.id,
                'sop_instance_uid': image.sop_instance_uid,
                'instance_number': image.instance_number,
                'series_description': image.series_description,
                'file_path': image.file_path,
                'file_size': image.file_size
            })
            studies_dict[study_uid]['image_count'] += 1
        
        studies_list = list(studies_dict.values())
        
        return JsonResponse({
            'success': True,
            'studies': studies_list
        })
    except Exception as e:
        logger.error(f"Error getting grouped studies: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

def get_centers(request):
    try:
        centers = DICOMImage.get_centers()
        center_list = []
        
        for center in centers:
            center_stats = DICOMImage.get_center_stats(center['center_name'])
            center_list.append(center_stats)
        
        return JsonResponse({
            'success': True,
            'centers': center_list
        })
    except Exception as e:
        logger.error(f"Error getting centers: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

def get_center_detail(request, center_name):
    try:
        center_stats = DICOMImage.get_center_stats(center_name)
        
        recent_images = DICOMImage.objects.filter(center_name=center_name).order_by('-created_at')[:10]
        
        images_data = []
        for image in recent_images:
            images_data.append({
                'id': image.id,
                'patient_name': image.patient_name,
                'patient_id': image.patient_id,
                'study_date': image.study_date,
                'study_description': image.study_description,
                'modality': image.modality,
                'file_size_mb': image.file_size_mb,
                'status': image.status,
                'assigned_doctors': image.assigned_doctors_list,
                'created_at': image.created_at.isoformat() if image.created_at else None
            })
        
        return JsonResponse({
            'success': True,
            'center_stats': center_stats,
            'recent_images': images_data
        })
    except Exception as e:
        logger.error(f"Error getting center detail: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

def get_study_detail(request, study_id):
    try:
        images = DICOMImage.objects.filter(id=study_id)
        if not images.exists():
            return JsonResponse({
                'success': False,
                'error': 'Study not found'
            }, status=404)
        
        study_data = []
        for image in images:
            study_data.append({
                'id': image.id,
                'center_name': image.center_name,
                'patient_name': image.patient_name,
                'patient_id': image.patient_id,
                'study_date': image.study_date,
                'study_description': image.study_description,
                'series_description': image.series_description,
                'modality': image.modality,
                'instance_number': image.instance_number,
                'file_size': image.file_size,
                'status': image.status,
                'assigned_doctors': image.assigned_doctors_list,
                'created_at': image.created_at
            })
        
        return JsonResponse({
            'success': True,
            'study': study_data
        })
    except Exception as e:
        logger.error(f"Error getting study detail: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

def get_study_images(request, study_uid):
    try:
        images = DICOMImage.objects.filter(study_instance_uid=study_uid).order_by('series_number', 'instance_number')
        
        image_list = []
        for image in images:
            image_list.append({
                'id': image.id,
                'center_name': image.center_name,
                'sop_instance_uid': image.sop_instance_uid,
                'instance_number': image.instance_number,
                'series_description': image.series_description,
                'file_path': image.file_path,
                'file_size': image.file_size,
                'status': image.status,
                'assigned_doctors': image.assigned_doctors_list
            })
        
        return JsonResponse({
            'success': True,
            'images': image_list
        })
    except Exception as e:
        logger.error(f"Error getting study images: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

def get_stats(request):
    try:
        center_name = request.GET.get('center_name', '')
        
        if center_name:
            stats = DICOMImage.get_center_stats(center_name)
        else:
            from django.db.models import Count, Sum
            
            total_images = DICOMImage.objects.count()
            total_studies = DICOMImage.objects.values('study_instance_uid').distinct().count()
            total_patients = DICOMImage.objects.values('patient_id').distinct().count()
            total_centers = DICOMImage.objects.values('center_name').distinct().count()
            
            status_counts = DICOMImage.objects.values('status').annotate(count=Count('id'))
            
            total_size = DICOMImage.objects.aggregate(total=Sum('file_size'))['total'] or 0
            
            stats = {
                'total_images': total_images,
                'total_studies': total_studies,
                'total_patients': total_patients,
                'total_centers': total_centers,
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2) if total_size else 0,
                'status_breakdown': {item['status']: item['count'] for item in status_counts}
            }
        
        return JsonResponse({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

def api_info(request):
    return JsonResponse({
        'success': True,
        'message': 'Telerad PACS API with Center Organization and Doctor Assignment',
        'version': '2.0',
        'endpoints': {
            'receive_dicom': '/api/dicom/receive/',
            'get_studies': '/api/studies/',
            'get_studies_grouped': '/api/studies-grouped/',
            'get_centers': '/api/centers/',
            'get_center_detail': '/api/centers/<center_name>/',
            'get_study_detail': '/api/studies/<id>/',
            'get_study_images': '/api/studies/<study_uid>/images/',
            'get_stats': '/api/stats/',
            'dicom_images_api': '/api/dicom-images/',
            'assign_doctors': '/api/dicom-images/assign_doctors/',
            'update_status': '/api/dicom-images/<id>/update_status/',
            'by_doctor': '/api/dicom-images/by_doctor/'
        },
        'features': [
            'Center-based organization',
            'Doctor assignment system',
            'Status tracking',
            'Emergency case flagging',
            'Center-specific statistics',
            'Study grouping by patient',
            'RESTful API design',
            'Patient-based pagination'
        ]
    })

def test_api(request):
    return JsonResponse({
        'success': True,
        'message': 'API is working correctly',
        'timestamp': datetime.datetime.now().isoformat()
    })

def get_all_dicom_images(request):
    try:
        center_name = request.GET.get('center_name', '')
        doctor_name = request.GET.get('doctor_name', '')
        status_filter = request.GET.get('status', '')
        
        queryset = DICOMImage.objects.all().order_by('-created_at')
        
        if center_name:
            queryset = queryset.filter(center_name=center_name)
        
        if doctor_name:
            queryset = queryset.filter(assigned_doctors__icontains=doctor_name)
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        images_list = []
        for image in queryset:
            images_list.append({
                'id': image.id,
                'center_name': image.center_name,
                'patient_name': image.patient_name,
                'patient_id': image.patient_id,
                'study_date': image.study_date,
                'study_description': image.study_description,
                'series_description': image.series_description,
                'modality': image.modality,
                'study_instance_uid': image.study_instance_uid,
                'instance_number': image.instance_number,
                'file_size': image.file_size,
                'file_path': image.file_path,
                'status': image.status,
                'assigned_doctors': image.assigned_doctors,
                'assigned_doctors_list': image.assigned_doctors_list,
                'reported_by': image.reported_by,
                'is_emergency': image.is_emergency,
                'created_at': image.created_at.isoformat() if image.created_at else None,
            })
        
        return JsonResponse({
            'success': True,
            'images': images_list
        })
    except Exception as e:
        logger.error(f"Error getting images: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

def get_fixed_stats(request):
    try:
        center_name = request.GET.get('center_name', '')
        
        if center_name:
            queryset = DICOMImage.objects.filter(center_name=center_name)
        else:
            queryset = DICOMImage.objects.all()
        
        patient_ids = []
        total_size = 0

        for image in queryset:
            if image.patient_id and image.patient_id not in patient_ids:
                patient_ids.append(image.patient_id)
            if image.file_size:
                total_size += image.file_size

        stats = {
            'patients': len(patient_ids),
            'size_bytes': total_size,
            'size_mb': round(total_size / (1024 * 1024), 2) if total_size else 0
        }
        
        if center_name:
            stats['center_name'] = center_name

        return JsonResponse({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def index(request):
    return render(request, '/static/index.html')

@csrf_exempt
def assign_doctors_to_images(request):
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': 'Only POST method allowed'
        }, status=405)
    
    try:
        data = json.loads(request.body)
        image_ids = data.get('image_ids', [])
        doctor_names = data.get('doctor_names', [])
        
        if not image_ids or not doctor_names:
            return JsonResponse({
                'success': False,
                'error': 'image_ids and doctor_names are required'
            }, status=400)
        
        images = DICOMImage.objects.filter(id__in=image_ids)
        if len(images) != len(image_ids):
            return JsonResponse({
                'success': False,
                'error': 'Some image IDs not found'
            }, status=404)
        
        updated_count = 0
        for image in images:
            for doctor_name in doctor_names:
                image.assign_doctor(doctor_name)
            updated_count += 1
        
        return JsonResponse({
            'success': True,
            'message': f'Successfully assigned doctors to {updated_count} images',
            'updated_images': updated_count
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error in assign_doctors_to_images: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


logger = logging.getLogger(__name__)


@csrf_exempt
def receive_dicom_data(request):
    print("=== DICOM RECEIVE DEBUG ===")
    print(f"Method: {request.method}")
    print(f"Content-Type: {request.content_type}")
    print(f"FILES keys: {list(request.FILES.keys()) if request.FILES else 'No files'}")
    print(f"POST keys: {list(request.POST.keys()) if request.POST else 'No POST data'}")
    print(f"CSRF Cookie: {request.META.get('CSRF_COOKIE')}")
    print(f"Headers: {dict(request.headers)}")
    
    if request.method == 'OPTIONS':
        response = HttpResponse()
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type'
        return response

    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': 'Only POST method allowed'
        }, status=405)
    
    try:
        logger.info("Received DICOM data request")
        
        if 'dicom_file' not in request.FILES:
            logger.error("No DICOM file in request")
            return JsonResponse({
                'success': False,
                'error': 'No DICOM file provided'
            }, status=400)
        
        center_name = request.POST.get('center_name', '').strip()
        if not center_name:
            logger.error("No center name provided")
            return JsonResponse({
                'success': False,
                'error': 'Center name is required'
            }, status=400)
        
        dicom_file = request.FILES['dicom_file']
        print(f"Processing DICOM file: {dicom_file.name} ({dicom_file.size} bytes)")
        
        try:
            file_content = dicom_file.read()
            ds = pydicom.dcmread(
                pydicom.filebase.DicomBytesIO(file_content),
                force=True
            )
            
            if not hasattr(ds, 'SpecificCharacterSet'):
                ds.SpecificCharacterSet = 'ISO_IR 100'
            
        except Exception as e:
            logger.error(f"Error reading DICOM file: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': f'Invalid DICOM file: {str(e)}'
            }, status=400)
        
        try:
            metadata = extract_dicom_metadata(ds)
        except Exception as e:
            logger.error(f"Error extracting metadata: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': f'Error processing DICOM metadata: {str(e)}'
            }, status=500)
        
        try:
            center_dir = center_name.replace(' ', '_').replace('/', '_').replace('\\', '_')
            filename = f"{center_dir}/{metadata.get('sop_instance_uid', 'unknown')}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.dcm"
            file_path = default_storage.save(filename, ContentFile(file_content))
            full_path = os.path.join(settings.MEDIA_ROOT, file_path)
            print(f"Saved file to: {file_path}")
        except Exception as e:
            logger.error(f"Error saving file: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': f'Error saving file: {str(e)}'
            }, status=500)
        
        try:
            dicom_image = DICOMImage.objects.create(
                center_name=center_name[:200],
                patient_name=metadata.get('patient_name', '')[:200],
                patient_id=metadata.get('patient_id', '')[:64],
                patient_birth_date=metadata.get('patient_birth_date', '') or None,
                patient_sex=metadata.get('patient_sex', '')[:10],
                study_instance_uid=metadata.get('study_instance_uid', '')[:64],
                study_date=metadata.get('study_date', '') or None,
                study_time=metadata.get('study_time', '') or None,
                study_description=metadata.get('study_description', '')[:200],
                referring_physician=metadata.get('referring_physician', '')[:200],
                series_instance_uid=metadata.get('series_instance_uid', '')[:64],
                series_number=metadata.get('series_number', '') or None,
                series_description=metadata.get('series_description', '')[:200],
                modality=metadata.get('modality', '')[:16],
                sop_instance_uid=metadata.get('sop_instance_uid', '')[:64],
                instance_number=metadata.get('instance_number', '') or None,
                file_path=file_path,
                file_size=len(file_content),
                image_orientation=json.dumps(metadata.get('image_orientation', [])) if metadata.get('image_orientation') else '',
                image_position=json.dumps(metadata.get('image_position', [])) if metadata.get('image_position') else '',
                pixel_spacing=json.dumps(metadata.get('pixel_spacing', [])) if metadata.get('pixel_spacing') else '',
                slice_thickness=metadata.get('slice_thickness')
            )
            
            print(f"Successfully created DICOMImage record with ID: {dicom_image.id}")
            logger.info(f"Successfully saved DICOM image for {center_name}: {dicom_image.id}")
            
        except Exception as e:
            print(f"Database error: {str(e)}")
            import traceback
            traceback.print_exc()
            logger.error(f"Error saving to database: {str(e)}")
            try:
                if os.path.exists(full_path):
                    os.remove(full_path)
            except:
                pass
            return JsonResponse({
                'success': False,
                'error': f'Error saving to database: {str(e)}'
            }, status=500)
        
        print("=== SUCCESS ===")
        response = JsonResponse({
            'success': True,
            'message': 'DICOM file processed successfully',
            'image_id': dicom_image.id,
            'filename': os.path.basename(filename),
            'center_name': center_name
        })
        
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type'
        
        return response
        
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        logger.error(f"Unexpected error in receive_dicom_data: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Server error: {str(e)}'
        }, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class ReceiveDICOMView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        return receive_dicom_data(request)


from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from django_filters import rest_framework as filters
from django.db.models import Q

class DICOMImageFilter(filters.FilterSet):
    patient_name__icontains = filters.CharFilter(field_name='patient_name', lookup_expr='icontains')
    patient_id__icontains = filters.CharFilter(field_name='patient_id', lookup_expr='icontains')
    status = filters.CharFilter(field_name='status')
    center_name = filters.CharFilter(field_name='center_name')
    is_emergency = filters.BooleanFilter(field_name='is_emergency')
    modality__in = filters.CharFilter(method='filter_modality')
    
    class Meta:
        model = DICOMImage
        fields = ['patient_name__icontains', 'patient_id__icontains', 'status', 'center_name', 'is_emergency']
    
    def filter_modality(self, queryset, name, value):
        if value:
            modalities = [m.strip() for m in value.split(',') if m.strip()]
            return queryset.filter(modality__in=modalities)
        return queryset

class DICOMImageListView(generics.ListAPIView):
    serializer_class = DICOMImageSerializer
    pagination_class = PageNumberPagination
    filterset_class = DICOMImageFilter
    
    def get_queryset(self):
        return DICOMImage.objects.all().order_by('-created_at')

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([AllowAny])
def current_user(request):
    user = request.user
    
    if not user or not user.is_authenticated:
        return Response({
            'success': False,
            'error': 'Not authenticated',
            'detail': 'Authentication credentials were not provided or are invalid.'
        }, status=status.HTTP_401_UNAUTHORIZED)

    try:
        profile = UserProfile.objects.filter(user=user).first()
        
        if profile:
            doctor_name = profile.full_name if profile.full_name else user.username
            role = profile.role.name if profile.role else 'Unknown'
        else:
            doctor_name = user.username
            role = 'Admin' if user.is_superuser else 'Unknown'

        center_name = None
        institute_name = None
        
        if role == 'Center':
            if profile and profile.center:
                center_obj = profile.center
                institute_name = center_obj.institute_name
                center_name_obj = center_obj.center_names.first()
                center_name = center_name_obj.name if center_name_obj else None
            else:
                center = Center.objects.filter(user=user).first()
                if center:
                    institute_name = center.institute_name
                    center_name_obj = center.center_names.first()
                    center_name = center_name_obj.name if center_name_obj else None
                    
                    if profile:
                        profile.center = center
                        profile.save()

        response_data = {
            'success': True,
            'username': user.username,
            'doctor_name': doctor_name,
            'full_name': profile.full_name if profile else '',
            'designation': profile.designation if profile else '',
            'qualification': profile.qualification if profile else '',
            'contact_number': profile.contact_number if profile else '',
            'bmdc_reg_no': profile.bmdc_reg_no if profile else '',
            'signature': profile.signature.url if (profile and profile.signature) else '',
            'role': role,
            'center_name': center_name,
            'institute_name': institute_name
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"ERROR in current_user view: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return Response({
            'success': False,
            'error': f'Server error: {str(e)}',
            'detail': 'Error retrieving user information'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_doctors(request):
    """Get list of all doctors with their details"""
    try:
        
        doctor_profiles = UserProfile.objects.filter(
            role__name='Doctor'
        ).select_related('user').values(
            'user__username',
            'full_name',
            'designation',
            'qualification',
            'bmdc_reg_no'
        )
        
        doctors = [
            {
                'name': profile['full_name'] or profile['user__username'],
                'username': profile['user__username'],
                'designation': profile['designation'],
                'qualification': profile['qualification'],
                'bmdc_reg_no': profile['bmdc_reg_no']
            }
            for profile in doctor_profiles
        ]
        
        return Response({
            'success': True,
            'doctors': doctors
        })
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_current_user_info(request):
    try:
        user = request.user
        
        if not user.is_authenticated:
            return Response({
                'success': False,
                'error': 'Not authenticated'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        profile = UserProfile.objects.filter(user=user).first()
        
        if not profile:
            return Response({
                'success': False,
                'error': 'User profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        role_name = profile.role.name if profile.role else 'Unknown'
        
        if role_name not in ['SubAdmin', 'Center']:
            return Response({
                'success': False,
                'error': 'Access denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        user_name = profile.full_name or user.username
        center_name = profile.center.name if role_name == 'Center' and profile.center else None
        
        return Response({
            'success': True,
            'username': user.username,
            'display_name': user_name,
            'role': role_name,
            'center_name': center_name
        })
        
    except Exception as e:
        logger.error(f"Error in get_current_user_info: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)   

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_dicom_report(request, dicom_id):
    try:
        dicom = DICOMImage.objects.get(id=dicom_id)
        
        if 'file' not in request.FILES:
            return Response({'success': False, 'error': 'No file provided'}, status=400)
        
        file = request.FILES['file']
        clean_filename = file.name.split('/')[-1].split('\\')[-1]
        final_filename = f'{dicom.patient_id}_{dicom_id}_{clean_filename}'
        
        dicom.report_file.save(final_filename, file, save=False)
        
        try:
            profile = UserProfile.objects.filter(user=request.user).first()
            doctor_name = profile.full_name if profile and profile.full_name else request.user.username
        except:
            doctor_name = request.user.username
        
        dicom.status = 'Reported'
        dicom.reported_by = doctor_name
        dicom.save()
        
        saved_report_path = dicom.report_file.name
        
        related_images = DICOMImage.objects.filter(
            patient_id=dicom.patient_id,
            study_instance_uid=dicom.study_instance_uid
        ).exclude(id=dicom_id)
        
        updated_count = 0
        for related_img in related_images:
            related_img.report_file = saved_report_path
            related_img.status = 'Reported'
            related_img.reported_by = doctor_name
            related_img.save()
            updated_count += 1
        
        return Response({
            'success': True,
            'message': 'Report uploaded successfully',
            'file_path': saved_report_path,
            'updated_images': updated_count + 1,
            'reported_by': doctor_name
        })
        
    except DICOMImage.DoesNotExist:
        return Response({'success': False, 'error': 'DICOM not found'}, status=404)
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        return Response({'success': False, 'error': str(e)}, status=500)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_dicom_status(request, dicom_id):
    try:
        dicom = DICOMImage.objects.get(id=dicom_id)
        
        new_status = request.data.get('status')
        reported_by = request.data.get('reported_by', '')
        report_content = request.data.get('report_content', '')
        
        if not new_status:
            return Response({
                'success': False,
                'error': 'Status is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        valid_statuses = ['Not Assigned', 'Unreported', 'Draft', 'Reviewed', 'Reported']
        if new_status not in valid_statuses:
            return Response({
                'success': False,
                'error': f'Invalid status. Valid options: {valid_statuses}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not reported_by:
            try:
                profile = UserProfile.objects.filter(user=request.user).first()
                reported_by = profile.full_name if profile and profile.full_name else request.user.username
            except:
                reported_by = request.user.username
        
        current_report_file = dicom.report_file.name if dicom.report_file else None
        
        dicom.status = new_status
        dicom.reported_by = reported_by
        if report_content:
            dicom.report_content = report_content
        dicom.save()
        
        related_images = DICOMImage.objects.filter(
            patient_id=dicom.patient_id,
            study_instance_uid=dicom.study_instance_uid
        ).exclude(id=dicom_id)
        
        updated_count = 0
        for related_img in related_images:
            related_img.status = new_status
            related_img.reported_by = reported_by
            
            if current_report_file:
                related_img.report_file = current_report_file
            
            if report_content:
                related_img.report_content = report_content
            
            related_img.save()
            updated_count += 1
        
        return Response({
            'success': True,
            'message': 'Status and report updated successfully',
            'image': DICOMImageSerializer(dicom).data,
            'updated_images': updated_count + 1,
            'reported_by': reported_by
        })
        
    except DICOMImage.DoesNotExist:
        return Response({
            'success': False,
            'error': 'DICOM image not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error updating status: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def remove_single_doctor(request):
    try:
        image_id = request.data.get('image_id')
        doctor_name = request.data.get('doctor_name')
        
        dicom_image = DICOMImage.objects.get(id=image_id)
        
        assigned_doctors = list(dicom_image.assigned_doctors_list or [])
        if doctor_name in assigned_doctors:
            assigned_doctors.remove(doctor_name)
            dicom_image.assigned_doctors_list = assigned_doctors
            dicom_image.save()
            
            return Response({'success': True})
        else:
            return Response({'success': False, 'error': 'Doctor not found'}, status=400)
            
    except DICOMImage.DoesNotExist:
        return Response({'success': False, 'error': 'Image not found'}, status=404)
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=500)


@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_institute_info(request):
    try:
        user = request.user
        
        if not user.is_authenticated:
            return Response({
                'success': False,
                'error': 'Not authenticated'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        profile = UserProfile.objects.filter(user=user).first()
        
        if not profile:
            return Response({
                'success': False,
                'error': 'User profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        role_name = profile.role.name if profile.role else 'Unknown'
        
        if role_name != 'Center':
            return Response({
                'success': False,
                'error': 'Access denied - Only Center users allowed'
            }, status=status.HTTP_403_FORBIDDEN)
        
        if profile.center:
            institute_name = profile.center.institute_name
            centers_in_institute = Center.objects.filter(institute_name=institute_name)
            center_names_list = []
            
            for center_obj in centers_in_institute:
                for center_name in center_obj.center_names.all():
                    center_names_list.append({
                        'name': center_name.name,
                        'id': center_name.id
                    })
            
            return Response({
                'success': True,
                'username': user.username,
                'role': role_name,
                'institute_name': institute_name,
                'centers': center_names_list,
                'center_count': len(center_names_list)
            })
        else:
            return Response({
                'success': False,
                'error': 'No center/institute assigned to user'
            }, status=status.HTTP_404_NOT_FOUND)
        
    except Exception as e:
        logger.error(f"Error in get_institute_info: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_institute_studies(request):
    """Get all studies for all centers under an institute"""
    try:
        user = request.user
        profile = UserProfile.objects.filter(user=user).first()
        
        if not profile or not profile.center:
            return Response({
                'success': False,
                'error': 'No institute assigned'
            }, status=status.HTTP_404_NOT_FOUND)
        
        institute_name = profile.center.institute_name
        
        centers_in_institute = Center.objects.filter(institute_name=institute_name)
        center_names_list = []
        
        for center_obj in centers_in_institute:
            for center_name in center_obj.center_names.all():
                center_names_list.append(center_name.name)
        
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 1000))
        
        queryset = DICOMImage.objects.filter(
            center_name__in=center_names_list
        ).order_by('-created_at')
        
        center_filter = request.GET.get('center_name')
        status_filter = request.GET.get('status')
        
        if center_filter:
            queryset = queryset.filter(center_name=center_filter)
        
        if status_filter and status_filter != 'All':
            queryset = queryset.filter(status=status_filter)
        
        serializer = DICOMImageSerializer(queryset, many=True)
        
        return Response({
            'success': True,
            'results': serializer.data,
            'institute_name': institute_name,
            'centers': center_names_list,
            'total_count': queryset.count()
        })
        
    except Exception as e:
        logger.error(f"Error in get_institute_studies: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_institute_stats(request):
    
    try:
        user = request.user
        profile = UserProfile.objects.filter(user=user).first()
        
        if not profile or not profile.center:
            return Response({
                'success': False,
                'error': 'No institute assigned'
            }, status=status.HTTP_404_NOT_FOUND)
        
        institute_name = profile.center.institute_name
        
        
        centers_in_institute = Center.objects.filter(institute_name=institute_name)
        center_names_list = []
        
        for center_obj in centers_in_institute:
            for center_name in center_obj.center_names.all():
                center_names_list.append(center_name.name)
        
        
        queryset = DICOMImage.objects.filter(center_name__in=center_names_list)
        
        from django.db.models import Count, Sum
        
        total_images = queryset.count()
        total_studies = queryset.values('study_instance_uid').distinct().count()
        total_patients = queryset.values('patient_id').distinct().count()
        
        status_counts = queryset.values('status').annotate(count=Count('id'))
        
        total_size = queryset.aggregate(total=Sum('file_size'))['total'] or 0
        
        
        center_stats = []
        for center_name in center_names_list:
            center_queryset = queryset.filter(center_name=center_name)
            center_stats.append({
                'center_name': center_name,
                'image_count': center_queryset.count(),
                'patient_count': center_queryset.values('patient_id').distinct().count(),
                'study_count': center_queryset.values('study_instance_uid').distinct().count()
            })
        
        return Response({
            'success': True,
            'institute_name': institute_name,
            'total_centers': len(center_names_list),
            'total_images': total_images,
            'total_studies': total_studies,
            'total_patients': total_patients,
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2) if total_size else 0,
            'status_breakdown': {item['status']: item['count'] for item in status_counts},
            'center_stats': center_stats
        })
        
    except Exception as e:
        logger.error(f"Error in get_institute_stats: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        

def template_manager_page(request):
    from django.http import HttpResponse
    import os
    from django.conf import settings
    
    html_path = os.path.join(settings.BASE_DIR, 'myapp', 'static', 'template.html')
    
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        return HttpResponse(html_content)
    except FileNotFoundError:
        return HttpResponse(f"""
            <h1>Template Not Found</h1>
            <p>File not found at: {html_path}</p>
            <p>Please place template.html at: myapp/static/template.html</p>
            <p>Full path: {html_path}</p>
        """, status=404)

@api_view(['GET'])
@permission_classes([AllowAny])
def get_report_templates(request):
    try:
        user = request.user
        
        if not user.is_authenticated:
            return Response({
                'success': False,
                'error': 'Authentication required'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        body_part = request.GET.get('body_part', '')
        
        profile = UserProfile.objects.filter(user=user).first()
        is_admin = False
        
        if profile and profile.role:
            is_admin = profile.role.name == 'Admin'
        elif user.is_superuser:
            is_admin = True
        
        if is_admin:
            templates = ReportTemplate.objects.filter(is_active=True)
        else:
            admin_group = Group.objects.filter(name='Admin').first()
            admin_profiles = UserProfile.objects.filter(role=admin_group) if admin_group else []
            admin_user_ids = [p.user_id for p in admin_profiles]
            
            superuser_ids = list(User.objects.filter(is_superuser=True).values_list('id', flat=True))
            all_admin_ids = list(set(admin_user_ids + superuser_ids))
            
            templates = ReportTemplate.objects.filter(
                is_active=True
            ).filter(
                Q(created_by=user) |
                Q(created_by__in=all_admin_ids) |
                Q(created_by__isnull=True)
            )
        
        if body_part:
            templates = templates.filter(body_part__iexact=body_part)
        
        templates = templates.order_by('body_part', 'template_name')
        serializer = ReportTemplateSerializer(templates, many=True)
        
        grouped = {}
        for template in serializer.data:
            bp = template['body_part']
            if bp not in grouped:
                grouped[bp] = []
            grouped[bp].append(template)
        
        return Response({
            'success': True,
            'templates': serializer.data,
            'grouped': grouped,
            'count': templates.count(),
            'is_admin': is_admin
        })
        
    except Exception as e:
        logger.error(f"Error getting report templates: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET', 'POST', 'PUT', 'DELETE'])
@permission_classes([AllowAny])
def manage_templates(request):
    
    user = request.user
    
    if not user.is_authenticated:
        return Response({
            'success': False,
            'error': 'Authentication required'
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    profile = UserProfile.objects.filter(user=user).first()
    is_admin = (profile and profile.role and profile.role.name == 'Admin') or user.is_superuser
    
    if request.method == 'GET':
        try:
            body_part = request.GET.get('body_part', '')
            
            if is_admin:
                templates = ReportTemplate.objects.filter(is_active=True)
            else:
                admin_group = Group.objects.filter(name='Admin').first()
                admin_profiles = UserProfile.objects.filter(role=admin_group) if admin_group else []
                admin_user_ids = [p.user_id for p in admin_profiles]
                superuser_ids = list(User.objects.filter(is_superuser=True).values_list('id', flat=True))
                all_admin_ids = list(set(admin_user_ids + superuser_ids))
                
                templates = ReportTemplate.objects.filter(
                    is_active=True
                ).filter(
                    Q(created_by=user) |
                    Q(created_by__in=all_admin_ids) |
                    Q(created_by__isnull=True)
                )
            
            if body_part:
                templates = templates.filter(body_part__iexact=body_part)
            
            templates = templates.order_by('body_part', 'template_name')
            serializer = ReportTemplateSerializer(templates, many=True)
            
            return Response({
                'success': True,
                'templates': serializer.data,
                'count': templates.count(),
                'is_admin': is_admin
            })
            
        except Exception as e:
            logger.error(f"Error retrieving templates: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    elif request.method == 'POST':
        try:
            body_part = request.data.get('body_part', '').strip()
            template_name = request.data.get('template_name', '').strip()
            content = request.data.get('content', '').strip()
            is_active = request.data.get('is_active', True)
            
            if not body_part or not template_name or not content:
                return Response({
                    'success': False,
                    'error': 'Body part, template name, and content are required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            template = ReportTemplate.objects.create(
                body_part=body_part,
                template_name=template_name,
                content=content,
                is_active=is_active,
                created_by=user
            )
            
            serializer = ReportTemplateSerializer(template)
            
            return Response({
                'success': True,
                'message': 'Template created successfully',
                'template': serializer.data
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Error creating template: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    elif request.method == 'PUT':
        try:
            template_id = request.data.get('id')
            
            if not template_id:
                return Response({
                    'success': False,
                    'error': 'Template ID is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            template = ReportTemplate.objects.get(id=template_id)
            
            if template.created_by and template.created_by != user and not is_admin:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to edit this template'
                }, status=status.HTTP_403_FORBIDDEN)
            
            template.body_part = request.data.get('body_part', template.body_part).strip()
            template.template_name = request.data.get('template_name', template.template_name).strip()
            template.content = request.data.get('content', template.content).strip()
            template.is_active = request.data.get('is_active', template.is_active)
            template.save()
            
            serializer = ReportTemplateSerializer(template)
            
            return Response({
                'success': True,
                'message': 'Template updated successfully',
                'template': serializer.data
            })
            
        except ReportTemplate.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Template not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error updating template: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    elif request.method == 'DELETE':
        try:
            template_id = request.data.get('id')
            
            if not template_id:
                return Response({
                    'success': False,
                    'error': 'Template ID is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            template = ReportTemplate.objects.get(id=template_id)
            
            if template.created_by and template.created_by != user and not is_admin:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to delete this template'
                }, status=status.HTTP_403_FORBIDDEN)
            
            template.is_active = False
            template.save()
            
            return Response({
                'success': True,
                'message': 'Template deleted successfully'
            })
            
        except ReportTemplate.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Template not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error deleting template: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)