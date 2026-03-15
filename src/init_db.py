"""
init_db.py — Create the SQLite schema and import all Excel data files.

Run once from any directory:
    python src/init_db.py

Import files are read from  <project_root>/import/
Database is written to      <project_root>/shop.db
"""

import os
import re
import sqlite3

import pandas as pd

# ── Paths (all relative to project root) ──────────────────────────────────
_SRC_DIR    = os.path.dirname(os.path.abspath(__file__))
BASE_DIR    = os.path.dirname(_SRC_DIR)
DB_PATH     = os.path.join(BASE_DIR, 'shop.db')
IMPORT_DIR  = os.path.join(BASE_DIR, 'import')

# ── Convenience helpers ────────────────────────────────────────────────────
def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def _import_path(filename: str) -> str:
    return os.path.join(IMPORT_DIR, filename)

# ── Schema ─────────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS role (
    role_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    role_name TEXT    NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS user (
    user_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT    NOT NULL,
    login     TEXT    NOT NULL UNIQUE,
    password  TEXT    NOT NULL,
    role_id   INTEGER NOT NULL,
    FOREIGN KEY (role_id) REFERENCES role(role_id)
);

CREATE TABLE IF NOT EXISTS category (
    category_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    category_name TEXT    NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS supplier (
    supplier_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_name TEXT    NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS manufacturer (
    manufacturer_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    manufacturer_name TEXT    NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS product (
    product_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    article         TEXT    NOT NULL UNIQUE,
    product_name    TEXT    NOT NULL,
    unit            TEXT    NOT NULL,
    price           REAL    NOT NULL,
    discount        REAL    NOT NULL DEFAULT 0,
    stock_qty       INTEGER NOT NULL DEFAULT 0,
    description     TEXT,
    photo           TEXT,
    category_id     INTEGER,
    supplier_id     INTEGER,
    manufacturer_id INTEGER,
    FOREIGN KEY (category_id)     REFERENCES category(category_id),
    FOREIGN KEY (supplier_id)     REFERENCES supplier(supplier_id),
    FOREIGN KEY (manufacturer_id) REFERENCES manufacturer(manufacturer_id)
);

CREATE TABLE IF NOT EXISTS pickup_point (
    pickup_point_id INTEGER PRIMARY KEY AUTOINCREMENT,
    address         TEXT    NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS "order" (
    order_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    order_number    INTEGER NOT NULL UNIQUE,
    order_date      TEXT,
    delivery_date   TEXT,
    pickup_point_id INTEGER,
    user_id         INTEGER,
    pickup_code     TEXT,
    status          TEXT    NOT NULL DEFAULT 'Новый',
    FOREIGN KEY (pickup_point_id) REFERENCES pickup_point(pickup_point_id),
    FOREIGN KEY (user_id)         REFERENCES user(user_id)
);

CREATE TABLE IF NOT EXISTS order_item (
    order_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id      INTEGER NOT NULL,
    product_id    INTEGER,
    article       TEXT    NOT NULL,
    quantity      INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (order_id)   REFERENCES "order"(order_id),
    FOREIGN KEY (product_id) REFERENCES product(product_id)
);
"""

def create_tables() -> None:
    conn = _connect()
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()

# ── Date parsing ───────────────────────────────────────────────────────────
def _parse_date(val) -> str | None:
    """Accept dd.mm.yyyy, m/d/yy, pandas Timestamp, or ISO strings."""
    if val is None:
        return None
    if hasattr(val, 'strftime'):          # pandas Timestamp
        try:
            return val.strftime('%Y-%m-%d')
        except Exception:
            return None
    s = str(val).strip()
    if not s or s.lower() in ('nan', 'nat', ''):
        return None
    # dd.mm.yyyy
    m = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$', s)
    if m:
        d, mo, y = m.groups()
        return f'{y}-{mo.zfill(2)}-{d.zfill(2)}'
    # Already ISO
    m2 = re.match(r'^(\d{4})-(\d{2})-(\d{2})', s)
    if m2:
        return s[:10]
    # Fallback: let pandas try
    try:
        import pandas as _pd
        ts = _pd.to_datetime(s, dayfirst=True)
        return ts.strftime('%Y-%m-%d')
    except Exception:
        return s

# ── Import functions ───────────────────────────────────────────────────────
def import_roles(conn: sqlite3.Connection) -> None:
    for role in ('Администратор', 'Менеджер', 'Авторизированный клиент', 'Гость'):
        conn.execute("INSERT OR IGNORE INTO role(role_name) VALUES(?)", (role,))
    conn.commit()

def import_users(conn: sqlite3.Connection) -> None:
    df = pd.read_excel(_import_path('user_import.xlsx'), dtype=str)
    for _, row in df.iterrows():
        role_name = str(row['Роль сотрудника']).strip()
        r = conn.execute(
            "SELECT role_id FROM role WHERE role_name=?", (role_name,)).fetchone()
        if not r:
            print(f"  WARN: unknown role '{role_name}' — skipping {row['ФИО']}")
            continue
        conn.execute(
            "INSERT OR IGNORE INTO user(full_name, login, password, role_id)"
            " VALUES(?,?,?,?)",
            (str(row['ФИО']).strip(),
             str(row['Логин']).strip(),
             str(row['Пароль']).strip(),
             r['role_id']))
    conn.commit()

def import_pickup_points(conn: sqlite3.Connection) -> None:
    df = pd.read_excel(_import_path('Пункты_выдачи_import.xlsx'), dtype=str, header=None)
    for _, row in df.iterrows():
        addr = str(row[0]).strip()
        if addr and addr.lower() != 'nan':
            conn.execute(
                "INSERT OR IGNORE INTO pickup_point(address) VALUES(?)", (addr,))
    conn.commit()

def import_products(conn: sqlite3.Connection) -> None:
    df = pd.read_excel(_import_path('Tovar.xlsx'))
    for _, row in df.iterrows():
        cat = str(row['Категория товара']).strip()
        sup = str(row['Поставщик']).strip()
        man = str(row['Производитель']).strip()

        for tbl, col, val in [
            ('category',     'category_name',     cat),
            ('supplier',     'supplier_name',     sup),
            ('manufacturer', 'manufacturer_name', man),
        ]:
            conn.execute(f"INSERT OR IGNORE INTO {tbl}({col}) VALUES(?)", (val,))
        conn.commit()

        cat_id = conn.execute(
            "SELECT category_id     FROM category     WHERE category_name=?",     (cat,)).fetchone()['category_id']
        sup_id = conn.execute(
            "SELECT supplier_id     FROM supplier     WHERE supplier_name=?",     (sup,)).fetchone()['supplier_id']
        man_id = conn.execute(
            "SELECT manufacturer_id FROM manufacturer WHERE manufacturer_name=?", (man,)).fetchone()['manufacturer_id']

        photo = str(row['Фото']).strip() if pd.notna(row['Фото']) else None
        if photo in ('nan', ''):
            photo = None
        desc  = str(row['Описание товара']).strip() if pd.notna(row['Описание товара']) else None

        conn.execute("""
            INSERT OR IGNORE INTO product
              (article, product_name, unit, price, discount, stock_qty,
               description, photo, category_id, supplier_id, manufacturer_id)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (str(row['Артикул']).strip(),
             str(row['Наименование товара']).strip(),
             str(row['Единица измерения']).strip(),
             float(row['Цена']),
             float(row['Действующая скидка']),
             int(row['Кол-во на складе']),
             desc, photo,
             cat_id, sup_id, man_id))
    conn.commit()

def import_orders(conn: sqlite3.Connection) -> None:
    df = pd.read_excel(_import_path('Заказ_import.xlsx'), dtype={'Номер заказа': int})

    # Build a 1-based positional index of pickup points (matches the Excel column values)
    pp_rows = conn.execute(
        "SELECT pickup_point_id FROM pickup_point ORDER BY pickup_point_id").fetchall()
    pp_by_index = {i + 1: r['pickup_point_id'] for i, r in enumerate(pp_rows)}

    for _, row in df.iterrows():
        order_num     = int(row['Номер заказа'])
        order_date    = _parse_date(row['Дата заказа'])
        delivery_date = _parse_date(row['Дата доставки'])

        pp_idx = None
        try:
            pp_idx = int(row['Адрес пункта выдачи'])
        except (ValueError, TypeError):
            pass
        pp_id = pp_by_index.get(pp_idx)

        fio = str(row['ФИО авторизированного клиента']).strip()
        u   = conn.execute(
            "SELECT user_id FROM user WHERE full_name=?", (fio,)).fetchone()
        user_id = u['user_id'] if u else None

        try:
            code = str(int(float(str(row['Код для получения']))))
        except (ValueError, TypeError):
            code = str(row['Код для получения']).strip() or None

        status = str(row['Статус заказа']).strip()

        conn.execute("""
            INSERT OR IGNORE INTO "order"
              (order_number, order_date, delivery_date,
               pickup_point_id, user_id, pickup_code, status)
            VALUES(?,?,?,?,?,?,?)""",
            (order_num, order_date, delivery_date, pp_id, user_id, code, status))
        conn.commit()

        ord_row = conn.execute(
            'SELECT order_id FROM "order" WHERE order_number=?', (order_num,)).fetchone()
        if not ord_row:
            continue
        order_id = ord_row['order_id']

        # Parse "А112Т4, 2, F635R4, 2" → [(А112Т4, 2), (F635R4, 2)]
        raw_items = str(row['Артикул заказа']).strip()
        parts = [p.strip() for p in raw_items.split(',')]
        i = 0
        while i < len(parts):
            article = parts[i]
            i += 1
            qty = 1
            if i < len(parts):
                try:
                    qty = int(parts[i])
                    i += 1
                except ValueError:
                    pass   # next token is an article, not a qty
            pr = conn.execute(
                "SELECT product_id FROM product WHERE article=?", (article,)).fetchone()
            conn.execute(
                "INSERT INTO order_item(order_id, product_id, article, quantity)"
                " VALUES(?,?,?,?)",
                (order_id, pr['product_id'] if pr else None, article, qty))
        conn.commit()

# ── Main ───────────────────────────────────────────────────────────────────
def main() -> None:
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"Removed existing database: {DB_PATH}")

    print("Creating schema…")
    create_tables()

    conn = _connect()
    print("Importing roles…")
    import_roles(conn)
    print("Importing users…")
    import_users(conn)
    print("Importing pickup points…")
    import_pickup_points(conn)
    print("Importing products…")
    import_products(conn)
    print("Importing orders…")
    import_orders(conn)
    conn.close()

    # Summary
    conn2 = _connect()
    print("\n=== Import summary ===")
    for tbl, label in [
        ('role',          'Роли'),
        ('user',          'Пользователи'),
        ('category',      'Категории'),
        ('supplier',      'Поставщики'),
        ('manufacturer',  'Производители'),
        ('product',       'Товары'),
        ('pickup_point',  'Пункты выдачи'),
        ('"order"',       'Заказы'),
        ('order_item',    'Позиции заказов'),
    ]:
        n = conn2.execute(f'SELECT COUNT(*) AS c FROM {tbl}').fetchone()['c']
        print(f"  {label}: {n}")
    conn2.close()
    print(f"\nDatabase saved to: {DB_PATH}")

if __name__ == '__main__':
    main()
