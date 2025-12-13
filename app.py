import os
import smtplib
import base64
import threading
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv

# 1. Cargar variables de entorno
load_dotenv()

app = Flask(__name__)
CORS(app)

# 2. Configurar Supabase
url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url, key) if url and key else None

# 3. Configurar Gmail
MAIL_USER = os.getenv("MAIL_USERNAME")
MAIL_PASS = os.getenv("MAIL_PASSWORD")

# --- RUTA PRINCIPAL ---
@app.route('/')
def index():
    return render_template('index.html')

# --- RUTA DE DIAGNÓSTICO (Prueba el correo en vivo) ---
@app.route('/test-email')
def test_email():
    try:
        if not MAIL_USER or not MAIL_PASS:
            return "ERROR: Faltan variables de entorno MAIL_USERNAME o MAIL_PASSWORD."

        msg = MIMEMultipart()
        msg['From'] = MAIL_USER
        msg['To'] = MAIL_USER
        msg['Subject'] = "Prueba Diagnóstico Render (Puerto 587) 🚀"
        msg.attach(MIMEText("Si lees esto, el puerto 587 funciona y el bloqueo se ha superado.", 'plain'))

        # CONEXIÓN DIRECTA PARA DIAGNÓSTICO (Puerto 587 + STARTTLS)
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.set_debuglevel(1) # Muestra detalles en los logs de Render
        server.starttls()        # Encriptamos la conexión
        server.login(MAIL_USER, MAIL_PASS)
        server.send_message(msg)
        server.quit()
        
        return "<h1>¡ÉXITO TOTAL! ✅</h1> <p>El correo salió por el puerto 587. Ahora la app debería funcionar.</p>"
    
    except Exception as e:
        return f"<h1>FALLÓ ❌</h1> <p>Error exacto:</p> <pre>{str(e)}</pre>"

# --- RUTA PARA GUARDAR Y ENVIAR ---
@app.route('/guardar', methods=['POST'])
def guardar_datos():
    try:
        data = request.json
        
        nombre = data.get('nombre')
        celular = data.get('celular')
        correo_usuario = data.get('correo')
        foto_base64 = data.get('foto')

        # 1. Guardar en Supabase (Rápido)
        if supabase:
            try:
                datos_usuario = {
                    "nombre": nombre,
                    "celular": celular,
                    "correo": correo_usuario
                }
                supabase.table('usuarios').insert(datos_usuario).execute()
            except Exception as e:
                print(f"Advertencia Supabase: {e}")

        # 2. Procesar Imagen
        if "," in foto_base64:
            header, encoded = foto_base64.split(",", 1)
        else:
            encoded = foto_base64  
        binary_data = base64.b64decode(encoded)

        # 3. Preparar HTML del cliente
        try:
            html_cliente = render_template('correo.html', nombre=nombre)
        except:
            html_cliente = f"<h1>Hola {nombre}</h1><p>Gracias por tu registro.</p>"

        # 4. Enviar Correos en SEGUNDO PLANO (Threading)
        # Esto evita el error de Timeout porque responde al usuario antes de enviar el mail
        hilo = threading.Thread(
            target=tarea_enviar_correos, 
            args=(nombre, celular, correo_usuario, binary_data, html_cliente)
        )
        hilo.start()

        return jsonify({"status": "ok", "mensaje": "Datos guardados. Correos procesándose."})

    except Exception as e:
        print(f"Error crítico: {e}")
        return jsonify({"status": "error", "mensaje": str(e)}), 500

# --- TAREA EN SEGUNDO PLANO ---
def tarea_enviar_correos(nombre, celular, correo_usuario, binary_data, html_cliente):
    """Se ejecuta en un hilo aparte para no bloquear al usuario"""
    try:
        enviar_correo_admin(nombre, celular, correo_usuario, binary_data)
        enviar_correo_cliente_con_html(nombre, correo_usuario, binary_data, html_cliente)
        print(f"--- Hilo finalizado: Correos enviados para {nombre} ---")
    except Exception as e:
        print(f"!!! ERROR EN HILO DE CORREO: {e}")

# --- FUNCIONES DE CONSTRUCCIÓN DE CORREO ---

def enviar_correo_admin(nombre, celular, correo_cliente, foto_bytes):
    msg = MIMEMultipart()
    msg['From'] = MAIL_USER
    msg['To'] = MAIL_USER
    msg['Subject'] = f"🔔 Nuevo Lead: {nombre}"

    html = f"""
    <h3>Nuevo Registro Capturado</h3>
    <ul>
        <li><b>Nombre:</b> {nombre}</li>
        <li><b>Celular:</b> {celular}</li>
        <li><b>Correo:</b> {correo_cliente}</li>
    </ul>
    """
    msg.attach(MIMEText(html, 'html'))
    image = MIMEImage(foto_bytes, name=f"registro_{nombre}.png")
    msg.attach(image)
    
    enviar_smtp_seguro(msg)

def enviar_correo_cliente_con_html(nombre, destinatario, foto_bytes, html_content):
    msg = MIMEMultipart()
    msg['From'] = MAIL_USER
    msg['To'] = destinatario 
    msg['Subject'] = f"¡Hola {nombre}, aquí tienes tu foto! 📸"

    msg.attach(MIMEText(html_content, 'html'))
    image = MIMEImage(foto_bytes, name="tu_foto.png")
    msg.attach(image)

    enviar_smtp_seguro(msg)

# --- FUNCIÓN DE ENVÍO SMTP (Puerto 587) ---
def enviar_smtp_seguro(mensaje):
    """
    Usa el puerto 587 con STARTTLS.
    Esencial para evitar el bloqueo de red de Render (Errno 101).
    """
    try:
        # Usamos smtplib.SMTP estándar (no _SSL) + Puerto 587
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.ehlo()      # Saludo
            server.starttls()  # Encriptación activa
            server.ehlo()      # Re-saludo seguro
            server.login(MAIL_USER, MAIL_PASS)
            server.send_message(mensaje)
            print(f"--> Correo enviado a: {mensaje['To']}")
            
    except Exception as e:
        print(f"!!! Error SMTP: {e}")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)