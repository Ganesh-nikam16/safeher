import os, math, time, sqlite3, secrets, requests
from xml.sax.saxutils import escape
from functools import wraps
import numpy as np
from flask import Flask, request, jsonify, render_template, g, session, redirect, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from sklearn.cluster import DBSCAN

DB = "safeher.db"
CENTER = (17.68, 74.00)          # default map centre (change to your city)
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-me-in-production")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

# ---------- database ----------
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB); g.db.row_factory = sqlite3.Row
    return g.db

def q(sql, a=(), one=False):
    cur = db().execute(sql, a); rows = cur.fetchall(); db().commit()
    return (rows[0] if rows else None) if one else rows

@app.teardown_appcontext
def close(_):
    d = g.pop("db", None)
    if d: d.close()

def init():
    c = sqlite3.connect(DB)
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, phone TEXT UNIQUE, pw TEXT, lat REAL, lon REAL, seen REAL);
    CREATE TABLE IF NOT EXISTS contacts(id INTEGER PRIMARY KEY, user_id INT, name TEXT, phone TEXT);
    CREATE TABLE IF NOT EXISTS friends(id INTEGER PRIMARY KEY, a INT, b INT, status TEXT);
    CREATE TABLE IF NOT EXISTS tracks(token TEXT PRIMARY KEY, user_id INT, active INT);
    CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY, user_id INT, lat REAL, lon REAL, source TEXT, ts REAL);
    CREATE TABLE IF NOT EXISTS camera_sessions(token TEXT PRIMARY KEY, user_id INT, active INT, image BLOB, mime TEXT, ts REAL);
    CREATE TABLE IF NOT EXISTS incidents(id INTEGER PRIMARY KEY, lat REAL, lon REAL, kind TEXT);""")
    if c.execute("SELECT COUNT(*) FROM incidents").fetchone()[0] == 0:   # demo data -> replace with real crime CSV
        rng = np.random.default_rng(1)
        for la, lo in [(17.680, 74.000), (17.690, 74.010), (17.672, 73.990)]:
            for _ in range(25):
                c.execute("INSERT INTO incidents(lat,lon,kind) VALUES(?,?,'seed')",
                          (la + rng.normal(0, .0015), lo + rng.normal(0, .0015)))
    c.commit(); c.close()

# ---------- helpers ----------
def norm(p): return "".join(ch for ch in p if ch.isdigit())[-10:]

def dist(a, b, c, d):   # metres
    p = math.pi / 180
    x = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2
    return 12742000 * math.asin(math.sqrt(x))

def auth(f):
    @wraps(f)
    def w(*a, **k):
        if "uid" not in session: return jsonify(error="login required"), 401
        return f(*a, **k)
    return w

def me(): return q("SELECT * FROM users WHERE id=?", (session["uid"],), one=True)

def send_sms(to, body):
    sid, tok, frm = (os.getenv(k) for k in ("TWILIO_SID", "TWILIO_TOKEN", "TWILIO_FROM"))
    if not (sid and tok and frm):
        print("[SMS dev-mode]", to, "|", body); return "dev-mode"
    try:
        from twilio.rest import Client
        Client(sid, tok).messages.create(to=to, from_=frm, body=body); return "sent"
    except Exception as e:
        return "failed"

def send_call(to, text):
    """Real phone call: Twilio reads the emergency message aloud (twice)."""
    sid, tok, frm = (os.getenv(k) for k in ("TWILIO_SID", "TWILIO_TOKEN", "TWILIO_FROM"))
    if not (sid and tok and frm):
        print("[CALL dev-mode]", to, "|", text); return "dev-mode"
    try:
        from twilio.rest import Client
        twiml = f'<Response><Say voice="alice" language="en-IN" loop="2">{escape(text)}</Say></Response>'
        Client(sid, tok).calls.create(to=to, from_=frm, twiml=twiml); return "calling"
    except Exception as e:
        print("[CALL failed]", e); return "failed"

def notify(u, msg, call_text=None, include_friends=True):
    # Emergency contacts + accepted SafeHer friends are notified server-side.
    # This means the recipient does not need to have SafeHer open.
    out, seen = [], set()
    recipients = [(c["name"], c["phone"]) for c in q(
        "SELECT name,phone FROM contacts WHERE user_id=?", (u["id"],))]
    if include_friends:
        rows = q("""SELECT x.name,x.phone FROM friends f
                   JOIN users x ON x.id=(CASE WHEN f.a=? THEN f.b ELSE f.a END)
                   WHERE (f.a=? OR f.b=?) AND f.status='ok'""", (u["id"], u["id"], u["id"]))
        recipients += [(r["name"], r["phone"]) for r in rows]
    for name, phone in recipients:
        key = norm(phone)
        if key in seen: continue
        seen.add(key)
        r = {"name": name, "status": send_sms(phone, msg)}
        if call_text: r["call"] = send_call(phone, call_text)
        out.append(r)
    return out

def track_token(uid):
    t = q("SELECT token FROM tracks WHERE user_id=? AND active=1", (uid,), one=True)
    if t: return t["token"]
    tok = secrets.token_urlsafe(9)
    q("INSERT INTO tracks(token,user_id,active) VALUES(?,?,1)", (tok, uid)); return tok

# ---------- PWA (installable app) ----------
@app.route("/manifest.json")
def manifest(): return send_from_directory("static", "manifest.json", mimetype="application/manifest+json")

@app.route("/sw.js")
def sw():
    r = send_from_directory("static", "sw.js", mimetype="application/javascript")
    r.headers["Service-Worker-Allowed"] = "/"; r.headers["Cache-Control"] = "no-cache"; return r

# ---------- pages ----------
@app.route("/")
def home():
    if "uid" not in session: return redirect("/login")
    return render_template("index.html", lat=CENTER[0], lon=CENTER[1])

@app.route("/login")
def login_page(): return render_template("auth.html")

@app.route("/track/<tok>")
def track_page(tok): return render_template("track.html", tok=tok, lat=CENTER[0], lon=CENTER[1])

# ---------- 1. registration / login ----------
@app.post("/api/register")
def register():
    d = request.json; name = d.get("name", "").strip(); ph = norm(d.get("phone", "")); pw = d.get("password", "")
    if not name or len(ph) < 10 or len(pw) < 6:
        return jsonify(error="Enter name, 10-digit phone and a password of 6+ characters"), 400
    if q("SELECT 1 FROM users WHERE phone=?", (ph,), one=True):
        return jsonify(error="Phone already registered"), 409
    q("INSERT INTO users(name,phone,pw) VALUES(?,?,?)", (name, ph, generate_password_hash(pw)))
    session["uid"] = q("SELECT id FROM users WHERE phone=?", (ph,), one=True)["id"]
    return jsonify(ok=True)

@app.post("/api/login")
def login():
    d = request.json; u = q("SELECT * FROM users WHERE phone=?", (norm(d.get("phone", "")),), one=True)
    if not u or not check_password_hash(u["pw"], d.get("password", "")):
        return jsonify(error="Wrong phone or password"), 401
    session["uid"] = u["id"]; return jsonify(ok=True)

@app.post("/api/logout")
def logout(): session.clear(); return jsonify(ok=True)

@app.get("/api/me")
@auth
def api_me():
    u = me(); t = q("SELECT token FROM tracks WHERE user_id=? AND active=1", (u["id"],), one=True)
    return jsonify(name=u["name"], phone=u["phone"], track=(request.host_url + "track/" + t["token"]) if t else None)

@app.post("/api/location")
@auth
def set_loc():
    d = request.json
    q("UPDATE users SET lat=?,lon=?,seen=? WHERE id=?", (d["lat"], d["lon"], time.time(), session["uid"]))
    return jsonify(ok=True)

# ---------- 2. emergency contacts ----------
@app.route("/api/contacts", methods=["GET", "POST", "DELETE"])
@auth
def contacts():
    uid = session["uid"]
    if request.method == "POST":
        d = request.json
        if d.get("name", "").strip() and len(d.get("phone", "")) >= 10:
            q("INSERT INTO contacts(user_id,name,phone) VALUES(?,?,?)", (uid, d["name"].strip(), d["phone"].strip()))
    if request.method == "DELETE":
        q("DELETE FROM contacts WHERE id=? AND user_id=?", (request.args["id"], uid))
    return jsonify([dict(r) for r in q("SELECT id,name,phone FROM contacts WHERE user_id=?", (uid,))])

# ---------- 6. friends, live map, nearby detector ----------
@app.route("/api/friends", methods=["GET", "POST", "DELETE"])
@auth
def friends():
    u = me(); uid = u["id"]
    if request.method == "POST":
        t = q("SELECT id FROM users WHERE phone=?", (norm(request.json.get("phone", "")),), one=True)
        if not t: return jsonify(error="That number is not registered on SafeHer"), 404
        if t["id"] == uid: return jsonify(error="That is your own number"), 400
        if q("SELECT 1 FROM friends WHERE (a=? AND b=?) OR (a=? AND b=?)", (uid, t["id"], t["id"], uid), one=True):
            return jsonify(error="Already connected or request pending"), 409
        q("INSERT INTO friends(a,b,status) VALUES(?,?,'pending')", (uid, t["id"]))
    if request.method == "DELETE":
        q("DELETE FROM friends WHERE id=? AND (a=? OR b=?)", (request.args["fid"], uid, uid))
    rows = q("""SELECT f.id fid,f.status,f.a,x.id uid,x.name,x.lat,x.lon,x.seen FROM friends f
                JOIN users x ON x.id=(CASE WHEN f.a=? THEN f.b ELSE f.a END) WHERE f.a=? OR f.b=?""", (uid, uid, uid))
    out = []
    for r in rows:
        it = {"fid": r["fid"], "name": r["name"], "status": r["status"], "incoming": r["status"] == "pending" and r["a"] != uid}
        if r["status"] == "ok":
            it["online"] = bool(r["seen"] and time.time() - r["seen"] < 600)
            if it["online"]:
                it["lat"], it["lon"] = r["lat"], r["lon"]
                if u["lat"] is not None:
                    it["dist"] = round(dist(u["lat"], u["lon"], r["lat"], r["lon"]))
                    it["nearby"] = it["dist"] <= 1000
            it["sos"] = bool(q("SELECT 1 FROM alerts WHERE user_id=? AND ts>?", (r["uid"], time.time() - 900), one=True))
        out.append(it)
    return jsonify(out)

@app.post("/api/friends/accept")
@auth
def accept():
    q("UPDATE friends SET status='ok' WHERE id=? AND b=?", (request.json["fid"], session["uid"])); return jsonify(ok=True)

# ---------- 7A. camera sharing ----------
def camera_token(uid):
    row = q("SELECT token FROM camera_sessions WHERE user_id=? AND active=1", (uid,), one=True)
    if row: return row["token"]
    tok = secrets.token_urlsafe(12)
    q("INSERT INTO camera_sessions(token,user_id,active,image,mime,ts) VALUES(?,?,1,NULL,NULL,0)",
      (tok, uid))
    return tok

@app.post("/api/camera/start")
@auth
def camera_start():
    u = me()
    tok = camera_token(u["id"])
    link = request.host_url + "camera/" + tok
    sent = notify(u, f"{u['name']} started emergency camera sharing. View: {link}", None)
    return jsonify(ok=True, link=link, sent=sent)

@app.post("/api/camera/frame")
@auth
def camera_frame():
    d = request.json or {}
    raw = d.get("image", "")
    if not raw.startswith("data:image/"):
        return jsonify(error="Invalid camera frame"), 400
    try:
        head, b64 = raw.split(",", 1)
        import base64
        data = base64.b64decode(b64, validate=True)
        if len(data) > 2_000_000:
            return jsonify(error="Frame too large"), 413
        mime = head.split(";", 1)[0].split(":", 1)[1]
        q("UPDATE camera_sessions SET image=?,mime=?,ts=? WHERE user_id=? AND active=1",
          (data, mime, time.time(), session["uid"]))
        return jsonify(ok=True)
    except Exception:
        return jsonify(error="Could not save frame"), 400

@app.post("/api/camera/stop")
@auth
def camera_stop():
    q("UPDATE camera_sessions SET active=0 WHERE user_id=?", (session["uid"],))
    return jsonify(ok=True)

@app.get("/camera/<tok>")
def camera_page(tok):
    t = q("SELECT token FROM camera_sessions WHERE token=?", (tok,), one=True)
    if not t: return "Camera share not found", 404
    return render_template("camera.html", tok=tok)

@app.get("/api/camera/<tok>")
def camera_data(tok):
    row = q("""SELECT c.active,c.image,c.mime,c.ts,u.name
               FROM camera_sessions c JOIN users u ON u.id=c.user_id
               WHERE c.token=?""", (tok,), one=True)
    if not row: return jsonify(active=False), 404
    if not row["active"]: return jsonify(active=False, name=row["name"])
    if row["image"] is None:
        return jsonify(active=True, name=row["name"], image=None)
    import base64
    return jsonify(active=True, name=row["name"],
                   image="data:%s;base64,%s" % (row["mime"], base64.b64encode(row["image"]).decode()),
                   age=int(time.time()-row["ts"]))

# ---------- 7. live tracking + SOS ----------
@app.post("/api/track/start")
@auth
def track_start():
    u = me(); link = request.host_url + "track/" + track_token(u["id"])
    sent = notify(u, f"{u['name']} is sharing her live location with you: {link}")
    return jsonify(link=link, sent=sent)

@app.post("/api/track/stop")
@auth
def track_stop():
    q("UPDATE tracks SET active=0 WHERE user_id=?", (session["uid"],)); return jsonify(ok=True)

@app.get("/api/track/<tok>")
def track_data(tok):
    t = q("SELECT * FROM tracks WHERE token=?", (tok,), one=True)
    if not t or not t["active"]: return jsonify(active=False)
    u = q("SELECT name,lat,lon,seen FROM users WHERE id=?", (t["user_id"],), one=True)
    return jsonify(active=True, name=u["name"], lat=u["lat"], lon=u["lon"], age=int(time.time() - (u["seen"] or 0)))

@app.post("/api/sos")
@auth
def sos():
    u = me(); d = request.json; la, lo = d["lat"], d["lon"]
    q("UPDATE users SET lat=?,lon=?,seen=? WHERE id=?", (la, lo, time.time(), u["id"]))
    q("INSERT INTO alerts(user_id,lat,lon,source,ts) VALUES(?,?,?,?,?)", (u["id"], la, lo, d.get("source", "button"), time.time()))
    link = request.host_url + "track/" + track_token(u["id"])
    cam = q("SELECT token FROM camera_sessions WHERE user_id=? AND active=1", (u["id"],), one=True)
    camlink = (request.host_url + "camera/" + cam["token"]) if cam else None
    msg = (f"EMERGENCY! {u['name']} needs help. Location: https://maps.google.com/?q={la},{lo} "
           f"Live tracking: {link}" + (f" Camera: {camlink}" if camlink else ""))
    call = f"Emergency alert. {u['name']} needs help right now. Please check your messages for her live location."
    return jsonify(sent=notify(u, msg, call), link=link)

# ---------- 5. safe route detector ----------
def hotspots():
    rows = q("SELECT lat,lon FROM incidents")
    if len(rows) < 5: return []
    X = np.array([[r["lat"], r["lon"]] for r in rows])
    lab = DBSCAN(eps=200 / 6371000, min_samples=5, metric="haversine", algorithm="ball_tree").fit_predict(np.radians(X))
    out = []
    for k in set(lab) - {-1}:
        p = X[lab == k]; la, lo = p[:, 0].mean(), p[:, 1].mean()
        rad = max(dist(la, lo, a, b) for a, b in p)
        out.append({"lat": float(la), "lon": float(lo), "n": int(len(p)), "radius": max(150.0, float(rad))})
    return out

def risk(la, lo, hs):
    return sum(h["n"] * math.exp(-(dist(la, lo, h["lat"], h["lon"]) / h["radius"]) ** 2) for h in hs)

@app.get("/api/hotspots")
@auth
def api_hot(): return jsonify(hotspots())

@app.post("/api/report")
@auth
def report():
    d = request.json; q("INSERT INTO incidents(lat,lon,kind) VALUES(?,?,'user')", (d["lat"], d["lon"])); return jsonify(ok=True)

@app.get("/api/route")
@auth
def route():
    a = request.args; hs = hotspots()
    url = (f"https://router.project-osrm.org/route/v1/driving/{a['slon']},{a['slat']};{a['elon']},{a['elat']}"
           "?alternatives=3&overview=full&geometries=geojson")
    try: routes = requests.get(url, timeout=15).json().get("routes", [])
    except Exception: routes = []
    out = []
    for r in routes:
        pts = r["geometry"]["coordinates"]; step = r["distance"] / max(len(pts), 1)
        out.append({"coords": [[la, lo] for lo, la in pts], "dist": r["distance"],
                    "exposure": sum(risk(la, lo, hs) for lo, la in pts) * step / 100})
    if not out: return jsonify(error="no route"), 404
    return jsonify(routes=out, safest=min(range(len(out)), key=lambda i: out[i]["exposure"]))

init()   # create tables on start (also when run by gunicorn on a host)

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
