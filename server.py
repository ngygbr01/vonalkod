from flask import Flask, render_template
from flask_cors import CORS
# A browser_manager import maradhat, de itt most nem hívunk meg belőle semmit indításkor
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
    print("----------------------------------------------------")
    print(" SZERVER INDÍTÁSA (Multi-user mód)")
    print(" Minden bejövő kérés új, izolált böngészőt kap.")
    print("----------------------------------------------------")
    
    # KIVETTÜK EZT A SORT: browser_service.start_global_browser()
    # Mert már nincs globális böngésző, mindenki sajátot kap.

    print("SZERVER FUT: http://localhost:5001")
    
    # threaded=True engedélyezi a párhuzamos kéréseket
    app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)

if __name__ == '__main__':
    start_server()