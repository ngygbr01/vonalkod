import os
import threading
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
        # A globális változókat (self.playwright, self.browser) KIVETTÜK,
        # mert szálanként egyedinek kell lenniük.
        
        # A Login Lock marad, hogy ne írják felül egymás state fájlját egyszerre
        self.login_lock = threading.Lock()

    def create_session(self):
        """
        Létrehoz egy TELJESEN ÚJ Playwright példányt és böngészőt az aktuális szálnak.
        Visszatér: (playwright_object, browser, context, page)
        FONTOS: A hívónak kell mindet bezárni a finally blokkban!
        """
        print(" -> [System] Új Playwright példány indítása a szálhoz...")
        
        # 1. Playwright indítása (Local scope)
        p = sync_playwright().start()
        
        # 2. Böngésző indítása
        # Headless=False, ha látni akarod, True ha szerveren fut
        browser = p.chromium.launch(headless=False)

        # 3. Context (State kezeléssel)
        context = None
        if os.path.exists(state_file_path):
            try:
                context = browser.new_context(
                    viewport={'width': 1366, 'height': 768},
                    storage_state=state_file_path
                )
            except Exception as e:
                print(f"State betöltés hiba (tiszta indítás): {e}")
        
        if context is None:
            context = browser.new_context(viewport={'width': 1366, 'height': 768})

        page = context.new_page()
        
        # Login ellenőrzés
        self._ensure_logged_in_safely(page, context)
        
        # Visszaadunk MINDENT, mert a végén a hívónak kell leállítania a 'p'-t és a 'browser'-t is.
        return p, browser, context, page

    def _ensure_logged_in_safely(self, page, context):
        base_url = "https://szvgtoolsshop.hu/administrator/index.php?view=products_all"
        
        if "administrator" not in page.url:
            page.goto(base_url, timeout=60000)

        if page.locator("input[name='username']").is_visible():
            print("--- Login szükséges ---")
            
            # Lock használata: egyszerre csak egy szál írhatja a state.json-t
            with self.login_lock:
                # Dupla ellenőrzés a Lockon belül
                if page.locator("input[name='username']").is_visible():
                    page.fill("input[name='username']", ADMIN_USER)
                    page.fill("input[type='password']", ADMIN_PASS)
                    page.click("button:has-text('Belépés'), button[type='submit']")
                    page.wait_for_load_state('networkidle')
                    
                    # State mentése
                    context.storage_state(path=state_file_path)
                    print("Login kész, state mentve.")

browser_service = BrowserManager()