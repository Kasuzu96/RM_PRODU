import os
import base64
import threading
import sys
import requests # <--- Usaremos requests para hablar con Brevo
import json
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

print("--- ARRANQUE V9: API BREVO (HTTPS) ---", file=sys.stdout)

# 1. Configuración Supabase
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase = create_client(url, key) if url and key else None

# 2. Configuración Brevo
BREVO_KEY = os.getenv("BREVO_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_NAME = os.getenv("SENDER_NAME", "Fiesta App")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/test-email')
def test_email():
    print(">>> Iniciando Test Brevo...", file=sys.stdout)
    try:
        if not BREVO_KEY or not SENDER_EMAIL:
            return "ERROR: Faltan credenciales BREVO en Render."

        # Enviar prueba simple
        respuesta = enviar_brevo(
            SENDER_EMAIL, # Te lo envías a ti mismo
            "Prueba de Conexión Brevo 🚀",
            "<h1>¡Funciona!</h1><p>Si lees esto, Render ya no bloquea tus correos.</p>",
            None # Sin foto
        )
        
        return f"<h1>¡RESULTADO!</h1> <pre>{json.dumps(respuesta, indent=2)}</pre>"
    
    except Exception as e:
        return f"<h1>FALLÓ ❌</h1> <pre>{str(e)}</pre>"

@app.route('/guardar', methods=['POST'])
def guardar_datos():
    try:
        data = request.json
        nombre = data.get('nombre')
        celular = data.get('celular')
        correo = data.get('correo')
        foto_base64 = data.get('foto')

        # Supabase
        if supabase:
            try:
                supabase.table('usuarios').insert({
                    "nombre": nombre, "celular": celular, "correo": correo
                }).execute()
            except Exception as e:
                print(f"Error Supabase: {e}", file=sys.stdout)

        # Limpiar base64
        encoded_img = foto_base64
        if "," in foto_base64:
            header, encoded_img = foto_base64.split(",", 1)

        # HTML
        try:
            html_cliente = render_template('correo.html', nombre=nombre)
        except:
            html_cliente = f"<h1>Hola {nombre}</h1><p>Aquí está tu recuerdo.</p>"

        # Hilo
        hilo = threading.Thread(
            target=tarea_enviar_brevo, 
            args=(nombre, celular, correo, encoded_img, html_cliente)
        )
        hilo.start()

        return jsonify({"status": "ok", "mensaje": "Enviando con Brevo..."})

    except Exception as e:
        return jsonify({"status": "error", "mensaje": str(e)}), 500

def tarea_enviar_brevo(nombre, celular, correo_cliente, foto_b64, html_cliente):
    try:
        # 1. Al Admin
        enviar_brevo(
            SENDER_EMAIL,
            f"🔔 Nuevo Lead: {nombre}",
            f"<p>Nombre: {nombre}<br>Cel: {celular}<br>Email: {correo_cliente}</p>",
            foto_b64
        )
        
        # 2. Al Cliente (AQUÍ SÍ FUNCIONA CON CUALQUIER CORREO)
        enviar_brevo(
            correo_cliente,
            f"¡Hola {nombre}, tu foto de la fiesta! 📸",
            html_cliente,
            foto_b64
        )
        print(f"--- Brevo: Correos enviados para {nombre} ---", file=sys.stdout)

    except Exception as e:
        print(f"!!! Error Brevo: {e}", file=sys.stdout)

def enviar_brevo(destinatario, asunto, html_content, foto_b64):
    url = "https://api.brevo.com/v3/smtp/email"
    
    headers = {
        "accept": "application/json",
        "api-key": BREVO_KEY,
        "content-type": "application/json"
    }
    
    payload = {
        "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
        "to": [{"email": destinatario}],
        "subject": asunto,
        "htmlContent": html_content
    }

    # Adjuntar foto si existe
    if foto_b64:
        payload["attachment"] = [
            {
                "content": foto_b64,
                "name": "recuerdo_fiesta.png"
            }
        ]

    try:
        response = requests.post(url, json=payload, headers=headers)
        print(f"Status Brevo ({destinatario}): {response.status_code}", file=sys.stdout)
        return response.json()
    except Exception as e:
        print(f"Error Request Brevo: {e}", file=sys.stdout)
        raise e

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)