import os
import smtplib
import base64
import threading
import sys # Para imprimir logs forzados
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# Imprimir logs inmediatamente (sin esperar buffer)
print("--- ARRANQUE V4: TIMEOUTS ACTIVADOS ---", file=sys.stdout)

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
    print(">>> Iniciando Test de Email...", file=sys.stdout)
    try:
        if not MAIL_USER or not MAIL_PASS:
            return "ERROR: Faltan credenciales en Render."
        
        # Validación de contraseña (espacios)
        if " " in MAIL_PASS:
            return "<h1>ERROR CRÍTICO ❌</h1><p>La contraseña tiene espacios. Quítalos en Render Dashboard.</p>"

        msg = MIMEMultipart()
        msg['From'] = MAIL_USER
        msg['To'] = MAIL_USER
        msg['Subject'] = "Test Render V4 (Timeout 10s)"
        msg.attach(MIMEText("Prueba de conexión con timeout explícito.", 'plain'))

        print(">>> Conectando a SMTP...", file=sys.stdout)
        
        # --- CAMBIO V4: Timeout de 10 segundos ---
        # Si no conecta en 10s, cancela y muestra el error.
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10) 
        
        server.set_debuglevel(1) # Logs detallados
        print(">>> Servidor conectado. Iniciando EHLO...", file=sys.stdout)
        server.ehlo()
        print(">>> Iniciando STARTTLS...", file=sys.stdout)
        server.starttls()
        print(">>> Iniciando EHLO (Post-TLS)...", file=sys.stdout)
        server.ehlo()
        print(">>> Iniciando Login...", file=sys.stdout)
        server.login(MAIL_USER, MAIL_PASS)
        print(">>> Enviando mensaje...", file=sys.stdout)
        server.send_message(msg)
        server.quit()
        
        print(">>> ¡ENVÍO EXITOSO!", file=sys.stdout)
        return "<h1>¡ÉXITO V4! ✅</h1> <p>Correo enviado sin congelarse.</p>"
    
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

        # Hilo con manejo de errores mejorado
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
        # Enviar Admin
        enviar_smtp(MAIL_USER, f"Lead: {nombre}", f"Datos: {celular} - {correo}", binary)
        # Enviar Cliente
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

        # Timeout de 15s para envío real
        with smtplib.SMTP('smtp.gmail.com', 587, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(MAIL_USER, MAIL_PASS)
            server.send_message(msg)
            
    except Exception as e:
        print(f"!!! Error SMTP ({destinatario}): {e}", file=sys.stdout)
        raise e

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)