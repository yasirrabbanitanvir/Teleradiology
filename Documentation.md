# DICOM PACS Project Documentation

---

## Project Structure

```
my_pacs/
│
├── dicom_project/
│   ├── db.sqlite3
│   ├── manage.py
│   ├── dicom_project/
│   │   ├── __init__.py
│   │   ├── asgi.py
│   │   ├── settings.py
│   │   ├── urls.py
│   │   ├── wsgi.py
│   │   └── __pycache__/
│   ├── media/
│   │   ├── dicom_files/
│   │   └── reports/
│   ├── myapp/
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   ├── permissions.py
│   │   ├── serializers.py
│   │   ├── tests.py
│   │   ├── urls.py
│   │   ├── views.py
│   │   ├── __pycache__/
│   │   ├── migrations/
│   │   └── static/
│   ├── staticfiles/
│   │   ├── admin.html
│   │   ├── doctor.html
│   │   ├── form.html
│   │   ├── index.html
│   │   ├── login.html
│   │   ├── logo.png
│   │   └── js/
│   │       ├── script.js
│   │       └── form.js
│   │   └── admin/
│   │       └── ...
└── project_env/
```

---

## How to Run the Project

1. **Activate the virtual environment:**
   ```bash
   cd my_pacs
   project_env\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install django djangorestframework
   ```

3. **Apply migrations:**
   ```bash
   cd dicom_project
   python manage.py migrate
   ```

4. **Create a superuser:**
   ```bash
   python manage.py createsuperuser
   ```

5. **Run the development server:**
   ```bash
   python manage.py runserver
   ```

6. **Access the app:**
   - Admin: `http://127.0.0.1:8000/admin/`
   - Web pages: `http://127.0.0.1:8000/`

---

## Static Folder Documentation

Your static folder contains all the frontend assets: HTML templates, JavaScript, CSS, and images.

### Static Folder Structure

```
staticfiles/
├── admin.html         # Admin dashboard page
├── doctor.html        # Doctor dashboard page
├── form.html          # DICOM upload form
├── index.html         # Main landing page
├── login.html         # Login page
├── logo.png           # Application logo
├── js/
│   ├── script.js      # Main JavaScript logic
│   └── form.js        # Form-specific JavaScript
└── admin/
    └── ...            # Additional admin static files
```

### Important Static Files

- **login.html**: Login page for all users. Contains a form for username and password.
- **admin.html**: Admin dashboard. Displays user, center, and system management options.
- **doctor.html**: Doctor’s dashboard. Lists assigned studies and allows report submission.
- **form.html**: DICOM file upload form for center users.
- **index.html**: Main landing page; may redirect users based on authentication.
- **js/script.js**: Handles dashboard logic, API calls, and DOM updates.
- **js/form.js**: Handles upload form validation and AJAX file uploads.
- **logo.png**: Application logo for branding.

---

## Most Important Backend Files

| File/Folder         | Purpose/Role                                      |
|---------------------|---------------------------------------------------|
| models.py           | Database models (users, centers, patients, studies)|
| views.py            | Handles HTTP requests, API endpoints, uploads     |
| serializers.py      | Converts model data to/from JSON for APIs         |
| urls.py             | Maps URLs to views and endpoints                  |
| admin.py            | Registers models for Django admin                 |

---

### File Details

#### `models.py`
- Defines all database tables and relationships.
- Typical models: UserProfile, Center, Patient, DicomStudy.

#### `views.py`
- Contains logic for listing, creating, updating, and deleting records.
- Handles file uploads and user actions.

#### `serializers.py`
- Converts model instances to JSON and vice versa for API endpoints.

#### `urls.py`
- Maps URLs to views for API endpoints and web pages.

#### `admin.py`
- Registers models for Django admin interface.

---

## Usage Instructions

- **Admins**: Manage users, centers, and assignments via the admin interface.
- **Centers**: Upload DICOM files for patients.
- **Doctors**: View assigned studies and write reports.
- **All data**: Stored in `db.sqlite3`.

---

## Security & Testing

- **Authentication**: Required for all views.
- **Role-based access**: Enforced in permissions.
- **File upload validation**: Ensures only valid files are stored.
- **Testing**: Use `tests.py` for unit tests (`python manage.py test`).

---

## Summary Table

| File/Folder         | Purpose/Role                                      |
|---------------------|---------------------------------------------------|
| staticfiles/        | All frontend assets (HTML, JS, CSS, images)       |
| login.html          | User login page                                   |
| admin.html          | Admin dashboard                                   |
| doctor.html         | Doctor dashboard                                  |
| form.html           | DICOM upload form                                 |
| js/script.js        | Dashboard logic, API calls                        |
| js/form.js          | Upload form logic                                 |
| logo.png            | Application logo                                  |
| models.py           | Database models                                   |
| views.py            | Request handling, business logic                  |
| serializers.py      | Data serialization for APIs                       |
| urls.py             | URL routing                                       |
| admin.py            | Django admin configuration                        |

---

## Notes

- For detailed code explanations, open any file and review the comments or ask for a line-by-line walkthrough.
- Update dependencies and settings as needed for your environment.
