import re
import os
from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash
)
from werkzeug.security import (
    generate_password_hash, check_password_hash
)
from database import get_db, create_tables

app = Flask(__name__)

# Set a secret key in your hosting environment before deployment.
app.secret_key = os.environ.get(
    "SECRET_KEY", "development-key-change-before-deployment"
)

create_tables()


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")

        if not re.fullmatch(r"[A-Za-z0-9_]{3,30}", username):
            flash("Username must be 3–30 characters using letters, numbers or underscores.")
            return redirect(url_for("signup"))

        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            flash("Enter a valid email address.")
            return redirect(url_for("signup"))

        if not re.fullmatch(r"\+?[0-9 ()-]{7,20}", phone):
            flash("Enter a valid phone number.")
            return redirect(url_for("signup"))

        if len(password) < 8:
            flash("Your password must contain at least 8 characters.")
            return redirect(url_for("signup"))

        db = get_db()

        try:
            db.execute(
                """
                INSERT INTO users (username, email, phone, password)
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
            flash("Account created successfully! Please log in.")
            return redirect(url_for("login"))

        except Exception as error:
            db.rollback()
            if "UNIQUE constraint failed" in str(error):
                flash("That username, email or phone number is already registered.")
            else:
                app.logger.exception("Registration failed")
                flash("We couldn't create your account. Please try again.")
            return redirect(url_for("signup"))

        finally:
            db.close()

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identity = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        db = get_db()

        try:
            user = db.execute(
                """
                SELECT * FROM users
                WHERE username = ? COLLATE NOCASE
                   OR email = ? COLLATE NOCASE
                """,
                (identity, identity)
            ).fetchone()
        finally:
            db.close()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("chat"))

        flash("Incorrect username/email or password.")

    return render_template("login.html")


@app.route("/chat")
def chat():
    if "user_id" not in session:
        return redirect(url_for("login"))

    return render_template(
        "chat.html",
        username=session["username"]
    )


@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
