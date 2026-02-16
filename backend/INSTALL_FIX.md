# Fix for Missing Package Installation

## Issue
The `djangorestframework-simplejwt` package cannot be installed due to:
1. `PIP_NO_INDEX` environment variable blocking PyPI access
2. Proxy configuration issues

## Solutions

### Option 1: Unset Environment Variables (Recommended)

In PowerShell, run:
```powershell
$env:PIP_NO_INDEX = $null
$env:HTTP_PROXY = $null
$env:HTTPS_PROXY = $null
pip install djangorestframework-simplejwt
```

Or permanently unset in your conda environment:
```powershell
conda env config vars unset PIP_NO_INDEX -n langchain_env
```

### Option 2: Install Without Proxy

```powershell
pip install --proxy="" djangorestframework-simplejwt
```

### Option 3: Use Conda (if available)

```powershell
conda install -c conda-forge djangorestframework-simplejwt
```

### Option 4: Install All Requirements

After fixing the environment variables:
```powershell
cd backend
pip install -r requirements.txt
```

## Verify Installation

```powershell
python -c "import rest_framework_simplejwt; print('OK')"
```

If this prints "OK", the package is installed correctly.

## Then Run Migrations

```powershell
python manage.py makemigrations
python manage.py migrate
```
