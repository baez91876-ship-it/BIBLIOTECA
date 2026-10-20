const bookList = document.querySelector("#book-list");
const emptyState = document.querySelector("#empty-state");
const emptyTitle = document.querySelector("#empty-title");
const emptyDescription = document.querySelector("#empty-description");
const dialog = document.querySelector("#book-dialog");
const form = document.querySelector("#book-form");
const notice = document.querySelector("#notice");
const searchInput = document.querySelector("#search");
let books = [];
let authors = [];
let categories = [];
let editingBookId = null;

function showNotice(message) {
  notice.textContent = message;
  notice.hidden = false;
}

function hideNotice() {
  notice.hidden = true;
  notice.textContent = "";
}

async function apiRequest(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    let detail = `Error ${response.status}: no se pudo completar la operación.`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) {
        detail = body.detail.map((item) => item.msg).join(" ");
      }
    } catch {
      // Keep the status-based message if the response is not JSON.
    }
    throw new Error(detail);
  }
  if (response.status === 204) return null;
  return response.json();
}

function createCell(text, className = "") {
  const cell = document.createElement("td");
  if (className) cell.className = className;
  cell.textContent = text;
  return cell;
}

function renderBooks() {
  const query = searchInput.value.trim().toLocaleLowerCase("es");
  const visibleBooks = books.filter((book) =>
    `${book.titulo} ${book.autor.nombre}`.toLocaleLowerCase("es").includes(query),
  );

  bookList.replaceChildren();
  for (const book of visibleBooks) {
    const row = document.createElement("tr");
    const titleCell = document.createElement("td");
    const title = document.createElement("div");
    title.className = "book-title";
    const cover = document.createElement("span");
    cover.className = "book-cover";
    cover.setAttribute("aria-hidden", "true");
    cover.textContent = book.titulo.trim().charAt(0).toLocaleUpperCase("es") || "L";
    const titleText = document.createElement("span");
    titleText.textContent = book.titulo;
    title.append(cover, titleText);
    titleCell.append(title);

    const actions = document.createElement("td");
    const actionGroup = document.createElement("div");
    actionGroup.className = "row-actions";
    const editButton = document.createElement("button");
    editButton.type = "button";
    editButton.className = "icon-button";
    editButton.dataset.action = "edit";
    editButton.dataset.id = String(book.id);
    editButton.setAttribute("aria-label", `Editar ${book.titulo}`);
    editButton.title = "Editar libro";
    editButton.textContent = "✎";
    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "icon-button delete-button";
    deleteButton.dataset.action = "delete";
    deleteButton.dataset.id = String(book.id);
    deleteButton.setAttribute("aria-label", `Eliminar ${book.titulo}`);
    deleteButton.title = "Eliminar libro";
    deleteButton.textContent = "⌫";
    actionGroup.append(editButton, deleteButton);
    actions.append(actionGroup);

    row.append(
      titleCell,
      createCell(book.autor.nombre),
      createCell(String(book.anio_publicacion)),
      createCell(book.isbn),
      createCell(String(book.ejemplares)),
      createCell(book.categorias.map((category) => category.nombre).join(", ") || "—"),
      actions,
    );
    bookList.append(row);
  }

  document.querySelector("#total-count").textContent = String(books.length);
  document.querySelector("#copy-count").textContent = String(
    books.reduce((total, book) => total + book.ejemplares, 0),
  );
  document.querySelector("#category-count").textContent = String(categories.length);
  document.querySelector("#result-count").textContent =
    `${visibleBooks.length} ${visibleBooks.length === 1 ? "libro" : "libros"}`;

  emptyState.hidden = visibleBooks.length !== 0;
  if (books.length === 0) {
    emptyTitle.textContent = "Tu próxima lectura empieza aquí";
    emptyDescription.textContent = "Añade un libro para comenzar tu colección.";
    document.querySelector("#empty-add-book").hidden = false;
  } else {
    emptyTitle.textContent = "No encontramos ese libro";
    emptyDescription.textContent = "Prueba con otro título o nombre de autor.";
    document.querySelector("#empty-add-book").hidden = true;
  }
}

async function loadBooks() {
  hideNotice();
  try {
    [books, authors, categories] = await Promise.all([
      apiRequest("/libros?limit=100"),
      apiRequest("/autores?limit=100"),
      apiRequest("/categorias?limit=100"),
    ]);
    renderBooks();
  } catch (error) {
    showNotice(`No se pudo cargar la colección: ${error.message}`);
  }
}

function openDialog(book = null) {
  editingBookId = book?.id ?? null;
  form.reset();
  document.querySelector("#dialog-title").textContent = book ? "Editar libro" : "Añadir libro";
  document.querySelector("#save-book").textContent = book ? "Guardar cambios" : "Guardar libro";
  document.querySelector("#title").value = book?.titulo ?? "";
  document.querySelector("#isbn").value = book?.isbn ?? "";
  const authorSelect = document.querySelector("#author");
  authorSelect.replaceChildren(new Option("Selecciona un autor", ""));
  for (const author of authors) {
    authorSelect.add(new Option(author.nombre, String(author.id)));
  }
  authorSelect.value = book ? String(book.autor.id) : "";
  document.querySelector("#year").value = book?.anio_publicacion ?? "";
  document.querySelector("#copies").value = book?.ejemplares ?? 1;
  const selectedCategoryIds = new Set(
    (book?.categorias ?? []).map((category) => String(category.id)),
  );
  const categorySelect = document.querySelector("#categories");
  categorySelect.replaceChildren();
  for (const category of categories) {
    const option = new Option(category.nombre, String(category.id));
    option.selected = selectedCategoryIds.has(option.value);
    categorySelect.add(option);
  }
  document.querySelector("#form-error").hidden = true;
  dialog.showModal();
  document.querySelector("#title").focus();
}

document.querySelector("#add-book").addEventListener("click", () => openDialog());
document.querySelector("#empty-add-book").addEventListener("click", () => openDialog());
document.querySelector("#close-dialog").addEventListener("click", () => dialog.close());
document.querySelector("#cancel-dialog").addEventListener("click", () => dialog.close());
document.querySelector("#refresh-books").addEventListener("click", loadBooks);
searchInput.addEventListener("input", renderBooks);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const saveButton = document.querySelector("#save-book");
  const errorMessage = document.querySelector("#form-error");
  const payload = {
    titulo: document.querySelector("#title").value.trim(),
    isbn: document.querySelector("#isbn").value.trim(),
    anio_publicacion: Number(document.querySelector("#year").value),
    ejemplares: Number(document.querySelector("#copies").value),
    autor_id: Number(document.querySelector("#author").value),
    categoria_ids: Array.from(
      document.querySelector("#categories").selectedOptions,
      (option) => Number(option.value),
    ),
  };
  saveButton.disabled = true;
  errorMessage.hidden = true;
  try {
    const path = editingBookId === null ? "/libros" : `/libros/${editingBookId}`;
    await apiRequest(path, {
      method: editingBookId === null ? "POST" : "PATCH",
      body: JSON.stringify(payload),
    });
    dialog.close();
    await loadBooks();
  } catch (error) {
    errorMessage.textContent = error.message;
    errorMessage.hidden = false;
  } finally {
    saveButton.disabled = false;
  }
});

bookList.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const book = books.find((item) => item.id === Number(button.dataset.id));
  if (!book) return;

  if (button.dataset.action === "edit") {
    openDialog(book);
    return;
  }
  if (!window.confirm(`¿Eliminar "${book.titulo}" de la colección?`)) return;
  hideNotice();
  try {
    await apiRequest(`/libros/${book.id}`, { method: "DELETE" });
    await loadBooks();
  } catch (error) {
    showNotice(`No se pudo eliminar el libro: ${error.message}`);
  }
});

loadBooks();
