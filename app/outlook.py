import os
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

SESSION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".outlook_session.json")
OUTLOOK_URL = "https://outlook.office.com/mail/"


def _do_login(page, email: str, password: str):
    page.locator('input[type="email"]').fill(email, timeout=15000)
    page.locator('input[type="submit"]').click()
    page.wait_for_load_state("networkidle", timeout=20000)

    page.locator('input[type="password"]').fill(password, timeout=15000)
    page.locator('input[type="submit"]').click()

    # "Continuar conectado?" → Não
    try:
        page.locator("#idBtn_Back").click(timeout=8000)
    except PlaywrightTimeout:
        pass

    page.wait_for_url("**/mail/**", timeout=60000)


def _ensure_logged_in(page, context, email: str, password: str, session_path: str):
    page.goto(OUTLOOK_URL, wait_until="networkidle", timeout=30000)

    if "login" in page.url or "microsoftonline" in page.url:
        print("Sessão expirada — fazendo login...")
        _do_login(page, email, password)
        context.storage_state(path=session_path)
        print("Sessão salva.")


def fetch_nfse_pdf(nfse_number: str) -> str | None:
    email = os.getenv("OUTLOOK_EMAIL")
    password = os.getenv("OUTLOOK_PASSWORD")

    if not email or not password:
        print("OUTLOOK_EMAIL ou OUTLOOK_PASSWORD ausentes no .env.")
        return None

    session_path = os.path.abspath(SESSION_FILE)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = (
            browser.new_context(storage_state=session_path)
            if os.path.exists(session_path)
            else browser.new_context()
        )
        page = context.new_page()

        try:
            _ensure_logged_in(page, context, email, password, session_path)

            # Abre a busca e pesquisa o número da NFSe
            page.locator('[aria-label="Pesquisar"], [aria-label="Search"]').first.click(timeout=10000)
            page.wait_for_timeout(500)
            search_input = page.locator('input[aria-label*="Pesquisar"], input[aria-label*="Search"]').first
            search_input.fill(nfse_number, timeout=10000)
            page.keyboard.press("Enter")
            page.wait_for_timeout(4000)

            # Clica no primeiro email dos resultados
            first_email = page.locator('[role="option"], [role="listitem"]').first
            first_email.click(timeout=15000)
            page.wait_for_timeout(2000)

            # Encontra e baixa o anexo PDF
            pdf_locator = page.locator('[aria-label$=".pdf"], [title$=".pdf"], button:has-text(".pdf")').first

            save_dir = "static/anexos"
            os.makedirs(save_dir, exist_ok=True)
            filepath = os.path.join(save_dir, f"nfse_{nfse_number}.pdf")

            with page.expect_download(timeout=30000) as dl_info:
                pdf_locator.click(timeout=10000)

            dl_info.value.save_as(filepath)
            print(f"PDF salvo em: {filepath}")
            return filepath

        except PlaywrightTimeout as e:
            print(f"Timeout na automação do Outlook: {e}")
            return None
        except Exception as e:
            print(f"Erro na automação do Outlook: {e}")
            return None
        finally:
            browser.close()
