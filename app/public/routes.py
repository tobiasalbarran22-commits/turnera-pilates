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

from flask import render_template, current_app, url_for, redirect, Response
from flask_login import current_user

from app.public import bp

# Cada página pública que exista suma una entrada acá: el sitemap.xml
# se arma solo recorriendo esta lista (ver sitemap_xml más abajo).
PAGINAS_PUBLICAS = [
    {"endpoint": "public.index", "changefreq": "monthly", "priority": "1.0"},
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
    {
        "pregunta": "¿Cómo reservo una clase?",
        "respuesta": "Reservás online, eligiendo día y horario desde la turnera del estudio, o nos escribís "
                     "por WhatsApp y te ayudamos a encontrar el horario que mejor te quede.",
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
    return {
        "@context": "https://schema.org",
        "@type": "ExerciseGym",
        "name": "Benincasa Pilates",
        "image": url_for("static", filename="img/estudio-interior.jpg", _external=True),
        "url": url_for("public.index", _external=True),
        "telephone": f"+{current_app.config['WHATSAPP_NUMERO']}",
        "priceRange": "$$",
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "Campana 1495",
            "addressLocality": "Villa Santa Rita, Ciudad Autónoma de Buenos Aires",
            "addressRegion": "CABA",
            "addressCountry": "AR",
        },
        # areaServed: además del barrio exacto, sumamos los barrios
        # linderos para las búsquedas de gente cercana que busca
        # "pilates" + su propio barrio. Esto lo lee Google (le dice
        # "el negocio también atiende esta zona"), pero no se muestra
        # como texto en la página - es la forma correcta de sumar
        # cobertura geográfica sin tener que escribirlo en el body.
        "areaServed": [
            {"@type": "Place", "name": "Villa Santa Rita, CABA"},
            {"@type": "Place", "name": "Monte Castro, CABA"},
            {"@type": "Place", "name": "Villa del Parque, CABA"},
            {"@type": "Place", "name": "Paternal, CABA"},
            {"@type": "Place", "name": "Floresta, CABA"},
        ],
        "sameAs": [current_app.config["INSTAGRAM_URL"]],
        "employee": [
            {"@type": "Person", "name": p["nombre"], "jobTitle": p["rol"]}
            for p in EQUIPO
        ],
        "aggregateRating": {
            "@type": "AggregateRating",
            "ratingValue": CALIFICACION_PROMEDIO,
            "reviewCount": len(RESENAS),
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


def _schema_faq():
    """FAQPage: le da a Google la chance de mostrar estas preguntas como resultado enriquecido."""
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
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
        "og_image_url": url_for("static", filename="img/estudio-interior.jpg", _external=True),
    }


@bp.route("/")
def index():
    # La única página pública que redirige: alguien ya logueado no
    # necesita ver la landing de nuevo, va directo a su panel.
    if current_user.is_authenticated:
        return redirect(url_for("auth.redirigir_segun_rol"))

    return render_template(
        "public/landing.html",
        canonical_url=url_for("public.index", _external=True),
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
        f"\nSitemap: {url_for('public.sitemap_xml', _external=True)}\n"
    )
    return Response(contenido, mimetype="text/plain")


@bp.route("/sitemap.xml")
def sitemap_xml():
    filas = []
    for pagina in PAGINAS_PUBLICAS:
        filas.append(
            "  <url>\n"
            f"    <loc>{url_for(pagina['endpoint'], _external=True)}</loc>\n"
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
