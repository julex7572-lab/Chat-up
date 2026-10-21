import re
import os

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from database import get_db, create_tables


app = Flask(__name__)

# Configure SECRET_KEY in Render's environment variables.
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "development-key-change-before-deployment"
)

# Create database tables.
create_tables()


# =========================
# HOME
# =========================

@app.route("/")
def home():
    return render_template("index.html")


# =========================
# REGISTER
# =========================

@app.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":

        username = request.form.get(
            "username", ""
        ).strip()

        email = request.form.get(
            "email", ""
        ).strip().lower()

        phone = request.form.get(
            "phone", ""
        ).strip()

        password = request.form.get(
            "password", ""
        )

        # Validate username.
        if not re.fullmatch(
            r"[A-Za-z0-9_]{3,30}",
            username
        ):
            flash(
                "Username must be 3–30 characters "
                "using letters, numbers or underscores."
            )
            return redirect(url_for("signup"))

        # Validate email.
        if not re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+",
            email
        ):
            flash("Enter a valid email address.")
            return redirect(url_for("signup"))

        # Validate phone.
        if not re.fullmatch(
            r"\+?[0-9 ()-]{7,20}",
            phone
        ):
            flash("Enter a valid phone number.")
            return redirect(url_for("signup"))

        # Validate password.
        if len(password) < 8:
            flash(
                "Your password must contain "
                "at least 8 characters."
            )
            return redirect(url_for("signup"))

        db = get_db()

        try:
            # Username, email and phone must be unique.
            db.execute(
                """
                INSERT INTO users
                (username, email, phone, password)
                VALUES (?, ?, ?, ?)
                """,
                (
                    username,
                    email,
                    phone,
                    generate_password_hash(password)
                )
            )

            db.commit()

            flash(
                "Account created successfully! "
                "Please log in."
            )

            return redirect(url_for("login"))

        except Exception as error:

            db.rollback()

            if "UNIQUE constraint failed" in str(error):
                flash(
                    "That username, email or phone "
                    "number is already registered."
                )
            else:
                app.logger.exception(
                    "Registration failed"
                )

                flash(
                    "We couldn't create your account. "
                    "Please try again."
                )

            return redirect(url_for("signup"))

        finally:
            db.close()

    return render_template("signup.html")


# =========================
# LOGIN WITH EMAIL OR PHONE
# =========================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        identity = request.form.get(
            "identity", ""
        ).strip()

        password = request.form.get(
            "password", ""
        )

        if not identity or not password:
            flash(
                "Enter your email address or phone "
                "number and your password."
            )

            return redirect(url_for("login"))

        db = get_db()

        try:
            # Users can log in using email OR phone.
            user = db.execute(
                """
                SELECT *
                FROM users
                WHERE email = ? COLLATE NOCASE
                   OR phone = ?
                """,
                (
                    identity.lower(),
                    identity
                )
            ).fetchone()

        finally:
            db.close()

        if (
            user
            and check_password_hash(
                user["password"],
                password
            )
        ):

            session.clear()

            session["user_id"] = user["id"]
            session["username"] = user["username"]

            return redirect(url_for("chat"))

        flash(
            "Incorrect email/phone number "
            "or password."
        )

    return render_template("login.html")


# =========================
# CHAT
# =========================

@app.route("/chat")
def chat():

    if "user_id" not in session:
        return redirect(url_for("login"))

    return render_template(
        "chat.html",
        username=session["username"]
    )


# =========================
# LOGOUT
# =========================

@app.route("/logout", methods=["GET", "POST"])
def logout():

    session.clear()

    return redirect(url_for("home"))


# =========================
# RUN APPLICATION
# =========================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
)
