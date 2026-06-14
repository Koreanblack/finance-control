import os
import json
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

# Uses PostgreSQL (Supabase/Vercel Postgres) when DATABASE_URL is set,
# otherwise falls back to local data.json for development.

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    def get_conn():
        return psycopg2.connect(DATABASE_URL, sslmode="require")

    def init_db():
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS ingresos (
                        id SERIAL PRIMARY KEY,
                        fecha DATE NOT NULL,
                        concepto TEXT NOT NULL,
                        monto NUMERIC(14,2) NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS gastos (
                        id SERIAL PRIMARY KEY,
                        fecha DATE NOT NULL,
                        concepto TEXT NOT NULL,
                        monto NUMERIC(14,2) NOT NULL,
                        categoria TEXT NOT NULL DEFAULT 'Sin Categorizar'
                    );
                """)

    def load_data():
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, fecha::text, concepto, CAST(monto AS FLOAT) AS monto FROM ingresos ORDER BY fecha DESC, id DESC")
                ingresos = [dict(r) for r in cur.fetchall()]
                cur.execute("SELECT id, fecha::text, concepto, CAST(monto AS FLOAT) AS monto, categoria FROM gastos ORDER BY fecha DESC, id DESC")
                gastos = [dict(r) for r in cur.fetchall()]
        return {"ingresos": ingresos, "gastos": gastos}

    def add_ingreso(fecha, concepto, monto):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO ingresos (fecha, concepto, monto) VALUES (%s, %s, %s)", (fecha, concepto, monto))

    def add_gasto(fecha, concepto, monto, categoria):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO gastos (fecha, concepto, monto, categoria) VALUES (%s, %s, %s, %s)", (fecha, concepto, monto, categoria))

    def delete_ingreso(row_id):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM ingresos WHERE id = %s", (row_id,))

    def delete_gasto(row_id):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM gastos WHERE id = %s", (row_id,))

    init_db()

else:
    import tempfile

    DATA_FILE = os.path.join(os.path.dirname(__file__), "data.json")

    def _load():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(data):
        dir_name = os.path.dirname(DATA_FILE)
        fd, tmp = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, DATA_FILE)
        except Exception:
            os.unlink(tmp)
            raise

    def load_data():
        return _load()

    def add_ingreso(fecha, concepto, monto):
        data = _load()
        data["ingresos"].append({"id": len(data["ingresos"]), "fecha": fecha, "concepto": concepto, "monto": float(monto)})
        _save(data)

    def add_gasto(fecha, concepto, monto, categoria):
        data = _load()
        data["gastos"].append({"id": len(data["gastos"]), "fecha": fecha, "concepto": concepto, "monto": float(monto), "categoria": categoria})
        _save(data)

    def delete_ingreso(row_id):
        data = _load()
        data["ingresos"] = [i for i in data["ingresos"] if str(i.get("id", "")) != str(row_id)]
        _save(data)

    def delete_gasto(row_id):
        data = _load()
        data["gastos"] = [g for g in data["gastos"] if str(g.get("id", "")) != str(row_id)]
        _save(data)


@app.route("/")
def index():
    data = load_data()
    ingresos = data.get("ingresos", [])
    gastos = data.get("gastos", [])

    total_ingresos = sum(i["monto"] for i in ingresos)
    total_gastos = sum(g["monto"] for g in gastos)
    balance = total_ingresos - total_gastos

    categorias = {}
    for g in gastos:
        cat = g.get("categoria", "Sin Categorizar")
        categorias[cat] = categorias.get(cat, 0) + g["monto"]

    return render_template(
        "index.html",
        ingresos=ingresos,
        gastos=gastos,
        total_ingresos=total_ingresos,
        total_gastos=total_gastos,
        balance=balance,
        categorias=categorias,
    )


@app.route("/agregar-ingreso", methods=["POST"])
def agregar_ingreso():
    add_ingreso(request.form["fecha"], request.form["concepto"], float(request.form["monto"]))
    return redirect(url_for("index"))


@app.route("/agregar-gasto", methods=["POST"])
def agregar_gasto():
    add_gasto(request.form["fecha"], request.form["concepto"], float(request.form["monto"]), request.form["categoria"])
    return redirect(url_for("index"))


@app.route("/eliminar-ingreso", methods=["POST"])
def eliminar_ingreso():
    delete_ingreso(request.form["id"])
    return redirect(url_for("index"))


@app.route("/eliminar-gasto", methods=["POST"])
def eliminar_gasto():
    delete_gasto(request.form["id"])
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
