# 🏥 Colmena Reembolso Bot

Automatización completa del proceso de solicitud de reembolso en Isapre Colmena.
Se activa automáticamente cuando llega una Boleta de Honorarios Electrónica del SII.

---

## Arquitectura

```
[Outlook/M365] → detecta email de siichile@sii.cl
      ↓
[Power Automate] → extrae PDF adjunto → llama al servidor
      ↓
[Servidor Railway] → recibe PDF → abre Colmena con Playwright
      ↓
[Portal Colmena] → login → formulario → sube PDF → envía
```

---

## Paso 1 — Desplegar el servidor en Railway

### 1.1 Crear cuenta en Railway
Ve a https://railway.app y regístrate (plan gratuito alcanza para esto).

### 1.2 Crear nuevo proyecto
- Clic en **"New Project"** → **"Deploy from GitHub repo"**
- Conecta tu GitHub y sube esta carpeta como repositorio
  - (Crea un repo nuevo en github.com, sube los archivos, y conéctalo a Railway)

### 1.3 Configurar variables de entorno
En Railway, ve a tu servicio → pestaña **"Variables"** → agrega:

| Variable          | Valor                        |
|-------------------|------------------------------|
| `COLMENA_RUT`     | Tu RUT (ej: `12345678-9`)    |
| `COLMENA_PASSWORD`| Tu contraseña de Colmena     |
| `API_SECRET`      | Una clave que tú inventes (ej: `mi-clave-secreta-2024`) |
| `PORT`            | `8000`                       |

### 1.4 Obtener la URL del servidor
Una vez desplegado, Railway te da una URL pública como:
`https://colmena-bot-production.up.railway.app`

Guárdala — la necesitas en el paso 2.

---

## Paso 2 — Configurar Power Automate

Ve a https://make.powerautomate.com e inicia sesión con tu cuenta Microsoft.

### Crear el flujo:

**Trigger:**
- Conector: **Office 365 Outlook**
- Evento: **"When a new email arrives (V3)"**
- Configurar filtros:
  - From: `siichile@sii.cl`
  - Subject filter: `Emision de Boleta de Honorarios Electronica`

**Paso 1 — Obtener adjunto:**
- Acción: **"Get attachment (V2)"**
- Message Id: usar el ID del email del trigger
- Attachment Id: seleccionar el primer adjunto

**Paso 2 — Llamar al servidor:**
- Acción: **"HTTP"**
- Method: `POST`
- URI: `https://TU-URL.up.railway.app/reembolso`
- Headers:
  ```
  X-Api-Secret: tu-clave-secreta-2024
  Content-Type: multipart/form-data
  ```
- Body: adjunto del paso anterior (archivo PDF)

**Paso 3 (opcional) — Notificación:**
- Acción: **"Send an email (V2)"**
- To: `ignacio@menichetti.cl`
- Subject: `✅ Reembolso Colmena solicitado automáticamente`
- Body: `Se procesó la boleta y se envió la solicitud de reembolso a Colmena.`

---

## Paso 3 — Verificar que funciona

1. Abre `https://TU-URL.up.railway.app/health` en el navegador
2. Debería responder: `{"status": "ok"}`
3. Envíate un correo de prueba desde siichile@sii.cl (o espera la próxima boleta real)
4. Revisa los logs en Railway para ver el proceso paso a paso

---

## Ajuste fino del script

Si el formulario cambia o hay algún selector que no funciona, edita `main.py`.
Los selectores clave están en las secciones comentadas del archivo.

Si necesitas depurar, cambia `headless=True` por `headless=False` en `main.py`
para ver el navegador en acción (solo funciona en entorno local, no en Railway).

---

## Notas de seguridad

- Las credenciales **nunca están en el código** — solo en variables de entorno de Railway
- El endpoint está protegido con `API_SECRET` — solo Power Automate puede llamarlo
- El PDF se procesa en memoria y se elimina después de cada solicitud
