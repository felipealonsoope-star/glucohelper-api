# 💉 GlucoHelper API

> **Calculadora de bolus de insulina, registro glicémico y análisis clínico con IA para personas con diabetes.**

Diseñada por y para diabéticos. Compatible con terapia MDI (múltiples dosis de inyección) y bomba de insulina.

⚠️ **Disclaimer:** Esta herramienta es de apoyo y NO reemplaza el consejo médico profesional. Consulta siempre con tu endocrinólogo.

---

## ✨ Funcionalidades

| Módulo | Descripción |
|--------|-------------|
| 🧮 **Calculadora de Bolus** | Ratio I:CHO + Factor Sensibilidad + IOB. Redondeo inteligente por tipo de terapia |
| 📸 **Estimación por Foto** | Claude Vision identifica alimentos y estima carbohidratos desde una foto |
| 🍽️ **Base de Alimentos** | +50 alimentos con CHO/100g. Arma tu plato y transfiere a la calculadora |
| 📋 **Registro Glicémico** | Guarda automáticamente cada cálculo. Registro manual. Exporta CSV |
| 📊 **Gráficos y Estadísticas** | Glicemia temporal, insulina por dosis, TIR, HbA1c estimada, análisis por momento |
| 🩺 **Análisis Clínico IA** | Endocrinólogo virtual analiza tus datos y da recomendaciones personalizadas |
| ⚡ **API REST** | Swagger docs, endpoints JSON para integrar en apps móviles o bots |

---

## 🚀 Inicio Rápido

### Opción 1: Python directo
```bash
git clone https://github.com/TU_USUARIO/glucohelper-api.git
cd glucohelper-api
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Opción 2: Docker
```bash
docker build -t glucohelper .
docker run -p 8000:8000 glucohelper
```

### Acceder
- 🌐 **App Web**: http://localhost:8000/app
- 📖 **API Docs**: http://localhost:8000/docs
- 📘 **ReDoc**: http://localhost:8000/redoc

---

## 📡 API Endpoints

### Calculadora
| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/api/v1/bolus` | Calcula dosis de bolus |

### Alimentos
| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/v1/alimentos` | Lista todos los alimentos |
| `GET` | `/api/v1/alimentos/buscar?q=arroz` | Busca alimento por nombre |
| `POST` | `/api/v1/estimar-carbohidratos` | Estima CHO por lista de alimentos |
| `POST` | `/api/v1/analizar-imagen` | Analiza foto con IA (Claude Vision) |

### Registro Glicémico
| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/api/v1/registros/{user_id}` | Crea nuevo registro |
| `GET` | `/api/v1/registros/{user_id}` | Obtiene registros (filtro por días/momento) |
| `DELETE` | `/api/v1/registros/{user_id}/{log_id}` | Elimina un registro |
| `GET` | `/api/v1/estadisticas/{user_id}` | Estadísticas clínicas del usuario |

---

## 🧮 Fórmulas

```
Bolus alimenticio = Carbohidratos / Ratio I:CHO
Bolus corrector   = (Glicemia actual - Glicemia objetivo) / Factor de sensibilidad
Bolus total       = Bolus alimenticio + Bolus corrector - Insulina Activa (IOB)

HbA1c estimada    = (Promedio glicemia + 46.7) / 28.7
TIR               = % de lecturas entre 70-180 mg/dL
```

---

## 🛠️ Stack Tecnológico

- **Backend**: Python 3.12 + FastAPI
- **Frontend**: HTML/CSS/JS vanilla + Chart.js
- **IA**: Anthropic Claude API (visión + análisis clínico)
- **Deploy**: Docker, Railway, Render, o cualquier host Python

---

## 🤝 Contribuir

¿Eres diabético y programador? ¡Contribuye!

- Agrega más alimentos a la base de datos
- Mejora estimaciones de porciones regionales
- Integra con CGM (Dexcom, FreeStyle Libre)
- Agrega soporte multi-idioma
- Implementa persistencia con SQLite/PostgreSQL

---

## 📄 Licencia

MIT — Libre para uso personal y comercial.
