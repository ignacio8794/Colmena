import os
import asyncio
import tempfile
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException, Header
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Colmena Reembolso Bot")

# ─── Variables de entorno requeridas ───────────────────────────────────────────
COLMENA_RUT      = os.environ["COLMENA_RUT"]       # ej: "12345678-9"
COLMENA_PASS     = os.environ["COLMENA_PASSWORD"]
API_SECRET       = os.environ["API_SECRET"]         # clave para proteger el endpoint
NOTIFY_EMAIL     = os.environ.get("NOTIFY_EMAIL", "")  # opcional: correo de notificación

BASE_URL         = "https://www.colmena.cl/afiliados"
LOGIN_URL        = f"{BASE_URL}/#/login"
REEMBOLSO_URL    = f"{BASE_URL}/#/reembolso/solicitar"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/reembolso")
async def solicitar_reembolso(
    boleta: UploadFile = File(...),
    x_api_secret: str = Header(...)
):
    """
    Recibe el PDF de la boleta y automatiza la solicitud de reembolso en Colmena.
    Requiere el header X-Api-Secret para autenticar la llamada.
    """
    # Validar clave de API
    if x_api_secret != API_SECRET:
        raise HTTPException(status_code=401, detail="API secret inválido")

    # Guardar PDF en archivo temporal
    suffix = os.path.splitext(boleta.filename)[-1] or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await boleta.read())
        pdf_path = tmp.name

    logger.info(f"PDF guardado en {pdf_path}")

    try:
        await automatizar_reembolso(pdf_path)
        return {"status": "ok", "mensaje": "Reembolso solicitado exitosamente"}
    except Exception as e:
        logger.error(f"Error al solicitar reembolso: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(pdf_path)


async def automatizar_reembolso(pdf_path: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900}
        )
        page = await context.new_page()

        try:
            # ── 1. Login ────────────────────────────────────────────────────────
            logger.info("Navegando al login de Colmena...")
            await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)

            # Esperar campo de RUT/usuario
            await page.wait_for_selector("input[name='rut'], input[placeholder*='RUT'], input[type='text']", timeout=15000)

            # Ingresar RUT (probar selectores comunes de Colmena)
            rut_field = page.locator("input[name='rut'], input[placeholder*='RUT'], input[placeholder*='rut']").first
            await rut_field.fill(COLMENA_RUT)

            # Ingresar contraseña
            pass_field = page.locator("input[type='password']").first
            await pass_field.fill(COLMENA_PASS)

            # Clic en botón de login
            login_btn = page.locator("button[type='submit'], button:has-text('Ingresar'), button:has-text('Iniciar')").first
            await login_btn.click()

            # Esperar navegación post-login
            await page.wait_for_url("**/afiliados/**", timeout=20000)
            logger.info("Login exitoso")

            # ── 2. Ir a formulario de reembolso ────────────────────────────────
            await page.goto(REEMBOLSO_URL, wait_until="networkidle", timeout=30000)

            # Pantalla 1: datos bancarios → clic en "Continuar"
            continuar = page.locator("button:has-text('Continuar')")
            await continuar.wait_for(timeout=15000)
            await continuar.click()
            logger.info("Clic en Continuar (pantalla datos bancarios)")

            # ── 3. Seleccionar tipo de prestación ──────────────────────────────
            await page.wait_for_selector("select, [role='combobox'], .dropdown", timeout=15000)

            # Buscar el dropdown de tipo de prestación
            dropdown = page.locator("select, [role='combobox']").first
            await dropdown.click()

            # Seleccionar "Consultas (médicas, psicológicas, psiquiátricas)"
            opcion = page.locator("text=Consultas").first
            await opcion.wait_for(timeout=10000)
            await opcion.click()
            logger.info("Tipo de prestación seleccionado: Consultas")

            # ── 4. Subir archivos ───────────────────────────────────────────────
            # Esperar que aparezcan los campos de archivo
            await page.wait_for_selector("input[type='file']", timeout=15000)

            file_inputs = page.locator("input[type='file']")
            count = await file_inputs.count()
            logger.info(f"Campos de archivo encontrados: {count}")

            # Campo 1: Boleta o factura
            await file_inputs.nth(0).set_input_files(pdf_path)
            logger.info("PDF subido en 'Boleta o factura'")
            await page.wait_for_timeout(1000)

            # Campo 2: Detalle de Prestación (mismo PDF)
            if count >= 2:
                await file_inputs.nth(1).set_input_files(pdf_path)
                logger.info("PDF subido en 'Detalle de Prestación'")
                await page.wait_for_timeout(1000)

            # ── 5. Aceptar términos y condiciones ──────────────────────────────
            checkbox = page.locator("input[type='checkbox']").first
            is_checked = await checkbox.is_checked()
            if not is_checked:
                await checkbox.click()
                logger.info("Términos y condiciones aceptados")

            # ── 6. Enviar formulario ────────────────────────────────────────────
            enviar_btn = page.locator(
                "button:has-text('Enviar'), button:has-text('Solicitar'), button[type='submit']"
            ).last
            await enviar_btn.wait_for(timeout=10000)
            await enviar_btn.click()
            logger.info("Formulario enviado")

            # Esperar confirmación
            await page.wait_for_selector(
                "text=solicitud, text=enviada, text=exitosa, text=confirmación",
                timeout=15000
            )
            logger.info("✅ Reembolso solicitado exitosamente")

        finally:
            await browser.close()
