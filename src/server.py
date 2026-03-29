"""
server.py — HTTP сервер для ООО «Обувь»
"""

import http.server
import json
import mimetypes
import os
import urllib.parse

from database import (
    BASE_DIR,
    # sessions
    create_session,
    session_from_cookie,
    # product
    fetch_products,
    fetch_product_by_id,
    fetch_categories,
    fetch_suppliers,
    fetch_manufacturers,
    save_product,
    delete_product,
    # orders
    fetch_orders,
    fetch_order_by_id,
    save_order,
    delete_order,
    fetch_users,
    fetch_pickup_points,
    # HTML helpers
    esc,
    products_table_html,
    user_badge_html,
    nav_bar_html,
    filter_bar_html,
)

TEMPLATES = os.path.join(BASE_DIR, "templates")
STATIC = os.path.join(BASE_DIR, "static")


def load_template(name: str) -> str:
    path = os.path.join(TEMPLATES, name)
    with open(path, encoding="utf-8") as f:
        return f.read()


def render(template_name: str, **ctx) -> str:
    """Load a template and substitute {{key}} placeholders."""
    html = load_template(template_name)
    for key, val in ctx.items():
        html = html.replace("{{" + key + "}}", str(val) if val is not None else "")
    return html


def common_ctx(sess, current_path: str = "") -> dict:
    """Context keys shared by every authenticated page."""
    return {
        "user_badge": user_badge_html(sess),
        "nav_bar": nav_bar_html(sess, current_path),
        "home_href": "/products" if sess else "/",
        "role": sess["role"] if sess else "",
    }


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silence default access log

    def send_html(
        self, html: str, status: int = 200, set_cookie: str | None = None
    ) -> None:
        enc = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(enc)))
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        self.end_headers()
        self.wfile.write(enc)

    def send_json(self, data, status: int = 200, set_cookie: str | None = None) -> None:
        enc = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(enc)))
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        self.end_headers()
        self.wfile.write(enc)

    def redirect(self, url: str, set_cookie: str | None = None) -> None:
        self.send_response(302)
        self.send_header("Location", url)
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        self.end_headers()

    def sess(self) -> dict | None:
        return session_from_cookie(self.headers.get("Cookie", ""))

    def body_str(self) -> str:
        n = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(n).decode("utf-8")

    def body_form(self) -> dict:
        return dict(urllib.parse.parse_qsl(self.body_str()))

    def body_json(self) -> dict:
        return json.loads(self.body_str())

    def parse_multipart(self):
        ctype = self.headers.get('Content-Type', '')
        if 'multipart/form-data' not in ctype:
            return None, None
        import cgi
        env = {'REQUEST_METHOD': 'POST'}
        fs = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ=env, keep_blank_values=True)
        return fs, ctype

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = dict(urllib.parse.parse_qsl(parsed.query))
        sess = self.sess()

        if path.startswith("/static/"):
            self.serve_static(path[len("/static/"):])
            return

        routes = {
            "/": lambda: self.pg_login(sess),
            "/login": lambda: self.pg_login(sess),
            "/logout": lambda: self.do_logout(),
            "/products": lambda: self.pg_products(sess, qs),
            "/orders": lambda: self.pg_orders(sess),
            "/api/product": lambda: self.api_get_product(sess, qs),
            "/api/categories": lambda: self.send_json(fetch_categories()),
            "/api/suppliers": lambda: self.send_json(fetch_suppliers()),
            "/api/manufacturers": lambda: self.send_json(fetch_manufacturers()),
            "/api/users": lambda: self.api_users(sess),
            "/api/pickup_points": lambda: self.send_json(fetch_pickup_points()),
            "/api/order": lambda: self.api_get_order(sess, qs),
        }
        handler = routes.get(path)
        if handler:
            handler()
        else:
            ctx = common_ctx(sess, path)
            self.send_html(render("404.html", **ctx), 404)

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        sess = self.sess()

        if path == "/api/product":
            ctype = self.headers.get('Content-Type', '')
            if 'multipart/form-data' in ctype:
                self.api_save_product_multipart(sess)
                return
        routes = {
            "/login": lambda: self.handle_login(),
            "/api/product": lambda: self.api_save_product(sess),
            "/api/product/delete": lambda: self.api_delete_product(sess),
            "/api/order": lambda: self.api_save_order(sess),
            "/api/order/delete": lambda: self.api_delete_order(sess),
        }
        handler = routes.get(path)
        if handler:
            handler()
        else:
            self.send_json({"error": "Not found"}, 404)

    def api_save_product_multipart(self, sess):
        if not sess or sess["role"] != "Администратор":
            self.send_json({"error": "forbidden"}, 403)
            return
        import shutil
        import uuid
        fs, _ = self.parse_multipart()
        if not fs:
            self.send_json({"error": "bad form"}, 400)
            return
        data = {k: fs.getvalue(k) for k in fs.keys() if k != 'photo_file'}
        # Обработка файла
        photo_file = fs['photo_file'] if 'photo_file' in fs else None
        static_img_dir = os.path.join(STATIC, 'images')
        os.makedirs(static_img_dir, exist_ok=True)
        old_photo = data.get('old_photo')
        new_photo_name = None
        if photo_file is not None and getattr(photo_file, 'filename', None):
            ext = os.path.splitext(photo_file.filename)[1].lower()
            if ext not in ['.jpg', '.jpeg', '.png', '.gif']:
                self.send_json({"error": "Недопустимый формат файла"}, 400)
                return
            new_photo_name = f"product_{uuid.uuid4().hex}{ext}"
            dest_path = os.path.join(static_img_dir, new_photo_name)
            with open(dest_path, 'wb') as f:
                shutil.copyfileobj(photo_file.file, f)
            data['photo'] = new_photo_name
            # Удалить старое фото, если оно есть и отличается
            if old_photo and old_photo not in ('', 'None') and old_photo != new_photo_name:
                old_path = os.path.join(static_img_dir, old_photo)
                if os.path.isfile(old_path):
                    try:
                        os.remove(old_path)
                    except Exception:
                        pass
        else:
            # Если не загружено новое фото, оставить старое
            data['photo'] = old_photo if old_photo not in ('', 'None') else None
        try:
            save_product(data)
            self.send_json({"ok": True})
        except Exception as e:
            self.send_json({"error": str(e)}, 400)

    def serve_static(self, rel: str) -> None:
        rel = rel.lstrip("/")
        full = os.path.normpath(os.path.join(STATIC, rel))
        # Security: reject path traversal
        if not full.startswith(
            os.path.normpath(STATIC) + os.sep
        ) and full != os.path.normpath(STATIC):
            self.send_response(403)
            self.end_headers()
            return
        if not os.path.isfile(full):
            self.send_response(404)
            self.end_headers()
            return
        mime, _ = mimetypes.guess_type(full)
        with open(full, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    def pg_login(self, sess) -> None:
        if sess:
            self.redirect("/products")
            return
        self.send_html(load_template("login.html"))

    def handle_login(self) -> None:
        form = self.body_form()
        login = form.get("login", "").strip()
        pw = form.get("password", "").strip()

        from database import get_db

        conn = get_db()
        row = conn.execute(
            """SELECT u.*, r.role_name FROM user u
               JOIN role r ON u.role_id = r.role_id
               WHERE u.login = ? AND u.password = ?""",
            (login, pw),
        ).fetchone()
        conn.close()

        if not row:
            self.send_json({"ok": False, "error": "Неверный логин или пароль"})
            return
        tok = create_session(row["user_id"], row["role_name"], row["full_name"])
        cookie = f"session={tok}; Path=/; HttpOnly; SameSite=Lax; Max-Age=86400"
        self.send_json({"ok": True}, set_cookie=cookie)

    def do_logout(self) -> None:
        self.redirect("/", set_cookie="session=; Path=/; Max-Age=0")

    def pg_products(self, sess, qs: dict) -> None:
        role = sess["role"] if sess else "Гость"
        can_filter = role in ("Менеджер", "Администратор")
        can_edit = role == "Администратор"

        search = qs.get("search", "")
        category = qs.get("category", "")
        sort = qs.get("sort", "")
        supplier = qs.get("supplier", "")

        products = fetch_products(search, category, sort, supplier)

        ctx = common_ctx(sess, "/products")
        ctx.update(
            {
                "filter_bar": (
                    filter_bar_html(search, category, sort, supplier)
                    if can_filter
                    else ""
                ),
                "toolbar": (
                    '<div class="toolbar"><button class="btn-primary"'
                    ' onclick="openProductModal(null)">＋ Добавить товар</button></div>'
                    if can_edit
                    else ""
                ),
                "products_table": products_table_html(products, can_edit),
                "product_modal": (
                    '<div id="product-modal" class="modal-overlay"'
                    ' style="display:none"></div>'
                    if can_edit
                    else ""
                ),
            }
        )
        self.send_html(render("products.html", **ctx))

    def pg_orders(self, sess) -> None:
        if not sess or sess["role"] not in ("Менеджер", "Администратор"):
            self.redirect("/products")
            return
        can_edit = sess["role"] == "Администратор"

        orders = fetch_orders()

        rows_html = ""
        for r in orders:
            act = ""
            if can_edit:
                act = (
                    f'<button class="btn-icon btn-edit"'
                    f' onclick="openOrderModal({r["order_id"]})">✏️</button> '
                    f'<button class="btn-icon btn-del"'
                    f' onclick="deleteOrder({r["order_id"]})">🗑️</button>'
                )
            sc = "status-done" if r["status"] == "Завершен" else "status-new"
            rows_html += (
                f"<tr>"
                f'<td class="td-num">{r["order_number"]}</td>'
                f'<td>{esc(r["order_date"] or "—")}</td>'
                f'<td>{esc(r["delivery_date"] or "—")}</td>'
                f'<td class="td-addr">{esc(r["address"] or "—")}</td>'
                f'<td>{esc(r["full_name"] or "—")}</td>'
                f'<td class="td-items">{esc(r["items_str"] or "—")}</td>'
                f'<td class="td-code">{esc(r["pickup_code"] or "—")}</td>'
                f'<td><span class="status-badge {sc}">{esc(r["status"])}</span></td>'
                f'<td class="td-act">{act}</td>'
                f"</tr>"
            )

        ctx = common_ctx(sess, "/orders")
        ctx.update(
            {
                "toolbar": (
                    '<div class="toolbar"><button class="btn-primary"'
                    ' onclick="openOrderModal(null)">＋ Добавить заказ</button></div>'
                    if can_edit
                    else ""
                ),
                "orders_rows": rows_html
                or '<tr><td colspan="9" class="empty-state">Заказов нет</td></tr>',
            }
        )
        self.send_html(render("orders.html", **ctx))

    def api_get_product(self, sess, qs: dict) -> None:
        pid = qs.get("id")
        if not pid:
            self.send_json({"error": "no id"}, 400)
            return
        p = fetch_product_by_id(int(pid))
        if not p:
            self.send_json({"error": "not found"}, 404)
            return
        self.send_json(
            {
                "product": dict(p),
                "categories": fetch_categories(),
                "suppliers": fetch_suppliers(),
                "manufacturers": fetch_manufacturers(),
            }
        )

    def api_save_product(self, sess) -> None:
        if not sess or sess["role"] != "Администратор":
            self.send_json({"error": "forbidden"}, 403)
            return
        try:
            save_product(self.body_json())
            self.send_json({"ok": True})
        except Exception as e:
            self.send_json({"error": str(e)}, 400)

    def api_delete_product(self, sess) -> None:
        if not sess or sess["role"] != "Администратор":
            self.send_json({"error": "forbidden"}, 403)
            return
        try:
            delete_product(int(self.body_json()["product_id"]))
            self.send_json({"ok": True})
        except Exception as e:
            self.send_json({"error": str(e)}, 400)

    def api_get_order(self, sess, qs: dict) -> None:
        if not sess or sess["role"] not in ("Менеджер", "Администратор"):
            self.send_json({"error": "forbidden"}, 403)
            return
        oid = qs.get("id")
        if not oid:
            self.send_json({"error": "no id"}, 400)
            return
        data = fetch_order_by_id(int(oid))
        if not data:
            self.send_json({"error": "not found"}, 404)
            return
        self.send_json(data)

    def api_save_order(self, sess) -> None:
        if not sess or sess["role"] != "Администратор":
            self.send_json({"error": "forbidden"}, 403)
            return
        try:
            save_order(self.body_json())
            self.send_json({"ok": True})
        except Exception as e:
            self.send_json({"error": str(e)}, 400)

    def api_delete_order(self, sess) -> None:
        if not sess or sess["role"] != "Администратор":
            self.send_json({"error": "forbidden"}, 403)
            return
        try:
            delete_order(int(self.body_json()["order_id"]))
            self.send_json({"ok": True})
        except Exception as e:
            self.send_json({"error": str(e)}, 400)

    def api_users(self, sess) -> None:
        if not sess:
            self.send_json([])
            return
        self.send_json(fetch_users())


PORT = 8000

if __name__ == "__main__":
    # Add src/ to path so `import database` works when run from any cwd
    import sys

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    print(f"Сервер запущен: http://localhost:{PORT}")
    # TODO: Add your server start logic here (socketserver removed)

    # Запуск обычного http-сервера
    http.server.test(HandlerClass=Handler, port=PORT)
