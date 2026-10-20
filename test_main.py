import unittest
from datetime import date, timedelta
from importlib import import_module, util

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

PACKAGE_NAME = "app" if util.find_spec("app") else "APP"
database = import_module(f"{PACKAGE_NAME}.core.database")
app_module = import_module(f"{PACKAGE_NAME}.main")
Base = database.Base
get_db = database.get_db
app = app_module.app


class BibliotecaApiTests(unittest.TestCase):
    def setUp(self):
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
            session = self.session_factory()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_24_casos_de_aceptacion_del_taller(self):
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
        top_books = self.client.get("/reportes/libros-mas-prestados?limite=3").json()
        self.assertLessEqual(len(top_books), 3)
        self.assertEqual(
            [row["total_prestamos"] for row in top_books],
            sorted(
                (row["total_prestamos"] for row in top_books), reverse=True
            ),
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
        self.assertEqual(self.client.get("/libros?skip=-1").status_code, 422)
        self.assertEqual(self.client.get("/libros?limit=0").status_code, 422)
        self.assertEqual(self.client.get("/libros?limit=101").status_code, 422)

    def test_interfaz_y_activos_en_rutas_de_pages(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('href="static/styles.css', response.text)
        self.assertIn('src="api-config.js', response.text)
        for view in ("libros", "autores", "categorias", "socios", "prestamos"):
            self.assertIn(f'data-view="{view}"', response.text)
        self.assertIn('id="record-fields" class="record-dialog-fields"', response.text)
        self.assertEqual(self.client.get("/api-config.js").status_code, 200)
        catalog = self.client.get("/catalogo.json")
        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(len(catalog.json()["autores"]), 40)
        self.assertEqual(len(catalog.json()["libros"]), 41)
        self.assertEqual(self.client.get("/static/app.js").status_code, 200)

    def test_patch_rechaza_nulos_en_campos_requeridos(self):
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
