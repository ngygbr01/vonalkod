import time
import os
from flask import Blueprint, jsonify, request
from browser_manager import browser_service, state_file_path

save_product_bp = Blueprint('termek_mentes', __name__)

@save_product_bp.route('/api/save', methods=['POST'])
def save_product():
    try:
        page = browser_service.get_current_page()
        if not page: return jsonify({"error": "Nincs aktív oldal"}), 500
        
        data = request.json or {}

        # 1. Mégse gomb
        if data.get('action') == 'cancel':
            print("Mégse gomb -> Kilépés mentés nélkül.")
            if page.locator("button:has-text('Mégse'), a:has-text('Mégse')").count() > 0:
                with page.expect_navigation():
                    page.locator("button:has-text('Mégse'), a:has-text('Mégse')").first.click()
            else:
                page.goto("https://szvgtoolsshop.hu/administrator/index.php?view=products_all")
            return jsonify({"status": "warning", "message": "Kilépve mentés nélkül."})

        # 2. Mentés folyamat
        print("Mentés kérése érkezett...")

        # Név frissítése
        if 'name' in data and data['name']:
            print(f" -> Név frissítése: {data['name']}")
            page.fill("#name", "") 
            page.fill("#name", str(data['name']))

        # Ár frissítése (Special Logic)
        if 'gross_price' in data and data['gross_price']:
            new_gross = str(data['gross_price']).replace(".", ",")
            print(f" -> Ár beállítása: {new_gross}")

            # Nettó törlése billentyűzettel
            try:
                page.click("#netto")
                page.keyboard.down("Control")
                page.keyboard.press("A")
                page.keyboard.up("Control")
                page.keyboard.press("Backspace")
                page.keyboard.press("Tab")
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
                page.keyboard.type(new_gross, delay=100)
                page.keyboard.press("Tab")
                time.sleep(0.5)
            except Exception as e:
                print(f"Hiba a bruttó írásánál: {e}")

        # Mentés gomb
        save_btn = page.locator("#save_close")
        if save_btn.count() > 0:
            print("Mentés gomb megnyomása...")
            save_btn.click()
            
            # Popup kezelés
            try:
                popup_confirm = page.locator("button.swal2-confirm")
                popup_confirm.wait_for(state="visible", timeout=1000)
                if popup_confirm.is_visible():
                    with page.expect_navigation():
                        popup_confirm.click()
            except: pass
            
            try:
                page.wait_for_load_state('domcontentloaded', timeout=3000)
            except: pass

            # Session frissítése
            browser_service.context.storage_state(path=state_file_path)
            return jsonify({"status": "success", "message": "Sikeres mentés!"})
        
        else:
            return jsonify({"status": "warning", "message": "Nem volt mentés gomb."})

    except Exception as e:
        print(f"Mentés hiba: {e}")
        return jsonify({"error": str(e)}), 500