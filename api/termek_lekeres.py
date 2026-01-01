import time
import re
from flask import Blueprint, jsonify
from browser_manager import browser_service

get_product_bp = Blueprint('termek_lekeres', __name__)

@get_product_bp.route('/api/product/<barcode>', methods=['GET'])
def get_product(barcode):
    # Inicializálás
    p = None
    browser = None
    context = None
    page = None
    
    try:
        print(f"--- [Thread] Új lekérdezés: {barcode} ---")
        
        # 1. MINDENT megkapunk (Playwright object, Browser, Context, Page)
        p, browser, context, page = browser_service.create_session()

        # 2. Navigáció
        if "view=products_all" not in page.url:
             page.goto("https://szvgtoolsshop.hu/administrator/index.php?view=products_all", timeout=60000)

        if page.locator("button:has-text('Mégse')").is_visible(timeout=500):
             page.click("button:has-text('Mégse')")

        # --- 3. KERESÉS ÉS ADATKINYERÉS BLOKK ---
        print("Keresés indítása...")
        
        # !!! ITT HIÁNYZOTT A TRY !!! 
        # Ez a try fogja össze a keresést és az adatkinyerést, ehhez tartozik a lenti except.
        try:
            search_input = page.locator("#searchField_all")
            search_input.fill("")
            search_input.fill(barcode)
            page.keyboard.press("Enter")
            
            target_link = page.locator("a[href*='view=product&id=']").first
            try:
                target_link.wait_for(state="visible", timeout=5000)
            except:
                return jsonify({"error": "Nincs találat erre a kódra."}), 404

            print("Termék megnyitása...")
            with page.expect_navigation():
                target_link.click()

            # --- 4. ADATKINYERÉS ---
            print("Adatok kinyerése...")
            
            # A) NÉV
            if page.locator("input#name").count() > 0:
                 name = page.locator("input#name").input_value()
            elif page.locator("label[for='name'] + div").count() > 0:
                 name = page.locator("label[for='name'] + div").inner_text().strip()
            else:
                 name = "Név nem azonosítható"
            
            # B) CIKKSZÁM
            sku = "-"
            if page.locator("input#sku").count() > 0:
                sku = page.locator("input#sku").input_value()
            elif page.locator("#sku").count() > 0:
                sku = page.locator("#sku").inner_text()
            elif page.locator("label[for='sku'] + div").count() > 0:
                sku = page.locator("label[for='sku'] + div").inner_text().strip()

            # C) KÉSZLET
            stock = "0"
            if page.locator(".total_all").count() > 0:
                stock = page.locator(".total_all").first.inner_text().strip()
            elif page.locator(".available_all").count() > 0:
                stock = page.locator(".available_all").first.inner_text().strip()

            # D) ÁRAK
            net_price = "0"
            if page.locator("#netto").count() > 0:
                raw_net = page.locator("#netto").input_value()
                net_price = raw_net.replace(" ", "").replace(",", ".")
            
            gross_price = "0"
            if page.locator("#brutto").count() > 0:
                raw_gross = page.locator("#brutto").input_value()
                gross_price = raw_gross.replace(" ", "").replace(",", ".")
            
            # E) LEÍRÁS
            description = "-"
            try:
                # Fül váltás (Leírások)
                try:
                    tab_locator = page.locator("label[for='leirasok']").first
                    if tab_locator.is_visible():
                        tab_locator.click()
                        # Kis várakozás, hogy a CKEditor/Iframe betöltsön
                        page.wait_for_timeout(500)
                except Exception: pass

                # Szöveg kinyerés
                frame_selector = "iframe[title='HTML szerkesztő, description']"
                if page.locator(frame_selector).count() > 0:
                    description = page.frame_locator(frame_selector).locator("body").inner_text()
                elif page.locator("#description").count() > 0:
                    raw_html = page.locator("#description").input_value() or page.locator("#description").inner_text()
                    description = re.sub('<[^<]+?>', '', raw_html)
                else:
                    description = "Nincs leírás."

                if not description.strip(): description = "Üres leírás."

                # Visszalépés "Általános" fülre
                try:
                    general_tab = page.locator("label").filter(has_text="Általános").first
                    if general_tab.is_visible():
                        general_tab.click()
                        page.wait_for_timeout(200)
                    else:
                        page.locator(".tabLabel").first.click()
                except Exception: pass

            except Exception as e:
                print(f"Leírás hiba: {e}")
                description = "Hiba a leírásnál"

            # SIKERES VÁLASZ
            return jsonify({
                "name": name,
                "sku": sku,
                "stock": stock,
                "net_price": net_price,
                "gross_price": gross_price,
                "description": description,
                "barcode": barcode
            })

        # EZ AZ EXCEPT OKOZTA A HIBÁT, MERT NEM VOLT ELŐTTE A 'try:' (most már van a 3. pontnál)
        except Exception as e:
            print(f"Keresési folyamat hiba: {e}")
            return jsonify({"error": "Hiba az adatok beolvasásakor."}), 500

    except Exception as e:
        print(f"Kritikus Szerver Hiba: {e}")
        return jsonify({"error": str(e)}), 500
        
    finally:
        # 5. TELJES TAKARÍTÁS (Fontos sorrend!)
        print(f"--- [Thread] Erőforrások felszabadítása: {barcode} ---")
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