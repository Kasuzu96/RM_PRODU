import os
import smtplib
import base64
import threading
import socket
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv

# --- PARCHE IPV4 (VITAL PARA RENDER) ---
# Esto evita que Python intente usar IPv6 y falle
old_getaddrinfo = socket.getaddrinfo
def new_getaddrinfo(*args, **kwargs):
    responses = old_getaddrinfo(*args, **kwargs)
    return [r for r in responses if r[0] == socket.AF_INET]
socket.getaddrinfo = new_getaddrinfo
# ---------------------------------------

load_dotenv()

app = Flask(__name__)
CORS(app)

print("--- ARRANQUE V6: IPV4 + PUERTO 465 (SSL DIRECTO) ---", file=sys.stdout)

# Configuración
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase = create_client(url, key) if url and key else None

MAIL_USER = os.getenv("MAIL_USERNAME")
MAIL_PASS = os.getenv("MAIL_PASSWORD")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/test-email')
def test_email():
    print(">>> Iniciando Test V6 (SSL 465)...", file=sys.stdout)
    try:
        if not MAIL_USER or not MAIL_PASS:
            return "ERROR: Faltan credenciales."
        
        msg = MIMEMultipart()
        msg['From'] = MAIL_USER
        msg['To'] = MAIL_USER
        msg['Subject'] = "Test Render V6 (SSL 465 + IPv4)"
        msg.attach(MIMEText("Si lees esto, la combinación SSL+IPv4 funcionó.", 'plain'))

        print(">>> Conectando a SMTP_SSL (Puerto 465)...", file=sys.stdout)
        
        # --- CAMBIO CLAVE: Volvemos a SMTP_SSL pero con el parche IPv4 activo ---
        # Timeout extendido a 20s
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=20)
        server.set_debuglevel(1)
        
        print(">>> Login...", file=sys.stdout)
        server.login(MAIL_USER, MAIL_PASS)
        
        print(">>> Enviando...", file=sys.stdout)
        server.send_message(msg)
        server.quit()
        
        return "<h1>¡VICTORIA V6! ✅</h1> <p>El puerto 465 funcionó gracias al parche IPv4.</p>"
    
    except Exception as e:
        print(f"!!! ERROR TEST: {e}", file=sys.stdout)
        return f"<h1>FALLÓ ❌</h1> <p>Error:</p> <pre>{str(e)}</pre>"

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

        # Imagen
        if "," in foto_base64:
            header, encoded = foto_base64.split(",", 1)
        else:
            encoded = foto_base64
        binary = base64.b64decode(encoded)

        # HTML
        try:
            html = render_template('correo.html', nombre=nombre)
        except:
            html = f"Hola {nombre}"

        # Hilo
        hilo = threading.Thread(
            target=tarea_enviar, 
            args=(nombre, celular, correo, binary, html)
        )
        hilo.start()

        return jsonify({"status": "ok", "mensaje": "Procesando envío"})

    except Exception as e:
        return jsonify({"status": "error", "mensaje": str(e)}), 500

def tarea_enviar(nombre, celular, correo, binary, html):
    try:
        enviar_smtp(MAIL_USER, f"Lead: {nombre}", f"Datos: {celular} - {correo}", binary)
        enviar_smtp(correo, f"¡Hola {nombre}!", html, binary, es_html=True)
        print(f"--- Hilo completado para {nombre} ---", file=sys.stdout)
    except Exception as e:
        print(f"!!! Error en hilo: {e}", file=sys.stdout)

def enviar_smtp(destinatario, asunto, cuerpo, foto, es_html=False):
    try:
        msg = MIMEMultipart()
        msg['From'] = MAIL_USER
        msg['To'] = destinatario
        msg['Subject'] = asunto

        if es_html:
            msg.attach(MIMEText(cuerpo, 'html'))
        else:
            msg.attach(MIMEText(cuerpo, 'plain'))
            
        img = MIMEImage(foto, name="foto.png")
        msg.attach(img)

        # Usamos SMTP_SSL y puerto 465 también aquí
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=30) as server:
            server.login(MAIL_USER, MAIL_PASS)
            server.send_message(msg)
            
    except Exception as e:
        print(f"!!! Error SMTP ({destinatario}): {e}", file=sys.stdout)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)