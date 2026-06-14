import json

def load_data():
    with open('data.json', 'r') as f:
        return json.load(f)

def show_summary():
    data = load_data()
    total_ingresos = sum(i['monto'] for i in data['ingresos'])
    total_gastos = sum(g['monto'] for g in data['gastos'])
    
    print(f"--- Resumen Financiero Junio 2026 ---")
    print(f"Total Ingresos: ${total_ingresos:,.2f}")
    print(f"Total Gastos: ${total_gastos:,.2f}")
    print(f"Balance Actual: ${total_ingresos - total_gastos:,.2f}")
    print("-" * 38)
    
    categorias = {}
    for g in data['gastos']:
        cat = g['categoria']
        categorias[cat] = categorias.get(cat, 0) + g['monto']
    
    print("Gastos por Categoría:")
    for cat, monto in categorias.items():
        print(f"- {cat}: ${monto:,.2f}")

if __name__ == "__main__":
    show_summary()
