from flask import Flask, render_template, request, redirect, url_for, flash, session
import mysql.connector
import uuid
import qrcode
from datetime import date
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PIL import Image
from flask import send_file, abort
from functools import wraps
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)
import secrets
import hmac
import os
from dotenv import load_dotenv
load_dotenv()
app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY")

def get_db_connection():
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD"),
        database=os.environ.get(
            "DB_NAME",
            "digital_certificate_system"
        )
    )
def admin_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if "admin_id" not in session:
            return redirect(url_for("admin_login"))

        return function(*args, **kwargs)

    return wrapper
# ADMIN LOGIN ROUTE

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if "admin_id" in session:
        return redirect(url_for("home"))

    if request.method == "POST":

        token = request.form.get("csrf_token", "")

        if not hmac.compare_digest(
            token,
            session.get("csrf_token", "")
        ):
            flash("Invalid request. Please try again.")
            return redirect(url_for("admin_login"))

        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            "SELECT * FROM admins WHERE email = %s",
            (email,)
        )

        admin = cursor.fetchone()

        cursor.close()
        connection.close()

        if admin and check_password_hash(
            admin["password"], password
        ):

            session.clear()

            session["admin_id"] = admin["id"]
            session["admin_name"] = admin["username"]

            return redirect(url_for("home"))

        else:
            flash("Invalid email or password.")

    session["csrf_token"] = secrets.token_hex(32)

    return render_template("admin_login.html")
# HOME PAGE
@app.route("/")
@admin_required
def home():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT * FROM certificates ORDER BY id DESC")
    certificates = cursor.fetchall()
    cursor.close()
    connection.close()
    return render_template("index.html", certificates=certificates)

@app.route("/generate", methods=["POST"])
@admin_required
def generate():
    student_name = request.form.get("student_name", "").strip()
    course_name = request.form.get("course_name", "").strip()

    if not student_name or not course_name:
        flash("Please enter both student name and course name.")
        return redirect(url_for("home"))

    certificate_id = "CERT-" + uuid.uuid4().hex[:10].upper()

    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        """INSERT INTO certificates
           (student_name, course_name, issue_date, certificate_id)
           VALUES (%s, %s, %s, %s)""",
        (student_name, course_name, date.today(), certificate_id)
    )
    connection.commit()
    cursor.close()
    connection.close()

    flash("Certificate generated successfully!")
    return redirect(url_for("home"))

@app.route("/verify", methods=["GET", "POST"])
def verify():
    certificate = None
    if request.method == "POST":
        certificate_id = request.form.get("certificate_id", "").strip()
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM certificates WHERE certificate_id = %s",
            (certificate_id,)
        )
        certificate = cursor.fetchone()
        cursor.close()
        connection.close()
    return render_template("verify.html", certificate=certificate)

@app.route("/download/<int:certificate_id>")
def download_certificate(certificate_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM certificates WHERE id = %s",
        (certificate_id,)
    )
    certificate = cursor.fetchone()

    cursor.close()
    connection.close()

    if certificate is None:
        abort(404)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(600, 842))
    logo_image=Image.open(r"C:\Users\haris\OneDrive\Desktop\DigitalCertificateSystem\logo1.jpeg").convert("RGB")
    pdf.drawImage(
        ImageReader(logo_image),
        465,755,
        width=90,
        height=55,
        preserveAspectRatio=True,
        mask="auto"
    )

    pdf.setStrokeColorRGB(0.08, 0.16, 0.32)
    pdf.setLineWidth(4)
    pdf.rect(25, 25, 550, 792)

    pdf.setStrokeColorRGB(0.78, 0.60, 0.25)
    pdf.setLineWidth(1.5)
    pdf.rect(35, 35, 530, 772)

    pdf.setFillColorRGB(0.08, 0.16, 0.32)
    pdf.setFont("Helvetica-Bold", 24)
    pdf.drawCentredString(300, 740, "CERTIFICATE OF ACHIEVEMENT")
    pdf.setFillColorRGB(0, 0, 0)

    pdf.setFont("Helvetica", 15)
    pdf.drawCentredString(300, 680, "This certificate is proudly presented to")

    pdf.setFillColorRGB(0.08, 0.16, 0.32)
    pdf.setFont("Helvetica-Bold", 28)
    pdf.drawCentredString(300, 625, certificate["student_name"])
    pdf.setFillColorRGB(0, 0, 0)

    pdf.setFont("Helvetica", 15)
    pdf.drawCentredString(300, 575, "For successfully completing")

    pdf.setFillColorRGB(0.78, 0.60, 0.25)
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawCentredString(300, 535, certificate["course_name"])
    pdf.setFillColorRGB(0, 0, 0)

    pdf.setFont("Helvetica", 13)
    pdf.drawCentredString(300, 460, f"Issue Date: {certificate['issue_date']}")
    pdf.drawCentredString(300, 430, f"Certificate ID: {certificate['certificate_id']}")
    qr = qrcode.make(
    f"http://127.0.0.1:5000/verify?certificate_id={certificate['certificate_id']}")

    qr_buffer = BytesIO()
    qr.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)

    pdf.drawImage(
    ImageReader(qr_buffer),
    250, 280,
    width=100,
    height=100)
    pdf.setStrokeColorRGB(0.78, 0.60, 0.25)
    pdf.setLineWidth(1.5)
    
    pdf.line(80, 180, 230, 180)

    pdf.setFillColorRGB(0.08, 0.16, 0.32)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawImage(
    "signature.jpeg",
    90, 180,
    width=130,
    height=40,
    preserveAspectRatio=True,
    mask="auto")
    pdf.drawCentredString(155, 130, "Authorized Signature")

    pdf.setFillColorRGB(0, 0, 0)

    pdf.setFillColorRGB(0, 0, 0)

    pdf.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"certificate_{certificate_id}.pdf",
        mimetype="application/pdf"
    )
# ADMIN LOGOUT ROUTE

@app.route("/admin/logout")
def admin_logout():

    session.clear()

    flash("You have successfully logged out.")

    return redirect(url_for("admin_login"))
if __name__ == "__main__":
    app.run(debug=True)