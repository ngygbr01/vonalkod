import os
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

# --- KONFIGURÁCIÓ ---
current_dir = os.path.dirname(os.path.abspath(__file__))
state_file_path = os.path.join(current_dir, 'state.json')

load_dotenv()
ADMIN_USER = os.getenv("ADMIN_USERNAME")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD")

class BrowserManager:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def init_browser(self):
        """Elindítja a Playwright motort és a böngészőt."""
        if self.playwright is None:
            print("1. Playwright motor indítása...")
            self.playwright = sync_playwright().start()
        
        if self.browser is None or not self.browser.is_connected():
            print("2. Chromium ablak nyitása...")
            self.browser = self.playwright.chromium.launch(headless=False)
            
        # KÖRNYEZET (CONTEXT) KEZELÉSE STATE.JSON-NAL
        if self.context is None:
            print("3. Böngésző kontextus létrehozása...")
            if os.path.exists(state_file_path):
                try:
                    self.context = self.browser.new_context(
                        viewport={'width': 1366, 'height': 768},
                        storage_state=state_file_path
                    )
                except Exception as e:
                    print(f"   -> Hiba a state.json betöltésekor: {e}")
                    self.context = self.browser.new_context(viewport={'width': 1366, 'height': 768})
            else:
                self.context = self.browser.new_context(viewport={'width': 1366, 'height': 768})

        if self.page is None or self.page.is_closed():
            print("4. Új lap nyitása...")
            self.page = self.context.new_page()

        return self.page

    def ensure_logged_in(self):
        """Bejelentkezés és navigáció az admin felületre."""
        page = self.init_browser()
        base_url = "https://szvgtoolsshop.hu/administrator/index.php?view=products_all"
        
        if page.url == "about:blank" or "administrator" not in page.url:
            page.goto(base_url, timeout=60000)

        # 1. Login ellenőrzés
        try:
            if page.locator("input[name='username']").is_visible(timeout=2000):
                print("--- BEJELENTKEZÉS SZÜKSÉGES ---")
                page.fill("input[name='username']", ADMIN_USER)
                page.fill("input[type='password']", ADMIN_PASS)
                page.click("button:has-text('Belépés'), button[type='submit']")
                page.wait_for_load_state('networkidle')
                print("Bejelentkezés kész. Állapot mentése...")
                self.context.storage_state(path=state_file_path)
        except Exception as e:
            print(f"Login ellenőrzés hiba: {e}")

        # 2. Navigációs korrekció
        if "view=products_all" not in page.url:
            if page.locator("button:has-text('Mégse')").is_visible(timeout=1000):
                 page.click("button:has-text('Mégse')")
            else:
                 page.goto(base_url)
            page.wait_for_load_state('domcontentloaded')
        
        return page

    def get_current_page(self):
        """Visszaadja az aktív oldalt, ha van, ha nincs, elindítja."""
        if self.page is None or self.page.is_closed():
            return self.ensure_logged_in()
        return self.page

# Singleton példány létrehozása
browser_service = BrowserManager()