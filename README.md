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

En producción no hace falta correr nada a mano: `seed.py` —que Render
ejecuta en cada arranque— aplica las mismas columnas nuevas. La lista
vive en `app/db_migrations.py`, y agregar una fila ahí es todo lo que
hace falta para que una columna nueva llegue al servidor. (Antes esa
lista vivía solo en `migrar_datos.py`, que en producción no corre
nadie: cualquier columna agregada a un modelo tiraba abajo la app en el
siguiente deploy.)

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
   `enviar_recordatorios.py`; en producción, un cron job de Render
   llamando a una ruta del sitio - ver ambos casos más abajo).
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
tu PC, sino de un cron job de Render llamando a una ruta del propio
sitio. Ver "Recordatorio diario en producción" dentro de la sección de
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

Usamos [Render](https://render.com) para tenerlo publicado de verdad.
El repo incluye `render.yaml` con **dos servicios**, que Render crea
juntos al conectar el repo:

1. **`turnera-pilates`** (web, plan **Starter**): a diferencia del
   plan gratuito, el Starter no "duerme" por falta de uso (siempre
   responde al instante) y soporta un **disco persistente**, así la
   base de datos no se pierde en cada redeploy o reinicio.
2. **`turnera-recordatorios`** (cron job): dispara una vez por día el
   mail de "mañana tenés clase", llamando a una ruta del propio sitio.
   Reemplaza al Programador de tareas de Windows (que dependía de una
   PC prendida) y no necesita nada externo a Render (antes usábamos
   GitHub Actions para esto; ya no hace falta).

### Si es la primera vez que se publica (Blueprint nuevo)

1. Entrá a [render.com](https://render.com) y creá una cuenta (podés
   registrarte directo con tu cuenta de GitHub).
2. Cargá un medio de pago en tu cuenta de Render (Account Settings →
   Billing) - el plan Starter, el disco y el cron job son pagos (ver
   costos más abajo), Render no deja crearlos sin una tarjeta cargada.
3. Dashboard → **"New +"** → **"Blueprint"**.
4. Elegí el repositorio `turnera-pilates`. Render lee el `render.yaml`
   solo y te muestra **los dos servicios** que va a crear: el web
   (plan Starter + disco de 1GB) y el cron job.
5. Te va a pedir completar los valores que **no** están en el repo por
   seguridad (nunca se suben credenciales a GitHub) - algunos se piden
   dos veces, una por cada servicio, porque `TAREAS_SECRETO` es una
   variable propia de cada uno (tiene que quedar **igual** en los
   dos):
   - `MAIL_USUARIO`: `benincasapilates@gmail.com` (solo en el web)
   - `MAIL_PASSWORD`: la contraseña de aplicación de 16 letras (la
     misma que está en tu `.env` local; solo en el web)
   - `TAREAS_SECRETO`: una clave larga y al azar, inventada por vos
     (por ejemplo generando 32 caracteres al azar en cualquier
     generador de contraseñas) - pegá el **mismo valor** en el web y
     en el cron job.
6. **"Apply"** / **"Create"** → Render instala las dependencias, corre
   `seed.py` (crea las tablas y el usuario admin), levanta el servidor
   con `gunicorn` y deja el cron job programado. Tarda unos minutos la
   primera vez.
7. Cuando termina, el servicio web te da una URL fija tipo
   `https://turnera-pilates.onrender.com`.
8. Entrá con el usuario admin del seed (`admin@estudio.com` /
   `cambiar123`) y **cambiá esa contraseña enseguida** desde el panel.

### Si el servicio ya existía (de antes de tener el cron job en Render)

1. Cargá un medio de pago en tu cuenta de Render (Account Settings →
   Billing), si todavía no lo hiciste.
2. Hacé `git push` con el `render.yaml` actualizado (incluye ahora el
   bloque del cron job `turnera-recordatorios`).
3. En el dashboard de Render, entrá al Blueprint del proyecto y
   sincronizalo con los cambios nuevos (o simplemente esperá: si el
   auto-deploy está activado, Render lo toma solo en cuanto detecta el
   push). Te va a mostrar el cron job nuevo para confirmar el costo
   antes de crearlo.
4. Te va a pedir el valor de `TAREAS_SECRETO` para el cron job -
   poné **el mismo valor** que ya tenías configurado en el servicio
   web (Render → servicio web → "Environment", ahí lo podés ver/copiar).
5. Si venías usando GitHub Actions para esto, ya podés desactivarlo:
   borrá el archivo `.github/workflows/recordatorios.yml` del repo (o
   simplemente el workflow desde la pestaña "Actions" → "..." →
   "Disable workflow") para no tener dos disparadores mandando el
   mismo recordatorio dos veces.

**Costo aproximado**: plan Starter (USD 7/mes) + disco de 1GB
(centavos por mes) + cron job (factura por segundo que corre, con un
mínimo de USD 1/mes) ≈ **USD 8-9/mes en total**. De sobra para una
base SQLite de un estudio de este tamaño durante años.

### Recordatorio diario en producción (cron job de Render)

El mail de "mañana tenés clase" necesita que algo lo dispare una vez
por día - en producción no depende de `enviar_recordatorios.py`
corriendo en tu PC (ver la sección de más arriba, que ahora es solo
para desarrollo local), sino del servicio `turnera-recordatorios` que
ya viene declarado en `render.yaml` (ver paso a paso arriba). Corre
todos los días a las 23:00 UTC (20:00 hora Argentina) y llama a la
misma ruta protegida por `TAREAS_SECRETO` que antes llamaba GitHub
Actions.

Para probarlo sin esperar al horario programado: Dashboard de Render →
servicio **`turnera-recordatorios`** → botón **"Trigger Run"** (o
"Run Job", según la versión del dashboard). Podés ver el resultado en
la pestaña "Logs" de ese mismo servicio.

### Chequeos después de publicar

- Abrí la URL desde el celular y confirmá que responde al instante
  (sin la pantalla de "iniciando servidor" del plan free).
- Reservá un turno de prueba y confirmá que llega el mail de
  confirmación.
- Dispará el cron job a mano (paso de arriba) y confirmá en sus logs
  que dice `recordatorios_enviados`.
- Hacé un redeploy de prueba (por ejemplo, con un commit chico) y
  confirmá que los usuarios/reservas siguen ahí después - eso confirma
  que el disco persistente está funcionando de verdad.

Cada vez que hagas `git push` a `main`, Render vuelve a desplegar solo
con los cambios nuevos, sin tocar los datos del disco persistente.

## Aparecer en Google ("pilates villa santa rita" / "pilates villa del parque")

### Lo que ya está hecho en el código

- **Título, descripción y `<h1>` apuntados a esas dos búsquedas.** El
  `<h1>` dice ahora *"Pilates reformer en Villa Santa Rita"* en vez de
  solo el nombre del estudio: para Google, el `<h1>` es la declaración
  de qué es la página, y nadie busca "benincasa" — buscan el servicio y
  el barrio.
- **Sección "Zonas"** (`templates/public/secciones/zonas.html`) con los
  barrios cercanos escritos como texto visible, no solo adentro de los
  datos estructurados. Es el cambio que hace posible aparecer en
  "pilates villa del parque": antes esas palabras no estaban en ninguna
  parte del texto de la página.
- **Preguntas frecuentes** que responden literalmente esas búsquedas
  ("¿Hacen pilates reformer en Villa Santa Rita?", "Vivo en Villa del
  Parque, ¿me queda cerca?"), y que Google puede mostrar desplegadas en
  los resultados.
- **Datos estructurados (schema.org) ampliados**: dirección, teléfono,
  equipo, reseñas, zona de cobertura, link al mapa, servicio ofrecido y
  —si se cargan las variables— coordenadas y horarios de atención.
- **Imagen de previsualización** propia de 1200x630
  (`static/img/og-benincasa-pilates.jpg`) para cuando se comparte el
  link por WhatsApp o Instagram. Antes se compartía la foto vertical del
  estudio con las medidas mal declaradas, y varias apps la descartaban.
- **Favicon propio** (`static/img/favicon.svg`): el iconito que Google
  muestra al lado de cada resultado en celular.
- **Redirección al dominio canónico**, y `robots.txt` / `sitemap.xml` /
  `canonical` coherentes entre sí (ver `SITIO_URL` más abajo).
- **Páginas de error propias** (400/403/404/500) con el código HTTP
  correcto, para que un link viejo no le devuelva basura a Google.

### Lo que falta, y solo lo puede hacer el estudio

Esto pesa **más** que todo lo anterior. Para búsquedas del tipo "pilates
+ barrio", Google muestra arriba de todo un mapa con tres negocios (el
"local pack"), y quién entra ahí lo decide la **ficha de Google Business
Profile**, no la página web. Por orden de impacto:

1. **Crear o reclamar la ficha en Google Business Profile**
   ([business.google.com](https://business.google.com)): categoría
   "Estudio de pilates", dirección exacta, teléfono, horarios, fotos
   reales y el link a este sitio. Sin ficha verificada, el estudio
   directamente no puede aparecer en ese mapa.
2. **Pedirle reseñas a las alumnas actuales.** La cantidad de reseñas y
   la frecuencia con que llegan reseñas nuevas es de lo que más mueve la
   posición en el local pack.
3. **Dar de alta el sitio en [Google Search
   Console](https://search.google.com/search-console)** y mandar el
   `sitemap.xml`. Es gratis, y es la única forma de ver por qué
   búsquedas te encuentra la gente de verdad.
4. **Comprar un dominio propio** (ej. `benincasapilates.com.ar`). Un
   `.onrender.com` transmite bastante menos confianza que un dominio
   propio. Cuando lo tengan, cargar `SITIO_URL`.
5. **Completar las variables opcionales** de `.env` / Render:
   `SITIO_URL`, `ESTUDIO_LATITUD` + `ESTUDIO_LONGITUD` y
   `HORARIOS_ATENCION`. Están vacías a propósito: el código no inventa
   las coordenadas ni los horarios del estudio. `.env.example` explica
   de dónde sacar cada dato.
6. **Que el nombre, la dirección y el teléfono sean idénticos** en la
   web, en Google Maps y en Instagram, hasta en cómo se abrevia la
   calle. Google cruza esos datos para confirmar que es el mismo
   negocio.

### Una aclaración honesta sobre "salir primero"

Nadie —ni Google— puede garantizar el primer puesto. Lo que sí se puede
decir: con la ficha de Google verificada, reseñas activas y la página
como quedó, el estudio compite en igualdad de condiciones por esas dos
búsquedas, que además son de barrio y tienen poca competencia. Los
cambios no son inmediatos: Google suele tardar entre unas semanas y un
par de meses en reflejarlos.

Lo que **no** hay que hacer, aunque parezca tentador: crear una página
por barrio ("pilates en villa del parque", "pilates en monte castro"…)
cambiando solo el nombre. Google llama a eso *doorway pages*, las
detecta y las penaliza. Por eso los barrios están todos en una sola
página, con información real de cada uno.

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
