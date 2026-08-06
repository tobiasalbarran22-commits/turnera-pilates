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

El sistema manda 5 tipos de mail, todos desde la cuenta
**benincasapilates@gmail.com** (usando el SMTP que configures, ver
más abajo):

1. **Confirmación**: al reservar un turno.
2. **Recordatorio**: el día anterior a la clase. Este NO lo dispara el
   sistema solo - necesita que algo lo llame una vez por día (en
   desarrollo local, el Programador de tareas de Windows corriendo
   `enviar_recordatorios.py`; en producción, GitHub Actions llamando a
   una ruta del sitio - ver ambos casos más abajo).
3. **Aviso de cupo liberado (🔔 campanita)**: si una clase está llena,
   el alumno puede tocar "Avisarme" para esa clase. Si alguien cancela
   y se libera un lugar, se le manda un mail a todas/os las/os que
   estén esperando.
4. **Aviso de clase cancelada**: el admin cancela una clase puntual (o
   todas las de un día) y se le avisa a cada alumno que tenía un turno
   ahí, aclarando que se le acreditó una clase para recuperar.
5. **Aviso de última clase del plan**: al reservar, si esa reserva
   deja al alumno sin clases disponibles (saldo en 0), se le manda un
   recordatorio de que tiene que abonar para renovar el saldo.

### Configurar el envío de mails con Gmail

Igual que con Google Calendar: si no está configurado, el sistema
sigue funcionando igual, simplemente no manda mails (`MAIL_HABILITADO`
queda en `False`).

1. Activá la verificación en 2 pasos en la cuenta de Gmail
   **benincasapilates@gmail.com** (Google lo exige para poder generar
   una contraseña de aplicación).
2. Generá una ["contraseña de aplicación"](https://myaccount.google.com/apppasswords)
   para esa cuenta — **no** es la contraseña normal de la cuenta, es
   una clave de 16 letras que Google genera específicamente para esto.
3. Copiá `.env.example` a un archivo nuevo llamado `.env` (en la raíz
   del proyecto, al lado de `run.py`) y completá:

   ```
   MAIL_USUARIO=benincasapilates@gmail.com
   MAIL_PASSWORD=la-contraseña-de-aplicación-de-16-letras
   ```

   `MAIL_USUARIO` ya viene con `benincasapilates@gmail.com` por
   default en `config.py` (no hace falta repetirlo en `.env` salvo que
   quieras usar otra cuenta) — lo único que sí o sí hay que completar
   es `MAIL_PASSWORD`, porque esa nunca tiene un valor por default.

   El archivo `.env` ya está en `.gitignore`: nunca se sube al
   repositorio. La app lo lee solo automáticamente al arrancar
   (`python run.py`, `python seed.py`, `python migrar_datos.py`,
   `python enviar_recordatorios.py`) - no hace falta configurar nada
   más en PowerShell ni en el sistema.

`MAIL_SERVIDOR` (`smtp.gmail.com`) y `MAIL_PUERTO` (`587`) ya vienen
con el valor correcto para Gmail por defecto; solo hace falta tocarlos
si el día de mañana cambian a otro proveedor de mail.

### Programar el recordatorio diario en Windows (solo para desarrollo local)

Mientras el sistema corra en tu PC (no publicado online), el
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

**Una vez publicado el sitio online (ver más abajo), este método deja
de usarse** - ya no depende de `enviar_recordatorios.py` corriendo en
tu PC, sino de GitHub Actions llamando a una ruta del propio sitio.
Ver "Recordatorio diario en producción" dentro de la sección de
Render.

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

## Publicar el sitio online (Render)

Usamos [Render](https://render.com) para tenerlo publicado de verdad,
con **plan Starter** (no el free): a diferencia del plan gratuito, el
Starter no "duerme" por falta de uso (siempre responde al instante) y
soporta un **disco persistente**, así la base de datos no se pierde
en cada redeploy o reinicio. El repo ya incluye `render.yaml` con toda
esta configuración - Render la aplica sola.

### Si es la primera vez que se publica (Blueprint nuevo)

1. Entrá a [render.com](https://render.com) y creá una cuenta (podés
   registrarte directo con tu cuenta de GitHub).
2. Cargá un medio de pago en tu cuenta de Render (Account Settings →
   Billing) - el plan Starter y el disco son pagos (ver costos más
   abajo), Render no deja crearlos sin una tarjeta cargada.
3. Dashboard → **"New +"** → **"Blueprint"**.
4. Elegí el repositorio `turnera-pilates`. Render detecta el
   `render.yaml` solo y muestra el servicio que va a crear, con el
   plan Starter y un disco de 1GB ya declarados.
5. Te va a pedir completar los valores que **no** están en el repo por
   seguridad (nunca se suben credenciales a GitHub):
   - `MAIL_USUARIO`: `benincasapilates@gmail.com`
   - `MAIL_PASSWORD`: la contraseña de aplicación de 16 letras (la
     misma que está en tu `.env` local)
   - `TAREAS_SECRETO`: una clave larga y al azar (la vas a necesitar
     de nuevo en el paso de GitHub Actions, más abajo - guardala)
6. **"Apply"** / **"Create"** → Render instala las dependencias, corre
   `seed.py` (crea las tablas y el usuario admin) y levanta el
   servidor con `gunicorn`. Tarda unos minutos la primera vez.
7. Cuando termina, te da una URL fija tipo
   `https://turnera-pilates.onrender.com`.
8. Entrá con el usuario admin del seed (`admin@estudio.com` /
   `cambiar123`) y **cambiá esa contraseña enseguida** desde el panel.

### Si el servicio ya existía en el plan free (pasar a Starter + disco)

1. Cargá un medio de pago en tu cuenta de Render (Account Settings →
   Billing), si todavía no lo hiciste.
2. Hacé `git push` con el `render.yaml` actualizado (plan `starter` +
   bloque `disk`).
3. En el dashboard de Render, entrá al Blueprint del proyecto y
   sincronizalo con los cambios nuevos (o simplemente esperá: si el
   auto-deploy está activado, Render lo toma solo en cuanto detecta el
   push). Te va a mostrar el cambio de plan y el disco nuevo para
   confirmar el costo antes de aplicarlo.
4. Sumá la variable `TAREAS_SECRETO` en la sección "Environment" del
   servicio (Render solo pregunta automáticamente por las variables
   nuevas si el sync las detecta; si no te la pidió, agregala a mano).
   Usá una clave larga y al azar - la vas a necesitar de nuevo en el
   paso de GitHub Actions, más abajo.

**Costo aproximado**: plan Starter (USD 7/mes) + disco de 1GB
(centavos por mes) ≈ **USD 7-8/mes en total**. De sobra para una base
SQLite de un estudio de este tamaño durante años.

### Recordatorio diario en producción (GitHub Actions)

El mail de "mañana tenés clase" necesita que algo lo dispare una vez
por día - en producción ya no depende de `enviar_recordatorios.py`
corriendo en tu PC (ver la sección de más arriba, que ahora es solo
para desarrollo local), sino de una llamada automática desde GitHub:

1. En GitHub, andá al repositorio → **Settings** → **Secrets and
   variables** → **Actions** → **New repository secret**.
2. Nombre: `TAREAS_SECRETO`. Valor: la misma clave que pusiste en
   Render (paso anterior) - tiene que ser **idéntica** en los dos
   lugares, es lo que valida que el llamado es legítimo.
3. Listo - el workflow `.github/workflows/recordatorios.yml` ya está
   en el repo, programado para las 20:00 hora Argentina todos los
   días. Podés probarlo ya mismo sin esperar: pestaña **"Actions"** del
   repo → **"Recordatorio diario"** → **"Run workflow"**.

### Chequeos después de publicar

- Abrí la URL desde el celular y confirmá que responde al instante
  (sin la pantalla de "iniciando servidor" del plan free).
- Reservá un turno de prueba y confirmá que llega el mail de
  confirmación.
- Corré el workflow de GitHub Actions a mano una vez (paso 3 de
  arriba) y confirmá en los logs de Render que dice
  `recordatorios_enviados`.
- Hacé un redeploy de prueba (por ejemplo, con un commit chico) y
  confirmá que los usuarios/reservas siguen ahí después - eso confirma
  que el disco persistente está funcionando de verdad.

Cada vez que hagas `git push` a `main`, Render vuelve a desplegar solo
con los cambios nuevos, sin tocar los datos del disco persistente.

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
