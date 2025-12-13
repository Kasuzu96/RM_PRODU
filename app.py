import os
import smtplib
import base64
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv

# 1. Cargar variables de entorno (desde .env en local)
load_dotenv()

app = Flask(__name__)
CORS(app)

# 2. Configurar Supabase con variables de entorno
url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")

# Validación básica para evitar errores si faltan variables
if not url or not key:
    print("ADVERTENCIA: Faltan las credenciales de Supabase en el archivo .env")

# Inicializar cliente Supabase (si hay credenciales)
supabase: Client = create_client(url, key) if url and key else None

# 3. Configurar Gmail
MAIL_USER = os.getenv("MAIL_USERNAME")
MAIL_PASS = os.getenv("MAIL_PASSWORD")

# --- RUTAS ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/guardar', methods=['POST'])
def guardar_datos():
    try:
        data = request.json
        
        nombre = data.get('nombre')
        celular = data.get('celular')
        correo_usuario = data.get('correo')
        foto_base64 = data.get('foto')

        # --- A. Guardar datos en Supabase (Nube) ---
        if supabase:
            datos_usuario = {
                "nombre": nombre,
                "celular": celular,
                "correo": correo_usuario
            }
            # Insertar en la tabla 'usuarios'
            supabase.table('usuarios').insert(datos_usuario).execute()
        
        # --- B. Procesar Imagen (Decodificar Base64) ---
        # Limpiar encabezado si existe
        if "," in foto_base64:
            header, encoded = foto_base64.split(",", 1)
        else:
            encoded = foto_base64
            
        binary_data = base64.b64decode(encoded)

        # --- C. Enviar los DOS correos ---
        
        # 1. Correo para TI (Admin) - Reporte técnico
        enviar_correo_admin(nombre, celular, correo_usuario, binary_data)
        
        # 2. Correo para el CLIENTE - Diseño bonito desde 'correo.html'
        enviar_correo_cliente(nombre, correo_usuario, binary_data)

        return jsonify({"status": "ok", "mensaje": "Guardado en Supabase y correos enviados"})

    except Exception as e:
        print(f"Error crítico en el servidor: {e}")
        return jsonify({"status": "error", "mensaje": str(e)}), 500

# --- FUNCIONES DE CORREO ---

def enviar_correo_admin(nombre, celular, correo_cliente, foto_bytes):
    """Envía un reporte técnico a tu propio correo"""
    msg = MIMEMultipart()
    msg['From'] = MAIL_USER
    msg['To'] = MAIL_USER # Te llega a ti mismo
    msg['Subject'] = f"🔔 Nuevo Lead Capturado: {nombre}"

    # HTML simple hardcodeado para el reporte interno
    html = f"""
    <h3>Nuevo Registro Capturado</h3>
    <p>Detalles del usuario:</p>
    <ul>
        <li><b>Nombre:</b> {nombre}</li>
        <li><b>Celular:</b> {celular}</li>
        <li><b>Correo:</b> {correo_cliente}</li>
    </ul>
    <p>Se adjunta la evidencia fotográfica.</p>
    """
    msg.attach(MIMEText(html, 'html'))
    
    # Adjuntar foto
    image = MIMEImage(foto_bytes, name=f"registro_{nombre}.png")
    msg.attach(image)
    
    enviar_smtp(msg)

def enviar_correo_cliente(nombre, destinatario, foto_bytes):
    """Envía el correo de agradecimiento al cliente usando la plantilla HTML"""
    msg = MIMEMultipart()
    msg['From'] = MAIL_USER
    msg['To'] = destinatario 
    msg['Subject'] = f"¡Hola {nombre}, aquí tienes tu foto! 📸"

    # Cargar el archivo templates/correo.html e inyectar el nombre
    try:
        html_content = render_template('correo.html', nombre=nombre)
    except Exception as e:
        # Fallback por si no existe el archivo, para que no falle el envío
        print(f"Error cargando template correo.html: {e}")
        html_content = f"<h1>Hola {nombre}</h1><p>Aquí tienes tu foto.</p>"

    msg.attach(MIMEText(html_content, 'html'))

    # Adjuntar foto
    image = MIMEImage(foto_bytes, name="tu_foto.png")
    msg.attach(image)

    enviar_smtp(msg)

def enviar_smtp(mensaje):
    """Función genérica para conectar con Gmail y enviar"""
    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(MAIL_USER, MAIL_PASS)
            server.send_message(mensaje)
            print(f"Correo enviado a {mensaje['To']}")
    except Exception as e:
        print(f"Error enviando correo SMTP: {e}")

# --- INICIO DEL SERVIDOR ---
if __name__ == '__main__':
    # Render asigna un puerto en la variable de entorno PORT
    # Si no existe, usa el 5000 (para local)
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)