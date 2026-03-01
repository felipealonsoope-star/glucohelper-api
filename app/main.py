"""
GlucoHelper API - Calculadora de Bolus y Estimador de Carbohidratos para Diabéticos
====================================================================================
API diseñada por y para personas con diabetes.
Permite calcular dosis de insulina basándose en ratio, sensibilidad,
glicemia actual y carbohidratos a ingerir.
Incluye estimación de carbohidratos por análisis de imagen de alimentos.
"""

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timedelta
import math
import json
import base64
import os
import uuid

# ─── App Setup ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="GlucoHelper API",
    description=(
        "API para diabéticos: calcula dosis de insulina (bolus), estima "
        "carbohidratos a partir de fotografías de alimentos, registra glicemias "
        "y dosis de insulina, genera gráficos y análisis clínico con IA. "
        "Compatible con usuarios de bomba de insulina y terapia MDI."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Models ───────────────────────────────────────────────────────────────────

class UserProfile(BaseModel):
    """Perfil de configuración del usuario diabético."""
    nombre: str = Field(..., description="Nombre del usuario", example="Carlos")
    ratio_insulina_carbohidratos: float = Field(
        ...,
        description="Ratio insulina:carbohidratos (1 unidad cubre X gramos de CHO)",
        example=10.0,
        gt=0
    )
    factor_sensibilidad: float = Field(
        ...,
        description="Factor de sensibilidad (1 unidad baja X mg/dL de glicemia)",
        example=40.0,
        gt=0
    )
    glicemia_objetivo: float = Field(
        default=110.0,
        description="Glicemia objetivo en mg/dL",
        example=110.0,
        gt=0
    )
    tipo_terapia: str = Field(
        default="MDI",
        description="Tipo de terapia: 'MDI' (múltiples dosis) o 'Bomba'",
        example="MDI"
    )
    insulina_activa: Optional[float] = Field(
        default=0.0,
        description="Insulina activa restante (IOB) en unidades. Relevante para usuarios de bomba.",
        example=0.5,
        ge=0
    )
    usa_media_unidad: bool = Field(
        default=False,
        description="Si el usuario puede dosificar en medias unidades (plumas con media unidad)",
    )

class BolusRequest(BaseModel):
    """Solicitud de cálculo de bolus."""
    perfil: UserProfile
    glicemia_actual: float = Field(
        ...,
        description="Glicemia actual medida en mg/dL",
        example=180.0,
        gt=0
    )
    carbohidratos: float = Field(
        ...,
        description="Gramos de carbohidratos a ingerir",
        example=60.0,
        ge=0
    )

class BolusResponse(BaseModel):
    """Resultado del cálculo de bolus."""
    bolus_alimenticio: float = Field(description="Unidades de insulina para cubrir carbohidratos")
    bolus_corrector: float = Field(description="Unidades de insulina para corregir glicemia")
    insulina_activa_descontada: float = Field(description="IOB descontada del bolus corrector")
    bolus_total_exacto: float = Field(description="Bolus total exacto (sin redondear)")
    bolus_total_recomendado: float = Field(description="Bolus total recomendado (redondeado)")
    detalle: dict = Field(description="Detalle paso a paso del cálculo")
    advertencias: list[str] = Field(description="Advertencias o notas relevantes")

class CarbEstimationResponse(BaseModel):
    """Resultado de estimación de carbohidratos por imagen."""
    alimentos_detectados: list[dict] = Field(description="Lista de alimentos identificados")
    carbohidratos_totales_estimados: float = Field(description="Total de CHO estimados en gramos")
    confianza: str = Field(description="Nivel de confianza de la estimación")
    nota: str = Field(description="Nota aclaratoria sobre la estimación")


# ─── Base de Datos de Alimentos (para estimación offline) ────────────────────

FOOD_DATABASE = {
    # Cereales y granos
    "arroz blanco cocido": {"cho_per_100g": 28, "porcion_tipica_g": 180},
    "arroz integral cocido": {"cho_per_100g": 23, "porcion_tipica_g": 180},
    "pasta cocida": {"cho_per_100g": 25, "porcion_tipica_g": 200},
    "pan blanco": {"cho_per_100g": 49, "porcion_tipica_g": 60},
    "pan integral": {"cho_per_100g": 41, "porcion_tipica_g": 60},
    "tortilla de maíz": {"cho_per_100g": 44, "porcion_tipica_g": 30},
    "tortilla de harina": {"cho_per_100g": 48, "porcion_tipica_g": 45},
    "avena cocida": {"cho_per_100g": 12, "porcion_tipica_g": 240},
    "quinoa cocida": {"cho_per_100g": 21, "porcion_tipica_g": 185},
    "cereal de desayuno": {"cho_per_100g": 75, "porcion_tipica_g": 40},

    # Frutas
    "manzana": {"cho_per_100g": 14, "porcion_tipica_g": 180},
    "plátano / banana": {"cho_per_100g": 23, "porcion_tipica_g": 120},
    "naranja": {"cho_per_100g": 12, "porcion_tipica_g": 150},
    "uvas": {"cho_per_100g": 17, "porcion_tipica_g": 150},
    "fresa": {"cho_per_100g": 8, "porcion_tipica_g": 150},
    "sandía": {"cho_per_100g": 8, "porcion_tipica_g": 280},
    "mango": {"cho_per_100g": 15, "porcion_tipica_g": 200},
    "piña": {"cho_per_100g": 13, "porcion_tipica_g": 165},

    # Tubérculos y legumbres
    "papa / patata cocida": {"cho_per_100g": 17, "porcion_tipica_g": 200},
    "papa / patata frita": {"cho_per_100g": 36, "porcion_tipica_g": 150},
    "camote / batata": {"cho_per_100g": 20, "porcion_tipica_g": 150},
    "frijoles / judías cocidos": {"cho_per_100g": 22, "porcion_tipica_g": 170},
    "lentejas cocidas": {"cho_per_100g": 20, "porcion_tipica_g": 200},
    "garbanzos cocidos": {"cho_per_100g": 27, "porcion_tipica_g": 165},

    # Lácteos
    "leche entera": {"cho_per_100g": 5, "porcion_tipica_g": 240},
    "yogur natural": {"cho_per_100g": 5, "porcion_tipica_g": 200},
    "yogur con fruta": {"cho_per_100g": 15, "porcion_tipica_g": 200},
    "helado": {"cho_per_100g": 24, "porcion_tipica_g": 100},

    # Bebidas
    "jugo de naranja": {"cho_per_100g": 10, "porcion_tipica_g": 250},
    "refresco / soda": {"cho_per_100g": 11, "porcion_tipica_g": 350},
    "cerveza": {"cho_per_100g": 3.5, "porcion_tipica_g": 350},

    # Comidas preparadas comunes
    "pizza (1 porción)": {"cho_per_100g": 33, "porcion_tipica_g": 120},
    "hamburguesa con pan": {"cho_per_100g": 20, "porcion_tipica_g": 200},
    "sushi (6 piezas)": {"cho_per_100g": 30, "porcion_tipica_g": 180},
    "empanada": {"cho_per_100g": 30, "porcion_tipica_g": 120},
    "tacos (2 unidades)": {"cho_per_100g": 22, "porcion_tipica_g": 200},

    # Snacks y dulces
    "galletas": {"cho_per_100g": 65, "porcion_tipica_g": 30},
    "chocolate con leche": {"cho_per_100g": 56, "porcion_tipica_g": 40},
    "barra de granola": {"cho_per_100g": 60, "porcion_tipica_g": 35},

    # Proteínas (bajo CHO)
    "pollo": {"cho_per_100g": 0, "porcion_tipica_g": 150},
    "carne de res": {"cho_per_100g": 0, "porcion_tipica_g": 150},
    "pescado": {"cho_per_100g": 0, "porcion_tipica_g": 150},
    "huevo": {"cho_per_100g": 1, "porcion_tipica_g": 50},
    "queso": {"cho_per_100g": 1.3, "porcion_tipica_g": 30},

    # Vegetales (bajo CHO)
    "ensalada verde": {"cho_per_100g": 2, "porcion_tipica_g": 150},
    "tomate": {"cho_per_100g": 4, "porcion_tipica_g": 120},
    "zanahoria": {"cho_per_100g": 10, "porcion_tipica_g": 80},
    "brócoli": {"cho_per_100g": 7, "porcion_tipica_g": 150},
    "maíz / elote": {"cho_per_100g": 19, "porcion_tipica_g": 150},
}


# ─── Helper Functions ─────────────────────────────────────────────────────────

def calcular_bolus(request: BolusRequest) -> BolusResponse:
    """
    Calcula el bolus de insulina usando la fórmula estándar:
    
    Bolus alimenticio = Carbohidratos / Ratio I:CHO
    Bolus corrector = (Glicemia actual - Glicemia objetivo) / Factor de sensibilidad
    Bolus total = Bolus alimenticio + Bolus corrector - IOB
    """
    perfil = request.perfil
    advertencias = []

    # 1) Bolus alimenticio (para cubrir los carbohidratos)
    bolus_alimenticio = request.carbohidratos / perfil.ratio_insulina_carbohidratos

    # 2) Bolus corrector (para corregir hiperglicemia)
    diferencia_glicemia = request.glicemia_actual - perfil.glicemia_objetivo
    bolus_corrector_bruto = diferencia_glicemia / perfil.factor_sensibilidad

    # Si la glicemia está por debajo del objetivo, el corrector es negativo
    if bolus_corrector_bruto < 0:
        advertencias.append(
            f"⚠️ Tu glicemia ({request.glicemia_actual} mg/dL) está por debajo del "
            f"objetivo ({perfil.glicemia_objetivo} mg/dL). Se restará del bolus total."
        )

    # 3) Descontar insulina activa (IOB)
    iob = perfil.insulina_activa or 0.0
    bolus_corrector = bolus_corrector_bruto
    iob_descontada = 0.0

    if bolus_corrector > 0 and iob > 0:
        iob_descontada = min(iob, bolus_corrector)
        bolus_corrector = bolus_corrector - iob_descontada
        if iob_descontada > 0:
            advertencias.append(
                f"ℹ️ Se descontaron {iob_descontada:.2f}U de insulina activa (IOB) del bolus corrector."
            )

    # 4) Bolus total
    bolus_total_exacto = bolus_alimenticio + bolus_corrector

    # No recomendar bolus negativo
    if bolus_total_exacto < 0:
        advertencias.append(
            "🍬 El cálculo sugiere un bolus negativo. Considera ingerir carbohidratos "
            "adicionales para evitar una hipoglicemia. No se recomienda inyectar insulina."
        )
        bolus_total_exacto = 0

    # 5) Redondeo según tipo de terapia
    if perfil.usa_media_unidad:
        bolus_recomendado = round(bolus_total_exacto * 2) / 2  # Redondeo a 0.5U
    elif perfil.tipo_terapia == "Bomba":
        bolus_recomendado = round(bolus_total_exacto * 20) / 20  # Redondeo a 0.05U
    else:
        bolus_recomendado = round(bolus_total_exacto)  # Redondeo a 1U para MDI

    # Advertencias adicionales de seguridad
    if request.glicemia_actual < 70:
        advertencias.insert(0,
            "🚨 HIPOGLICEMIA DETECTADA: Tu glicemia es < 70 mg/dL. "
            "Trata la hipoglicemia primero con 15g de carbohidratos rápidos. "
            "Espera 15 minutos y vuelve a medir antes de calcular un bolus."
        )
    elif request.glicemia_actual < 80:
        advertencias.insert(0,
            "⚠️ Glicemia baja. Considera reducir la dosis o ingerir carbohidratos sin bolus completo."
        )

    if request.glicemia_actual > 300:
        advertencias.append(
            "🚨 Glicemia muy elevada (>300 mg/dL). Verifica cetonas. "
            "Si tienes cetonas moderadas/altas, contacta a tu equipo médico."
        )

    if bolus_recomendado > 20:
        advertencias.append(
            "⚠️ Bolus alto (>20U). Verifica que los datos ingresados sean correctos."
        )

    detalle = {
        "formula_alimenticio": f"{request.carbohidratos}g ÷ {perfil.ratio_insulina_carbohidratos} = {bolus_alimenticio:.2f}U",
        "formula_corrector": f"({request.glicemia_actual} - {perfil.glicemia_objetivo}) ÷ {perfil.factor_sensibilidad} = {bolus_corrector_bruto:.2f}U",
        "iob_aplicada": f"{iob_descontada:.2f}U descontadas de {iob:.2f}U de IOB",
        "formula_total": f"{bolus_alimenticio:.2f}U + {bolus_corrector:.2f}U = {bolus_total_exacto:.2f}U",
        "redondeo": f"{'0.05U (bomba)' if perfil.tipo_terapia == 'Bomba' else '0.5U (media unidad)' if perfil.usa_media_unidad else '1U (unidad completa MDI)'}",
    }

    return BolusResponse(
        bolus_alimenticio=round(bolus_alimenticio, 2),
        bolus_corrector=round(bolus_corrector, 2),
        insulina_activa_descontada=round(iob_descontada, 2),
        bolus_total_exacto=round(bolus_total_exacto, 2),
        bolus_total_recomendado=bolus_recomendado,
        detalle=detalle,
        advertencias=advertencias,
    )


def estimar_carbohidratos_offline(alimentos_texto: list[str]) -> CarbEstimationResponse:
    """
    Estima carbohidratos basándose en la base de datos local.
    Se usa cuando no hay API de visión disponible.
    """
    resultados = []
    total_cho = 0.0

    for alimento in alimentos_texto:
        alimento_lower = alimento.strip().lower()
        encontrado = False

        for nombre, datos in FOOD_DATABASE.items():
            if alimento_lower in nombre or nombre in alimento_lower:
                cho_porcion = (datos["cho_per_100g"] * datos["porcion_tipica_g"]) / 100
                resultados.append({
                    "alimento": nombre,
                    "porcion_g": datos["porcion_tipica_g"],
                    "cho_por_100g": datos["cho_per_100g"],
                    "cho_estimados": round(cho_porcion, 1),
                })
                total_cho += cho_porcion
                encontrado = True
                break

        if not encontrado:
            resultados.append({
                "alimento": alimento,
                "porcion_g": None,
                "cho_por_100g": None,
                "cho_estimados": None,
                "nota": "Alimento no encontrado en la base de datos. Ingresa manualmente."
            })

    return CarbEstimationResponse(
        alimentos_detectados=resultados,
        carbohidratos_totales_estimados=round(total_cho, 1),
        confianza="media" if all(r.get("cho_estimados") for r in resultados) else "baja",
        nota=(
            "Estimación basada en porciones típicas. Los valores reales pueden variar "
            "según el tamaño de la porción y la preparación. Siempre verifica con tu "
            "nutricionista o usa una balanza de alimentos para mayor precisión."
        )
    )


# ─── API Endpoints ────────────────────────────────────────────────────────────

@app.get("/", tags=["General"])
async def root():
    return {
        "nombre": "GlucoHelper API",
        "version": "1.0.0",
        "descripcion": "API para diabéticos: cálculo de bolus y estimación de carbohidratos",
        "endpoints": {
            "docs": "/docs",
            "calcular_bolus": "POST /api/v1/bolus",
            "estimar_carbohidratos": "POST /api/v1/estimar-carbohidratos",
            "buscar_alimento": "GET /api/v1/alimentos/buscar?q=...",
            "base_alimentos": "GET /api/v1/alimentos",
            "analizar_imagen": "POST /api/v1/analizar-imagen",
        },
        "disclaimer": (
            "⚠️ Esta herramienta es de apoyo. NO reemplaza el consejo médico profesional. "
            "Siempre consulta con tu endocrinólogo o equipo de diabetes."
        )
    }


@app.post("/api/v1/bolus", response_model=BolusResponse, tags=["Calculadora de Bolus"])
async def calcular_bolus_endpoint(request: BolusRequest):
    """
    Calcula la dosis de bolus de insulina recomendada.

    **Fórmulas utilizadas:**
    - Bolus alimenticio = Carbohidratos ÷ Ratio I:CHO
    - Bolus corrector = (Glicemia actual - Glicemia objetivo) ÷ Factor de sensibilidad
    - Bolus total = Bolus alimenticio + Bolus corrector - Insulina activa (IOB)

    **Importante:** Esta es una herramienta de apoyo. Siempre confirma con tu equipo médico.
    """
    try:
        return calcular_bolus(request)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/v1/alimentos", tags=["Base de Alimentos"])
async def listar_alimentos():
    """
    Lista todos los alimentos en la base de datos con sus valores de carbohidratos.
    """
    alimentos = []
    for nombre, datos in FOOD_DATABASE.items():
        cho_porcion = (datos["cho_per_100g"] * datos["porcion_tipica_g"]) / 100
        alimentos.append({
            "nombre": nombre,
            "cho_por_100g": datos["cho_per_100g"],
            "porcion_tipica_g": datos["porcion_tipica_g"],
            "cho_por_porcion": round(cho_porcion, 1),
        })
    return {"alimentos": alimentos, "total": len(alimentos)}


@app.get("/api/v1/alimentos/buscar", tags=["Base de Alimentos"])
async def buscar_alimento(q: str):
    """
    Busca un alimento por nombre en la base de datos.
    """
    resultados = []
    q_lower = q.lower()
    for nombre, datos in FOOD_DATABASE.items():
        if q_lower in nombre:
            cho_porcion = (datos["cho_per_100g"] * datos["porcion_tipica_g"]) / 100
            resultados.append({
                "nombre": nombre,
                "cho_por_100g": datos["cho_per_100g"],
                "porcion_tipica_g": datos["porcion_tipica_g"],
                "cho_por_porcion": round(cho_porcion, 1),
            })
    return {"query": q, "resultados": resultados, "total": len(resultados)}


@app.post("/api/v1/estimar-carbohidratos", tags=["Estimador de Carbohidratos"])
async def estimar_carbohidratos(alimentos: list[str]):
    """
    Estima carbohidratos para una lista de alimentos (modo texto).

    Envía una lista de nombres de alimentos y recibirás la estimación
    de carbohidratos basada en porciones típicas.

    **Ejemplo:**
    ```json
    ["arroz blanco", "pollo", "plátano"]
    ```
    """
    return estimar_carbohidratos_offline(alimentos)


@app.post("/api/v1/analizar-imagen", tags=["Análisis de Imagen"])
async def analizar_imagen(
    image: UploadFile = File(..., description="Fotografía de los alimentos"),
    api_key: Optional[str] = Form(None, description="API key de Anthropic (Claude) para análisis por IA"),
):
    """
    Analiza una fotografía de alimentos para estimar carbohidratos.

    **Modo 1 - Con API Key de Anthropic:**
    Envía la imagen junto con tu API key de Claude para obtener
    análisis por IA con identificación automática de alimentos.

    **Modo 2 - Sin API Key:**
    La imagen se recibe pero se solicita al usuario que identifique
    los alimentos manualmente para buscar en la base de datos local.
    """
    # Read image
    image_data = await image.read()
    image_base64 = base64.b64encode(image_data).decode("utf-8")

    # Determine content type
    content_type = image.content_type or "image/jpeg"

    if api_key:
        # Use Anthropic Claude API for vision analysis
        try:
            import httpx

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 1024,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image",
                                        "source": {
                                            "type": "base64",
                                            "media_type": content_type,
                                            "data": image_base64,
                                        },
                                    },
                                    {
                                        "type": "text",
                                        "text": (
                                            "Eres un nutricionista experto en conteo de carbohidratos para personas con diabetes. "
                                            "Analiza esta imagen de alimentos y responde SOLO con un JSON válido (sin markdown, sin backticks) con esta estructura:\n"
                                            '{"alimentos": [{"nombre": "...", "porcion_estimada_g": 0, "cho_estimados": 0}], '
                                            '"carbohidratos_totales": 0, "confianza": "alta|media|baja", '
                                            '"notas": "..."}\n'
                                            "Estima porciones de forma realista. Incluye todos los alimentos visibles. "
                                            "Los carbohidratos deben ser en gramos."
                                        ),
                                    },
                                ],
                            }
                        ],
                    },
                )

                if response.status_code == 200:
                    result = response.json()
                    text_content = result["content"][0]["text"]
                    # Parse the JSON response
                    parsed = json.loads(text_content)
                    return {
                        "modo": "IA (Claude Vision)",
                        "alimentos_detectados": parsed.get("alimentos", []),
                        "carbohidratos_totales_estimados": parsed.get("carbohidratos_totales", 0),
                        "confianza": parsed.get("confianza", "media"),
                        "nota": parsed.get("notas", "Estimación por IA. Verifica con tu equipo médico."),
                    }
                else:
                    raise HTTPException(
                        status_code=502,
                        detail=f"Error de la API de Anthropic: {response.status_code} - {response.text}"
                    )

        except json.JSONDecodeError:
            return {
                "modo": "IA (Claude Vision) - respuesta parcial",
                "respuesta_cruda": text_content,
                "nota": "La IA respondió pero no en formato JSON. Revisa la respuesta cruda."
            }
        except ImportError:
            raise HTTPException(
                status_code=500,
                detail="httpx no está instalado. Ejecuta: pip install httpx"
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error al analizar imagen: {str(e)}")
    else:
        # Without API key, return guidance for manual entry
        return {
            "modo": "manual",
            "mensaje": (
                "Imagen recibida correctamente. Para análisis automático por IA, "
                "proporciona una API key de Anthropic. Alternativamente, identifica "
                "los alimentos en la foto y usa el endpoint /api/v1/estimar-carbohidratos "
                "con la lista de alimentos."
            ),
            "tip": "Usa /api/v1/alimentos/buscar?q=nombre para buscar en la base de datos.",
            "imagen_recibida": True,
            "tamano_bytes": len(image_data),
        }


# ─── Registry Models ──────────────────────────────────────────────────────────

class GlucoseLog(BaseModel):
    """Registro de glicemia, insulina y carbohidratos."""
    datetime: str = Field(..., description="Fecha y hora ISO 8601", example="2025-03-01T08:30:00Z")
    glicemia: float = Field(..., description="Glicemia en mg/dL", ge=20, le=600, example=145)
    cho: Optional[float] = Field(default=0, description="Carbohidratos ingeridos en gramos", ge=0)
    insulina: Optional[float] = Field(default=0, description="Insulina administrada en unidades", ge=0)
    momento: Optional[str] = Field(default="Otro", description="Momento: Ayunas, Desayuno, Almuerzo, Cena, Snack, Nocturno, Corrección")
    notas: Optional[str] = Field(default="", description="Notas adicionales")
    source: Optional[str] = Field(default="api", description="Fuente del registro")

class GlucoseLogResponse(GlucoseLog):
    id: str = Field(description="ID único del registro")

class StatsResponse(BaseModel):
    promedio: float
    desviacion_estandar: float
    coeficiente_variacion: float
    tiempo_en_rango: float
    tiempo_hipoglicemia: float
    tiempo_hiperglicemia: float
    hba1c_estimada: float
    total_registros: int
    insulina_total: float
    cho_total: float
    por_momento: dict


# ─── In-Memory Registry Store ────────────────────────────────────────────────
# For production, replace with a real database (SQLite, PostgreSQL, etc.)

glucose_logs: dict[str, list[GlucoseLogResponse]] = {}


def get_user_logs(user_id: str) -> list[GlucoseLogResponse]:
    return glucose_logs.get(user_id, [])


def add_user_log(user_id: str, log: GlucoseLog) -> GlucoseLogResponse:
    if user_id not in glucose_logs:
        glucose_logs[user_id] = []
    entry = GlucoseLogResponse(
        id=str(uuid.uuid4())[:8],
        **log.model_dump()
    )
    glucose_logs[user_id].append(entry)
    glucose_logs[user_id].sort(key=lambda x: x.datetime, reverse=True)
    return entry


# ─── Registry Endpoints ──────────────────────────────────────────────────────

@app.post("/api/v1/registros/{user_id}", response_model=GlucoseLogResponse, tags=["Registro Glicémico"])
async def crear_registro(user_id: str, log: GlucoseLog):
    """
    Crea un nuevo registro de glicemia, insulina y carbohidratos.

    El `user_id` es un identificador libre (ej: nombre, email, ID).
    """
    return add_user_log(user_id, log)


@app.get("/api/v1/registros/{user_id}", tags=["Registro Glicémico"])
async def obtener_registros(
    user_id: str,
    dias: Optional[int] = Query(None, description="Filtrar últimos N días"),
    momento: Optional[str] = Query(None, description="Filtrar por momento del día"),
):
    """
    Obtiene los registros de un usuario, opcionalmente filtrados por período y momento.
    """
    logs = get_user_logs(user_id)

    if dias:
        cutoff = datetime.utcnow() - timedelta(days=dias)
        logs = [l for l in logs if datetime.fromisoformat(l.datetime.replace('Z', '+00:00')).replace(tzinfo=None) >= cutoff]

    if momento:
        logs = [l for l in logs if momento.lower() in (l.momento or '').lower()]

    return {"user_id": user_id, "registros": logs, "total": len(logs)}


@app.delete("/api/v1/registros/{user_id}/{log_id}", tags=["Registro Glicémico"])
async def eliminar_registro(user_id: str, log_id: str):
    """Elimina un registro por su ID."""
    if user_id not in glucose_logs:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    original_len = len(glucose_logs[user_id])
    glucose_logs[user_id] = [l for l in glucose_logs[user_id] if l.id != log_id]
    if len(glucose_logs[user_id]) == original_len:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    return {"eliminado": True, "id": log_id}


@app.get("/api/v1/estadisticas/{user_id}", response_model=StatsResponse, tags=["Análisis y Estadísticas"])
async def obtener_estadisticas(
    user_id: str,
    dias: Optional[int] = Query(None, description="Período en días para las estadísticas"),
):
    """
    Calcula estadísticas clínicas del usuario: promedio, desviación estándar,
    tiempo en rango (TIR), HbA1c estimada, y promedios por momento del día.
    """
    logs = get_user_logs(user_id)
    if not logs:
        raise HTTPException(status_code=404, detail="Sin registros")

    if dias:
        cutoff = datetime.utcnow() - timedelta(days=dias)
        logs = [l for l in logs if datetime.fromisoformat(l.datetime.replace('Z', '+00:00')).replace(tzinfo=None) >= cutoff]

    if not logs:
        raise HTTPException(status_code=404, detail="Sin registros en el período")

    g_values = [l.glicemia for l in logs if l.glicemia]
    n = len(g_values)

    avg = sum(g_values) / n
    sd = math.sqrt(sum((v - avg) ** 2 for v in g_values) / n)
    cv = (sd / avg * 100) if avg > 0 else 0
    tir = len([v for v in g_values if 70 <= v <= 180]) / n * 100
    tir_low = len([v for v in g_values if v < 70]) / n * 100
    tir_high = len([v for v in g_values if v > 180]) / n * 100
    a1c = (avg + 46.7) / 28.7

    # By moment
    by_moment = {}
    for l in logs:
        m = l.momento or "Otro"
        if m not in by_moment:
            by_moment[m] = {"glicemias": [], "insulinas": [], "chos": []}
        if l.glicemia:
            by_moment[m]["glicemias"].append(l.glicemia)
        if l.insulina:
            by_moment[m]["insulinas"].append(l.insulina)
        if l.cho:
            by_moment[m]["chos"].append(l.cho)

    moment_stats = {}
    for m, data in by_moment.items():
        moment_stats[m] = {
            "promedio_glicemia": round(sum(data["glicemias"]) / len(data["glicemias"]), 1) if data["glicemias"] else None,
            "promedio_insulina": round(sum(data["insulinas"]) / len(data["insulinas"]), 1) if data["insulinas"] else None,
            "promedio_cho": round(sum(data["chos"]) / len(data["chos"]), 1) if data["chos"] else None,
            "n_registros": len(data["glicemias"]),
        }

    return StatsResponse(
        promedio=round(avg, 1),
        desviacion_estandar=round(sd, 1),
        coeficiente_variacion=round(cv, 1),
        tiempo_en_rango=round(tir, 1),
        tiempo_hipoglicemia=round(tir_low, 1),
        tiempo_hiperglicemia=round(tir_high, 1),
        hba1c_estimada=round(a1c, 1),
        total_registros=n,
        insulina_total=round(sum(l.insulina or 0 for l in logs), 1),
        cho_total=round(sum(l.cho or 0 for l in logs), 1),
        por_momento=moment_stats,
    )


# ─── Serve Frontend ──────────────────────────────────────────────────────────

STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/app", tags=["Frontend"])
    async def serve_frontend():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
