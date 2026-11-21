
import re
import os
import secrets

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

from werkzeug.utils import secure_filename

from database import get_db, create_tables


app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "development-key-change-before-deployment"
)

# =========================
# VIDEO UPLOAD SETTINGS
# =========================

app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

VIDEO_FOLDER = os.path.join(
    app.root_path,
    "static",
    "uploads",
    "videos"
)

os.makedirs(VIDEO_FOLDER, exist_ok=True)

ALLOWED_VIDEO_EXTENSIONS = {
    "mp4",
    "webm",
    "mov"
}

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

        if not re.fullmatch(
            r"[A-Za-z0-9_]{3,30}",
            username
        ):
            flash(
                "Username must be 3–30 characters "
                "using letters, numbers or underscores."
            )
            return redirect(url_for("signup"))

        if not re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+",
            email
        ):
            flash("Enter a valid email address.")
            return redirect(url_for("signup"))

        if not re.fullmatch(
            r"\+?[0-9 ()-]{7,20}",
            phone
        ):
            flash("Enter a valid phone number.")
            return redirect(url_for("signup"))

        if len(password) < 8:
            flash(
                "Your password must contain "
                "at least 8 characters."
            )
            return redirect(url_for("signup"))

        db = get_db()

        try:
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
                    "We couldn't create your account."
                )

            return redirect(url_for("signup"))

        finally:
            db.close()

    return render_template("signup.html")


# =========================
# LOGIN
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
            flash("Enter your email/phone and password.")
            return redirect(url_for("login"))

        db = get_db()

        try:
            user = db.execute(
                """
                SELECT *
                FROM users
                WHERE email = ? COLLATE NOCASE
                   OR phone = ?
                """,
                (identity.lower(), identity)
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

        flash("Incorrect email/phone or password.")

    return render_template("login.html")


# =========================
# CHAT
# =========================

@app.route("/chat")
def chat():

    if "user_id" not in session:
        return redirect(url_for("login"))

    current_user_id = session["user_id"]

    recipient_username = request.args.get(
        "with", ""
    ).strip()

    db = get_db()

    try:

        users = db.execute(
            """
            SELECT id, username
            FROM users
            WHERE id != ?
            ORDER BY username
            """,
            (current_user_id,)
        ).fetchall()

        recipient = None
        messages = []

        if recipient_username:

            recipient = db.execute(
                """
                SELECT id, username
                FROM users
                WHERE username = ? COLLATE NOCASE
                  AND id != ?
                """,
                (
                    recipient_username,
                    current_user_id
                )
            ).fetchone()

            if recipient:

                messages = db.execute(
                    """
                    SELECT
                        messages.id,
                        messages.sender_id,
                        messages.receiver_id,
                        messages.message,
                        messages.created_at,
                        sender.username AS sender_username
                    FROM messages
                    JOIN users AS sender
                      ON sender.id = messages.sender_id
                    WHERE
                        (
                            messages.sender_id = ?
                            AND messages.receiver_id = ?
                        )
                        OR
                        (
                            messages.sender_id = ?
                            AND messages.receiver_id = ?
                        )
                    ORDER BY
                        messages.created_at,
                        messages.id
                    """,
                    (
                        current_user_id,
                        recipient["id"],
                        recipient["id"],
                        current_user_id
                    )
                ).fetchall()

    finally:
        db.close()

    return render_template(
        "chat.html",
        username=session["username"],
        users=users,
        recipient=recipient,
        messages=messages
    )


# =========================
# SEND MESSAGE
# =========================

@app.route("/send-message", methods=["POST"])
def send_message():

    if "user_id" not in session:
        return redirect(url_for("login"))

    recipient_username = request.form.get(
        "recipient", ""
    ).strip()

    message = request.form.get(
        "message", ""
    ).strip()

    if not recipient_username or not message:
        flash("Enter a recipient and a message.")
        return redirect(url_for("chat"))

    if len(message) > 2000:
        flash("Message is too long.")
        return redirect(
            url_for(
                "chat",
                **{"with": recipient_username}
            )
        )

    db = get_db()

    try:

        recipient = db.execute(
            """
            SELECT id
            FROM users
            WHERE username = ? COLLATE NOCASE
              AND id != ?
            """,
            (
                recipient_username,
                session["user_id"]
            )
        ).fetchone()

        if not recipient:

            flash("User not found.")

            return redirect(url_for("chat"))

        db.execute(
            """
            INSERT INTO messages
            (sender_id, receiver_id, message)
            VALUES (?, ?, ?)
            """,
            (
                session["user_id"],
                recipient["id"],
                message
            )
        )

        db.commit()

    except Exception:

        db.rollback()
        app.logger.exception("Message sending failed")

        flash("Could not send message.")

    finally:
        db.close()

    return redirect(
        url_for(
            "chat",
            **{"with": recipient_username}
        )
    )


# =========================
# SHORT VIDEOS / REELS
# =========================

@app.route("/shorts")
def shorts():

    if "user_id" not in session:
        return redirect(url_for("login"))

    db = get_db()

    try:

        videos = db.execute(
            """
            SELECT
                videos.id,
                videos.user_id,
                videos.filename,
                videos.caption,
                videos.created_at,
                users.username
            FROM videos
            JOIN users
              ON users.id = videos.user_id
            ORDER BY
                videos.created_at DESC,
                videos.id DESC
            """
        ).fetchall()

    finally:
        db.close()

    return render_template(
        "shorts.html",
        username=session["username"],
        videos=videos
    )


# =========================
# UPLOAD VIDEO
# =========================

@app.route("/upload-video", methods=["POST"])
def upload_video():

    if "user_id" not in session:
        return redirect(url_for("login"))

    video = request.files.get("video")

    caption = request.form.get(
        "caption", ""
    ).strip()

    if not video or not video.filename:

        flash("Please select a video to upload.")

        return redirect(url_for("shorts"))

    if len(caption) > 300:

        flash("Caption must not exceed 300 characters.")

        return redirect(url_for("shorts"))

    original_filename = secure_filename(
        video.filename
    )

    extension = os.path.splitext(
        original_filename
    )[1].lower().lstrip(".")

    if extension not in ALLOWED_VIDEO_EXTENSIONS:

        flash(
            "Only MP4, WEBM and MOV videos are allowed."
        )

        return redirect(url_for("shorts"))

    filename = (
        str(session["user_id"])
        + "_"
        + secrets.token_hex(16)
        + "."
        + extension
    )

    filepath = os.path.join(
        VIDEO_FOLDER,
        filename
    )

    db = get_db()

    try:

        video.save(filepath)

        db.execute(
            """
            INSERT INTO videos
            (user_id, filename, caption)
            VALUES (?, ?, ?)
            """,
            (
                session["user_id"],
                filename,
                caption
            )
        )

        db.commit()

        flash("Your video was uploaded successfully!")

    except Exception:

        db.rollback()

        if os.path.exists(filepath):
            os.remove(filepath)

        app.logger.exception(
            "Video upload failed"
        )

        flash("Could not upload your video.")

    finally:
        db.close()

    return redirect(url_for("shorts"))


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
