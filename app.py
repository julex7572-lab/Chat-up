
import os
import re
import secrets

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, send_from_directory
)

from werkzeug.security import (
    generate_password_hash, check_password_hash
)
from werkzeug.utils import secure_filename

from database import get_db, create_tables


app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "development-key-change-before-deployment"
)

app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

UPLOAD_ROOT = os.path.join(
    app.root_path, "static", "uploads"
)

VIDEO_FOLDER = os.path.join(UPLOAD_ROOT, "videos")
IMAGE_FOLDER = os.path.join(UPLOAD_ROOT, "images")
VOICE_FOLDER = os.path.join(UPLOAD_ROOT, "voices")

for folder in (VIDEO_FOLDER, IMAGE_FOLDER, VOICE_FOLDER):
    os.makedirs(folder, exist_ok=True)

ALLOWED_VIDEO = {"mp4", "webm", "mov"}
ALLOWED_IMAGE = {"jpg", "jpeg", "png", "webp", "gif"}
ALLOWED_AUDIO = {"webm", "ogg", "mp3", "wav", "m4a", "mp4"}

create_tables()


# =========================
# HELPER FUNCTIONS
# =========================

def logged_in():
    return "user_id" in session


def save_upload(file, folder, allowed_extensions):
    if not file or not file.filename:
        return None

    original = secure_filename(file.filename)
    extension = os.path.splitext(original)[1].lower().lstrip(".")

    if extension not in allowed_extensions:
        return None

    filename = (
        str(session["user_id"])
        + "_"
        + secrets.token_hex(16)
        + "."
        + extension
    )

    file.save(os.path.join(folder, filename))
    return filename


def get_private_recipient(username):
    db = get_db()

    try:
        return db.execute(
            """
            SELECT id, username FROM users
            WHERE username = ? COLLATE NOCASE AND id != ?
            """,
            (username, session["user_id"])
        ).fetchone()

    finally:
        db.close()


# =========================
# HOME PAGE
# =========================

@app.route("/")
def home():
    chats = []

    if logged_in():
        current_id = session["user_id"]

        db = get_db()

        try:
            chats = db.execute(
                """
                SELECT
                    u.id,
                    u.username,

                    (
                        SELECT m.message
                        FROM messages m
                        WHERE
                            (m.sender_id = u.id AND m.receiver_id = ?)
                            OR
                            (m.sender_id = ? AND m.receiver_id = u.id)
                        ORDER BY m.id DESC
                        LIMIT 1
                    ) AS last_message,

                    (
                        SELECT m.created_at
                        FROM messages m
                        WHERE
                            (m.sender_id = u.id AND m.receiver_id = ?)
                            OR
                            (m.sender_id = ? AND m.receiver_id = u.id)
                        ORDER BY m.id DESC
                        LIMIT 1
                    ) AS last_time

                FROM users u

                WHERE u.id != ?

                ORDER BY
                    (
                        SELECT MAX(m.id)
                        FROM messages m
                        WHERE
                            (m.sender_id = u.id AND m.receiver_id = ?)
                            OR
                            (m.sender_id = ? AND m.receiver_id = u.id)
                    ) DESC,

                    u.username ASC
                """,
                (
                    current_id,
                    current_id,
                    current_id,
                    current_id,
                    current_id,
                    current_id,
                    current_id
                )
            ).fetchall()

        finally:
            db.close()

    return render_template(
        "index.html",
        chats=chats,
        logged_in=logged_in(),
        username=session.get("username")
    )


# =========================
# SIGNUP
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
            r"[A-Za-z0-9_]{3,30}", username
        ):
            flash("Username must be 3–30 characters.")
            return redirect(url_for("signup"))

        if not re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+", email
        ):
            flash("Enter a valid email address.")
            return redirect(url_for("signup"))

        if not re.fullmatch(
            r"\+?[0-9 ()-]{7,20}", phone
        ):
            flash("Enter a valid phone number.")
            return redirect(url_for("signup"))

        if len(password) < 8:
            flash("Password must contain at least 8 characters.")
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

            flash("Account created! Please log in.")
            return redirect(url_for("login"))

        except Exception as error:

            db.rollback()

            if "UNIQUE constraint failed" in str(error):
                flash(
                    "Username, email or phone already registered."
                )
            else:
                app.logger.exception("Signup failed")
                flash("Could not create account.")

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

        db = get_db()

        try:
            user = db.execute(
                """
                SELECT * FROM users
                WHERE email = ? COLLATE NOCASE OR phone = ?
                """,
                (identity.lower(), identity)
            ).fetchone()

        finally:
            db.close()

        if user and check_password_hash(
            user["password"], password
        ):

            session.clear()

            session["user_id"] = user["id"]
            session["username"] = user["username"]

            return redirect(url_for("home"))

        flash("Incorrect email/phone or password.")

    return render_template("login.html")


# =========================
# PRIVATE CHAT
# =========================

@app.route("/chat")
def chat():

    if not logged_in():
        return redirect(url_for("login"))

    current_id = session["user_id"]

    recipient_username = request.args.get(
        "with", ""
    ).strip()

    db = get_db()

    try:

        users = db.execute(
            """
            SELECT id, username FROM users
            WHERE id != ?
            ORDER BY username
            """,
            (current_id,)
        ).fetchall()

        recipient = None
        messages = []

        if recipient_username:

            recipient = db.execute(
                """
                SELECT id, username FROM users
                WHERE username = ? COLLATE NOCASE
                AND id != ?
                """,
                (recipient_username, current_id)
            ).fetchone()

            if recipient:

                messages = db.execute(
                    """
                    SELECT
                        m.*,
                        u.username AS sender_username,
                        a.filename AS attachment_filename,
                        a.media_type AS attachment_type

                    FROM messages m

                    JOIN users u
                    ON u.id = m.sender_id

                    LEFT JOIN message_attachments a
                    ON a.message_id = m.id

                    WHERE
                        (m.sender_id = ? AND m.receiver_id = ?)
                        OR
                        (m.sender_id = ? AND m.receiver_id = ?)

                    ORDER BY m.created_at, m.id
                    """,
                    (
                        current_id,
                        recipient["id"],
                        recipient["id"],
                        current_id
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
# SEND TEXT MESSAGE
# =========================

@app.route("/send-message", methods=["POST"])
def send_message():

    if not logged_in():
        return redirect(url_for("login"))

    recipient_username = request.form.get(
        "recipient", ""
    ).strip()

    message = request.form.get(
        "message", ""
    ).strip()

    if not message or len(message) > 2000:

        flash("Enter a message of up to 2000 characters.")

        return redirect(
            url_for("chat", **{"with": recipient_username})
        )

    recipient = get_private_recipient(recipient_username)

    if not recipient:
        flash("User not found.")
        return redirect(url_for("home"))

    db = get_db()

    try:

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
        url_for("chat", **{"with": recipient_username})
    )


# =========================
# SEND PICTURE OR VOICE NOTE
# =========================

@app.route("/send-media", methods=["POST"])
def send_media():

    if not logged_in():
        return redirect(url_for("login"))

    recipient_username = request.form.get(
        "recipient", ""
    ).strip()

    message = request.form.get(
        "message", ""
    ).strip()

    recipient = get_private_recipient(recipient_username)

    if not recipient:
        flash("User not found.")
        return redirect(url_for("home"))

    image_file = request.files.get("picture")
    audio_file = request.files.get("voice")

    has_image = bool(image_file and image_file.filename)
    has_audio = bool(audio_file and audio_file.filename)

    if has_image == has_audio:
        flash("Choose one picture or one voice note.")
        return redirect(
            url_for("chat", **{"with": recipient_username})
        )

    if has_image:
        folder = IMAGE_FOLDER
        allowed = ALLOWED_IMAGE
        media_type = "image"
        upload = image_file
    else:
        folder = VOICE_FOLDER
        allowed = ALLOWED_AUDIO
        media_type = "audio"
        upload = audio_file

    filename = save_upload(upload, folder, allowed)

    if not filename:
        flash("Unsupported file type.")
        return redirect(
            url_for("chat", **{"with": recipient_username})
        )

    db = get_db()

    try:

        cursor = db.execute(
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

        db.execute(
            """
            INSERT INTO message_attachments
            (message_id, filename, media_type)
            VALUES (?, ?, ?)
            """,
            (
                cursor.lastrowid,
                filename,
                media_type
            )
        )

        db.commit()

        flash("Attachment sent!")

    except Exception:

        db.rollback()

        path = os.path.join(folder, filename)

        if os.path.exists(path):
            os.remove(path)

        app.logger.exception("Attachment sending failed")
        flash("Could not send attachment.")

    finally:
        db.close()

    return redirect(
        url_for("chat", **{"with": recipient_username})
    )


# =========================
# VIEW UPLOADS
# =========================

@app.route("/uploads/<media_type>/<filename>")
def view_upload(media_type, filename):

    if not logged_in():
        return redirect(url_for("login"))

    folders = {
        "images": (IMAGE_FOLDER, "image"),
        "voices": (VOICE_FOLDER, "audio")
    }

    if media_type not in folders:
        return "Not found", 404

    folder, expected_type = folders[media_type]

    db = get_db()

    try:

        attachment = db.execute(
            """
            SELECT a.id
            FROM message_attachments a

            JOIN messages m
            ON m.id = a.message_id

            WHERE a.filename = ?
            AND a.media_type = ?
            AND (
                m.sender_id = ? OR m.receiver_id = ?
            )
            """,
            (
                filename,
                expected_type,
                session["user_id"],
                session["user_id"]
            )
        ).fetchone()

    finally:
        db.close()

    if not attachment:
        return "Not found", 404

    return send_from_directory(folder, filename)


# =========================
# SHORTS
# =========================

@app.route("/shorts")
def shorts():

    if not logged_in():
        return redirect(url_for("login"))

    db = get_db()

    try:

        videos = db.execute(
            """
            SELECT videos.*, users.username
            FROM videos
            JOIN users ON users.id = videos.user_id
            ORDER BY videos.created_at DESC, videos.id DESC
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

    if not logged_in():
        return redirect(url_for("login"))

    video = request.files.get("video")

    caption = request.form.get(
        "caption", ""
    ).strip()

    if len(caption) > 300:
        flash("Caption is too long.")
        return redirect(url_for("shorts"))

    filename = save_upload(
        video,
        VIDEO_FOLDER,
        ALLOWED_VIDEO
    )

    if not filename:
        flash("Choose a valid MP4, WEBM or MOV video.")
        return redirect(url_for("shorts"))

    db = get_db()

    try:

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

        flash("Video uploaded!")

    except Exception:

        db.rollback()

        path = os.path.join(VIDEO_FOLDER, filename)

        if os.path.exists(path):
            os.remove(path)

        app.logger.exception("Video upload failed")
        flash("Could not upload video.")

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
# FILE SIZE ERROR
# =========================

@app.errorhandler(413)
def too_large(error):

    flash("File is too large. Maximum upload size is 50 MB.")

    if logged_in():
        return redirect(url_for("home"))

    return redirect(url_for("login"))


# =========================
# RUN APP
# =========================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
