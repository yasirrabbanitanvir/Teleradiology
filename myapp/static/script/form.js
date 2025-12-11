const baseUrl = window.location.origin;
let token = localStorage.getItem('token');
let selectedFiles = [];

function goBack() {
  window.location.href = '/static/institute.html';
}

async function loadPatients() {
  if (!token) {
    alert('Please log in first');
    window.location.href = 'login.html';
    return;
  }
  try {
    const res = await fetch(`${baseUrl}/api/dicom-images/?page_size=1000`, {
      headers: { 
        'Authorization': `Token ${token}`,
        'Content-Type': 'application/json'
      }
    });
    
    if (!res.ok) {
      throw new Error(`HTTP error! status: ${res.status}`);
    }
    
    const data = await res.json();
    
    const patientsMap = new Map();
    const images = data.results || [];
    
    images.forEach(img => {
      if (img.patient_id && !patientsMap.has(img.patient_id)) {
        patientsMap.set(img.patient_id, {
          patient_id: img.patient_id,
          name: img.patient_name || 'Unknown',
          patient_sex: img.patient_sex || '',
          patient_birth_date: img.patient_birth_date || ''
        });
      }
    });
    
    const patientSelect = document.getElementById('patient-id');
    patientSelect.innerHTML = '<option value="">— Add New Patient —</option>';
    
    patientsMap.forEach(patient => {
      const option = document.createElement('option');
      option.value = patient.patient_id;
      option.textContent = `${patient.name} (ID: ${patient.patient_id})`;
      patientSelect.appendChild(option);
    });
    
  } catch (err) {
    console.error('Error loading patients:', err);
  }
}

function updateFileList() {
  const fileListEl = document.getElementById('file-list');
  
  if (selectedFiles.length === 0) {
    fileListEl.classList.add('hidden');
    fileListEl.innerHTML = '';
    return;
  }
  
  fileListEl.classList.remove('hidden');
  fileListEl.innerHTML = selectedFiles.map((file, index) => {
    return `
      <div class="file-item">
        <span>
          ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)
        </span>
        <button type="button" onclick="removeFile(${index})">Remove</button>
      </div>
    `;
  }).join('');
}

window.removeFile = function(index) {
  selectedFiles.splice(index, 1);
  updateFileList();
};

document.getElementById('dicom-file-input').addEventListener('change', (e) => {
  const newFiles = Array.from(e.target.files);
  
  if (newFiles.length === 0) {
    return;
  }
  
  const validFiles = newFiles.filter(file => file.name.toLowerCase().endsWith('.dcm'));
  
  if (validFiles.length !== newFiles.length) {
    const msgEl = document.getElementById('form-message');
    msgEl.textContent = 'Only DICOM (.dcm) files are allowed. Some files were skipped.';
    msgEl.className = 'error';
    msgEl.classList.remove('hidden');
    setTimeout(() => {
      msgEl.classList.add('hidden');
    }, 3000);
  }
  
  if (validFiles.length > 0) {
    selectedFiles = [...selectedFiles, ...validFiles];
    updateFileList();
  }
  
  e.target.value = '';
});

document.getElementById('patient-upload-form').addEventListener('submit', async e => {
  e.preventDefault();
  const form = e.target;
  const msgEl = document.getElementById('form-message');
  const submitButton = e.target.querySelector('button[type="submit"]');
  const patientId = form.patient_id.value;
  const centerName = form.center.value.trim();
  const isEmergency = form.emergency.checked;

  if (selectedFiles.length === 0) {
    msgEl.textContent = 'Please select at least one DICOM file.';
    msgEl.className = 'error';
    msgEl.classList.remove('hidden');
    return;
  }

  if (!centerName) {
    msgEl.textContent = 'Center name is required.';
    msgEl.className = 'error';
    msgEl.classList.remove('hidden');
    return;
  }

  try {
    submitButton.disabled = true;
    submitButton.textContent = 'Uploading...';
    
    msgEl.textContent = `Uploading ${selectedFiles.length} DICOM file(s)...`;
    msgEl.className = 'info';
    msgEl.classList.remove('hidden');

    let successCount = 0;
    let failedCount = 0;
    let duplicateCount = 0;
    const failedFiles = [];
    const duplicateFiles = [];

    for (let i = 0; i < selectedFiles.length; i++) {
      const file = selectedFiles[i];
      const uploadData = new FormData();
      uploadData.append('dicom_file', file);
      uploadData.append('center_name', centerName);
      
      if (patientId) {
        uploadData.append('patient_id', patientId);
      }
      
      if (isEmergency) {
        uploadData.append('is_emergency', 'true');
      }

      try {
        const uploadRes = await fetch(`${baseUrl}/api/dicom/receive/`, {
          method: 'POST',
          headers: { 
            'Authorization': `Token ${token}`
          },
          body: uploadData
        });

        const uploadResult = await uploadRes.json();
        
        if (uploadRes.ok && uploadResult.success) {
          successCount++;
        } else if (uploadRes.status === 409 && uploadResult.duplicate) {
          duplicateCount++;
          duplicateFiles.push(file.name);
        } else {
          failedCount++;
          failedFiles.push(file.name);
        }
        
        msgEl.textContent = `Uploading: ${i + 1}/${selectedFiles.length} (${successCount} succeeded, ${duplicateCount} duplicates, ${failedCount} failed)`;
        
      } catch (err) {
        console.error(`Failed to upload ${file.name}:`, err);
        failedCount++;
        failedFiles.push(file.name);
      }
    }

    submitButton.disabled = false;
    submitButton.textContent = 'Submit';

    if (failedCount === 0 && duplicateCount === 0) {
      msgEl.textContent = `All ${successCount} DICOM files uploaded successfully`;
      msgEl.className = 'success';
      
      selectedFiles = [];
      updateFileList();
      
      await loadPatients();
      
      setTimeout(() => {
        msgEl.classList.add('hidden');
      }, 5000);
    } else {
      let message = `Upload completed: ${successCount} succeeded`;
      
      if (duplicateCount > 0) {
        message += `, ${duplicateCount} duplicates (skipped)`;
        if (duplicateFiles.length > 0 && duplicateFiles.length <= 5) {
          message += `. Duplicates: ${duplicateFiles.join(', ')}`;
        }
      }
      
      if (failedCount > 0) {
        message += `, ${failedCount} failed`;
        if (failedFiles.length > 0 && failedFiles.length <= 5) {
          message += `. Failed: ${failedFiles.join(', ')}`;
        }
      }
      
      msgEl.textContent = message;
      msgEl.className = duplicateCount > 0 && failedCount === 0 ? 'warning' : 'error';
      
      selectedFiles = selectedFiles.filter((file, index) => 
        !duplicateFiles.includes(file.name) && !failedFiles.includes(file.name)
      );
      updateFileList();
    }

  } catch (err) {
    submitButton.disabled = false;
    submitButton.textContent = 'Submit';
    msgEl.textContent = `Error: ${err.message}`;
    msgEl.className = 'error';
    msgEl.classList.remove('hidden');
  }
});

window.onload = () => {
  const centerInput = document.querySelector('input[name="center"]');
  const instituteInput = document.querySelector('input[name="institute_name"]');
  centerInput.value = localStorage.getItem('center_name') || '';
  instituteInput.value = localStorage.getItem('institute_name') || '';
  
  document.getElementById('file-list').classList.add('hidden');
  document.getElementById('form-message').classList.add('hidden');
  
  loadPatients();
};