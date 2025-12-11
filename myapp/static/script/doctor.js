const baseUrl = window.location.origin;
let allPatients = [];
let filteredPatients = []; 
let token = sessionStorage.getItem('token') || localStorage.getItem('token');
let currentPage = parseInt(sessionStorage.getItem('doctorCurrentPage')) || 1;
let itemsPerPage = 10;
let totalPages = 1;
let totalCount = 0;
let loggedInDoctorName = '';
let autoRefreshInterval = null;

async function checkDoctorAccess() {
  if (!token) {
    window.location.href = 'login.html';
    return false;
  }

  try {
    const response = await fetch(`${baseUrl}/api/current-user/`, {
      method: 'GET',
      headers: {
        'Authorization': `Token ${token}`,
        'Content-Type': 'application/json'
      }
    });

    if (!response.ok) {
      window.location.href = 'login.html';
      return false;
    }

    const data = await response.json();
    
    if (data.success) {
      if (data.role !== 'Doctor') {
        if (data.role === 'SubAdmin') {
          window.location.href = 'index.html';
        } else if (data.role === 'Center') {
          window.location.href = 'institute.html';
        } else {
          window.location.href = 'login.html';
        }
        return false;
      }
      return true;
    }
    
    return false;
  } catch (error) {
    console.error('Error checking doctor access:', error);
    window.location.href = 'login.html';
    return false;
  }
}

async function getLoggedInDoctor() {
  if (!token) {
    alert('No authentication token found. Please login again.');
    logout();
    return null;
  }

  try {
    const response = await fetch(`${baseUrl}/api/current-user/`, {
      method: 'GET',
      headers: {
        'Authorization': `Token ${token}`,
        'Content-Type': 'application/json'
      }
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    
    if (data.success) {
      return data.doctor_name || data.full_name || data.username;
    } else {
      throw new Error(data.error || 'Failed to get doctor name from response');
    }
  } catch (error) {
    console.error('Error fetching current user:', error);
    return null;
  }
}

document.getElementById('doctor-name').addEventListener('change', async () => {
  const doctorName = document.getElementById('doctor-name').value;
  const patientListDiv = document.getElementById('patient-list');
  const patientTableBody = document.getElementById('patient-table-body');

  if (!doctorName) {
    patientListDiv.style.display = 'none';
    patientTableBody.innerHTML = '';
    return;
  }

  currentPage = 1;
  sessionStorage.setItem('doctorCurrentPage', currentPage);
  await fetchAssignedStudies(doctorName, currentPage);
});

async function fetchAssignedStudies(doctorName, page = 1, maintainPage = false) {
  try {
    const res = await fetch(`${baseUrl}/api/dicom-images/by_doctor/?doctor_name=${encodeURIComponent(doctorName)}&page=${page}`, {
      headers: { 'Authorization': `Token ${token}` }
    });
    
    if (!res.ok) throw new Error('Failed to fetch assigned studies');
    
    const responseData = await res.json();
    
    if (responseData.success) {
      const images = responseData.images || [];
      
      allPatients = images.map(dicom => {
        let age = 0;
        if (dicom.patient_birth_date) {
          const birthDate = new Date(dicom.patient_birth_date.replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3'));
          const today = new Date();
          age = today.getFullYear() - birthDate.getFullYear();
        }

        let scanDateTime = '';
        if (dicom.study_date && dicom.study_time) {
          const dateStr = dicom.study_date.replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3');
          const timeStr = dicom.study_time.replace(/(\d{2})(\d{2})(\d{2})/, '$1:$2:$3');
          scanDateTime = new Date(`${dateStr}T${timeStr}`).toLocaleString();
        } else if (dicom.study_date) {
          const dateStr = dicom.study_date.replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3');
          scanDateTime = new Date(dateStr).toLocaleDateString();
        }

        const reportFile = dicom.report_file;
        const reportUrl = reportFile ? (reportFile.startsWith('http') ? reportFile : `${baseUrl}/media/${reportFile}`) : null;

        const displayInstitute = dicom.institute_name || dicom.center_name || 'Unknown';

        return {
          id: dicom.id,
          name: dicom.patient_name || 'Unknown',
          patient_id: dicom.patient_id || '',
          age: age,
          sex: dicom.patient_sex || '',
          body_part: dicom.series_description || '',
          modality: dicom.modality || '',
          center: dicom.center_name || 'Default',
          institute_name: displayInstitute,
          scan_datetime: scanDateTime,
          status: dicom.status || 'Unreported',
          locked: dicom.is_emergency || false,
          dicom_file_path: dicom.file_path,
          reported_by: dicom.reported_by || '',
          studyUID: dicom.study_instance_uid || dicom.study_uid || dicom.StudyInstanceUID || '',
          report_file: reportFile,
          report_url: reportUrl,
          images: dicom.images || dicom.image_urls || [],
          thumbnailUrl: dicom.thumbnail_url || '',
          uploads: [{
            id: dicom.id,
            status: dicom.status || 'Unreported',
            dicom_file: dicom.file_path ? `${baseUrl}/media/${dicom.file_path}` : null,
            report_pdf: reportUrl
          }]
        };
      });
      
      searchPatients(maintainPage);
      populateCenterDropdown();
    } else {
      throw new Error(responseData.error || 'Failed to fetch assigned studies');
    }
  } catch (err) {
    console.error('Error fetching assigned studies:', err);
    alert('Error fetching assigned studies: ' + err.message);
    allPatients = [];
    filteredPatients = [];
    document.getElementById('patient-list').style.display = 'none';
  }
}

function populateCenterDropdown() {
  const centerSelect = document.getElementById('center');
  if (!centerSelect) return;
  
  const currentValue = centerSelect.value;
  
  const allOption = centerSelect.querySelector('option[value="ALL"]');
  centerSelect.innerHTML = '';
  
  if (allOption) {
    centerSelect.appendChild(allOption);
  } else {
    const newAllOption = document.createElement('option');
    newAllOption.value = 'ALL';
    newAllOption.textContent = 'All Centers';
    centerSelect.appendChild(newAllOption);
  }
  
  const instituteMap = new Map();
  
  allPatients.forEach(p => {
    const institute = p.institute_name;
    const center = p.center;
    
    if (institute && !instituteMap.has(institute)) {
      instituteMap.set(institute, new Set());
    }
    
    if (institute && center) {
      instituteMap.get(institute).add(center);
    }
  });

  const sortedInstitutes = Array.from(instituteMap.keys()).sort();
  
  sortedInstitutes.forEach(institute => {
    const option = document.createElement('option');
    option.value = Array.from(instituteMap.get(institute))[0];
    option.textContent = institute;
    centerSelect.appendChild(option);
  });
  
  if (currentValue && Array.from(centerSelect.options).some(opt => opt.value === currentValue)) {
    centerSelect.value = currentValue;
  } else {
    centerSelect.value = 'ALL';
  }
}

document.getElementById('modality-all').addEventListener('change', (event) => {
  const isChecked = event.target.checked;
  document.querySelectorAll('.modality-checkbox').forEach(checkbox => {
    checkbox.checked = isChecked;
  });
});

function searchPatients(maintainPage = false) {
  const nameQ = document.getElementById('patient-name').value.toLowerCase();
  const idQ = document.getElementById('patient-id').value.toLowerCase();
  const statusQ = document.getElementById('status').value;
  const centerQ = document.getElementById('center').value;
  const emergencyFilter = document.getElementById('emergency').checked;
  const selectedModalities = Array.from(document.querySelectorAll('.modality-checkbox:checked')).map(cb => cb.value);
  
  const startDate = document.getElementById('scan-start-date').value;
  const endDate = document.getElementById('scan-end-date').value;

  filteredPatients = allPatients.filter(p => {
    if (emergencyFilter && !p.locked) return false;
    if (statusQ !== 'All' && p.status !== statusQ) return false;
    
    if (centerQ !== 'ALL') {
      if (p.center !== centerQ && p.institute_name !== centerQ) return false;
    }
    
    if (nameQ && !p.name.toLowerCase().includes(nameQ)) return false;
    if (idQ && !p.patient_id.toLowerCase().includes(idQ)) return false;
    if (selectedModalities.length > 0 && !selectedModalities.includes(p.modality)) return false;
    
    if (startDate || endDate) {
      const scanDate = new Date(p.scan_datetime);
      if (startDate && scanDate < new Date(startDate)) return false;
      if (endDate && scanDate > new Date(endDate + ' 23:59:59')) return false;
    }
    
    return true;
  });

  totalCount = filteredPatients.length;
  totalPages = Math.ceil(totalCount / itemsPerPage);
  
  if (!maintainPage) {
    currentPage = 1;
    sessionStorage.setItem('doctorCurrentPage', currentPage);
  }
  
  if (currentPage > totalPages && totalPages > 0) {
    currentPage = totalPages;
    sessionStorage.setItem('doctorCurrentPage', currentPage);
  }
  if (currentPage < 1) {
    currentPage = 1;
    sessionStorage.setItem('doctorCurrentPage', currentPage);
  }
  
  loadCurrentPage();
  createPaginationControls();
}

function loadCurrentPage() {
  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = startIndex + itemsPerPage;
  const patientsToShow = filteredPatients.slice(startIndex, endIndex);
  
  loadPatients(patientsToShow);
}

function generateImageThumbnails(study) {
  if (!study.images || !Array.isArray(study.images) || study.images.length === 0) {
    if (study.thumbnailUrl) {
      return `<img src="${study.thumbnailUrl}" alt="Preview" class="study-table-img" onerror="this.style.display='none'" />`;
    }
    return '<span style="color:#999; font-size:12px;">No img</span>';
  }
  
  const thumbnailsHtml = study.images.slice(0, 3).map((img, imgIndex) => {
    const imgUrl = typeof img === 'string' ? img : (img.thumbnail_url || img.url || '#');
    return `<img src="${imgUrl}" alt="Preview ${imgIndex + 1}" class="study-table-img" onerror="this.style.display='none'" />`;
  }).join('');
  
  const moreCount = study.images.length > 3 ? 
    `<span style="color:#666; font-size:11px;">+${study.images.length - 3} more</span>` : '';
  
  return `<div class="img-thumbnails">${thumbnailsHtml}${moreCount}</div>`;
}

function loadPatients(data) {
  const patientListDiv = document.getElementById('patient-list');
  const patientTableBody = document.getElementById('patient-table-body');
  patientTableBody.innerHTML = '';
  
  data.forEach((p, index) => {
    const tr = document.createElement('tr');
    if (p.locked) tr.classList.add('emergency-case');
    
    const status = p.status;
    const timestamp = new Date().getTime();
    const dicomUrl = p.uploads[0]?.dicom_file ? `${p.uploads[0].dicom_file}?t=${timestamp}` : '';
    const studyUID = p.studyUID || '';
    const hasReport = p.report_url ? true : false;
    
    const imagesThumbnails = generateImageThumbnails(p);

    tr.innerHTML = `
      <td>${p.name}</td>
      <td>${p.patient_id}</td>
      <td>${p.age}</td>
      <td>${p.sex}</td>
      <td>${p.body_part}</td>
      <td>${p.modality}</td>
      <td>${p.center}</td>
      <td>${p.institute_name}</td>
      <td>${p.scan_datetime}</td>
      <td>
        <select class="status-select" data-id="${p.id}" data-upload-id="${p.uploads[0]?.id || ''}" disabled style="background-color: ${status === 'Reported' ? '#d4edda' : status === 'Reviewed' ? '#fff3cd' : status === 'Draft' ? '#d1ecf1' : '#f8d7da'}; cursor: not-allowed;">
          <option value="Unreported" ${status === 'Unreported' ? 'selected' : ''}>Unreported</option>
          <option value="Draft" ${status === 'Draft' ? 'selected' : ''}>Draft</option>
          <option value="Reviewed" ${status === 'Reviewed' ? 'selected' : ''}>Reviewed</option>
          <option value="Reported" ${status === 'Reported' ? 'selected' : ''}>Reported</option>
        </select>
      </td>
      <td>
        ${hasReport ? `<button class="action-btn preview-btn" data-report-url="${p.report_url}">👁️ Preview</button>` : `<span style="color: #999;">No Report</span>`}
      </td>
      <td>
        <button class="action-btn view-btn" data-dicom-url="${dicomUrl}" data-study-uid="${studyUID}" data-patient-id="${p.id}">📄</button>
      </td>
    `;
    patientTableBody.appendChild(tr);
  });
  
  patientListDiv.style.display = 'block';

  document.querySelectorAll('.preview-btn').forEach(btn => {
    btn.addEventListener('click', function() {
      const reportUrl = this.dataset.reportUrl;
      if (reportUrl) {
        window.open(reportUrl, '_blank');
      }
    });
  });
  
  document.querySelectorAll('.view-btn').forEach(btn => {
    btn.addEventListener('click', function() {
      const dicomUrl = this.dataset.dicomUrl;
      const studyUID = this.dataset.studyUid;
      const patientId = this.dataset.patientId;
      openViewer(dicomUrl, studyUID, patientId);
    });
  });
}

function createPaginationControls() {
  let paginationContainer = document.getElementById('pagination-container');
  
  if (!paginationContainer) {
    paginationContainer = document.createElement('div');
    paginationContainer.id = 'pagination-container';
    paginationContainer.className = 'pagination-container';
    
    const patientList = document.getElementById('patient-list');
    if (patientList) {
      patientList.appendChild(paginationContainer);
    }
  }
  
  if (totalCount === 0) {
    paginationContainer.style.display = 'none';
    return;
  }
  
  paginationContainer.style.display = 'block';
  
  paginationContainer.innerHTML = `
    <div class="pagination-wrapper">
      <div class="pagination-info">
        <span id="pagination-info-text"></span>
      </div>
      
      <div class="pagination-buttons">
        <button onclick="goToPage(1)" ${currentPage === 1 ? 'disabled' : ''} class="pagination-btn">⟪</button>
        <button onclick="goToPage(${currentPage - 1})" ${currentPage === 1 ? 'disabled' : ''} class="pagination-btn">⟨</button>
        <div class="page-numbers" id="page-numbers"></div>
        <button onclick="goToPage(${currentPage + 1})" ${currentPage === totalPages ? 'disabled' : ''} class="pagination-btn">⟩</button>
        <button onclick="goToPage(${totalPages})" ${currentPage === totalPages ? 'disabled' : ''} class="pagination-btn">⟫</button>
      </div>
    </div>
  `;

  generatePageNumbers();
  updatePaginationInfo();
}

function generatePageNumbers() {
  const pageNumbersContainer = document.getElementById('page-numbers');
  if (!pageNumbersContainer) return;
  
  pageNumbersContainer.innerHTML = '';
  
  let startPage = Math.max(1, currentPage - 2);
  let endPage = Math.min(totalPages, currentPage + 2);
  
  if (currentPage <= 3) {
    endPage = Math.min(5, totalPages);
  }
  if (currentPage > totalPages - 3) {
    startPage = Math.max(totalPages - 4, 1);
  }
  
  for (let i = startPage; i <= endPage; i++) {
    const button = document.createElement('button');
    button.textContent = i;
    button.className = `pagination-btn page-btn ${i === currentPage ? 'active' : ''}`;
    button.onclick = () => goToPage(i);
    pageNumbersContainer.appendChild(button);
  }
}

function updatePaginationInfo() {
  const infoElement = document.getElementById('pagination-info-text');
  if (!infoElement) return;
  
  const startPatient = Math.min((currentPage - 1) * itemsPerPage + 1, totalCount);
  const endPatient = Math.min(currentPage * itemsPerPage, totalCount);
  
  if (totalCount === 0) {
    infoElement.textContent = 'No patients to show';
  } else {
    infoElement.textContent = `Showing ${startPatient}-${endPatient} of ${totalCount} patients`;
  }
}

function goToPage(page) {
  if (page < 1 || page > totalPages || page === currentPage) return;
  
  currentPage = page;
  sessionStorage.setItem('doctorCurrentPage', currentPage);
  loadCurrentPage();
  createPaginationControls();
}

function openViewer(fileUrl, studyUID, patientId) {
  if (!fileUrl && !studyUID) {
    alert("No DICOM file available");
    return;
  }
  
  try {
    const screenW = screen.availWidth || window.screen.width;
    const screenH = screen.availHeight || window.screen.height;
    const fullWindowFeatures = `toolbar=no,menubar=no,location=no,resizable=yes,scrollbars=yes,status=no,width=${screenW},height=${screenH},left=0,top=0`;
    
    if (patientId) {
      sessionStorage.setItem('currentPatientId', patientId);
    }
    
    if (studyUID && studyUID !== '' && studyUID !== 'undefined') {
      const viewerUrl = `./viewer.html?study=${studyUID}`;
      window.open(viewerUrl, "_blank", fullWindowFeatures);
      startAutoRefresh();
      return;
    }
    
    if (fileUrl) {
      const cleanUrl = fileUrl.split("?")[0];
      let filename = '';
      
      if (cleanUrl.includes('/media/')) {
        filename = cleanUrl.split('/media/')[1];
      } else if (cleanUrl.includes('/dicom_files/')) {
        filename = 'dicom_files/' + cleanUrl.split('/dicom_files/')[1];
      } else {
        filename = cleanUrl.replace(baseUrl + '/', '');
      }
      
      const dicomUrl = `/dicom/${filename}/`;
      window.open(`/static/viewer.html?file=${encodeURIComponent(dicomUrl)}`, "_blank", fullWindowFeatures);
      startAutoRefresh();
    } else {
      alert("No valid DICOM file or study UID found");
    }
    
  } catch (error) {
    console.error('Error opening DICOM viewer:', error);
    alert("Error opening DICOM viewer. Please check the file path.");
  }
}

function startAutoRefresh() {
  if (autoRefreshInterval) {
    clearInterval(autoRefreshInterval);
  }
  
  autoRefreshInterval = setInterval(async () => {
    const doctorName = document.getElementById('doctor-name').value;
    if (doctorName) {
      const savedPage = parseInt(sessionStorage.getItem('doctorCurrentPage')) || currentPage;
      await fetchAssignedStudies(doctorName, savedPage, true);
    }
  }, 5000);
}

function stopAutoRefresh() {
  if (autoRefreshInterval) {
    clearInterval(autoRefreshInterval);
    autoRefreshInterval = null;
  }
}

window.addEventListener('focus', async () => {
  const doctorName = document.getElementById('doctor-name').value;
  if (doctorName) {
    const savedPage = parseInt(sessionStorage.getItem('doctorCurrentPage')) || currentPage;
    await fetchAssignedStudies(doctorName, savedPage, true);
  }
});

window.addEventListener('beforeunload', () => {
  stopAutoRefresh();
});

function logout() {
  stopAutoRefresh();
  localStorage.removeItem('token');
  localStorage.removeItem('role');
  sessionStorage.removeItem('token');
  sessionStorage.removeItem('role');
  sessionStorage.removeItem('doctorCurrentPage');
  window.location.href = 'login.html';
}

window.addEventListener('DOMContentLoaded', async () => {
  const hasAccess = await checkDoctorAccess();
  
  if (!hasAccess) {
    return;
  }
  
  if (!token) {
    alert('Please login first');
    window.location.href = 'login.html';
    return;
  }
  
  const savedPage = parseInt(sessionStorage.getItem('doctorCurrentPage'));
  if (savedPage) {
    currentPage = savedPage;
  }
  
  try {
    loggedInDoctorName = await getLoggedInDoctor();
    
    if (loggedInDoctorName) {
      document.getElementById('doctor-display-name').textContent = loggedInDoctorName;
      
      const dropdown = document.getElementById('doctor-name');
      if (dropdown) {
        dropdown.value = loggedInDoctorName;
      }
      
      await fetchAssignedStudies(loggedInDoctorName, currentPage, true);
    } else {
      document.getElementById('doctor-display-name').textContent = 'Error loading name';
    }
  } catch (error) {
    console.error('Error during initialization:', error);
    document.getElementById('doctor-display-name').textContent = 'Error: ' + error.message;
  }
});