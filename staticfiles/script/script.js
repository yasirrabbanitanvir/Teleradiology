const baseUrl = window.location.origin;
let allStudies = [];
let token = sessionStorage.getItem('token') || localStorage.getItem('token');
let role = sessionStorage.getItem('role') || localStorage.getItem('role');
let availableDoctors = [];

let currentPage = parseInt(sessionStorage.getItem('currentPage')) || 1;
let itemsPerPage = 10;
let totalPages = 1;
let totalCount = 0;
let groupedPatients = {};

async function checkUserRole() {
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
      localStorage.removeItem('token');
      localStorage.removeItem('role');
      sessionStorage.removeItem('token');
      sessionStorage.removeItem('role');
      window.location.href = 'login.html';
      return false;
    }

    const data = await response.json();
    
    if (data.success) {
      const userRole = data.role;
      const currentPage = window.location.pathname;
      
      if (userRole === 'Doctor' && !currentPage.includes('doctor.html')) {
        window.location.href = 'doctor.html';
        return false;
      }
      
      if (userRole === 'SubAdmin' && !currentPage.includes('index.html')) {
        window.location.href = 'index.html';
        return false;
      }
      
      if (userRole === 'Center' && !currentPage.includes('institute.html')) {
        window.location.href = 'institute.html';
        return false;
      }
      
      return true;
    }
    
    return false;
  } catch (error) {
    console.error('Error checking user role:', error);
    window.location.href = 'login.html';
    return false;
  }
}

async function getCurrentUser() {
  if (!token) {
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
      return null;
    }

    const data = await response.json();
    
    if (data.success) {
      return data.doctor_name || data.username;
    }
    
    return null;
  } catch (error) {
    console.error('Error fetching user info:', error);
    return null;
  }
}

function checkAuthentication() {
  if (!token) {
    alert('Please log in first');
    window.location.href = 'login.html';
    return false;
  }
  return true;
}

function removeDuplicateStudies(studies) {
  const seen = new Set();
  const duplicatesRemoved = [];
  
  studies.forEach(study => {
    const uniqueKey = `${study.patientID || study.patient_id || ''}_${study.studyUID || study.study_instance_uid || study.id || ''}_${study.scanDateTime || study.study_date || ''}`;
    
    if (!seen.has(uniqueKey)) {
      seen.add(uniqueKey);
      duplicatesRemoved.push(study);
    }
  });
  
  return duplicatesRemoved;
}

async function loadDoctors() {
  try {
    const response = await fetch(`${baseUrl}/api/doctors/`, {
      headers: { 
        'Authorization': `Token ${token}`,
        'Content-Type': 'application/json'
      }
    });
    
    if (!response.ok) {
      throw new Error('Failed to fetch doctors');
    }
    
    const data = await response.json();
    
    if (data.success && data.doctors) {
      availableDoctors = data.doctors.map(doc => doc.name);
      
      const assignSelect = document.getElementById('assign-doctors');
      if (assignSelect) {
        assignSelect.innerHTML = '';
        
        data.doctors.forEach(doctor => {
          const option = document.createElement('option');
          option.value = doctor.name;
          option.textContent = `${doctor.name} ${doctor.designation ? '(' + doctor.designation + ')' : ''}`;
          assignSelect.appendChild(option);
        });
      }
    }
  } catch (err) {
    console.error('Error loading doctors:', err);
    alert('Failed to load doctors list');
  }
}

async function fetchAndLoadStudies(maintainPage = false) {
  if (!checkAuthentication()) {
    return;
  }
  
  try {
    const params = new URLSearchParams();
    params.append('page', '1');
    params.append('page_size', '1000');

    const res = await fetch(`${baseUrl}/api/dicom-images/?${params.toString()}`, {
      headers: { 
        'Authorization': `Token ${token}`,
        'Content-Type': 'application/json'
      }
    });
    
    if (res.status === 401) {
      alert('Session expired. Please log in again.');
      localStorage.removeItem('token');
      localStorage.removeItem('role');
      sessionStorage.removeItem('token');
      sessionStorage.removeItem('role');
      sessionStorage.removeItem('currentPage');
      window.location.href = 'login.html';
      return;
    }
    
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    
    const responseData = await res.json();
    
    let dicomImages;
    if (responseData.results && Array.isArray(responseData.results)) {
      dicomImages = responseData.results;
    } else if (Array.isArray(responseData)) {
      dicomImages = responseData;
    } else {
      throw new Error('Invalid response format from server');
    }
    
    let processedStudies = dicomImages.map(dicom => {
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
        patientName: dicom.patient_name || 'Unknown',
        patientID: dicom.patient_id || '',
        age: dicom.age || 0,
        sex: dicom.patient_sex || '',
        bodyPart: dicom.series_description || '',
        modality: dicom.modality || '',
        center: dicom.center_name || 'Default',
        institute: displayInstitute,
        scanDateTime: scanDateTime,
        status: dicom.status || 'Not Assigned',
        reportedBy: dicom.reported_by || '',
        group: dicom.assigned_doctors || '',
        assignedDoctors: dicom.assigned_doctors_list || [],
        dicomFile: dicom.file_path ? `${baseUrl}/media/${dicom.file_path}` : '',
        reportPdf: reportUrl || '',
        locked: dicom.is_emergency || false,
        studyDescription: dicom.study_description || '',
        images: dicom.images || dicom.image_urls || [],
        thumbnailUrl: dicom.thumbnail_url || '',
        studyUID: dicom.study_instance_uid || dicom.study_uid || dicom.id,
        dbId: dicom.id
      };
    });

    allStudies = removeDuplicateStudies(processedStudies);
    allStudies.sort((a, b) => b.dbId - a.dbId);
    
    populateCenterDropdown();
    await loadDoctors();
    
    searchStudies(maintainPage);
    
  } catch (err) {
    console.error('Error fetching studies:', err);
    alert('Error fetching studies: ' + err.message);
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
  
  allStudies.forEach(s => {
    const institute = s.institute;
    const center = s.center;
    
    if (institute && !instituteMap.has(institute)) {
      instituteMap.set(institute, new Set());
    }
    
    if (institute && center) {
      instituteMap.get(institute).add(center);
    }
  });
  
  const sortedInstitutes = Array.from(instituteMap.keys()).sort();
  
  sortedInstitutes.forEach(institute => {
    const centers = Array.from(instituteMap.get(institute));
    
    const option = document.createElement('option');
    option.value = centers[0];
    option.textContent = institute;
    option.dataset.institute = institute;
    centerSelect.appendChild(option);
  });
  
  if (currentValue && Array.from(centerSelect.options).some(opt => opt.value === currentValue)) {
    centerSelect.value = currentValue;
  } else {
    centerSelect.value = 'ALL';
  }
}

function setupPagination(filteredStudies) {
  const groupedAll = {};
  filteredStudies.forEach(study => {
    const patientId = study.patientID || 'Unknown';
    if (!groupedAll[patientId]) {
      groupedAll[patientId] = {
        patientID: patientId,
        maxId: study.dbId,
        images: []
      };
    }
    groupedAll[patientId].images.push(study);
    if (study.dbId > groupedAll[patientId].maxId) {
      groupedAll[patientId].maxId = study.dbId;
    }
  });
  
  const sortedPatients = Object.values(groupedAll).sort((a, b) => b.maxId - a.maxId);
  
  totalCount = sortedPatients.length;
  totalPages = Math.ceil(totalCount / itemsPerPage);
  
  if (currentPage > totalPages && totalPages > 0) {
    currentPage = totalPages;
    sessionStorage.setItem('currentPage', currentPage);
  }
  if (currentPage < 1) {
    currentPage = 1;
    sessionStorage.setItem('currentPage', currentPage);
  }
  
  groupedPatients = sortedPatients;
  
  createPaginationControls();
}

function goToPage(page) {
  if (page < 1 || page > totalPages) return;
  currentPage = page;
  sessionStorage.setItem('currentPage', currentPage);
  loadStudies();
  createPaginationControls();
}

function searchStudies(maintainPage = false) {
  const nameQ = document.getElementById('patient-name')?.value.toLowerCase() || '';
  const idQ = document.getElementById('patient-id')?.value.toLowerCase() || '';
  const statusQ = document.getElementById('status')?.value || 'All';
  const centerQ = document.getElementById('center')?.value || 'ALL';
  const emergencyFilter = document.getElementById('emergency')?.checked || false;
  const selectedModalities = Array.from(document.querySelectorAll('.modality-checkbox:checked')).map(cb => cb.value);
  const startDate = document.getElementById('scan-start-date')?.value || '';
  const endDate = document.getElementById('scan-end-date')?.value || '';

  const filteredStudies = allStudies.filter(s => {
    if (emergencyFilter && !s.locked) return false;
    if (statusQ !== 'All' && s.status !== statusQ) return false;
    
    if (centerQ !== 'ALL') {
      if (s.center !== centerQ && s.institute !== centerQ) return false;
    }
    
    if (nameQ && !s.patientName.toLowerCase().includes(nameQ)) return false;
    if (idQ && !s.patientID.toLowerCase().includes(idQ)) return false;
    if (selectedModalities.length > 0 && !selectedModalities.includes(s.modality)) return false;
    
    if (startDate || endDate) {
      const scanDate = new Date(s.scanDateTime);
      if (startDate && scanDate < new Date(startDate)) return false;
      if (endDate && scanDate > new Date(endDate + ' 23:59:59')) return false;
    }
    
    return true;
  });

  if (!maintainPage) {
    currentPage = 1;
    sessionStorage.setItem('currentPage', currentPage);
  }
  
  setupPagination(filteredStudies);
  loadStudies();
}

function createPaginationControls() {
  let paginationContainer = document.getElementById('pagination-container');
  
  if (!paginationContainer) {
    paginationContainer = document.createElement('div');
    paginationContainer.id = 'pagination-container';
    paginationContainer.className = 'pagination-container';
    
    const table = document.querySelector('table');
    if (table && table.parentNode) {
      table.parentNode.insertBefore(paginationContainer, table.nextSibling);
    }
  }
  
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
  
  if (!document.getElementById('pagination-styles')) {
    addPaginationStyles();
  }
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

async function removeSingleDoctor(imageId, doctorName) {
  const confirmed = confirm(`Remove ${doctorName} from this study?`);
  if (!confirmed) {
    return;
  }
  
  try {
    const response = await fetch(`${baseUrl}/api/dicom-images/remove_single_doctor/`, {
      method: 'POST',
      headers: {
        'Authorization': `Token ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        image_id: imageId,
        doctor_name: doctorName
      })
    });
    
    const result = await response.json();
    
    if (result.success) {
      const study = allStudies.find(s => s.id === imageId);
      if (study) {
        study.assignedDoctors = study.assignedDoctors.filter(d => d !== doctorName);
        study.group = study.assignedDoctors.join(', ');
      }
      
      await fetchAndLoadStudies(true);
    } else {
      throw new Error(result.error || 'Removal failed');
    }
    
  } catch (error) {
    console.error('Error removing doctor:', error);
    alert('Error removing doctor: ' + error.message);
  }
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

function generateDoctorsList(study) {
  if (!study.assignedDoctors || study.assignedDoctors.length === 0) {
    return '—';
  }
  
  return study.assignedDoctors.map(doctor => {
    return `<div style="display: flex; justify-content: space-between; align-items: center; margin: 3px 0; padding: 3px 5px; background: #f0f0f0; border-radius: 3px;">
      <span>${doctor}</span>
      <button onclick="removeSingleDoctor(${study.id}, '${doctor}')" style="background: #ff4444; color: white; border: none; border-radius: 3px; padding: 2px 6px; cursor: pointer; font-size: 12px; margin-left: 5px;">×</button>
    </div>`;
  }).join('');
}

function loadStudies() {
  const tbody = document.getElementById('study-table-body');
  if (!tbody) {
    console.error('Table body element not found');
    return;
  }
  
  tbody.innerHTML = '';
  
  const start = (currentPage - 1) * itemsPerPage;
  const end = start + itemsPerPage;
  const currentPatients = groupedPatients.slice(start, end);
  
  currentPatients.forEach(patient => {
    const sortedImages = patient.images.sort((a, b) => b.dbId - a.dbId);
    
    sortedImages.forEach((s, index) => {
      const timestamp = new Date().getTime();
      const dicomFileUrl = s.dicomFile ? `${s.dicomFile}?t=${timestamp}` : '';
      const reportButton = s.reportPdf ? `<button class="action-btn" onclick="openReport('${s.reportPdf}?t=${timestamp}')">📝</button>` : '—';
      
      const imagesThumbnails = generateImageThumbnails(s);
      const doctorsList = generateDoctorsList(s);
      
      const tr = document.createElement('tr');
      if (s.locked) {
        tr.classList.add('emergency-case');
      }
      
      if (s.status === 'Reported') {
        tr.classList.add('reported-case');
      } else if (s.status === 'Not Assigned') {
        tr.classList.add('unassigned-case');
      }
      
      if (index === 0) {
        tr.classList.add('first-patient-row');
      }
      
      tr.innerHTML = `
        <td><input type="checkbox" class="row-checkbox" data-patient-pk="${s.id}" /></td>
        <td><button class="action-btn" onclick="openViewer('${dicomFileUrl}', '${s.studyUID}')" ${!dicomFileUrl ? 'disabled' : ''}>📄</button></td>
        <td>${reportButton}</td>
        <td><button class="action-btn" onclick="openHistory('${s.patientID}')">📚</button></td>
        <td>${s.patientName}</td>
        <td>${s.patientID}</td>
        <td>${s.age}</td>
        <td>${s.sex}</td>
        <td>${s.bodyPart}</td>
        <td>${s.modality}</td>
        <td>${s.center}</td>
        <td>${s.institute}</td>
        <td>${s.scanDateTime}</td>
        <td>
          <span class="status-badge status-${s.status.toLowerCase().replace(' ', '-')}">${s.status}</span>
        </td>
        <td>${s.reportedBy}</td>
        <td title="${s.group}">${doctorsList}</td>
      `;
      tbody.appendChild(tr);
    });
  });

  const selectAll = document.getElementById('select-all');
  if (selectAll) {
    selectAll.replaceWith(selectAll.cloneNode(true));
    const newSelectAll = document.getElementById('select-all');
    
    newSelectAll.addEventListener('change', () => {
      const checkboxes = document.querySelectorAll('.row-checkbox');
      const maxSelect = 20;
      checkboxes.forEach((cb, idx) => {
        if (idx < maxSelect) {
          cb.checked = newSelectAll.checked;
        }
      });
    });
  }
}

function addPaginationStyles() {
  const style = document.createElement('style');
  style.id = 'pagination-styles';
  style.textContent = `
    .pagination-container {
      margin-top: 20px;
      background: #fff;
      border-radius: 8px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
      padding: 15px 20px;
    }
    
    .pagination-wrapper {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 15px;
    }
    
    .pagination-info {
      color: #666;
      font-size: 14px;
    }
    
    .pagination-controls {
      display: flex;
      align-items: center;
      gap: 20px;
      flex-wrap: wrap;
    }
    
    .pagination-buttons {
      display: flex;
      align-items: center;
      gap: 5px;
    }
    
    .pagination-btn {
      padding: 8px 12px;
      border: 1px solid #ddd;
      background: white;
      color: #333;
      cursor: pointer;
      border-radius: 4px;
      font-size: 14px;
      transition: all 0.2s ease;
      min-width: 40px;
    }
    
    .pagination-btn:hover:not(:disabled) {
      background: #f5f5f5;
      border-color: #ccc;
    }
    
    .pagination-btn:disabled {
      background: #f9f9f9;
      color: #ccc;
      cursor: not-allowed;
      border-color: #eee;
    }
    
    .pagination-btn.active {
      background: #007bff;
      color: white;
      border-color: #007bff;
    }
    
    .pagination-btn.active:hover {
      background: #0056b3;
      border-color: #0056b3;
    }
    
    .page-numbers {
      display: flex;
      gap: 2px;
    }
    
    .pagination-ellipsis {
      padding: 8px 4px;
      color: #999;
      font-size: 14px;
    }
    
    .img-thumbnails {
      display: flex;
      gap: 5px;
      flex-wrap: wrap;
    }
    
    .study-table-img {
      width: 40px;
      height: 40px;
      border-radius: 4px;
      object-fit: cover;
      border: 1px solid #ddd;
    }
    
    @media (max-width: 768px) {
      .pagination-wrapper {
        flex-direction: column;
        align-items: stretch;
        text-align: center;
      }
      
      .pagination-controls {
        justify-content: center;
        flex-wrap: wrap;
      }
      
      .pagination-buttons {
        flex-wrap: wrap;
        justify-content: center;
      }
    }
  `;
  document.head.appendChild(style);
}

document.addEventListener('DOMContentLoaded', function() {
  const modalityAll = document.getElementById('modality-all');
  if (modalityAll) {
    modalityAll.addEventListener('change', (event) => {
      const isChecked = event.target.checked;
      document.querySelectorAll('.modality-checkbox').forEach(checkbox => {
        checkbox.checked = isChecked;
      });
    });
  }

  const assignBtn = document.getElementById('assign-btn');
  if (assignBtn) {
    assignBtn.addEventListener('click', assignSelectedStudies);
  }
});

async function assignSelectedStudies() {
  const selectedCheckboxes = document.querySelectorAll('.row-checkbox:checked');
  const assignSelect = document.getElementById('assign-doctors');
  
  if (selectedCheckboxes.length === 0) {
    alert('Please select at least one study to assign');
    return;
  }
  
  if (!assignSelect || assignSelect.selectedOptions.length === 0) {
    alert('Please select at least one doctor to assign');
    return;
  }
  
  const imageIds = Array.from(selectedCheckboxes).map(cb => parseInt(cb.dataset.patientPk));
  const doctorNames = Array.from(assignSelect.selectedOptions).map(option => option.value);
  
  try {
    const response = await fetch(`${baseUrl}/api/dicom-images/assign_doctors/`, {
      method: 'POST',
      headers: {
        'Authorization': `Token ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        image_ids: imageIds,
        doctor_names: doctorNames
      })
    });
    
    const result = await response.json();
    
    if (result.success) {
      alert(`Successfully assigned doctors to ${result.updated_images} studies`);
      
      selectedCheckboxes.forEach(cb => cb.checked = false);
      document.getElementById('select-all').checked = false;
      assignSelect.selectedIndex = -1;
      
      await fetchAndLoadStudies(true);
    } else {
      throw new Error(result.error || 'Assignment failed');
    }
    
  } catch (error) {
    console.error('Error assigning doctors:', error);
    alert('Error assigning doctors: ' + error.message);
  }
}

function openViewer(fileUrl, studyUID) {
  if (!fileUrl && !studyUID) {
    alert("No DICOM file available");
    return;
  }
  
  try {
    const screenW = screen.availWidth || window.screen.width;
    const screenH = screen.availHeight || window.screen.height;
    const fullWindowFeatures = `toolbar=no,menubar=no,location=no,resizable=yes,scrollbars=yes,status=no,width=${screenW},height=${screenH},left=0,top=0`;
    
    if (studyUID) {
      const viewerUrl = `./viewer.html?study=${studyUID}`;
      window.open(viewerUrl, "_blank", fullWindowFeatures);
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
    }
    
  } catch (error) {
    console.error('Error opening DICOM viewer:', error);
    alert("Error opening DICOM viewer. Please check the file path.");
  }
}

function openReport(reportUrl) {
  if (reportUrl) {
    window.open(reportUrl, "_blank");
  } else {
    alert("No report available");
  }
}

function openHistory(patientId) { 
  if (!patientId) return;
  const historyUrl = `./history.html?patient=${patientId}`;
  window.open(historyUrl, '_blank', 'width=950,height=900,scrollbars=yes,resizable=yes');
}

function logout() {
  localStorage.removeItem('token');
  localStorage.removeItem('role');
  sessionStorage.removeItem('token');
  sessionStorage.removeItem('role');
  sessionStorage.removeItem('currentPage');
  window.location.href = 'login.html';
}

window.onload = async function() {
  const isAuthorized = await checkUserRole();
  
  if (!isAuthorized) {
    return;
  }
  
  const userName = await getCurrentUser();
  
  const displayElement = document.getElementById('user-display-name');
  if (displayElement) {
    displayElement.textContent = userName || 'User';
  }
  
  fetchAndLoadStudies(true);
};