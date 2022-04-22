import os
import datetime

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    if request.method == "GET":
        # Select ALL rows with user_id
        index_rows = db.execute("SELECT user_id, company, symbol, SUM(shares) AS shares, price, date FROM transactions WHERE user_id=? GROUP BY symbol", session["user_id"])
        cash_total = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])
        grand_total = cash_total[0]["cash"]
        for row in index_rows:
            row["total"] = row["price"] * row["shares"]
            row["usd_total"] = usd(row["price"] * row["shares"])
            row["usd_price"] = usd(row["price" * 1])
            grand_total += row["total"]
        return render_template("index.html", index_rows=index_rows, cash_total=usd(cash_total[0]["cash"]), grand_total=usd(grand_total))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    balance = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])
    if request.method == "GET":
        return render_template("buy.html")
    else:
        if not request.form.get("symbol"):
            return apology("Enter symbol!")
        elif not lookup(request.form.get("symbol")):
            return apology("Invalid symbol!")
        elif request.form.get("shares") == '' or int(request.form.get("shares")) <= 0:
            return apology("Invalid number!")
        elif balance[0]["cash"] - int(request.form.get("shares")) * int(lookup(request.form.get("symbol"))["price"]) < 0:
            return apology("Not enough money!")
        # Insert data into database
        entry = db.execute("SELECT * FROM transactions WHERE symbol=?", request.form.get("symbol"))
        db.execute("INSERT INTO transactions(user_id, company, symbol, shares, price, date) VALUES(?,?,?,?,?,?);",
        session["user_id"], lookup(request.form.get("symbol"))["name"], request.form.get("symbol"),
        request.form.get("shares"), lookup(request.form.get("symbol"))["price"],
        datetime.datetime.now().replace(microsecond=0))
        # Update cash balance
        db.execute("UPDATE users SET cash = ? WHERE id=?", balance[0]["cash"] - int(request.form.get("shares"))
        * int(lookup(request.form.get("symbol"))["price"]), session["user_id"])

        return redirect("/")

@app.route("/history")
@login_required
def history():
    if request.method == "GET":
        # Select ALL rows with user_id
        history_rows = db.execute("SELECT * FROM transactions WHERE user_id=?", session["user_id"])
        for row in history_rows:
            row["usd_price"] = usd(row["price" * 1])
        return render_template("history.html", history_rows=history_rows)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "GET":
        return render_template("quote.html")
    else:
        return render_template("quoted.html", lookup=lookup(request.form.get("symbol")), price=usd(lookup(request.form.get("symbol"))["price"]))
    return apology("TODO")


@app.route("/register", methods=["GET", "POST"])
def register():
    # Get register page
    if request.method == "GET":
        return render_template("register.html")
    # Register new account (POST)
    else:
        # Get inputs
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Check username
        is_there = db.execute("SELECT * FROM users WHERE username = :username;", username=username)

        if not username:
            return apology("Enter username!")
        elif len(is_there) == 1:
            return apology("Username already exists!")

        # Check passwords
        if not password or not confirmation:
            return apology("Fill in passwords!")

        elif password != confirmation:
            return apology("Passwords don't match!")

        # Successful
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?);", username, generate_password_hash(password))
        return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    balance = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])
    if request.method == "GET":
        return render_template("sell.html")
    if request.method == "POST":
        option = request.form.get("symbol")
        shares = db.execute("SELECT * FROM transactions WHERE user_id=? AND symbol=?", session["user_id"], option)
        share_count = 0
        for share in shares:
            share_count += share["shares"]
        if option == "Symbol":
            return apology("Select stock!")
        elif len(shares) == 0:
            return apology("No shares!")
        elif int(request.form.get("shares")) <= 0:
            return apology("Invalid number!")
        elif share_count < int(request.form.get("shares")):
            return apology("Not enough shares!")
        # Insert data into database
        entry = db.execute("SELECT * FROM transactions WHERE symbol=?", request.form.get("symbol"))
        db.execute("INSERT INTO transactions(user_id, company, symbol, shares, price, date) VALUES(?,?,?,?,?,?);",
                    session["user_id"], lookup(request.form.get("symbol"))["name"], request.form.get("symbol"),
                    int(request.form.get("shares")) * -1, lookup(request.form.get("symbol"))["price"],
                    datetime.datetime.now().replace(microsecond=0))
        # Update cash balance
        db.execute("UPDATE users SET cash = ? WHERE id=?", balance[0]["cash"] + int(request.form.get("shares"))
        * int(lookup(request.form.get("symbol"))["price"]), session["user_id"])

        return redirect("/")

@app.route("/cash", methods=["GET", "POST"])
@login_required
def cash():
    if request.method == "GET":
        return render_template("cash.html")
    else:
        if not request.form.get("cash"):
            return apology("Enter number!")
        # Change cash in database
        cash = request.form.get("cash")
        db.execute("UPDATE users SET cash = cash + ? WHERE id=?", cash, session["user_id"])
        return redirect("/")

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
