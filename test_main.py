"""Pruebas de aceptación de la API usando SQLite aislado en memoria."""

import re
import unittest
from datetime import date, timedelta
from html.parser import HTMLParser
from importlib import import_module, util

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

PACKAGE_NAME = "app" if util.find_spec("app") else "APP"
database = import_module(f"{PACKAGE_NAME}.core.database")
app_module = import_module(f"{PACKAGE_NAME}.main")
Base = database.Base
get_db = database.get_db
app = app_module.app


class PageStructureParser(HTMLParser):
    """Recopila IDs y recursos HTML para validar el contrato de la interfaz."""

    def __init__(self):
        super().__init__()
        self.element_ids: set[str] = set()
        self.assets: set[str] = set()
        self.views: set[str] = set()

    def handle_starttag(self, tag, attrs):
        """Registra identificadores, recursos y vistas declaradas en cada etiqueta."""
        attributes = dict(attrs)
        if element_id := attributes.get("id"):
            self.element_ids.add(element_id)
        for attribute in ("src", "href"):
            value = attributes.get(attribute, "")
            if value.startswith(("static/", "api-config.js")):
                self.assets.add(value.split("?", maxsplit=1)[0])
        if tag == "button" and (view := attributes.get("data-view")):
            self.views.add(view)


class BibliotecaApiTests(unittest.TestCase):
    """Ejecuta cada caso con una base temporal y cliente FastAPI aislado."""

    def setUp(self):
        """Crea el esquema SQLite y sustituye la dependencia de base de datos."""
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.session_factory = sessionmaker(
            bind=self.engine, autoflush=False, autocommit=False
        )

        def override_get_db():
            """Abre y cierra una sesión de prueba por solicitud HTTP."""
            session = self.session_factory()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        """Libera el cliente, los overrides y el motor de prueba."""
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_24_casos_de_aceptacion_del_taller(self):
        """Comprueba reglas funcionales de catálogo, préstamos y reportes."""
        author_names = [
            ("Gabriel García Márquez", "Colombiana", 1927),
            ("Isabel Allende", "Chilena", 1942),
            ("George Orwell", "Británica", 1903),
        ]
        authors = [
            self.client.post(
                "/autores",
                json={
                    "nombre": name,
                    "nacionalidad": nationality,
                    "anio_nacimiento": birth_year,
                },
            ).json()
            for name, nationality, birth_year in author_names
        ]
        categories = [
            self.client.post("/categorias", json={"nombre": name}).json()
            for name in ("Novela", "Realismo Mágico", "Distopía", "Poesía")
        ]
        books = [
            {
                "titulo": "Cien años de soledad",
                "isbn": "9780307474728",
                "anio_publicacion": 1967,
                "ejemplares": 2,
                "autor_id": authors[0]["id"],
                "categoria_ids": [categories[0]["id"], categories[1]["id"]],
            },
            {
                "titulo": "El amor en los tiempos del cólera",
                "isbn": "9780307389732",
                "anio_publicacion": 1985,
                "ejemplares": 1,
                "autor_id": authors[0]["id"],
                "categoria_ids": [categories[0]["id"]],
            },
            {
                "titulo": "La casa de los espíritus",
                "isbn": "9780553383805",
                "anio_publicacion": 1982,
                "ejemplares": 2,
                "autor_id": authors[1]["id"],
                "categoria_ids": [categories[0]["id"], categories[1]["id"]],
            },
            {
                "titulo": "1984",
                "isbn": "9780451524935",
                "anio_publicacion": 1949,
                "ejemplares": 3,
                "autor_id": authors[2]["id"],
                "categoria_ids": [categories[0]["id"], categories[2]["id"]],
            },
        ]
        created_books = [
            self.client.post("/libros", json=book).json() for book in books
        ]
        members = [
            self.client.post(
                "/socios",
                json={"nombre": name, "email": email},
            ).json()
            for name, email in (
                ("Ana Torres", "ANA@example.com"),
                ("Luis Pérez", "luis@example.com"),
                ("Marta Ruiz", "marta@example.com"),
            )
        ]

        self.assertEqual(authors[0]["nombre"], "Gabriel García Márquez")
        self.assertEqual(members[0]["email"], "ana@example.com")

        # 1. Duplicate author is a conflict.
        self.assertEqual(
            self.client.post(
                "/autores",
                json={"nombre": "Gabriel García Márquez"},
            ).status_code,
            409,
        )
        # 2. ISBN must contain exactly 13 digits.
        invalid_isbn = {**books[0], "isbn": "123"}
        self.assertEqual(self.client.post("/libros", json=invalid_isbn).status_code, 422)
        # 3. Repeated category IDs are rejected.
        duplicate_categories = {**books[0], "isbn": "9780307474000", "categoria_ids": [1, 1]}
        self.assertEqual(
            self.client.post("/libros", json=duplicate_categories).status_code, 422
        )
        # 4. A missing author returns 404.
        missing_author = {**books[0], "isbn": "9780307474001", "autor_id": 99}
        self.assertEqual(
            self.client.post("/libros", json=missing_author).status_code, 404
        )
        # 5. Category and order filters can be combined.
        filtered = self.client.get("/libros?categoria_id=2&orden=-anio").json()
        self.assertEqual(len(filtered), 2)
        self.assertGreaterEqual(filtered[0]["anio_publicacion"], filtered[1]["anio_publicacion"])
        # 6. Author substring filter joins authors.
        self.assertEqual(len(self.client.get("/libros?autor=gabriel").json()), 2)
        # 7. First member borrows the only copy of book 2.
        active_loan = self.client.post(
            "/prestamos",
            json={"libro_id": 2, "socio_id": 1},
        )
        self.assertEqual(active_loan.status_code, 201)
        self.assertEqual(active_loan.json()["estado"], "activo")
        duplicate_loan = self.client.post(
            "/prestamos",
            json={"libro_id": 2, "socio_id": 1},
        )
        self.assertEqual(duplicate_loan.status_code, 409)
        # 8. No copy remains for a different member.
        unavailable = self.client.post(
            "/prestamos",
            json={"libro_id": 2, "socio_id": 2},
        )
        self.assertEqual(unavailable.status_code, 422)
        # 9. Available copies are calculated from open loans.
        self.assertEqual(self.client.get("/libros/2").json()["disponibles"], 0)
        # 10. Register an overdue loan from 20 days ago with a 7-day term.
        overdue_response = self.client.post(
            "/prestamos",
            json={
                "libro_id": 1,
                "socio_id": 2,
                "fecha_prestamo": (date.today() - timedelta(days=20)).isoformat(),
                "dias": 7,
            },
        )
        self.assertEqual(overdue_response.status_code, 201)
        overdue_loan = overdue_response.json()
        self.assertEqual(overdue_loan["estado"], "vencido")
        # 11. A member with an overdue loan cannot borrow another book.
        self.assertEqual(
            self.client.post(
                "/prestamos", json={"libro_id": 4, "socio_id": 2}
            ).status_code,
            422,
        )
        # 12. The overdue-loan report includes the overdue loan and late days.
        overdue_report = self.client.get("/reportes/prestamos-vencidos").json()
        overdue_report_item = next(
            row for row in overdue_report if row["prestamo_id"] == overdue_loan["id"]
        )
        self.assertEqual(overdue_report_item["dias_retraso"], 13)
        # 13. Returning late charges 0.50 for each late day.
        returned = self.client.post(
            f"/prestamos/{overdue_loan['id']}/devolucion",
            json={"fecha_devolucion": date.today().isoformat()},
        )
        self.assertEqual(returned.status_code, 200)
        self.assertEqual(returned.json()["multa"], 6.5)
        # 14. A returned loan cannot be returned again.
        self.assertEqual(
            self.client.post(
                f"/prestamos/{overdue_loan['id']}/devolucion",
                json={"fecha_devolucion": date.today().isoformat()},
            ).status_code,
            409,
        )
        # 15. A member cannot exceed three open loans.
        for book_id in (1, 3, 4):
            self.assertEqual(
                self.client.post(
                    "/prestamos",
                    json={"libro_id": book_id, "socio_id": 3},
                ).status_code,
                201,
            )
        self.assertEqual(
            self.client.post(
                "/prestamos", json={"libro_id": 2, "socio_id": 3}
            ).status_code,
            422,
        )
        # 16. Exemplars cannot be fewer than active loans.
        self.assertEqual(
            self.client.patch("/libros/4", json={"ejemplares": 0}).status_code,
            422,
        )
        # 17. An author with books cannot be deleted.
        self.assertEqual(self.client.delete("/autores/1").status_code, 409)
        # 18. A book with an open loan cannot be deleted.
        self.assertEqual(self.client.delete("/libros/2").status_code, 409)
        # 19. A member with only returned history is soft-deleted.
        self.assertEqual(self.client.delete("/socios/2").status_code, 204)
        self.assertFalse(self.client.get("/socios/2").json()["activo"])
        # 20. An inactive member cannot borrow.
        self.assertEqual(
            self.client.post(
                "/prestamos", json={"libro_id": 4, "socio_id": 2}
            ).status_code,
            422,
        )
        # 21. Categories with no books remain in reports.
        category_report = self.client.get("/reportes/categorias").json()
        poetry = next(row for row in category_report if row["nombre"] == "poesía")
        self.assertEqual(poetry["total_libros"], 0)
        # 22. Fine report includes the member with the late fine.
        fine_report = self.client.get("/reportes/socios-con-multas").json()
        self.assertEqual(len(fine_report), 1)
        self.assertEqual(fine_report[0]["nombre"], "Luis Pérez")
        self.assertEqual(fine_report[0]["total_multas"], 6.5)
        # 23. Top borrowed books are ordered by loan count.
        top_books = self.client.get("/reportes/libros-mas-prestados?limit=3").json()
        self.assertLessEqual(len(top_books), 3)
        self.assertEqual(
            [row["total_prestamos"] for row in top_books],
            sorted(
                (row["total_prestamos"] for row in top_books), reverse=True
            ),
        )
        self.assertEqual(
            self.client.get("/reportes/libros-mas-prestados?limite=3").json(),
            top_books,
        )
        # 24. Pagination returns distinct book pages.
        first_page = self.client.get("/libros?skip=0&limit=2").json()
        second_page = self.client.get("/libros?skip=2&limit=2").json()
        self.assertEqual((len(first_page), len(second_page)), (2, 2))
        self.assertFalse(
            {book["id"] for book in first_page}
            & {book["id"] for book in second_page}
        )

        self.assertEqual(len(created_books), 4)
        self.assertEqual(self.client.get("/reportes/resumen").status_code, 200)

    def test_validaciones_de_paginacion(self):
        """Rechaza límites de paginación fuera del rango permitido."""
        self.assertEqual(self.client.get("/libros?skip=-1").status_code, 422)
        self.assertEqual(self.client.get("/libros?limit=0").status_code, 422)
        self.assertEqual(self.client.get("/libros?limit=101").status_code, 422)
        self.assertEqual(
            self.client.get("/reportes/libros-mas-prestados?limit=101").status_code,
            422,
        )

    def test_primeras_diez_acciones_de_aceptacion(self):
        """Verifica las primeras diez acciones de aceptación con peticiones HTTP."""
        authors = [
            self.client.post(
                "/autores",
                json={"nombre": name},
            ).json()
            for name in (
                "Gabriel García Márquez",
                "Isabel Allende",
                "George Orwell",
            )
        ]
        categories = [
            self.client.post("/categorias", json={"nombre": name}).json()
            for name in ("Novela", "Realismo Mágico", "Distopía", "Poesía")
        ]
        books = [
            {
                "titulo": "Cien años de soledad",
                "isbn": "9780307474728",
                "anio_publicacion": 1967,
                "ejemplares": 2,
                "autor_id": authors[0]["id"],
                "categoria_ids": [categories[0]["id"], categories[1]["id"]],
            },
            {
                "titulo": "El amor en los tiempos del cólera",
                "isbn": "9780307389732",
                "anio_publicacion": 1985,
                "ejemplares": 1,
                "autor_id": authors[0]["id"],
                "categoria_ids": [categories[0]["id"]],
            },
            {
                "titulo": "La casa de los espíritus",
                "isbn": "9780553383805",
                "anio_publicacion": 1982,
                "ejemplares": 2,
                "autor_id": authors[1]["id"],
                "categoria_ids": [categories[0]["id"], categories[1]["id"]],
            },
            {
                "titulo": "1984",
                "isbn": "9780451524935",
                "anio_publicacion": 1949,
                "ejemplares": 3,
                "autor_id": authors[2]["id"],
                "categoria_ids": [categories[0]["id"], categories[2]["id"]],
            },
        ]
        for book in books:
            response = self.client.post("/libros", json=book)
            self.assertEqual(response.status_code, 201)
        members = [
            self.client.post(
                "/socios", json={"nombre": name, "email": email}
            ).json()
            for name, email in (
                ("Ana Torres", "ana@example.com"),
                ("Luis Pérez", "luis@example.com"),
            )
        ]

        # 1. Duplicate author is a conflict.
        self.assertEqual(
            self.client.post(
                "/autores", json={"nombre": "Gabriel García Márquez"}
            ).status_code,
            409,
        )
        # 2. Invalid ISBN is rejected.
        self.assertEqual(
            self.client.post(
                "/libros", json={**books[0], "isbn": "123"}
            ).status_code,
            422,
        )
        # 3. Duplicate category IDs are rejected.
        self.assertEqual(
            self.client.post(
                "/libros",
                json={
                    **books[0],
                    "isbn": "9780307474000",
                    "categoria_ids": [1, 1],
                },
            ).status_code,
            422,
        )
        # 4. A missing author returns 404.
        self.assertEqual(
            self.client.post(
                "/libros",
                json={**books[0], "isbn": "9780307474001", "autor_id": 99},
            ).status_code,
            404,
        )
        # 5. Category and descending-year filters return the expected books.
        filtered = self.client.get("/libros?categoria_id=2&orden=-anio").json()
        self.assertEqual(
            [book["anio_publicacion"] for book in filtered], [1982, 1967]
        )
        # 6. Author substring filter returns both books by García Márquez.
        self.assertEqual(len(self.client.get("/libros?autor=gabriel").json()), 2)
        # 7. The first member can borrow book 2.
        loan = self.client.post(
            "/prestamos",
            json={"libro_id": 2, "socio_id": members[0]["id"]},
        )
        self.assertEqual(loan.status_code, 201)
        self.assertEqual(loan.json()["estado"], "activo")
        # 8. The second member cannot borrow the unavailable copy.
        self.assertEqual(
            self.client.post(
                "/prestamos",
                json={"libro_id": 2, "socio_id": members[1]["id"]},
            ).status_code,
            422,
        )
        # 9. No copies remain available for book 2.
        self.assertEqual(
            self.client.get("/libros/2").json()["disponibles"], 0
        )
        # 10. A loan from 20 days ago with a 7-day term is overdue.
        overdue = self.client.post(
            "/prestamos",
            json={
                "libro_id": 1,
                "socio_id": members[1]["id"],
                "fecha_prestamo": (date.today() - timedelta(days=20)).isoformat(),
                "dias": 7,
            },
        )
        self.assertEqual(overdue.status_code, 201)
        self.assertEqual(overdue.json()["estado"], "vencido")

    def test_recursos_inexistentes_responden_404_json(self):
        """Los endpoints de detalle y sus relaciones informan los recursos ausentes."""
        expected_details = {
            "/autores/999": "Autor no encontrado",
            "/autores/999/libros": "Autor no encontrado",
            "/categorias/999": "Categoría no encontrada",
            "/libros/999": "Libro no encontrado",
            "/socios/999": "Socio no encontrado",
            "/socios/999/prestamos": "Socio no encontrado",
            "/prestamos/999": "Préstamo no encontrado",
        }
        for path, detail in expected_details.items():
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json(), {"detail": detail})

    def test_formato_de_errores_de_validacion_y_respuesta_204(self):
        """Valida el formato Pydantic para 422 y la respuesta vacía para 204."""
        invalid_book = self.client.post(
            "/libros",
            json={
                "titulo": "Libro de prueba",
                "isbn": "123",
                "anio_publicacion": 2020,
                "ejemplares": 1,
                "autor_id": 1,
                "categoria_ids": [1],
            },
        )
        self.assertEqual(invalid_book.status_code, 422)
        validation_errors = invalid_book.json()["detail"]
        isbn_error = next(
            error for error in validation_errors if error["loc"] == ["body", "isbn"]
        )
        self.assertIsInstance(isbn_error["msg"], str)

        created_category = self.client.post(
            "/categorias", json={"nombre": "Pruebas"}
        )
        self.assertEqual(created_category.status_code, 201)
        deleted_category = self.client.delete(
            f"/categorias/{created_category.json()['id']}"
        )
        self.assertEqual(deleted_category.status_code, 204)
        self.assertEqual(deleted_category.content, b"")

    def test_cada_reporte_ejecuta_una_consulta_sql(self):
        """Comprueba que cada endpoint de reporte ejecuta una sola sentencia."""
        statements = []

        def capture_statement(
            connection, cursor, statement, parameters, context, executemany
        ):
            statements.append(statement)

        event.listen(self.engine, "before_cursor_execute", capture_statement)
        try:
            for path in (
                "/reportes/libros-mas-prestados",
                "/reportes/categorias",
                "/reportes/prestamos-vencidos",
                "/reportes/socios-con-multas",
                "/reportes/autores",
                "/reportes/resumen",
            ):
                with self.subTest(path=path):
                    statements.clear()
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(len(statements), 1)
        finally:
            event.remove(self.engine, "before_cursor_execute", capture_statement)

    def test_interfaz_y_activos_en_rutas_de_pages(self):
        """Verifica la interfaz, Swagger y los recursos estáticos publicados."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        page = PageStructureParser()
        page.feed(response.text)
        self.assertEqual(
            page.views, {"libros", "autores", "categorias", "socios", "prestamos"}
        )
        self.assertEqual(
            page.assets,
            {"static/styles.css", "api-config.js", "static/app.js"},
        )
        app_script = self.client.get("/static/app.js")
        self.assertEqual(app_script.status_code, 200)
        referenced_ids = set(
            re.findall(
                r"""querySelector(?:All)?\(["']#([\w-]+)""",
                app_script.text,
            )
        )
        self.assertTrue(
            referenced_ids <= page.element_ids,
            f"Selectores sin elemento HTML: {sorted(referenced_ids - page.element_ids)}",
        )
        self.assertTrue(
            {
                "books-view",
                "management-view",
                "book-dialog",
                "record-dialog",
                "book-list",
                "management-list",
                "record-fields",
            } <= page.element_ids
        )
        self.assertEqual(self.client.get("/docs").status_code, 200)
        documented_paths = self.client.get("/openapi.json").json()["paths"]
        self.assertIn("/reportes/resumen", documented_paths)
        self.assertEqual(
            self.client.get("/static/styles.css").status_code,
            200,
        )
        self.assertEqual(
            self.client.get("/api-config.js").headers["content-type"],
            "application/javascript",
        )
        catalog = self.client.get("/catalogo.json")
        self.assertEqual(catalog.status_code, 200)
        catalog_data = catalog.json()
        self.assertEqual(len(catalog_data["autores"]), 40)
        self.assertEqual(len(catalog_data["libros"]), 41)
        author_ids = {author["id"] for author in catalog_data["autores"]}
        category_ids = {category["id"] for category in catalog_data["categorias"]}
        self.assertTrue(
            all(book["autor"]["id"] in author_ids for book in catalog_data["libros"])
        )
        self.assertTrue(
            all(
                category["id"] in category_ids
                for book in catalog_data["libros"]
                for category in book["categorias"]
            )
        )

    def test_patch_rechaza_nulos_en_campos_requeridos(self):
        """Impide anular campos obligatorios mediante actualizaciones parciales."""
        self.assertEqual(
            self.client.patch("/autores/1", json={"nombre": None}).status_code,
            422,
        )
        self.assertEqual(
            self.client.patch("/categorias/1", json={"nombre": None}).status_code,
            422,
        )
        self.assertEqual(
            self.client.patch("/libros/1", json={"titulo": None}).status_code,
            422,
        )
        self.assertEqual(
            self.client.patch("/socios/1", json={"nombre": None}).status_code,
            422,
        )

    def test_categorias_duplicadas_y_categoria_se_elimina_de_libros(self):
        """Protege nombres únicos y elimina asociaciones sin borrar los libros."""
        author = self.client.post(
            "/autores", json={"nombre": "Autor de prueba"}
        ).json()
        first = self.client.post("/categorias", json={"nombre": "Ficción"}).json()
        conflict = self.client.post("/categorias", json={"nombre": "FICCIÓN"})
        self.assertEqual(conflict.status_code, 409)
        book = self.client.post(
            "/libros",
            json={
                "titulo": "Prueba",
                "isbn": "1234567890123",
                "anio_publicacion": 2020,
                "ejemplares": 1,
                "autor_id": author["id"],
                "categoria_ids": [first["id"]],
            },
        ).json()
        self.assertEqual(self.client.delete(f"/categorias/{first['id']}").status_code, 204)
        self.assertEqual(self.client.get(f"/libros/{book['id']}").json()["categorias"], [])

    def test_prestamos_abiertos_se_pueden_editar_y_eliminar(self):
        """Permite modificar o borrar préstamos abiertos, nunca los devueltos."""
        author = self.client.post(
            "/autores", json={"nombre": "Autora de préstamos"}
        ).json()
        category = self.client.post(
            "/categorias", json={"nombre": "Aventura"}
        ).json()
        book = self.client.post(
            "/libros",
            json={
                "titulo": "Libro prestado",
                "isbn": "1234567890123",
                "anio_publicacion": 2020,
                "ejemplares": 2,
                "autor_id": author["id"],
                "categoria_ids": [category["id"]],
            },
        ).json()
        members = [
            self.client.post(
                "/socios", json={"nombre": name, "email": email}
            ).json()
            for name, email in (
                ("Socio Uno", "socio1@example.com"),
                ("Socio Dos", "socio2@example.com"),
            )
        ]
        loans = [
            self.client.post(
                "/prestamos",
                json={"libro_id": book["id"], "socio_id": member["id"]},
            ).json()
            for member in members
        ]

        new_due_date = date.today() + timedelta(days=21)
        updated = self.client.patch(
            f"/prestamos/{loans[0]['id']}",
            json={"fecha_limite": new_due_date.isoformat()},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["fecha_limite"], new_due_date.isoformat())
        self.assertEqual(
            self.client.patch(
                f"/prestamos/{loans[0]['id']}",
                json={"fecha_limite": (date.today() - timedelta(days=1)).isoformat()},
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.delete(f"/prestamos/{loans[1]['id']}").status_code, 204
        )

        self.assertEqual(
            self.client.post(
                f"/prestamos/{loans[0]['id']}/devolucion",
                json={"fecha_devolucion": date.today().isoformat()},
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.patch(
                f"/prestamos/{loans[0]['id']}",
                json={"fecha_limite": new_due_date.isoformat()},
            ).status_code,
            409,
        )
        self.assertEqual(
            self.client.delete(f"/prestamos/{loans[0]['id']}").status_code, 409
        )


if __name__ == "__main__":
    unittest.main()
