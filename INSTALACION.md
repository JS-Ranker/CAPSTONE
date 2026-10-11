# Guía de instalación local – TTDH Automation

Paso a paso para dejar el proyecto corriendo en un PC con **Windows 10/11**. Si sigues los pasos en orden, al final tendrás:

- La base de datos `TTDH_Automation` en tu SQL Server.
- La API (FastAPI) en <http://localhost:8000>.
- La aplicación web (React) en <http://localhost:5173>.

Todos los comandos son para **PowerShell** (no para `cmd`). Se ejecutan desde la carpeta raíz del repositorio (`CAPSTONE`), salvo que el paso diga otra cosa.

---

## 1. Instalar los programas (una sola vez)

| Programa | Versión | Dónde descargarlo | Ojo con |
|---|---|---|---|
| Git | cualquiera reciente | <https://git-scm.com/download/win> | Opciones por defecto. |
| Python | **3.12** | <https://www.python.org/downloads/> | Marcar **"Add python.exe to PATH"** en la primera pantalla del instalador. |
| Node.js | **22 LTS** (o 20 LTS) | <https://nodejs.org/> | Opciones por defecto. |
| SQL Server | 2019 o superior, edición **Developer** o **Express** | <https://www.microsoft.com/es-es/sql-server/sql-server-downloads> | Instalación "Básica". Anota el **nombre de la instancia** que muestra al final (ver paso 3). |
| ODBC Driver for SQL Server | **17** o **18** | <https://learn.microsoft.com/es-es/sql/connect/odbc/download-odbc-driver-for-sql-server> | Anota cuál instalaste: va en el `.env` (paso 5). |
| sqlcmd | cualquiera | En PowerShell: `winget install Microsoft.Sqlcmd` | Cierra y abre PowerShell después de instalarlo. |
| Tesseract OCR | 5.x | <https://github.com/UB-Mannheim/tesseract/wiki> | En "Choose Components" → *Additional language data* → marcar **Spanish**. Sin el español, la extracción OCR falla. |

> SQL Server Management Studio (SSMS) es opcional, pero cómodo para mirar las tablas.

> **No clones el repositorio dentro de OneDrive** (Escritorio o Documentos sincronizados). OneDrive intenta sincronizar `node_modules` y `.venv` y causa errores raros. Usa, por ejemplo, `C:\proyectos\`.

### Verificar que quedó todo instalado

Abre una **PowerShell nueva** y ejecuta:

```powershell
git --version
python --version          # debe decir Python 3.12.x
node --version            # v22.x o v20.x
sqlcmd -?                 # muestra la ayuda de sqlcmd
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs    # la lista debe incluir "spa"
```

Si alguno falla, revisa la sección [Problemas comunes](#9-problemas-comunes) antes de seguir.

---

## 2. Clonar el repositorio

```powershell
cd C:\proyectos            # o la carpeta que prefieras (fuera de OneDrive)
git clone https://github.com/JS-Ranker/CAPSTONE.git
cd CAPSTONE
```

---

## 3. Averiguar el nombre de tu servidor SQL

Depende de cómo se instaló SQL Server:

```powershell
Get-Service MSSQL*
```

| Si aparece el servicio… | Tu servidor es |
|---|---|
| `MSSQLSERVER` (típico de la edición Developer) | `localhost` |
| `MSSQL$SQLEXPRESS` (típico de la edición Express) | `localhost\SQLEXPRESS` |

El servicio debe estar en estado **Running**. Si está detenido: `Start-Service MSSQLSERVER` (o `Start-Service 'MSSQL$SQLEXPRESS'`) en una PowerShell abierta como administrador.

Guarda el nombre en una variable para los pasos siguientes (cámbialo si te tocó Express):

```powershell
$SERVIDOR = "localhost"
```

---

## 4. Crear la base de datos

Los scripts se ejecutan **en orden** y desde su carpeta. Usan autenticación de Windows (`-E`); `-f 65001` es necesario para que los acentos queden bien.

```powershell
cd "Fase 2\Evidencias Proyecto\Evidencias de sistema\Base de datos"
sqlcmd -S $SERVIDOR -E -C -f 65001 -i 01_crear_base_datos.sql
sqlcmd -S $SERVIDOR -E -C -f 65001 -i 02_tablas.sql
sqlcmd -S $SERVIDOR -E -C -f 65001 -i 03_datos_iniciales.sql
sqlcmd -S $SERVIDOR -E -C -f 65001 -i 04_recepcion.sql
sqlcmd -S $SERVIDOR -E -C -f 65001 -i 05_remitentes.sql
```

Comprobar que quedó bien (debe mostrar **4**, los roles iniciales):

```powershell
sqlcmd -S $SERVIDOR -E -C -Q "SELECT COUNT(*) FROM TTDH_Automation.dbo.Roles"
```

> **Cuidado:** `02_tablas.sql` borra y recrea todas las tablas. Si lo vuelves a ejecutar, después hay que correr de nuevo `03`, `04` y `05`. Los scripts `04` y `05` no borran datos y se pueden ejecutar las veces que quieras.

Vuelve a la raíz del repositorio:

```powershell
cd ..\..\..\..
```

---

## 5. Backend (API en Python)

### 5.1 Entorno virtual y dependencias

```powershell
cd "Fase 2\Evidencias Proyecto\Evidencias de sistema\Aplicación\backend"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Si `Activate.ps1` da un error de *"la ejecución de scripts está deshabilitada"*, ejecuta esto una vez y vuelve a activar:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Con el entorno activo, la línea de PowerShell empieza con `(.venv)`.

### 5.2 Archivo de configuración `.env`

```powershell
Copy-Item .env.example .env
notepad .env
```

Revisa estas líneas y ajústalas a tu PC:

| Variable | Qué poner |
|---|---|
| `DB_SERVER` | El servidor del paso 3: `localhost` o `localhost\SQLEXPRESS`. |
| `DB_DRIVER` | `ODBC Driver 17 for SQL Server` o `ODBC Driver 18 for SQL Server`, según el que instalaste. |
| `DB_TRUSTED_CONNECTION` | Dejar `yes` (autenticación de Windows). |
| `TESSERACT_CMD` | Dejar el valor por defecto si instalaste Tesseract en la ruta normal. |

Lo demás (`IMAP_*`, `SFTP_*`) puede quedar como está: si `IMAP_SERVIDOR` va vacío, simplemente no se revisa el correo.

> El `.env` **nunca** se sube al repositorio (ya está en el `.gitignore`). No pongas contraseñas reales en `.env.example`.

### 5.3 Probar y levantar la API

```powershell
python -m pytest
```

Tarda unos 3 minutos (las pruebas de OCR son lentas). Todas las pruebas deben pasar. Si falla `test_conexion_base_datos` o hay pruebas **skipped** con el mensaje *"SQL Server no disponible"*, el backend no logra conectarse a la base de datos: revisa `DB_SERVER` y `DB_DRIVER` en el `.env`.

```powershell
uvicorn app.main:app --reload
```

Deja **esta terminal abierta**: la API queda en <http://localhost:8000> y su documentación interactiva en <http://localhost:8000/docs>.

---

## 6. Frontend (aplicación web en React)

Abre **otra** PowerShell, ve a la raíz del repositorio y ejecuta:

```powershell
cd "Fase 2\Evidencias Proyecto\Evidencias de sistema\Aplicación\frontend"
npm ci
npm run dev
```

(`npm ci` instala exactamente las versiones del `package-lock.json`, así todos tenemos las mismas.)

Abre <http://localhost:5173>. Se muestra la pantalla **Gestión de Ingesta**.

---

## 7. Comprobar que todo funciona

| Revisa | Resultado esperado |
|---|---|
| <http://localhost:8000/api/health> | `{"estado":"ok", ...}` |
| <http://localhost:8000/api/health/db> | `{"estado":"ok","base_datos":"TTDH_Automation","roles":4}` |
| <http://localhost:5173> | Al pie del menú, la API y la base de datos aparecen conectadas. |
| Cargar un archivo de prueba | Arrastra `Aplicación\data\simulados\estructurados\02_nomina_valida.csv` a la zona de carga: debe aparecer en la tabla de lotes. |

Para probar con otros archivos usa **solo** los de `Aplicación\data\simulados\` (su README explica qué prueba cada uno). **Nunca** cargues datos reales de deudores.

---

## 8. El día a día

Cada vez que vayas a trabajar:

```powershell
git pull
```

**Terminal 1 – API:**

```powershell
cd "Fase 2\Evidencias Proyecto\Evidencias de sistema\Aplicación\backend"
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt     # solo si cambió requirements.txt
uvicorn app.main:app --reload
```

**Terminal 2 – Web:**

```powershell
cd "Fase 2\Evidencias Proyecto\Evidencias de sistema\Aplicación\frontend"
npm ci                              # solo si cambió package-lock.json
npm run dev
```

Si después de un `git pull` aparece un script nuevo en `Base de datos\` (por ejemplo `06_...sql`), ejecútalo como en el paso 4. Antes de volver a correr `02_tablas.sql`, recuerda que borra todo.

Para detener la API o la web: `Ctrl + C` en su terminal.

---

## 9. Problemas comunes

| Síntoma | Causa y solución |
|---|---|
| `python` abre la Microsoft Store o dice *"no se encontró Python"* | Python no quedó en el PATH. Reinstálalo marcando **"Add python.exe to PATH"**, y en *Configuración → Aplicaciones → Alias de ejecución de aplicaciones* desactiva `python.exe` y `python3.exe`. Abre una PowerShell nueva. |
| `sqlcmd` no se reconoce | Cierra y abre PowerShell después de instalarlo. Si sigue igual, reinstálalo con `winget install Microsoft.Sqlcmd`. |
| `sqlcmd` dice *"Login timeout expired"* o *"server was not found"* | Nombre de servidor incorrecto o servicio detenido. Revisa el paso 3 (¿es `localhost\SQLEXPRESS`?). |
| `/api/health/db` responde **503** o las pruebas salen *skipped* | El backend no se conecta a SQL Server o faltan las tablas. Revisa `DB_SERVER` y `DB_DRIVER` en `backend\.env` (el nombre del driver debe coincidir exactamente con el instalado; para verlo: `Get-OdbcDriver -Name "*SQL Server*"`) y que hayas ejecutado los 5 scripts del paso 4. |
| Error *"Data source name not found and no default driver specified"* | El `DB_DRIVER` del `.env` no coincide con el driver instalado. |
| Las pruebas se saltan con *"Falta ejecutar 'Base de datos/04_recepcion.sql'"* (o `05`) | Ejecuta ese script como en el paso 4. |
| *"No se encontró Tesseract"* | `TESSERACT_CMD` en el `.env` no apunta a `tesseract.exe`. |
| *"Tesseract no tiene instalado el idioma 'spa'"* | Reinstala Tesseract marcando *Additional language data → Spanish*. |
| `Activate.ps1` *"no se puede cargar… la ejecución de scripts está deshabilitada"* | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` y vuelve a activar. |
| `pip install` falla compilando un paquete | Estás usando una versión de Python distinta de la 3.12. Borra la carpeta `.venv`, instala Python 3.12 y crea el entorno con `py -3.12 -m venv .venv`. |
| La web dice *"No se pudo conectar con la API"* | La API no está corriendo: levántala en la Terminal 1 (paso 5.3). |
| *"address already in use"* / puerto 8000 o 5173 ocupado | Ya tienes otra API o web abierta en otra terminal. Ciérrala con `Ctrl + C`. |

Si después de esto sigue sin funcionar, comparte en el grupo el **mensaje de error completo** (copiado, no una foto) y el paso en que ocurrió.
