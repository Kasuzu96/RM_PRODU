import os
import smtplib
import base64
import threading
import socket  # <--- Necesario para el parche
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv

# --- PARCHE DE COMPATIBILIDAD IPV4 (SOLUCIÓN ERROR 101) ---
# Esto obliga a Python a usar solo conexiones IPv4 antiguas y estables
# ignorando IPv6 que causa el error "Network unreachable" en Render.
old_getaddrinfo = socket.getaddrinfo
def new_getaddrinfo(*args, **kwargs):
    responses = old_getaddrinfo(*args, **kwargs)
    return [r for r in responses if r[0] == socket.AF_INET]
socket.getaddrinfo = new_getaddrinfo
# ----------------------------------------------------------

load_dotenv()

app = Flask(__name__)
CORS(app)

print("--- ARRANQUE V5: PARCHE IPV4 ACTIVADO ---", file=sys.stdout)

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
    print(">>> Iniciando Test V5...", file=sys.stdout)
    try:
        if not MAIL_USER or not MAIL_PASS:
            return "ERROR: Faltan credenciales."
        
        if " " in MAIL_PASS:
            return "<h1>ERROR</h1><p>La contraseña tiene espacios. Quítalos en Render.</p>"

        msg = MIMEMultipart()
        msg['From'] = MAIL_USER
        msg['To'] = MAIL_USER
        msg['Subject'] = "Test Render V5 (IPv4 Forzado)"
        msg.attach(MIMEText("Si lees esto, el parche IPv4 funcionó y superamos el error 101.", 'plain'))

        print(">>> Conectando a SMTP (Puerto 587)...", file=sys.stdout)
        
        # Conexión estándar
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=20)
        server.set_debuglevel(1)
        
        print(">>> STARTTLS...", file=sys.stdout)
        server.ehlo()
        server.starttls()
        server.ehlo()
        
        print(">>> Login...", file=sys.stdout)
        server.login(MAIL_USER, MAIL_PASS)
        
        print(">>> Enviando...", file=sys.stdout)
        server.send_message(msg)
        server.quit()
        
        return "<h1>¡VICTORIA! ✅</h1> <p>Correo enviado usando IPv4.</p>"
    
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

        with smtplib.SMTP('smtp.gmail.com', 587, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(MAIL_USER, MAIL_PASS)
            server.send_message(msg)
            
    except Exception as e:
        print(f"!!! Error SMTP ({destinatario}): {e}", file=sys.stdout)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)