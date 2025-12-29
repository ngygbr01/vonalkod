import os
import time
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

# --- ÚTVONALAK ---
current_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(current_dir, '.env')

print("--- ROBOT INDÍTÁSA ---")
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

# Globális változók
playwright_instance = None
browser_instance = None
context_instance = None
page_instance = None

def init_browser():
    """Elindítja a böngészőt, ha még nem fut."""
    global playwright_instance, browser_instance, context_instance, page_instance
    
    if playwright_instance is None:
        print("Playwright motor indítása...")
        playwright_instance = sync_playwright().start()
    
    if browser_instance is None or not browser_instance.is_connected():
        print("Chromium ablak nyitása...")
        browser_instance = playwright_instance.chromium.launch(headless=False)
        
    if context_instance is None:
        context_instance = browser_instance.new_context(viewport={'width': 1366, 'height': 768})
        
    if page_instance is None or page_instance.is_closed():
        print("Új lap nyitása...")
        page_instance = context_instance.new_page()
        
    return page_instance

def get_active_page():
    """Visszaadja az aktív, bejelentkezett oldalt."""
    page = init_browser()

    try:
        # Ha kidobott volna, vagy nem az adminon vagyunk
        if "administrator" not in page.url:
            print("Navigálás az adminra...")
            page.goto("https://szvgtoolsshop.hu/administrator/", timeout=60000)

        # Login ellenőrzés
        try:
            if page.locator("input[name='username']").is_visible(timeout=2000):
                print("Bejelentkezés...")
                page.fill("input[name='username']", ADMIN_USER)
                page.fill("input[type='password']", ADMIN_PASS)
                page.click("button:has-text('Belépés'), button[type='submit']")
                page.wait_for_load_state('networkidle')
        except:
            pass 

    except Exception as e:
        print(f"Böngésző hiba, újraindítás... ({e})")
        try: page.close()
        except: pass
        global page_instance
        page_instance = None
        return get_active_page()

    return page

def reset_to_list_view(page):
    """Biztosítja, hogy a listanézeten legyünk a keresés előtt."""
    try:
        # Ha be vagyunk lépve egy termékbe (van Mégse gomb), lépjünk ki
        if page.locator("button:has-text('Mégse')").is_visible(timeout=1000):
            print("Előző termék nyitva maradt. Kilépés...")
            page.click("button:has-text('Mégse')")
            page.wait_for_load_state('domcontentloaded')
        
        # Ha nem a terméklistán vagyunk, navigáljunk oda
        if "view=products_all" not in page.url:
            print("Navigálás a terméklistára...")
            page.goto("https://szvgtoolsshop.hu/administrator/index.php?view=products_all")
            page.wait_for_load_state('domcontentloaded')
            
    except Exception as e:
        print(f"Hiba a lista nézetre álláskor: {e}")
        page.goto("https://szvgtoolsshop.hu/administrator/index.php?view=products_all")


@app.route('/')
def index():
    return render_template('index.html')

# --- 1. LÉPÉS: KERESÉS ÉS MEGNYITÁS ---
@app.route('/api/product/<barcode>', methods=['GET'])
def get_product(barcode):
    try:
        page = get_active_page()
        
        # Biztosítjuk, hogy tiszta lappal induljunk (ha előzőleg nem mentettünk)
        reset_to_list_view(page)
        
        print(f"--- Keresés: {barcode} ---")

        # Keresés
        print("Keresőmező kitöltése...")
        try:
            search_input = page.locator("#searchField_all")
            search_input.wait_for(state="visible", timeout=10000)
            search_input.fill("") 
            search_input.type(barcode, delay=50) 
            page.keyboard.press("Enter")
            time.sleep(2) # Várunk a JS frissítésre
        except Exception as e:
            return jsonify({"error": "Keresőmező hiba."}), 500

        # Találat megnyitása
        target_link_selector = "a[href*='view=product&id=']"
        try:
            if page.locator(target_link_selector).count() == 0:
                print("Nincs találat.")
                return jsonify({"error": "Nincs találat erre a kódra."}), 404
                
            print("Termék megnyitása...")
            with page.expect_navigation():
                page.click(f"{target_link_selector} >> nth=0")
        except Exception as e:
             return jsonify({"error": f"Hiba a megnyitásnál: {e}"}), 500

        # Adatok kinyerése
        print("Adatok olvasása...")
        try:
            page.wait_for_selector("label[for='name']", timeout=10000)

            name = page.locator("label[for='name'] + div").inner_text().strip()
            
            sku = "-"
            if page.locator("#sku").count() > 0:
                sku = page.locator("#sku").input_value()

            stock = "0"
            if page.locator(".total_all").count() > 0:
                stock = page.locator(".total_all").first.inner_text().strip()
            elif page.locator(".available_all").count() > 0:
                stock = page.locator(".available_all").first.inner_text().strip()

            net_price = page.locator("#netto").input_value()
            gross_price = page.locator("#brutto").input_value()
            
            unit = "db"
            if page.locator("label[for='unit'] + div").count() > 0:
                unit = page.locator("label[for='unit'] + div").inner_text().strip()

        except Exception as e:
            print(f"Hiba az adat kinyerésnél: {e}")
            return jsonify({"error": "Nem sikerült kiolvasni az adatokat."}), 500

        print(f"Siker: {name}. VÁRAKOZÁS MENTÉSRE...")
        # ITT A KÜLÖNBSÉG: Nem lépünk ki, hanem visszaküldjük az adatot és várunk.

        return jsonify({
            "name": name,
            "sku": sku,
            "stock": stock,
            "net_price": net_price,
            "gross_price": gross_price,
            "unit": unit,
            "barcode": barcode
        })

    except Exception as e:
        print(f"Szerver Hiba: {e}")
        return jsonify({"error": f"Szerver hiba: {str(e)}"}), 500


# --- 2. LÉPÉS: MENTÉS ÉS KILÉPÉS ---
@app.route('/api/save', methods=['POST'])
def save_product():
    try:
        page = get_active_page()
        print("Mentés kérése érkezett...")

        # Opcionális: Ha küldtél adatot (pl. új ár), itt beírhatnánk a page.fill-el.
        # Most csak a mentés gombot nyomjuk meg.

        # Megkeressük a 'Mentés és bezárás' gombot
        save_btn = page.locator("button:has-text('Mentés és bezárás'), .button-save-close")
        
        if save_btn.count() > 0:
            print("Mentés gomb megnyomva.")
            with page.expect_navigation(): # Megvárjuk amíg visszatér a listához
                save_btn.first.click()
            print("Sikeresen mentve és bezárva.")
            return jsonify({"status": "success", "message": "Termék mentve!"})
        else:
            print("Nem találtam Mentés gombot! Kilépés Mégse gombbal.")
            # Ha nincs mentés, legalább lépjünk ki
            cancel_btn = page.locator("button:has-text('Mégse')")
            if cancel_btn.count() > 0:
                cancel_btn.first.click()
            return jsonify({"status": "warning", "message": "Nem volt mentés gomb, csak kiléptem."})

    except Exception as e:
        print(f"Mentés hiba: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("SZERVER FUT (Single Thread): http://localhost:5001")
    app.run(host='0.0.0.0', port=5001, debug=False, threaded=False)