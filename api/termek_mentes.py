import time
from flask import Blueprint, jsonify, request
from browser_manager import browser_service

save_product_bp = Blueprint('termek_mentes', __name__)

@save_product_bp.route('/api/save', methods=['POST'])
def save_product():
    p = None
    browser = None
    context = None
    page = None

    try:
        data = request.json or {}
        if 'barcode' not in data:
            return jsonify({"error": "Hiányzó vonalkód!"}), 400

        print(f"--- [Thread] Mentés indítása: {data['barcode']} ---")

        # 1. Session indítása
        p, browser, context, page = browser_service.create_session()

        # 2. Navigáció és Keresés
        if "view=products_all" not in page.url:
            page.goto("https://szvgtoolsshop.hu/administrator/index.php?view=products_all")

        page.fill("#searchField_all", data['barcode'])
        page.keyboard.press("Enter")
        
        target_link = page.locator("a[href*='view=product&id=']").first
        target_link.wait_for(state="visible", timeout=5000)
        target_link.click()

        # 4. ADATOK MÓDOSÍTÁSA (A te logikád alapján)
        
        # --- Név frissítése ---
        if 'name' in data and data['name']:
            print(f" -> Név átírása: {data['name']}")
            page.fill("#name", "") 
            page.fill("#name", str(data['name']))

        # --- Ár frissítése ---
        if 'gross_price' in data and data['gross_price']:
            new_gross = str(data['gross_price']).replace(".", ",")
            print(f" -> Ár beállítása: {new_gross}")

            # Nettó törlése (Billentyűzet szimuláció)
            try:
                page.click("#netto")
                page.keyboard.down("Control")
                page.keyboard.press("A")
                page.keyboard.up("Control")
                page.keyboard.press("Backspace")
                page.keyboard.press("Tab") # Kilépünk a mezőből
                time.sleep(0.2) 
            except Exception as e:
                print(f"Hiba a nettó törlésénél: {e}")

            # Bruttó írása
            try:
                page.click("#brutto")
                page.keyboard.down("Control")
                page.keyboard.press("A")
                page.keyboard.up("Control")
                page.keyboard.press("Backspace")
                # Lassabb gépelés, hogy a JS biztosan érzékelje
                page.keyboard.type(new_gross, delay=100)
                page.keyboard.press("Tab") # Kilépés a kalkulációhoz
                time.sleep(0.5)
            except Exception as e:
                print(f"Hiba a bruttó írásánál: {e}")

        # 5. MENTÉS ÉS VÁRAKOZÁS (Kritikus rész!)
        save_btn = page.locator("#save_close")
        if save_btn.count() > 0:
            save_btn.click()
            try:
                page.locator("button.swal2-confirm").click(timeout=1500)
            except: pass
            
            # VÁRAKOZÁS
            print("Várakozás mentésre...")
            page.wait_for_load_state('networkidle', timeout=15000)
            
            return jsonify({"status": "success", "message": "Mentés kész!"})
        
        return jsonify({"status": "warning", "message": "Nincs mentés gomb."})

    except Exception as e:
        print(f"Mentés hiba: {e}")
        return jsonify({"error": str(e)}), 500
        
    finally:
        # 5. TAKARÍTÁS
        if page: 
            try: page.close()
            except: pass
        if context: 
            try: context.close()
            except: pass
        if browser: 
            try: browser.close()
            except: pass
        if p: 
            try: p.stop()
            except: pass
        print("--- [Thread] Munkamenet lezárva. ---")