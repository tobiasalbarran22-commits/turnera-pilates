"""
PÁGINAS PÚBLICAS (sin login) - landing, y a futuro /nosotros, /contacto,
o lo que haga falta.

Para agregar una página pública nueva:
1. Crear su template en templates/public/, extendiendo
   "public/base_publica.html" (así hereda el <head> con SEO/Open
   Graph/JSON-LD, la nav, el footer, el botón flotante y el JS de
   animaciones - no hay que volver a escribir nada de eso).
2. Agregar acá abajo una función de ruta nueva (@bp.route(...)) que la
   renderice, reutilizando _contexto_estudio() para los datos de
   contacto/ubicación.
3. Sumarla a PAGINAS_PUBLICAS para que aparezca sola en el sitemap.

No hace falta tocar nada de app/__init__.py ni de las otras páginas.
"""

from urllib.parse import quote

from flask import render_template, current_app, url_for, redirect, Response, request, abort
from flask_login import current_user

from app.public import bp
from app.extensions import csrf


def url_absoluta(endpoint, **valores):
    """
    URL completa (con https://dominio) de una página del sitio.

    Por qué no alcanza con url_for(..., _external=True): eso arma la
    URL con el dominio POR EL QUE ENTRÓ la visita. Si el sitio se puede
    abrir por dos dominios (el .onrender.com y el propio), el canonical
    y el sitemap terminarían diciendo cosas distintas según quién los
    pida - justo lo contrario de lo que un canonical tiene que hacer,
    que es señalar UNA dirección fija. Con SITIO_URL configurado (ver
    config.py) todas las URLs absolutas apuntan siempre ahí. Si no está
    configurado, se comporta como antes.
    """
    ruta = url_for(endpoint, **valores)
    sitio_url = current_app.config.get("SITIO_URL")
    if sitio_url:
        return sitio_url + ruta
    return url_for(endpoint, _external=True, **valores)

# Cada página pública que exista suma una entrada acá: el sitemap.xml
# se arma solo recorriendo esta lista (ver sitemap_xml más abajo).
PAGINAS_PUBLICAS = [
    # "lastmod" es la fecha del último cambio de CONTENIDO real de esa
    # página (no la fecha de hoy calculada en cada visita - eso es un
    # antipatrón de SEO, Google desconfía de un sitemap donde todo dice
    # "recién cambiado" siempre). Se actualiza a mano cuando cambie
    # algo de la landing.
    {"endpoint": "public.index", "changefreq": "monthly", "priority": "1.0", "lastmod": "2026-08-08"},
]

# El equipo del estudio: una sola fuente de verdad que alimenta tanto
# la sección "¿Quiénes te reciben?" de la landing como los datos
# estructurados (JSON-LD) - así no hay que mantener los nombres/roles
# escritos dos veces en dos lugares que se puedan desincronizar.
EQUIPO = [
    {"nombre": "Gise", "rol": "Directora del estudio", "inicial": "G"},
    {"nombre": "Mile", "rol": "Instructora de pilates reformer", "inicial": "M"},
    {"nombre": "Adri", "rol": "Instructora de pilates reformer", "inicial": "A"},
]

# Reseñas reales de Google Maps (no inventadas: las cargó el dueño del
# estudio a partir de lo que ve publicado ahí). Se muestran en la
# sección "Reseñas" Y alimentan el bloque "review" del JSON-LD, para
# que lo que Google indexa como dato estructurado sea exactamente lo
# mismo que una persona ve en la página - nunca un número o una
# reseña que no esté realmente visible.
RESENAS = [
    {
        "autor": "Mónica Sosa",
        "texto": "Me encanta el lugar, las profes unas divinas, muy atentas a todos. Pocas personas, y así se "
                 "hacen más supervisados los ejercicios que te dan, sobre todo cuando no tenés experiencia.",
    },
    {
        "autor": "Lina Maria Mangones Cuello",
        "texto": "Excelente lugar, profesionalismo, grandes profesionales.",
    },
    {
        "autor": "Silvina Elisabet",
        "texto": "Hermoso y cálido lugar. Excelente profesionales.",
    },
    {
        "autor": "Tobías",
        "texto": "Clases muy llevaderas y adaptadas a cada alumno. Muy recomendable.",
    },
]
CALIFICACION_PROMEDIO = 5.0  # Puntuación general real en Google Maps

# Preguntas frecuentes: contenido real (no relleno) para la sección de
# la landing y su JSON-LD (FAQPage) - ayuda tanto a SEO (Google puede
# mostrar esto como resultado enriquecido) como a que quien todavía no
# es alumna/o entienda cómo funciona el estudio antes de escribir.
PREGUNTAS_FRECUENTES = [
    {
        "pregunta": "¿Necesito experiencia previa para empezar?",
        "respuesta": "No. Adaptamos cada ejercicio a tu nivel y a tu cuerpo, así que podés arrancar aunque "
                     "nunca hayas hecho pilates.",
    },
    {
        "pregunta": "¿Cuántas personas hay por clase?",
        "respuesta": "Grupos de hasta 5 personas. Así la profesora puede ver cómo te movés y ajustar cada "
                     "ejercicio a vos, en vez de dar una clase genérica para todos por igual.",
    },
    {
        "pregunta": "¿Dónde queda el estudio?",
        "respuesta": "En Campana 1495, Villa Santa Rita, Ciudad Autónoma de Buenos Aires.",
    },
    # No es relleno: es literalmente la búsqueda por la que queremos
    # que aparezca la página ("pilates villa santa rita"), respondida
    # de verdad. Google le da mucho peso a que la página conteste la
    # pregunta que la persona escribió en el buscador.
    {
        "pregunta": "¿Hacen pilates reformer en Villa Santa Rita?",
        "respuesta": "Sí. El estudio está en Villa Santa Rita, sobre Campana al 1400, y todas las clases son "
                     "de pilates reformer en grupos de hasta 5 personas.",
    },
    {
        "pregunta": "¿Qué es el pilates reformer y en qué se diferencia del pilates en el piso?",
        "respuesta": "El reformer es una camilla con una plataforma deslizante y resortes que acompañan o "
                     "resisten el movimiento. Eso permite trabajar con menos impacto en las articulaciones "
                     "que el pilates de suelo, y graduar la dificultad de cada ejercicio persona por persona.",
    },
    {
        "pregunta": "¿Cómo reservo una clase?",
        "respuesta": "Si ya sos alumna/o, reservás tocando el botón \"Tomar un turno\" y elegís día y "
                     "horario desde la turnera. Si todavía no sos parte del estudio, escribinos por "
                     "WhatsApp o Instagram y te ayudamos a arrancar.",
    },
]


def _schema_negocio():
    """
    Datos estructurados (schema.org) del estudio en sí, tipo
    ExerciseGym: sirven para que Google entienda qué es la página y
    pueda mostrar dirección, teléfono, zona de cobertura, equipo y
    reseñas directo en los resultados de búsqueda, en vez de solo un
    link azul. Arma un dict de Python (no un string de JSON escrito a
    mano) para que Jinja lo pase por el filtro `tojson`, que se
    encarga solo de escapar comillas/tildes/etc. correctamente -
    escribir el JSON a mano con {{ }} adentro es donde suelen aparecer
    bugs raros de escaping.

    reseñas y calificación: son las mismas 4 reseñas reales que se ven
    en la sección "Reseñas" de la página (ver RESENAS arriba) - nunca
    un número inflado que no se pueda verificar mirando la página.
    """
    url_home = url_absoluta("public.index")
    direccion = current_app.config["DIRECCION_ESTUDIO"]

    schema = {
        "@context": "https://schema.org",
        "@type": "ExerciseGym",
        # @id: un identificador estable del negocio. Sirve para que
        # Google entienda que este bloque, el de la FAQ y cualquier
        # otro que se agregue después hablan de la MISMA entidad, en
        # vez de tratarlos como cosas sueltas.
        "@id": url_home + "#estudio",
        "name": "Benincasa Pilates",
        "alternateName": "Pilates Benincasa",
        "description": (
            "Estudio de pilates reformer en Villa Santa Rita, CABA, con clases en grupos de hasta 5 personas "
            "y seguimiento personalizado."
        ),
        "image": url_absoluta("static", filename="img/estudio-interior.jpg"),
        "logo": url_absoluta("static", filename="img/favicon.svg"),
        "url": url_home,
        "telephone": f"+{current_app.config['WHATSAPP_NUMERO']}",
        "priceRange": "$$",
        "currenciesAccepted": "ARS",
        "knowsLanguage": "es-AR",
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "Campana 1495",
            "addressLocality": "Villa Santa Rita, Ciudad Autónoma de Buenos Aires",
            "addressRegion": "CABA",
            "postalCode": "C1416",
            "addressCountry": "AR",
        },
        # hasMap: el link al lugar en Google Maps. Es una de las señales
        # que Google cruza para asociar esta página con la ficha del
        # negocio en Maps (que es lo que decide el "local pack", el
        # mapita con 3 negocios que sale arriba de todo).
        "hasMap": f"https://www.google.com/maps/search/?api=1&query={quote(f'Benincasa Pilates, {direccion}')}",
        # areaServed: a pedido del estudio, la página (y sus datos
        # estructurados) solo mencionan Villa Santa Rita - ningún otro
        # barrio, ni siquiera acá adentro del JSON-LD que no se ve en
        # pantalla.
        "areaServed": [
            {"@type": "Place", "name": "Villa Santa Rita, Ciudad Autónoma de Buenos Aires"},
        ],
        "sameAs": [current_app.config["INSTAGRAM_URL"]],
        "employee": [
            {"@type": "Person", "name": p["nombre"], "jobTitle": p["rol"]}
            for p in EQUIPO
        ],
        # makesOffer: qué vende el negocio, en los términos que la gente
        # busca. Es otra forma (legítima, no relleno) de que "pilates
        # reformer" quede asociado a esta entidad.
        "makesOffer": [
            {
                "@type": "Offer",
                "itemOffered": {
                    "@type": "Service",
                    "name": "Clases de pilates reformer en grupo reducido",
                    "description": "Clases de pilates reformer de 60 minutos en grupos de hasta 5 personas.",
                    "areaServed": {"@type": "Place", "name": "Villa Santa Rita, Ciudad Autónoma de Buenos Aires"},
                },
            }
        ],
        "aggregateRating": {
            "@type": "AggregateRating",
            "ratingValue": CALIFICACION_PROMEDIO,
            "reviewCount": len(RESENAS),
            "bestRating": "5",
        },
        "review": [
            {
                "@type": "Review",
                "author": {"@type": "Person", "name": r["autor"]},
                "reviewRating": {"@type": "Rating", "ratingValue": "5", "bestRating": "5"},
                "reviewBody": r["texto"],
            }
            for r in RESENAS
        ],
    }

    # Coordenadas exactas: se incluyen SOLO si están cargadas (ver
    # ESTUDIO_LATITUD/ESTUDIO_LONGITUD en config.py). Es de los datos
    # que más pesan para aparecer en el mapita de "pilates cerca mío",
    # pero unas coordenadas inventadas son peores que ninguna, así que
    # no ponemos un valor por defecto.
    latitud = current_app.config.get("ESTUDIO_LATITUD")
    longitud = current_app.config.get("ESTUDIO_LONGITUD")
    if latitud and longitud:
        schema["geo"] = {
            "@type": "GeoCoordinates",
            "latitude": float(latitud),
            "longitude": float(longitud),
        }

    horarios = _horarios_de_atencion_schema()
    if horarios:
        schema["openingHoursSpecification"] = horarios

    return schema


def _horarios_de_atencion_schema():
    """
    Traduce la variable HORARIOS_ATENCION (ver config.py) al formato
    que espera schema.org. Formato de entrada:
        "Monday,Tuesday 08:00-21:00|Saturday 09:00-13:00"

    Si está vacía o mal escrita, devuelve None y el bloque
    simplemente no se incluye: preferimos no declarar horarios antes
    que declarar horarios equivocados (que Google puede llegar a
    mostrar como "Abierto ahora" cuando el estudio está cerrado).
    """
    crudo = (current_app.config.get("HORARIOS_ATENCION") or "").strip()
    if not crudo:
        return None

    especificaciones = []
    for tramo in crudo.split("|"):
        partes = tramo.strip().split()
        if len(partes) != 2 or "-" not in partes[1]:
            current_app.logger.warning(f"HORARIOS_ATENCION: no se entiende el tramo '{tramo}', se ignora.")
            continue
        dias, rango = partes
        apertura, cierre = rango.split("-", 1)
        especificaciones.append({
            "@type": "OpeningHoursSpecification",
            "dayOfWeek": [d.strip() for d in dias.split(",") if d.strip()],
            "opens": apertura,
            "closes": cierre,
        })
    return especificaciones or None


def _schema_faq():
    """FAQPage: le da a Google la chance de mostrar estas preguntas como resultado enriquecido."""
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "@id": url_absoluta("public.index") + "#preguntas",
        "mainEntity": [
            {
                "@type": "Question",
                "name": p["pregunta"],
                "acceptedAnswer": {"@type": "Answer", "text": p["respuesta"]},
            }
            for p in PREGUNTAS_FRECUENTES
        ],
    }


def _contexto_estudio():
    """
    Datos de contacto/ubicación que va a necesitar CUALQUIER página
    pública (no solo la landing): el botón de WhatsApp, el link de
    Instagram, el mapa, la imagen para Open Graph. Centralizarlo acá
    evita que cada página nueva tenga que rearmar estas URLs a mano.
    """
    mensaje_whatsapp = quote("¡Hola! Quiero consultar por las clases de pilates.")
    whatsapp_numero = current_app.config["WHATSAPP_NUMERO"]
    direccion = current_app.config["DIRECCION_ESTUDIO"]
    consulta_mapa = quote(f"Benincasa Pilates, {direccion}")

    return {
        "whatsapp_url": f"https://wa.me/{whatsapp_numero}?text={mensaje_whatsapp}",
        "whatsapp_numero": whatsapp_numero,
        "instagram_url": current_app.config["INSTAGRAM_URL"],
        "direccion": direccion,
        "mapa_embed_url": f"https://www.google.com/maps?q={consulta_mapa}&output=embed",
        "mapa_url": f"https://www.google.com/maps/search/?api=1&query={consulta_mapa}",
        # Imagen de previsualización al compartir el link (WhatsApp,
        # Instagram, Facebook, Google). Es un archivo aparte, recortado
        # a 1200x630: la foto del estudio es vertical (960x1280) y en
        # una tarjeta de link horizontal se recortaba sola, cortando
        # justo la parte de arriba y abajo. Además el <head> declaraba
        # 1200x900, que no era el tamaño de ninguna de las dos - y una
        # medida declarada que no coincide hace que algunas apps
        # descarten la imagen y muestren el link pelado.
        "og_image_url": url_absoluta("static", filename="img/og-benincasa-pilates.jpg"),
    }


@bp.route("/")
def index():
    # La única página pública que redirige: alguien ya logueado no
    # necesita ver la landing de nuevo, va directo a su panel.
    if current_user.is_authenticated:
        return redirect(url_for("auth.redirigir_segun_rol"))

    return render_template(
        "public/landing.html",
        canonical_url=url_absoluta("public.index"),
        equipo=EQUIPO,
        resenas=RESENAS,
        calificacion_promedio=CALIFICACION_PROMEDIO,
        preguntas=PREGUNTAS_FRECUENTES,
        datos_estructurados=[_schema_negocio(), _schema_faq()],
        **_contexto_estudio(),
    )


@bp.route("/robots.txt")
def robots_txt():
    contenido = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin/\n"
        "Disallow: /alumno/\n"
        "Disallow: /login\n"
        "Disallow: /cambiar-password\n"
        "Disallow: /redirigir\n"
        "Disallow: /logout\n"
        # La ruta de la tarea programada: no es una página, no tiene
        # nada que indexar, y no hace falta anunciarle a nadie que
        # existe.
        "Disallow: /tareas/\n"
        f"\nSitemap: {url_absoluta('public.sitemap_xml')}\n"
    )
    return Response(contenido, mimetype="text/plain")


@bp.route("/sitemap.xml")
def sitemap_xml():
    filas = []
    for pagina in PAGINAS_PUBLICAS:
        filas.append(
            "  <url>\n"
            f"    <loc>{url_absoluta(pagina['endpoint'])}</loc>\n"
            f"    <lastmod>{pagina['lastmod']}</lastmod>\n"
            f"    <changefreq>{pagina['changefreq']}</changefreq>\n"
            f"    <priority>{pagina['priority']}</priority>\n"
            "  </url>"
        )
    contenido = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(filas) + "\n"
        "</urlset>\n"
    )
    return Response(contenido, mimetype="application/xml")


# ------------------------------------------------------------------
# TAREA PROGRAMADA: recordatorio del día anterior ("mañana tenés
# clase"). No lo dispara ninguna persona ni acción de la turnera -
# necesita que algo externo lo llame una vez por día (ver render.yaml,
# servicio "turnera-recordatorios": un cron job de Render que llama a
# esta ruta, sin depender de que ninguna PC esté prendida).
# ------------------------------------------------------------------

@bp.route("/tareas/recordatorios", methods=["POST"])
@csrf.exempt  # lo llama un curl externo, no un <form> con sesión - no tiene token CSRF para mandar
def tarea_recordatorios():
    # Protegido con un token compartido (no con login: quien llama a
    # esto no es una persona con sesión, es un disparador automático).
    # Sin este chequeo, cualquiera que encontrara esta URL podría
    # hacer que el sistema mande recordatorios de más con solo
    # pegarla en el navegador.
    token_esperado = current_app.config.get("TAREAS_SECRETO")
    token_recibido = request.headers.get("X-Tarea-Token")
    if not token_esperado or token_recibido != token_esperado:
        abort(403)

    from app.alumno.services import enviar_recordatorios_del_dia_siguiente

    cantidad = enviar_recordatorios_del_dia_siguiente()
    return {"recordatorios_enviados": cantidad}, 200
