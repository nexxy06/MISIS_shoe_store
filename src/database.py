"""
database.py — Доступ к БД и HTML-фрагменты для ООО «Обувь»
"""

import os
import sqlite3
import secrets
import time
import re

# src/ is one level below the project root
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(_SRC_DIR)
DB_PATH = os.path.join(BASE_DIR, "shop.db")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


_sessions: dict = {}


def create_session(user_id: int, role: str, full_name: str) -> str:
    tok = secrets.token_hex(24)
    _sessions[tok] = {
        "user_id": user_id,
        "role": role,
        "full_name": full_name,
        "exp": time.time() + 86400,
    }
    return tok


def session_from_cookie(cookie: str | None) -> dict | None:
    if not cookie:
        return None
    m = re.search(r"session=([a-f0-9]+)", cookie)
    if not m:
        return None
    s = _sessions.get(m.group(1))
    return s if (s and s["exp"] > time.time()) else None


_SORT_MAP = {
    "name_asc": "p.product_name ASC",
    "name_desc": "p.product_name DESC",
    "price_asc": "p.price ASC",
    "price_desc": "p.price DESC",
    "disc_asc": "p.discount ASC",
    "disc_desc": "p.discount DESC",
    "stock_asc": "p.stock_qty ASC",
    "stock_desc": "p.stock_qty DESC",
}


def fetch_products(
    search: str = "", category: str = "", sort: str = "", supplier: str = ""
) -> list:
    conn = get_db()
    sql = """
        SELECT p.*,
               c.category_name,
               s.supplier_name,
               m.manufacturer_name
        FROM product p
        LEFT JOIN category     c ON p.category_id     = c.category_id
        LEFT JOIN supplier     s ON p.supplier_id     = s.supplier_id
        LEFT JOIN manufacturer m ON p.manufacturer_id = m.manufacturer_id
        WHERE 1=1
    """
    params = []
    if search:
        sql += (
            " AND (p.article       LIKE ?"
            "   OR p.product_name  LIKE ?"
            "   OR c.category_name LIKE ?"
            "   OR s.supplier_name LIKE ?"
            "   OR m.manufacturer_name LIKE ?"
            "   OR p.description   LIKE ?"
            "   OR p.unit         LIKE ?)"
        )
        params += [f"%{search}%"] * 7
    if category:
        sql += " AND c.category_name = ?"
        params.append(category)
    if supplier:
        sql += " AND s.supplier_name = ?"
        params.append(supplier)
    sql += f" ORDER BY {_SORT_MAP.get(sort, 'p.product_id ASC')}"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def fetch_categories() -> list[str]:
    conn = get_db()
    rows = conn.execute(
        "SELECT category_name FROM category ORDER BY category_name"
    ).fetchall()
    conn.close()
    return [r["category_name"] for r in rows]


def fetch_suppliers() -> list[str]:
    conn = get_db()
    rows = conn.execute(
        """
        SELECT DISTINCT s.supplier_name
        FROM supplier s
        JOIN product p ON s.supplier_id = p.supplier_id
        WHERE s.supplier_name IS NOT NULL AND s.supplier_name != ''
        ORDER BY s.supplier_name
        """
    ).fetchall()
    conn.close()
    return [r["supplier_name"] for r in rows]


def fetch_manufacturers() -> list[str]:
    conn = get_db()
    rows = conn.execute(
        "SELECT manufacturer_name FROM manufacturer ORDER BY manufacturer_name"
    ).fetchall()
    conn.close()
    return [r["manufacturer_name"] for r in rows]


def fetch_product_by_id(pid: int) -> sqlite3.Row | None:
    conn = get_db()
    row = conn.execute(
        """
        SELECT p.*,
               c.category_name,
               s.supplier_name,
               m.manufacturer_name
        FROM product p
        LEFT JOIN category     c ON p.category_id     = c.category_id
        LEFT JOIN supplier     s ON p.supplier_id     = s.supplier_id
        LEFT JOIN manufacturer m ON p.manufacturer_id = m.manufacturer_id
        WHERE p.product_id = ?""",
        (pid,),
    ).fetchone()
    conn.close()
    return row


def save_product(data: dict) -> None:
    """Insert or update a product. Upserts category/supplier/manufacturer."""
    conn = get_db()
    try:
        for tbl, col, val in [
            ("category", "category_name", data.get("category_name", "")),
            ("supplier", "supplier_name", data.get("supplier_name", "")),
            ("manufacturer", "manufacturer_name",
             data.get("manufacturer_name", "")),
        ]:
            if val:
                conn.execute(f"INSERT OR IGNORE INTO {tbl}({col}) VALUES(?)", (val,))
        conn.commit()

        def fk(tbl, col, val):
            if not val:
                return None
            r = conn.execute(
                f"SELECT {tbl}_id FROM {tbl} WHERE {col}=?", (val,)
            ).fetchone()
            return r[0] if r else None

        cat_id = fk("category", "category_name", data.get("category_name"))
        sup_id = fk("supplier", "supplier_name", data.get("supplier_name"))
        man_id = fk("manufacturer", "manufacturer_name", data.get("manufacturer_name"))
        pid = data.get("product_id")

        args = (
            data["article"],
            data["product_name"],
            data["unit"],
            float(data["price"]),
            float(data.get("discount", 0)),
            int(data.get("stock_qty", 0)),
            data.get("description") or None,
            data.get("photo") or None,
            cat_id,
            sup_id,
            man_id,
        )
        if pid:
            conn.execute(
                """UPDATE product SET
                article=?, product_name=?, unit=?, price=?, discount=?,
                stock_qty=?, description=?, photo=?,
                category_id=?, supplier_id=?, manufacturer_id=?
                WHERE product_id=?""",
                (*args, int(pid)),
            )
        else:
            conn.execute(
                """INSERT INTO product
                (article, product_name, unit, price, discount, stock_qty,
                 description, photo, category_id, supplier_id, manufacturer_id)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                args,
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_product(product_id: int) -> None:
    conn = get_db()
    conn.execute("DELETE FROM order_item WHERE product_id=?", (product_id,))
    conn.execute("DELETE FROM product     WHERE product_id=?", (product_id,))
    conn.commit()
    conn.close()


def fetch_orders() -> list:
    conn = get_db()
    rows = conn.execute(
        """
        SELECT o.*,
               u.full_name,
               pp.address,
               GROUP_CONCAT(oi.article || ' ×' || oi.quantity, ', ') AS items_str
        FROM "order" o
        LEFT JOIN user         u  ON o.user_id         = u.user_id
        LEFT JOIN pickup_point pp ON o.pickup_point_id = pp.pickup_point_id
        LEFT JOIN order_item   oi ON o.order_id        = oi.order_id
        GROUP BY o.order_id
        ORDER BY o.order_number
    """
    ).fetchall()
    conn.close()
    return rows


def fetch_order_by_id(oid: int) -> dict | None:
    conn = get_db()
    o = conn.execute(
        """
        SELECT o.*, u.full_name, pp.address
        FROM "order" o
        LEFT JOIN user         u  ON o.user_id         = u.user_id
        LEFT JOIN pickup_point pp ON o.pickup_point_id = pp.pickup_point_id
        WHERE o.order_id=?""",
        (oid,),
    ).fetchone()
    if not o:
        conn.close()
        return None
    items = conn.execute(
        """
        SELECT oi.*, p.product_name
        FROM order_item oi
        LEFT JOIN product p ON oi.product_id = p.product_id
        WHERE oi.order_id=?""",
        (oid,),
    ).fetchall()
    users = conn.execute(
        "SELECT user_id, full_name FROM user ORDER BY full_name"
    ).fetchall()
    pps = conn.execute(
        "SELECT pickup_point_id, address FROM pickup_point ORDER BY address"
    ).fetchall()
    conn.close()
    return {
        "order": dict(o),
        "items": [dict(i) for i in items],
        "users": [dict(u) for u in users],
        "pickup_points": [dict(p) for p in pps],
    }


def save_order(data: dict) -> None:
    conn = get_db()
    try:
        uid = data.get("user_id") or None
        ppid = data.get("pickup_point_id") or None
        oid = data.get("order_id")

        if oid:
            conn.execute(
                """UPDATE "order" SET
                order_date=?, delivery_date=?, pickup_point_id=?,
                user_id=?, pickup_code=?, status=?
                WHERE order_id=?""",
                (
                    data.get("order_date") or None,
                    data.get("delivery_date") or None,
                    ppid,
                    uid,
                    data.get("pickup_code") or None,
                    data.get("status", "Новый"),
                    int(oid),
                ),
            )
            conn.execute("DELETE FROM order_item WHERE order_id=?", (int(oid),))
        else:
            mx = conn.execute(
                'SELECT COALESCE(MAX(order_number), 0) AS m FROM "order"'
            ).fetchone()["m"]
            conn.execute(
                """INSERT INTO "order"
                (order_number, order_date, delivery_date, pickup_point_id,
                 user_id, pickup_code, status)
                VALUES(?,?,?,?,?,?,?)""",
                (
                    mx + 1,
                    data.get("order_date") or None,
                    data.get("delivery_date") or None,
                    ppid,
                    uid,
                    data.get("pickup_code") or None,
                    data.get("status", "Новый"),
                ),
            )
            oid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]

        for item in data.get("items", []):
            art = (item.get("article") or "").strip()
            if not art:
                continue
            pr = conn.execute(
                "SELECT product_id FROM product WHERE article=?", (art,)
            ).fetchone()
            conn.execute(
                "INSERT INTO order_item(order_id, product_id, article, quantity)"
                " VALUES(?,?,?,?)",
                (
                    oid,
                    pr["product_id"] if pr else None,
                    art,
                    int(item.get("quantity", 1)),
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_order(order_id: int) -> None:
    conn = get_db()
    conn.execute("DELETE FROM order_item WHERE order_id=?", (order_id,))
    conn.execute('DELETE FROM "order"     WHERE order_id=?', (order_id,))
    conn.commit()
    conn.close()


def fetch_users() -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT user_id, full_name FROM user ORDER BY full_name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def fetch_pickup_points() -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT pickup_point_id, address FROM pickup_point ORDER BY address"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def esc(s) -> str:
    """HTML-escape a value."""
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def sel_opts(
    items: list[str], selected: str = "", empty_label: str | None = None
) -> str:
    """Build <option> tags for a <select>."""
    out = ""
    if empty_label is not None:
        sel = "selected" if not selected else ""
        out += f'<option value="" {sel}>{esc(empty_label)}</option>'
    for item in items:
        s = "selected" if item == selected else ""
        out += f'<option value="{esc(item)}" {s}>{esc(item)}</option>'
    return out


def product_row_html(p, can_edit: bool = False) -> str:
    discount = float(p["discount"] or 0)
    price = float(p["price"])
    stock = int(p["stock_qty"])
    final_p = round(price * (1 - discount / 100), 2)

    # Row highlight class
    if stock == 0:
        row_cls = "row-no-stock"
    elif discount > 15:
        row_cls = "row-big-discount"
    else:
        row_cls = ""

    # Photo
    photo = p["photo"]
    img_src = (
        f"/static/images/{photo}"
        if photo and photo not in ("None", "")
        else "/static/images/picture.png"
    )

    # Price display
    if discount > 0:
        price_html = (
            f'<span class="price-old">{price:,.2f}\u00a0₽</span>'
            f'<span class="price-new">{final_p:,.2f}\u00a0₽</span>'
        )
    else:
        price_html = f'<span class="price-plain">{price:,.2f}\u00a0₽</span>'

    # Discount badge
    disc_cell = (
        f'<span class="disc-badge">{discount:.0f}%</span>'
        if discount > 0
        else '<span class="no-disc">—</span>'
    )

    # Admin action buttons
    actions = ""
    if can_edit:
        actions = (
            f'<div class="action-btns">'
            f'<button class="btn-icon btn-edit" title="Редактировать"'
            f' onclick="editProduct({p["product_id"]})">✏️</button>'
            f'<button class="btn-icon btn-del"  title="Удалить"'
            f' onclick="deleteProduct({p["product_id"]})">🗑️</button>'
            f"</div>"
        )

    info = (
        f'<div class="prod-info">'
        f'  <div class="prod-title">'
        f'    <span class="prod-cat">{esc(p["category_name"])}</span>'
        f'    <span class="prod-sep"> | </span>'
        f'    <strong class="prod-name">{esc(p["product_name"])}</strong>'
        f"  </div>"
        f'  <div class="prod-detail">Описание товара: {esc(p["description"]) or "—"}</div>'
        f'  <div class="prod-detail">Производитель: {esc(p["manufacturer_name"]) or "—"}</div>'
        f'  <div class="prod-detail">Поставщик: {esc(p["supplier_name"]) or "—"}</div>'
        f'  <div class="prod-detail prod-price">Цена: {price_html}</div>'
        f'  <div class="prod-detail">Единица измерения: {esc(p["unit"])}</div>'
        f'  <div class="prod-detail">Количество на складе: {stock}</div>'
        f"</div>"
    )

    return (
        f'<tr class="{row_cls}" data-id="{p["product_id"]}">'
        f'  <td class="td-img">'
        f'    <img src="{img_src}" alt="фото" class="prod-img"'
        f"         onerror=\"this.src='/static/images/picture.png'\">"
        f"    {actions}"
        f"  </td>"
        f'  <td class="td-info">{info}</td>'
        f'  <td class="td-disc">{disc_cell}</td>'
        f"</tr>"
    )


def products_table_html(products: list, can_edit: bool = False) -> str:
    if not products:
        return '<div class="empty-state">Товары не найдены</div>'
    rows = "".join(product_row_html(p, can_edit) for p in products)
    return (
        '<table class="prod-table">'
        "  <thead><tr>"
        '    <th class="th-img">Фото</th>'
        '    <th class="th-info">Информация о товаре</th>'
        '    <th class="th-disc">Скидка</th>'
        "  </tr></thead>"
        f"  <tbody>{rows}</tbody>"
        "</table>"
    )


def user_badge_html(sess: dict | None) -> str:
    if sess:
        role_label = {
            "Администратор": "Администратор",
            "Менеджер": "Менеджер",
            "Авторизированный клиент": "Клиент",
        }.get(sess["role"], sess["role"])
        return (
            f'<div class="user-badge">'
            f'  <span class="user-role-pill">{esc(role_label)}</span>'
            f'  <span class="user-fullname">{esc(sess["full_name"])}</span>'
            f'  <a href="/logout" class="btn-logout">Выйти</a>'
            f"</div>"
        )
    return '<div class="user-badge"><a href="/" class="btn-logout">Войти</a></div>'


def nav_bar_html(sess: dict | None, current: str = "") -> str:
    if not sess:
        return ""
    role = sess["role"]
    links = [("/products", "Товары")]
    if role in ("Менеджер", "Администратор"):
        links.append(("/orders", "Заказы"))
    items = "".join(
        f'<a href="{href}" class="nav-link{" active" if href == current else ""}">{label}</a>'
        for href, label in links
    )
    return f'<nav class="site-nav">{items}</nav>'


def filter_bar_html(search: str, category: str, sort: str, supplier: str = "") -> str:
    sort_options = [
        ("", "Без сортировки"),
        ("name_asc", "Название А→Я"),
        ("name_desc", "Название Я→А"),
        ("price_asc", "Цена ↑"),
        ("price_desc", "Цена ↓"),
        ("disc_asc", "Скидка ↑"),
        ("disc_desc", "Скидка ↓"),
        ("stock_asc", "На складе ↑"),
        ("stock_desc", "На складе ↓"),
    ]
    sort_html = "".join(
        f'<option value="{v}" {"selected" if v == sort else ""}>{esc(l)}</option>'
        for v, l in sort_options
    )
    supplier_html = sel_opts(fetch_suppliers(), supplier, "Все поставщики")
    return (
        f'<form class="filter-bar" method="get" action="/products">'
        f'  <input id="fb-search" type="text" name="search" value="{esc(search)}"'
        f'         placeholder="Поиск: название, артикул, категория…">'
        f'  <select id="fb-category" name="category">'
        f'    {sel_opts(fetch_categories(), category, "Все категории")}'
        f"  </select>"
        f'  <select name="supplier" id="fb-supplier">{supplier_html}</select>'
        f'  <select name="sort" id="fb-sort">{sort_html}</select>'
        f'  <button type="submit" class="btn-primary">Найти</button>'
        f'  <a href="/products" class="btn-secondary" id="fb-reset">✕ Сбросить</a>'
        f"</form>"
    )