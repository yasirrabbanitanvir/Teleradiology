const baseUrl = window.location.origin;

let token = localStorage.getItem('token');
let role = localStorage.getItem('role');

if (!token || role !== 'Admin') {
  alert('Please log in as Admin');
  window.location.href = 'login.html';
}

async function fetchCenters() {
  try {
    const res = await fetch(`${baseUrl}/api/centers/`, {
      headers: { 'Authorization': `Token ${token}` }
    });
    if (!res.ok) throw new Error('Failed to fetch centers');
    const centers = await res.json();
    const centerSelect = document.querySelector('select[name="center"]');
    centers.forEach(center => {
      const option = document.createElement('option');
      option.value = center.id;
      option.textContent = center.name;
      centerSelect.appendChild(option);
    });
  } catch (err) {
    console.error('Error fetching centers:', err);
  }
}

async function fetchUsers() {
  try {
    const res = await fetch(`${baseUrl}/api/users/`, {
      headers: { 'Authorization': `Token ${token}` }
    });
    if (!res.ok) throw new Error('Failed to fetch users');
    const users = await res.json();
    const tbody = document.getElementById('user-table-body');
    tbody.innerHTML = '';
    users.forEach(user => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${user.username}</td>
        <td>${user.profile ? user.profile.role : 'Unknown'}</td>
        <td>${user.profile && user.profile.center ? user.profile.center.name : 'N/A'}</td>
        <td><button class="action-btn" onclick="deleteUser('${user.id}')">Delete</button></td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error('Error fetching users:', err);
  }
}

async function deleteUser(userId) {
  if (!confirm('Are you sure you want to delete this user?')) return;
  try {
    const res = await fetch(`${baseUrl}/api/users/${userId}/`, {
      method: 'DELETE',
      headers: { 'Authorization': `Token ${token}` }
    });
    if (!res.ok) throw new Error('Failed to delete user');
    alert('User deleted successfully');
    fetchUsers();
  } catch (err) {
    console.error('Error deleting user:', err);
    alert('Error deleting user');
  }
}

document.getElementById('create-user-form').addEventListener('submit', async e => {
  e.preventDefault();
  const form = e.target;
  const msgEl = document.getElementById('form-message');
  const username = form.username.value;
  const password = form.password.value;
  const role = form.role.value;
  const centerId = form.center.value;

  try {
    const userData = {
      username,
      password,
      role,
      center: role === 'Center' ? centerId : null
    };
    const res = await fetch(`${baseUrl}/api/users/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Token ${token}`
      },
      body: JSON.stringify(userData)
    });
    if (!res.ok) {
      const errorData = await res.json();
      throw new Error(errorData.detail || 'User creation failed');
    }
    msgEl.textContent = 'User created successfully!';
    msgEl.className = 'success';
    form.reset();
    fetchUsers();
  } catch (err) {
    console.error('Error creating user:', err);
    msgEl.textContent = `${err.message}`;
    msgEl.className = 'error';
  }
});

function logout() {
  localStorage.removeItem('token');
  localStorage.removeItem('role');
  window.location.href = 'login.html';
}

window.onload = () => {
  fetchCenters();
  fetchUsers();
};