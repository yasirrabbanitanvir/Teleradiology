@echo off
cd /d D:\pacs\telesoftweb
call venv\Scripts\activate

start "" waitress-serve --listen=127.0.0.1:8000 dicom_project.wsgi:application

timeout /t 5

echo [INFO] Starting NGINX server...
cd D:\pacs\telesoftweb\nginx-1.28.0

start "" nginx.exe -c "D:\pacs\telesoftweb\nginx-1.28.0\conf\nginx.conf" -p "D:\pacs\telesoftweb\nginx-1.28.0"

echo [INFO] All servers started successfully
exit