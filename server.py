from flask import Flask, render_template
from flask_cors import CORS
from browser_manager import browser_service
from api.termek_lekeres import get_product_bp
from api.termek_mentes import save_product_bp

app = Flask(__name__, template_folder='.', static_folder='.')
CORS(app)

# Blueprint-ek regisztrálása
app.register_blueprint(get_product_bp)
app.register_blueprint(save_product_bp)

@app.route('/')
def index():
    return render_template('index.html')

def start_server():
    print("\n========================================")
    print(" BÖNGÉSZŐ ELŐKÉSZÍTÉSE A HÁTTÉRBEN...")
    print("========================================")
    try:
        browser_service.ensure_logged_in()
        print(">> BÖNGÉSZŐ KÉSZEN ÁLL A LEKÉRDEZÉSEKRE! <<\n")
    except Exception as e:
        print(f"Hiba az indítási előkészítésnél: {e}")

    print("SZERVER INDÍTÁSA: http://localhost:5001")
    app.run(host='0.0.0.0', port=5001, debug=False, threaded=False)

if __name__ == '__main__':
    start_server()