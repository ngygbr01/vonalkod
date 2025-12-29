import os
import time
import json
import re
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

# --- KONFIGURÁCIÓ ---
current_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(current_dir, '.env')
state_file_path = os.path.join(current_dir, 'state.json') # ITT TÁROLJUK A BEJELENTKEZÉST

print("--- ROBOT KONFIGURÁCIÓ BETÖLTÉSE ---")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    load_dotenv() 

ADMIN_USER = os.getenv("ADMIN_USERNAME")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD")

if not ADMIN_USER or not ADMIN_PASS:
    print("HIBA: Nincs felhasználónév/jelszó a .env fájlban!")
    exit()

app = Flask(__name__, template_folder='.', static_folder='.')
CORS(app)

# --- GLOBÁLIS VÁLTOZÓK ---
playwright_instance = None
browser_instance = None
context_instance = None
page_instance = None

def init_browser_engine():
    """Elindítja a Playwright motort és a böngészőt (csak egyszer)."""
    global playwright_instance, browser_instance, context_instance, page_instance
    
    if playwright_instance is None:
        print("1. Playwright motor indítása...")
        playwright_instance = sync_playwright().start()
    
    if browser_instance is None or not browser_instance.is_connected():
        print("2. Chromium ablak nyitása...")
        browser_instance = playwright_instance.chromium.launch(headless=False)
        
    # KÖRNYEZET (CONTEXT) KEZELÉSE STATE.JSON-NAL
    if context_instance is None:
        print("3. Böngésző kontextus létrehozása...")
        if os.path.exists(state_file_path):
            try:
                context_instance = browser_instance.new_context(
                    viewport={'width': 1366, 'height': 768},
                    storage_state=state_file_path # Sütik betöltése
                )
            except Exception as e:
                print(f"   -> Hiba a state.json betöltésekor, tiszta indítás: {e}")
                context_instance = browser_instance.new_context(viewport={'width': 1366, 'height': 768})
        else:
            print("   -> Nincs mentett munkamenet, tiszta indítás.")
            context_instance = browser_instance.new_context(viewport={'width': 1366, 'height': 768})

    if page_instance is None or page_instance.is_closed():
        print("4. Új lap nyitása...")
        page_instance = context_instance.new_page()

    return page_instance

def ensure_logged_in_and_on_list():
    """Ez a függvény felelős a bejelentkezésért és a lista oldalra navigálásért."""
    global context_instance, page_instance
    
    page = init_browser_engine()
    
    base_url = "https://szvgtoolsshop.hu/administrator/index.php?view=products_all"
    
    # Ha üres a lap, vagy nem az adminon vagyunk
    if page.url == "about:blank" or "administrator" not in page.url:
        print("Navigálás az admin felületre...")
        page.goto(base_url, timeout=60000)

    # 1. ELLENŐRZÉS: Kell-e bejelentkezni?
    try:
        if page.locator("input[name='username']").is_visible(timeout=2000):
            print("--- BEJELENTKEZÉS SZÜKSÉGES ---")
            page.fill("input[name='username']", ADMIN_USER)
            page.fill("input[type='password']", ADMIN_PASS)
            page.click("button:has-text('Belépés'), button[type='submit']")
            page.wait_for_load_state('networkidle')
            print("Bejelentkezés kész. Állapot mentése...")
            context_instance.storage_state(path=state_file_path)
        else:
            pass # Már be vagyunk jelentkezve
            
    except Exception as e:
        print(f"Login ellenőrzés hiba: {e}")

    # 2. ELLENŐRZÉS: Jó helyen vagyunk-e (Terméklista)?
    if "view=products_all" not in page.url:
        print("Nem a terméklistán vagyunk. Korrekció...")
        # Először megnézzük, nem ragadtunk-e be egy termékbe (Mégse gomb)
        if page.locator("button:has-text('Mégse')").is_visible(timeout=1000):
             page.click("button:has-text('Mégse')")
        else:
             page.goto(base_url)
        page.wait_for_load_state('domcontentloaded')
    
    return page


# --- SZERVER INDULÁSAKOR LEFUTÓ LOGIN ---
def start_browser_service():
    print("\n========================================")
    print(" BÖNGÉSZŐ ELŐKÉSZÍTÉSE A HÁTTÉRBEN...")
    print("========================================")
    try:
        ensure_logged_in_and_on_list()
        print(">> BÖNGÉSZŐ KÉSZEN ÁLL A LEKÉRDEZÉSEKRE! <<\n")
    except Exception as e:
        print(f"Hiba az indítási előkészítésnél: {e}")


@app.route('/')
def index():
    return render_template('index.html')

# --- API ENDPOINTS ---

@app.route('/api/product/<barcode>', methods=['GET'])
def get_product(barcode):
    global page_instance
    try:
        print(f"--- API Kérés: {barcode} ---")
        
        # Gyors ellenőrzés
        if page_instance is None or page_instance.is_closed():
            page = ensure_logged_in_and_on_list()
        else:
            page = page_instance
            if "administrator" not in page.url or page.locator("input[name='username']").is_visible(timeout=500):
                 page = ensure_logged_in_and_on_list()

        # Ha bent ragadtunk egy termékben az előző mentésnél, kilépünk
        if page.locator("button:has-text('Mégse')").is_visible(timeout=500):
             page.click("button:has-text('Mégse')")
             page.wait_for_load_state('domcontentloaded')

        if "view=products_all" not in page.url:
             page.goto("https://szvgtoolsshop.hu/administrator/index.php?view=products_all")

        # --- KERESÉS ---
        print("Keresés indítása...")
        try:
            search_input = page.locator("#searchField_all")
            search_input.fill(barcode)
            page.keyboard.press("Enter")
            
            time.sleep(1.5) 
            
            target_link = page.locator("a[href*='view=product&id=']").first
            if not target_link.is_visible(timeout=3000):
                 print("Nincs találat.")
                 return jsonify({"error": "Nincs találat erre a kódra."}), 404

            print("Termék megnyitása...")
            with page.expect_navigation():
                target_link.click()

            # --- UNIVERZÁLIS ADATKINYERÉS (Smart Mode) ---
            print("Adatok kinyerése...")
            
            # 1. NÉV (Name)
            if page.locator("input#name").count() > 0:
                 name = page.locator("input#name").input_value()
            elif page.locator("label[for='name'] + div").count() > 0:
                 name = page.locator("label[for='name'] + div").inner_text().strip()
            else:
                 name = "Név nem azonosítható"
            
            # 2. CIKKSZÁM (SKU)
            sku = "-"
            if page.locator("input#sku").count() > 0:
                sku = page.locator("input#sku").input_value()
            elif page.locator("#sku").count() > 0:
                sku = page.locator("#sku").inner_text()
            elif page.locator("label[for='sku'] + div").count() > 0:
                sku = page.locator("label[for='sku'] + div").inner_text().strip()

            # 3. KÉSZLET (Stock)
            stock = "0"
            if page.locator(".total_all").count() > 0:
                stock = page.locator(".total_all").first.inner_text().strip()
            elif page.locator(".available_all").count() > 0:
                stock = page.locator(".available_all").first.inner_text().strip()

            # 4. ÁRAK (Netto/Brutto)
            # A vesszőt lecseréljük pontra a megjelenítéshez
            net_price = "0"
            if page.locator("#netto").count() > 0:
                raw_net = page.locator("#netto").input_value()
                net_price = raw_net.replace(" ", "").replace(",", ".")
            
            gross_price = "0"
            if page.locator("#brutto").count() > 0:
                raw_gross = page.locator("#brutto").input_value()
                gross_price = raw_gross.replace(" ", "").replace(",", ".")
            
            # 5. LEÍRÁS (Description) - Fülváltással és visszalépéssel
            description = "-"
            try:
                # A) FÜL VÁLTÁS: Először a Leírás fülre kattintunk
                try:
                    tab_locator = page.locator("label[for='leirasok']").first
                    if tab_locator.is_visible():
                        print(" -> Leírás fülre kattintás...")
                        tab_locator.click()
                        time.sleep(0.5) # Kis idő a betöltéshez
                except Exception as tab_err:
                    print(f" -> Nem sikerült váltani a leírásra: {tab_err}")

                # B) ADATKINYERÉS: Pontosított szelektorral
                frame_selector = "iframe[title='HTML szerkesztő, description']"
                
                if page.locator(frame_selector).count() > 0:
                    description = page.frame_locator(frame_selector).locator("body").inner_text()
                elif page.locator("#description").count() > 0:
                    raw_html = page.locator("#description").input_value() or page.locator("#description").inner_text()
                    description = re.sub('<[^<]+?>', '', raw_html)
                else:
                    description = "Nincs leírás."

                if not description.strip(): description = "Üres leírás."

                # C) VISSZALÉPÉS AZ ÁLTALÁNOS FÜLRE (FONTOS!)
                # Megkeressük az "Általános" feliratú fület, hogy a Save funkció megtalálja a mezőket
                try:
                    # Keresünk egy label-t, amiben benne van, hogy "Általános"
                    general_tab = page.locator("label").filter(has_text="Általános").first
                    if general_tab.is_visible():
                        print(" -> Visszalépés az Általános fülre...")
                        general_tab.click()
                        time.sleep(0.2)
                    else:
                        # Ha nem találjuk szöveg alapján, próbáljuk meg az első fület (általában az a default)
                        print(" -> 'Általános' fül nem található név szerint, próbálkozás az első füllel...")
                        page.locator(".tabLabel").first.click()
                except Exception as back_err:
                    print(f" -> Hiba a visszalépésnél: {back_err}")

            except Exception as e:
                print(f"Leírás kinyerési hiba: {e}")
                description = "Hiba a leírásnál"

            # ... (A return jsonify részben cseréld ki a unit-ot description-re)
            return jsonify({
                "name": name,
                "sku": sku,
                "stock": stock,
                "net_price": net_price,
                "gross_price": gross_price,
                "description": description, # ITT A VÁLTOZÁS
                "barcode": barcode
            })

        except Exception as e:
            print(f"Keresési hiba részletei: {e}")
            return jsonify({"error": "Hiba az adatok beolvasásakor (lehet, hogy megváltozott az oldal szerkezete)."}), 500

    except Exception as e:
        print(f"Szerver Hiba: {e}")
        return jsonify({"error": f"Szerver hiba: {str(e)}"}), 500


# --- MÓDOSÍTOTT MENTÉS (A TE LOGIKÁDDAL: NETTÓ TÖRLÉS + BRUTTÓ GÉPELÉS) ---
@app.route('/api/save', methods=['POST'])
def save_product():
    global page_instance, context_instance
    try:
        if page_instance is None: return jsonify({"error": "Nincs aktív oldal"}), 500
        data = request.json or {}

        # 1. ESET: Ha a MÉGSE gombot nyomtuk (Cancel)
        if data.get('action') == 'cancel':
            print("Mégse gomb -> Kilépés mentés nélkül.")
            if page_instance.locator("button:has-text('Mégse'), a:has-text('Mégse')").count() > 0:
                with page_instance.expect_navigation():
                    page_instance.locator("button:has-text('Mégse'), a:has-text('Mégse')").first.click()
            else:
                page_instance.goto("https://szvgtoolsshop.hu/administrator/index.php?view=products_all")
            return jsonify({"status": "warning", "message": "Kilépve mentés nélkül."})

        # 2. ESET: MENTÉS
        print("Mentés kérése érkezett...")

        # --- NÉV FRISSÍTÉSE ---
        if 'name' in data and data['name']:
            print(f" -> Név frissítése: {data['name']}")
            page_instance.fill("#name", "") 
            page_instance.fill("#name", str(data['name']))

        # --- ÁR FRISSÍTÉSE (MANUÁLIS BILLENTYŰZET SZIMULÁCIÓ) ---
        if 'gross_price' in data and data['gross_price']:
            new_gross = str(data['gross_price']).replace(".", ",")
            print(f" -> Ár beállítása: {new_gross}")

            # A) NETTÓ MEZŐ MANUÁLIS TÖRLÉSE (Hogy ne zavarjon be a számításba)
            try:
                print(" -> Nettó mező ürítése billentyűzettel...")
                page_instance.click("#netto")
                
                # Kijelölés (Ctrl+A)
                page_instance.keyboard.down("Control")
                page_instance.keyboard.press("A")
                page_instance.keyboard.up("Control")
                
                # Törlés
                page_instance.keyboard.press("Backspace")
                
                # FONTOS: Tabulátorral kilépünk a mezőből
                page_instance.keyboard.press("Tab")
                time.sleep(0.2) 

            except Exception as e:
                print(f"Hiba a nettó törlésénél: {e}")

            # B) BRUTTÓ MEZŐ KITÖLTÉSE (Gépeléssel)
            try:
                print(f" -> Bruttó ár begépelése: {new_gross}")
                
                # Rákattintunk a bruttóra
                page_instance.click("#brutto")

                # Kijelöljük a régit (Ctrl+A -> Törlés) - Biztonság kedvéért
                page_instance.keyboard.down("Control")
                page_instance.keyboard.press("A")
                page_instance.keyboard.up("Control")
                page_instance.keyboard.press("Backspace")

                # BEGÉPELJÜK AZ ÚJ ÁRAT (karakterenként)
                # A delay=100 lassabb, de biztosabb, hogy a JS feldolgozza
                page_instance.keyboard.type(new_gross, delay=100)

                # Kilépünk a mezőből (Tab), hogy elinduljon a kalkuláció
                page_instance.keyboard.press("Tab")
                time.sleep(0.5)

            except Exception as e:
                print(f"Hiba a bruttó írásánál: {e}")

        # --- Mentés gomb kattintás (#save_close) ---
        save_btn = page_instance.locator("#save_close")
        
        if save_btn.count() > 0:
            print("Mentés gomb megnyomása...")
            save_btn.click() 
            
            # --- POPUP ELLENŐRZÉS ---
            try:
                popup_confirm = page_instance.locator("button.swal2-confirm")
                popup_confirm.wait_for(state="visible", timeout=1000)
                if popup_confirm.is_visible():
                    with page_instance.expect_navigation():
                        popup_confirm.click()
            except:
                pass
            
            # Várakozás a betöltésre
            try:
                page_instance.wait_for_load_state('domcontentloaded', timeout=3000)
            except:
                pass

            context_instance.storage_state(path=state_file_path)
            return jsonify({"status": "success", "message": "Sikeres mentés!"})
        
        else:
            print("HIBA: Nem találom a mentés gombot!")
            return jsonify({"status": "warning", "message": "Nem volt mentés gomb."})

    except Exception as e:
        print(f"Mentés hiba: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    # ELŐSZÖR ELINDÍTJUK A BÖNGÉSZŐT
    start_browser_service()
    
    print("SZERVER INDÍTÁSA: http://localhost:5001")
    app.run(host='0.0.0.0', port=5001, debug=False, threaded=False)