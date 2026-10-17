from flask import Flask, render_template_string

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>ChatUp</title>
    <style>
        body {
            margin: 0;
            font-family: Arial, sans-serif;
            background: #eef3ff;
        }
        header {
            background: #1769ff;
            color: white;
            padding: 22px;
            text-align: center;
            font-size: 28px;
            font-weight: bold;
        }
        .container {
            max-width: 500px;
            margin: 30px auto;
            padding: 20px;
        }
        .card {
            background: white;
            padding: 25px;
            border-radius: 16px;
            box-shadow: 0 4px 15px #0001;
        }
        h2 { color: #1769ff; }
        input {
            width: 100%;
            padding: 13px 0;
            margin: 8px 0;
            border: 1px solid #ddd;
            border-radius: 8px;
            font-size: 16px;
            text-indent: 10px;
        }
        button {
            width: 100%;
            padding: 14px;
            background: #1769ff;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 17px;
        }
        #message {
            color: #1769ff;
            margin-top: 15px;
        }
    </style>
</head>
<body>
    <header>💬 ChatUp</header>
    <div class="container">
        <div class="card">
            <h2>Welcome to ChatUp!</h2>
            <p>Connect with friends and start chatting.</p>
            <form onsubmit="welcome(event)">
                <input id="username" placeholder="Enter your username" required>
                <button type="submit">Get Started</button>
            </form>
            <p id="message"></p>
        </div>
    </div>
    <script>
        function welcome(event) {
            event.preventDefault();
            const name = document.getElementById('username').value.trim();
            document.getElementById('message').textContent =
                'Welcome to ChatUp, ' + name + '! 🎉';
        }
    </script>
</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(HTML)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
