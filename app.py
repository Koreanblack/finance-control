import sqlite3
import json
import os
from datetime import date
from flask import Flask, render_template, request, redirect, url_for, flash, g

app = Flask(__name__)
app.secret_key = 'finance-control-secret-2026'

_base_dir = os.path.dirname(__file__)
# Vercel's filesystem is read-only except /tmp
DATABASE = '/tmp/finance.db' if os.environ.get('VERCEL') else os.path.join(_base_dir, 'finance.db')
DATA_JSON = os.path.join(_base_dir, 'data.json')

WALLETS = [
    'Banco Macro',
    'Personal Pay',
    'Banco Ciudad',
    'MercadoPago',
]

CATEGORIES = [
    'Gasto hormiga',
    'Gasto fijo',
    'Placer',
    'Gastos variables',
    'Sin determinar',
]

TYPES = ['ingreso', 'egreso', 'transferencia']

# Category normalization map from data.json legacy values
CATEGORY_MAP = {
    'gasto fijo variable': 'Gastos variables',
    'gastos variables': 'Gastos variables',
    'gasto hormiga': 'Gasto hormiga',
    'gasto fijo': 'Gasto fijo',
    'placer': 'Placer',
    'sin categorizar': 'Sin determinar',
    'sin determinar': 'Sin determinar',
}


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            type TEXT NOT NULL,
            category TEXT,
            wallet TEXT NOT NULL,
            wallet_destination TEXT,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    ''')
    conn.commit()

    # Seed from data.json only if DB is empty
    cur.execute('SELECT COUNT(*) as cnt FROM transactions')
    count = cur.fetchone()['cnt']
    if count == 0 and os.path.exists(DATA_JSON):
        with open(DATA_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)

        default_wallet = 'Banco Macro'

        for item in data.get('ingresos', []):
            cur.execute('''
                INSERT INTO transactions (date, description, amount, type, category, wallet)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                item.get('fecha', str(date.today())),
                item.get('concepto') or item.get('descripcion', ''),
                float(item.get('monto', 0)),
                'ingreso',
                None,
                item.get('billetera', default_wallet),
            ))

        for item in data.get('gastos', []):
            raw_cat = (item.get('categoria') or '').strip().lower()
            category = CATEGORY_MAP.get(raw_cat, 'Sin determinar')
            cur.execute('''
                INSERT INTO transactions (date, description, amount, type, category, wallet)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                item.get('fecha', str(date.today())),
                item.get('concepto') or item.get('descripcion', ''),
                float(item.get('monto', 0)),
                'egreso',
                category,
                item.get('billetera', default_wallet),
            ))

        conn.commit()
    conn.close()


def format_ars(amount):
    """Format amount as Argentine pesos: $ 1.234,56"""
    negative = amount < 0
    amount = abs(amount)
    integer_part = int(amount)
    decimal_part = round((amount - integer_part) * 100)
    int_str = f'{integer_part:,}'.replace(',', '.')
    result = f'$ {int_str},{decimal_part:02d}'
    if negative:
        result = f'-{result}'
    return result


app.jinja_env.filters['ars'] = format_ars

CATEGORY_BADGES = {
    'Gasto hormiga': 'bg-warning text-dark',
    'Gasto fijo': 'bg-secondary',
    'Placer': 'bg-purple',
    'Gastos variables': 'bg-orange',
    'Sin determinar': 'bg-light text-dark border',
}

CATEGORY_BARS = {
    'Gasto hormiga': 'bg-warning',
    'Gasto fijo': 'bg-secondary',
    'Placer': 'bg-purple',
    'Gastos variables': 'bg-orange',
    'Sin determinar': 'bg-light',
}


@app.context_processor
def inject_helpers():
    def cat_badge(cat):
        return CATEGORY_BADGES.get(cat, 'bg-light text-dark border')

    def cat_bar(cat):
        return CATEGORY_BARS.get(cat, 'bg-secondary')

    return dict(cat_badge=cat_badge, cat_bar=cat_bar, WALLETS=WALLETS, CATEGORIES=CATEGORIES)


def get_wallet_balances(db):
    balances = {}
    for w in WALLETS:
        balances[w] = 0.0

    rows = db.execute(
        "SELECT wallet, type, wallet_destination, SUM(amount) as total "
        "FROM transactions GROUP BY wallet, type, wallet_destination"
    ).fetchall()

    for row in rows:
        wallet = row['wallet']
        t = row['type']
        total = row['total'] or 0.0
        dest = row['wallet_destination']

        if wallet not in balances:
            balances[wallet] = 0.0
        if dest and dest not in balances:
            balances[dest] = 0.0

        if t == 'ingreso':
            balances[wallet] = balances.get(wallet, 0.0) + total
        elif t == 'egreso':
            balances[wallet] = balances.get(wallet, 0.0) - total
        elif t == 'transferencia':
            balances[wallet] = balances.get(wallet, 0.0) - total
            if dest:
                balances[dest] = balances.get(dest, 0.0) + total

    return balances


@app.route('/')
def index():
    db = get_db()
    balances = get_wallet_balances(db)
    total_balance = sum(balances.values())

    # Expenses by category this month
    today = date.today()
    month_start = f'{today.year}-{today.month:02d}-01'
    cat_rows = db.execute(
        "SELECT category, SUM(amount) as total FROM transactions "
        "WHERE type='egreso' AND date >= ? GROUP BY category ORDER BY total DESC",
        (month_start,)
    ).fetchall()

    # Last 10 transactions
    recent = db.execute(
        "SELECT * FROM transactions ORDER BY date DESC, created_at DESC LIMIT 10"
    ).fetchall()

    return render_template(
        'index.html',
        wallets=WALLETS,
        balances=balances,
        total_balance=total_balance,
        cat_rows=cat_rows,
        recent=recent,
        today=today,
    )


@app.route('/transactions')
def transactions():
    db = get_db()
    query = "SELECT * FROM transactions WHERE 1=1"
    params = []

    wallet_filter = request.args.get('wallet', '')
    type_filter = request.args.get('type', '')
    category_filter = request.args.get('category', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    if wallet_filter:
        query += " AND (wallet=? OR wallet_destination=?)"
        params += [wallet_filter, wallet_filter]
    if type_filter:
        query += " AND type=?"
        params.append(type_filter)
    if category_filter:
        query += " AND category=?"
        params.append(category_filter)
    if date_from:
        query += " AND date>=?"
        params.append(date_from)
    if date_to:
        query += " AND date<=?"
        params.append(date_to)

    query += " ORDER BY date DESC, created_at DESC"
    rows = db.execute(query, params).fetchall()

    return render_template(
        'transactions.html',
        transactions=rows,
        wallets=WALLETS,
        categories=CATEGORIES,
        types=TYPES,
        wallet_filter=wallet_filter,
        type_filter=type_filter,
        category_filter=category_filter,
        date_from=date_from,
        date_to=date_to,
    )


@app.route('/add', methods=['GET', 'POST'])
def add_transaction():
    if request.method == 'POST':
        t = request.form.get('type', '').strip()
        description = request.form.get('description', '').strip()
        amount_str = request.form.get('amount', '0').strip().replace(',', '.')
        wallet = request.form.get('wallet', '').strip()
        category = request.form.get('category', '').strip() or None
        wallet_destination = request.form.get('wallet_destination', '').strip() or None
        notes = request.form.get('notes', '').strip() or None
        txn_date = request.form.get('date', str(date.today())).strip()

        errors = []
        if not description:
            errors.append('La descripción es requerida.')
        try:
            amount = float(amount_str)
            if amount <= 0:
                errors.append('El monto debe ser mayor a cero.')
        except ValueError:
            errors.append('Monto inválido.')
        if t not in TYPES:
            errors.append('Tipo de transacción inválido.')
        if wallet not in WALLETS:
            errors.append('Billetera inválida.')
        if t == 'transferencia':
            if not wallet_destination:
                errors.append('Debe seleccionar una billetera destino.')
            elif wallet_destination == wallet:
                errors.append('La billetera destino debe ser diferente a la de origen.')
            category = None
        elif t == 'ingreso':
            category = None

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template(
                'add_transaction.html',
                wallets=WALLETS,
                categories=CATEGORIES,
                types=TYPES,
                today=str(date.today()),
                form=request.form,
            )

        db = get_db()
        db.execute(
            "INSERT INTO transactions (date, description, amount, type, category, wallet, wallet_destination, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (txn_date, description, amount, t, category, wallet, wallet_destination, notes)
        )
        db.commit()
        flash('Transacción agregada correctamente.', 'success')
        return redirect(url_for('index'))

    return render_template(
        'add_transaction.html',
        wallets=WALLETS,
        categories=CATEGORIES,
        types=TYPES,
        today=str(date.today()),
        form={},
    )


@app.route('/edit/<int:txn_id>', methods=['GET', 'POST'])
def edit_transaction(txn_id):
    db = get_db()
    txn = db.execute("SELECT * FROM transactions WHERE id=?", (txn_id,)).fetchone()
    if not txn:
        flash('Transacción no encontrada.', 'danger')
        return redirect(url_for('transactions'))

    if request.method == 'POST':
        t = request.form.get('type', '').strip()
        description = request.form.get('description', '').strip()
        amount_str = request.form.get('amount', '0').strip().replace(',', '.')
        wallet = request.form.get('wallet', '').strip()
        category = request.form.get('category', '').strip() or None
        wallet_destination = request.form.get('wallet_destination', '').strip() or None
        notes = request.form.get('notes', '').strip() or None
        txn_date = request.form.get('date', str(date.today())).strip()

        errors = []
        if not description:
            errors.append('La descripción es requerida.')
        try:
            amount = float(amount_str)
            if amount <= 0:
                errors.append('El monto debe ser mayor a cero.')
        except ValueError:
            errors.append('Monto inválido.')
        if t not in TYPES:
            errors.append('Tipo de transacción inválido.')
        if wallet not in WALLETS:
            errors.append('Billetera inválida.')
        if t == 'transferencia':
            if not wallet_destination:
                errors.append('Debe seleccionar una billetera destino.')
            elif wallet_destination == wallet:
                errors.append('La billetera destino debe ser diferente a la de origen.')
            category = None
        elif t == 'ingreso':
            category = None

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template(
                'add_transaction.html',
                wallets=WALLETS,
                categories=CATEGORIES,
                types=TYPES,
                today=str(date.today()),
                form=request.form,
                edit_mode=True,
                txn_id=txn_id,
            )

        db.execute(
            "UPDATE transactions SET date=?, description=?, amount=?, type=?, category=?, "
            "wallet=?, wallet_destination=?, notes=? WHERE id=?",
            (txn_date, description, amount, t, category, wallet, wallet_destination, notes, txn_id)
        )
        db.commit()
        flash('Transacción actualizada correctamente.', 'success')
        return redirect(url_for('transactions'))

    return render_template(
        'add_transaction.html',
        wallets=WALLETS,
        categories=CATEGORIES,
        types=TYPES,
        today=str(date.today()),
        form=txn,
        edit_mode=True,
        txn_id=txn_id,
    )


@app.route('/delete/<int:txn_id>', methods=['POST'])
def delete_transaction(txn_id):
    db = get_db()
    db.execute("DELETE FROM transactions WHERE id=?", (txn_id,))
    db.commit()
    flash('Transacción eliminada.', 'success')
    return redirect(url_for('transactions'))


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
