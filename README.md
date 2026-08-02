# Turnera Pilates

Sistema de turnos para un estudio de pilates: login con dos roles
(administrador / alumno), gestión de horarios, reserva de clases con
cupo máximo, sistema de recuperación de clases, alumnas/os de día y
horario fijo o de "clases libres", avisos por mail y campanita de
cupo liberado.

## Estructura del proyecto

```
turnera_pilates/
├── app/
│   ├── __init__.py       # application factory
│   ├── extensions.py     # db, login_manager, bcrypt
│   ├── models.py         # Usuario, Plan, Horario, Clase, Reserva,
│   │                     # InscripcionFija, AvisoCupo
│   ├── decorators.py      # @admin_required
│   ├── auth/              # login / logout
│   ├── admin/              # panel del administrador
│   ├── alumno/              # panel del alumno
│   ├── integrations/       # Google Calendar y envío de emails
│   ├── templates/
│   └── static/
├── config.py             # configuración y reglas de negocio
├── run.py                # arranca el servidor
├── seed.py                # crea la base de datos y el admin inicial
├── migrar_datos.py        # actualiza una base de datos ya existente
├── enviar_recordatorios.py # recordatorio del día anterior (correr 1 vez/día)
└── requirements.txt
```

## Cómo correrlo (primera vez)

```bash
# 1. Creá un entorno virtual (recomendado)
python -m venv venv
source venv/bin/activate      # en Windows: venv\Scripts\activate

# 2. Instalá las dependencias
pip install -r requirements.txt

# 3. Creá la base de datos y el usuario admin inicial
python seed.py

# 4. Arrancá el servidor
python run.py
```

Abrí `http://127.0.0.1:5000` en el navegador.

**Usuario admin inicial:**
- Email: `admin@estudio.com`
- Contraseña: `cambiar123`

⚠️ Cambiá esta contraseña en cuanto tengamos la pantalla de gestión
de usuarios lista.

### Si ya tenías una base de datos de antes de este cambio

Corré `python migrar_datos.py` una vez: agrega las tablas/columnas
nuevas (modalidad fija/libre, horarios fijos, campanita de cupo,
recordatorios) y actualiza los planes a los 4 vigentes, sin borrar
nada de lo que ya tenías cargado.

## Planes, modalidad fija y clases libres

Los planes del estudio son 4: **4, 8, 12 y 16 clases por mes**. Se
gestionan en la base de datos (los crea `seed.py`/`migrar_datos.py`);
el admin le asigna un plan a cada alumno desde "Usuarios".

Cada alumno tiene una **modalidad**:

- **Día y horario fijo**: el admin lo asigna a uno o más horarios
  semanales fijos desde Usuarios → "Horarios fijos" (ej: "todos los
  Lunes 10hs"). A partir de ahí queda reservada/o automáticamente cada
  vez que se generan las clases de ese horario, sin tener que entrar
  a elegir el día todos los meses. Si cancela una clase puntual (con
  la anticipación mínima configurada), se le acredita una clase de
  recuperación para elegir otra clase del mes con cupo disponible -
  su horario fijo no se pierde, sigue reservado las semanas
  siguientes.
- **Clases libres**: no tiene horario fijo. Usa el saldo mensual
  (`clases_disponibles`) para reservar la clase que quiera, el día
  que quiera, mientras haya cupo.

El saldo mensual (`clases_disponibles`) **nunca se resetea solo**: el
admin lo restablece a mano cuando corresponda, con el botón
"Restablecer saldo" en la lista de usuarios (o editando el número
directamente).

## Horarios y camillas

El admin carga la grilla semanal (día + hora) en "Horarios": esa
plantilla vale para todos los meses. Si un día/horario puntual no va
a haber clase (feriado, etc.), se desactiva o se elimina desde ahí sin
afectar el resto de las semanas.

Desde "Clases" el admin ve, para cualquier día, cada clase con la
cantidad de camillas ocupadas (`X / cupo_maximo`) y el listado de
quiénes se anotaron (con su modalidad y si es un turno de
recuperación).

## Avisos por mail y campanita de cupo

El sistema manda 3 tipos de mail (usando el SMTP que configures, ver
más abajo):

1. **Confirmación**: al reservar un turno.
2. **Recordatorio**: el día anterior a la clase. Este NO lo dispara el
   sistema solo - hay que programar `python enviar_recordatorios.py`
   para que corra una vez por día (Programador de tareas de Windows,
   o cron en Linux/Mac; ver pasos concretos para Windows más abajo).
3. **Aviso de cupo liberado (🔔 campanita)**: si una clase está llena,
   el alumno puede tocar "Avisarme" para esa clase. Si alguien cancela
   y se libera un lugar, se le manda un mail a todas/os las/os que
   estén esperando.

### Configurar el envío de mails con Gmail

Igual que con Google Calendar: si no está configurado, el sistema
sigue funcionando igual, simplemente no manda mails (`MAIL_HABILITADO`
queda en `False`).

1. Activá la verificación en 2 pasos en la cuenta de Gmail del
   estudio (Google lo exige para poder generar una contraseña de
   aplicación).
2. Generá una ["contraseña de aplicación"](https://myaccount.google.com/apppasswords)
   — **no** es la contraseña normal de la cuenta, es una clave de 16
   letras que Google genera específicamente para esto.
3. Copiá `.env.example` a un archivo nuevo llamado `.env` (en la raíz
   del proyecto, al lado de `run.py`) y completá:

   ```
   MAIL_USUARIO=turnera@estudio.com
   MAIL_PASSWORD=la-contraseña-de-aplicación-de-16-letras
   ```

   El archivo `.env` ya está en `.gitignore`: nunca se sube al
   repositorio. La app lo lee solo automáticamente al arrancar
   (`python run.py`, `python seed.py`, `python migrar_datos.py`,
   `python enviar_recordatorios.py`) - no hace falta configurar nada
   más en PowerShell ni en el sistema.

`MAIL_SERVIDOR` (`smtp.gmail.com`) y `MAIL_PUERTO` (`587`) ya vienen
con el valor correcto para Gmail por defecto; solo hace falta tocarlos
si el día de mañana cambian a otro proveedor de mail.

### Programar el recordatorio diario en Windows (mientras corre en local)

Mientras el sistema corra en tu PC (no publicado online todavía), el
recordatorio del día anterior necesita que la PC esté prendida a la
hora programada. Pasos con el Programador de tareas de Windows:

1. Abrí "Programador de tareas" (buscalo en el menú de inicio).
2. "Crear tarea básica..." → nombre: `Turnera - recordatorios`.
3. Desencadenador: **Diariamente**, a la hora que prefieras (ej: 20:00).
4. Acción: **Iniciar un programa**.
   - Programa o script: `C:\Users\gujar\OneDrive\Escritorio\turnera_pilates\venv\Scripts\python.exe`
   - Argumentos: `enviar_recordatorios.py`
   - Iniciar en: `C:\Users\gujar\OneDrive\Escritorio\turnera_pilates`
5. Finalizar. Podés probarla ya mismo con clic derecho → "Ejecutar", y
   revisar en la pestaña "Historial" que haya corrido sin errores.

Cuando el día de mañana se despliegue online, este paso se reemplaza
por la tarea programada nativa del hosting que se elija (ya no
dependería de que la PC esté prendida).

## Integración con Google Calendar (opcional)

El sistema funciona perfecto sin esto (usa su propio calendario). Si
querés que cada turno reservado también aparezca en un Google
Calendar del estudio, seguí estos pasos (una sola vez, ~10 minutos):

1. Andá a [Google Cloud Console](https://console.cloud.google.com/) y creá un proyecto nuevo (o usá uno existente).
2. Buscá "Google Calendar API" en la barra de búsqueda y habilitala.
3. Andá a "Credenciales" → "Crear credenciales" → "Cuenta de servicio". Ponele un nombre (ej: "turnera-pilates") y creala.
4. Entrá a la cuenta de servicio recién creada → pestaña "Claves" → "Agregar clave" → "Crear clave nueva" → tipo **JSON**. Se descarga un archivo.
5. Renombrá ese archivo a `google-credentials.json` y ponelo en la raíz del proyecto (al lado de `run.py`). **Nunca lo subas a un repositorio público** (agregalo a tu `.gitignore`).
6. Abrí [Google Calendar](https://calendar.google.com) con la cuenta del estudio, creá (o elegí) el calendario que querés usar, andá a su configuración → "Compartir con determinadas personas" → agregá el email de la cuenta de servicio (algo como `turnera-pilates@tu-proyecto.iam.gserviceaccount.com`, lo encontrás en la cuenta de servicio) con permiso **"Hacer cambios en los eventos"**.
7. En la configuración de ese calendario, copiá el "ID de calendario" (sección "Integrar calendario").
8. Definí la variable de entorno `GOOGLE_CALENDAR_ID` con ese valor antes de correr `python run.py`:
   ```bash
   export GOOGLE_CALENDAR_ID="ese-id-que-copiaste@group.calendar.google.com"
   python run.py
   ```

Listo: a partir de acá, cada turno reservado crea un evento en ese calendario, y cada cancelación lo borra. Si en algún momento Google Calendar no responde (sin internet, credenciales vencidas, etc.), la turnera sigue funcionando igual - la integración nunca bloquea una reserva.

## Estado actual

Lo que ya funciona:
- [x] Estructura del proyecto y base de datos (SQLite)
- [x] Login / logout con roles (admin / alumno)
- [x] Modelos: Usuario, Plan, Horario, Clase, Reserva, InscripcionFija, AvisoCupo
- [x] Panel admin: crear/editar/eliminar usuarios, con modalidad fija/libre
- [x] Panel admin: configurar días y horarios disponibles (grilla semanal, vale para todos los meses)
- [x] Panel admin: asignar horarios fijos a un alumno
- [x] Panel admin: restablecer saldo mensual a mano
- [x] Panel admin: ver clases del día con camillas ocupadas y quién se anotó
- [x] Panel alumno: calendario para elegir día y horario del mes (modalidad libre)
- [x] Lógica de reserva (respetando cupo máximo y saldo del plan)
- [x] Lógica de cancelación y sistema de recuperación de clases
- [x] Reserva automática de alumnas/os de horario fijo al generarse las clases
- [x] Mails: confirmación de reserva, recordatorio del día anterior, campanita de cupo liberado
- [x] Integración con Google Calendar
