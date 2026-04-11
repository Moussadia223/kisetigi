@echo off
title Déploiement Kise Tigi sur PythonAnywhere
color 0A
echo ===================================================
echo   Déploiement Kise Tigi sur PythonAnywhere
echo ===================================================
echo.
cd /d "%USERPROFILE%\Desktop\kisetigi"
if errorlevel 1 (
    echo Dossier kisetigi introuvable sur le Bureau.
    pause
    exit /b
)
echo 1. Vérification de l'archive ZIP...
if not exist KiseTigi.zip (
    echo Création de KiseTigi.zip...
    powershell -Command "Get-ChildItem -Path '%CD%' -Exclude 'venv','__pycache__','*.pyc','KiseTigi.zip','deployer_pythonanywhere.cmd','auto_pythonanywhere.cmd' | Compress-Archive -DestinationPath 'KiseTigi.zip' -Force"
    echo Archive créée.
) else (
    echo Archive KiseTigi.zip déjà présente.
)
echo.
echo 2. Ouverture de la page d'inscription PythonAnywhere...
start https://www.pythonanywhere.com/registration/register/?next=/accounts/signup/
echo.
echo 3. Après inscription et connexion, uploadez le fichier :
echo    - Fichier : %CD%\KiseTigi.zip
echo    - Page d'upload : https://www.pythonanywhere.com/user/votre_nom/files/
echo.
echo Appuyez sur une touche pour ouvrir la page d'upload.
pause >nul
start https://www.pythonanywhere.com/user/ton_nom/files/
echo.
echo ===================================================
echo   INSTRUCTIONS
echo ===================================================
echo 1. Créez un compte (gratuit).
echo 2. Dans l'onglet "Files", uploadez KiseTigi.zip.
echo 3. Extrayez l'archive (cliquez dessus -> Extract here).
echo 4. Allez dans "Web" -> "Add a new web app" -> Manual config (Python 3.10).
echo 5. Chemin du code : /home/votre_nom/kisetigi/run.py
echo 6. Créez un environnement virtuel.
echo 7. Console Bash : cd ~/kisetigi ^&^& pip install --user -r requirements.txt
echo 8. Rechargez l'application.
echo.
echo Votre site sera accessible sur https://votre_nom.pythonanywhere.com
echo.
pausepause)  
