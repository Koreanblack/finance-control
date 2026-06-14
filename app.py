import json
import os
import tempfile
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

DATA_FILE = os.path.join(os.path.dirname(__file__), 'data.json')


def load_data():
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_data(data):
    dir_name = os.path.dirname(DATA_FILE)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, DATA_FILE)
    except Exception:
        os.unlink(tmp_path)
        raise


@app.route('/')
def index():
    data = load_data()
    ingresos = data.get('ingresos', [])
    gastos = data.get('gastos', [])

    total_ingresos = sum(i['monto'] for i in ingresos)
    total_gastos = sum(g['monto'] for g in gastos)
    balance = total_ingresos - total_gastos

    categorias = {}
    for g in gastos:
        cat = g.get('categoria', 'Sin Categorizar')
        categorias[cat] = categorias.get(cat, 0) + g['monto']

    return render_template(
        'index.html',
        ingresos=ingresos,
        gastos=gastos,
        total_ingresos=total_ingresos,
        total_gastos=total_gastos,
        balance=balance,
        categorias=categorias,
    )


@app.route('/agregar-ingreso', methods=['POST'])
def agregar_ingreso():
    data = load_data()
    data['ingresos'].append({
        'fecha': request.form['fecha'],
        'concepto': request.form['concepto'],
        'monto': float(request.form['monto']),
    })
    save_data(data)
    return redirect(url_for('index'))


@app.route('/agregar-gasto', methods=['POST'])
def agregar_gasto():
    data = load_data()
    data['gastos'].append({
        'fecha': request.form['fecha'],
        'concepto': request.form['concepto'],
        'monto': float(request.form['monto']),
        'categoria': request.form['categoria'],
    })
    save_data(data)
    return redirect(url_for('index'))


@app.route('/eliminar-ingreso', methods=['POST'])
def eliminar_ingreso():
    idx = int(request.form['index'])
    data = load_data()
    if 0 <= idx < len(data['ingresos']):
        data['ingresos'].pop(idx)
        save_data(data)
    return redirect(url_for('index'))


@app.route('/eliminar-gasto', methods=['POST'])
def eliminar_gasto():
    idx = int(request.form['index'])
    data = load_data()
    if 0 <= idx < len(data['gastos']):
        data['gastos'].pop(idx)
        save_data(data)
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
