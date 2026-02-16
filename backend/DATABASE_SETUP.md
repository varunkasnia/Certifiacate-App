# Database Setup Guide

## Option 1: Use SQLite (Quick Start - Recommended for Development)

SQLite requires no setup and works immediately. Update your `.env` file:

```env
# Use SQLite instead of PostgreSQL
USE_SQLITE=True
```

Then update `settings.py` to check for this flag, or simply change the database engine.

**Pros:** No installation needed, works immediately
**Cons:** Not suitable for production, limited concurrent connections

## Option 2: Start PostgreSQL with Docker

1. **Start Docker Desktop** (if installed)
2. Run:
   ```powershell
   docker-compose up -d db
   ```
3. Wait for PostgreSQL to start (about 10-30 seconds)
4. Verify it's running:
   ```powershell
   docker ps
   ```

## Option 3: Install PostgreSQL Manually

1. **Download PostgreSQL** from https://www.postgresql.org/download/windows/
2. **Install** with default settings
3. **Create database**:
   ```powershell
   # Open PostgreSQL command line (psql)
   psql -U postgres
   
   # Then in psql:
   CREATE DATABASE livequiz;
   \q
   ```
4. **Update `.env`** if your PostgreSQL uses different credentials

## Option 4: Use Existing PostgreSQL

If you already have PostgreSQL installed:

1. **Start PostgreSQL service**:
   ```powershell
   # Check if service is running
   Get-Service postgresql*
   
   # Start if not running
   Start-Service postgresql-x64-15  # Adjust version number
   ```

2. **Create database**:
   ```powershell
   psql -U postgres -c "CREATE DATABASE livequiz;"
   ```

3. **Verify connection**:
   ```powershell
   psql -U postgres -d livequiz -c "SELECT version();"
   ```

## After Database is Ready

Once PostgreSQL is running or SQLite is configured:

```powershell
cd backend
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
```

## Troubleshooting

### "Connection refused" error
- PostgreSQL is not running
- Check if service is running: `Get-Service postgresql*`
- Check if port 5432 is in use: `netstat -an | findstr 5432`

### "Database does not exist" error
- Create the database: `CREATE DATABASE livequiz;`

### "Authentication failed" error
- Check username/password in `.env`
- Default PostgreSQL superuser is usually `postgres`
