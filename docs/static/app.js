// Estado de la interfaz y referencias a los elementos principales del DOM.
const bookList = document.querySelector("#book-list");
const emptyState = document.querySelector("#empty-state");
const emptyTitle = document.querySelector("#empty-title");
const emptyDescription = document.querySelector("#empty-description");
const dialog = document.querySelector("#book-dialog");
const form = document.querySelector("#book-form");
const notice = document.querySelector("#notice");
const searchInput = document.querySelector("#search");
const booksView = document.querySelector("#books-view");
const managementView = document.querySelector("#management-view");
const managementList = document.querySelector("#management-list");
const managementSearch = document.querySelector("#management-search");
const recordDialog = document.querySelector("#record-dialog");
const recordForm = document.querySelector("#record-form");
const recordFields = document.querySelector("#record-fields");
const recordError = document.querySelector("#record-error");

let books = [];
let authors = [];
let categories = [];
let members = [];
let loans = [];
let editingBookId = null;
let activeView = "libros";
let activeRecordId = null;
const apiBaseUrl = (window.BIBLIOTECA_API_URL || "").replace(/\/+$/, "");
const pagesApiNotConfigured =
  window.location.hostname.endsWith(".github.io") && !apiBaseUrl;

// Metadatos de tablas y formularios para las pantallas de administración.
const resources = {
  autores: {
    title: "Autores",
    singular: "autor",
    endpoint: "/autores",
    records: () => authors,
    columns: [
      ["Nombre", (item) => item.nombre],
      ["Nacionalidad", (item) => item.nacionalidad],
      ["Nacimiento", (item) => item.anio_nacimiento],
    ],
    fields: [
      { name: "nombre", label: "Nombre", type: "text", required: true, maxLength: 100 },
      { name: "nacionalidad", label: "Nacionalidad", type: "text", maxLength: 60 },
      { name: "anio_nacimiento", label: "Año de nacimiento", type: "number", min: 1000, max: new Date().getFullYear() },
    ],
  },
  categorias: {
    title: "Categorías",
    singular: "categoría",
    endpoint: "/categorias",
    records: () => categories,
    columns: [
      ["Nombre", (item) => item.nombre],
      ["Descripción", (item) => item.descripcion],
    ],
    fields: [
      { name: "nombre", label: "Nombre", type: "text", required: true, minLength: 3, maxLength: 50 },
      { name: "descripcion", label: "Descripción", type: "text", maxLength: 200 },
    ],
  },
  socios: {
    title: "Socios",
    singular: "socio",
    endpoint: "/socios",
    records: () => members,
    columns: [
      ["Nombre", (item) => item.nombre],
      ["Correo", (item) => item.email],
      ["Teléfono", (item) => item.telefono],
      ["Estado", (item) => item.activo ? "Activo" : "Inactivo"],
      ["Fecha de alta", (item) => new Date(item.fecha_alta).toLocaleDateString("es")],
    ],
    fields: [
      { name: "nombre", label: "Nombre", type: "text", required: true, minLength: 2, maxLength: 100 },
      { name: "email", label: "Correo electrónico", type: "email", required: true, maxLength: 150 },
      { name: "telefono", label: "Teléfono", type: "tel", minLength: 7, maxLength: 15 },
      { name: "activo", label: "Estado", type: "boolean", required: true, options: [["true", "Activo"], ["false", "Inactivo"]] },
    ],
  },
  prestamos: {
    title: "Préstamos",
    singular: "préstamo",
    endpoint: "/prestamos",
    records: () => loans,
    columns: [
      ["Libro", (item) => item.libro.titulo],
      ["Socio", (item) => item.socio.nombre],
      ["Préstamo", (item) => item.fecha_prestamo],
      ["Fecha límite", (item) => item.fecha_limite],
      ["Estado", (item) => item.estado],
      ["Multa", (item) => `$${Number(item.multa).toFixed(2)}`],
    ],
    fields: [
      { name: "libro_id", label: "Libro", type: "reference", source: "libros", required: true },
      { name: "socio_id", label: "Socio activo", type: "reference", source: "socios", required: true },
      { name: "fecha_prestamo", label: "Fecha del préstamo (opcional)", type: "date" },
      { name: "dias", label: "Duración en días", type: "number", min: 1, max: 30, value: 14, required: true },
    ],
    editFields: [
      { name: "fecha_limite", label: "Fecha límite", type: "date", required: true },
    ],
  },
};

// GitHub Pages puede servir el catálogo local cuando no se configura una API.
if (pagesApiNotConfigured) {
  document.querySelector("#connection-label").textContent = "Catálogo estático";
  document.querySelector("#database-label").textContent = "Solo lectura";
  document.querySelector("#add-book").hidden = true;
  document.querySelector("#refresh-books").hidden = true;
  for (const link of document.querySelectorAll(".nav-link[data-view]:not([data-view='libros'])")) {
    link.hidden = true;
  }
  document.querySelector("#api-docs").hidden = true;
} else {
  document.querySelector("#api-docs-frame").src = `${apiBaseUrl}/docs`;
}

function showNotice(message) {
  // Presenta avisos de error o de solo lectura junto a la colección.
  notice.textContent = message;
  notice.classList.toggle("read-only-notice", pagesApiNotConfigured);
  notice.hidden = false;
}

function hideNotice() {
  // Limpia el aviso visible para que no persista tras una nueva carga.
  notice.hidden = true;
  notice.textContent = "";
  notice.classList.remove("read-only-notice");
}

async function apiRequest(path, options = {}) {
  // Centraliza errores HTTP y evita solicitudes de escritura en Pages estático.
  if (pagesApiNotConfigured) {
    throw new Error(
      "La interfaz está publicada, pero la API aún no está desplegada. Configura su URL en api-config.js.",
    );
  }
  const response = await fetch(`${apiBaseUrl}${path}`, {
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

async function listAll(path) {
  // Recorre todas las páginas de 100 registros para cargar colecciones completas.
  const records = [];
  for (let skip = 0; ; skip += 100) {
    const page = await apiRequest(`${path}?skip=${skip}&limit=100`);
    records.push(...page);
    if (page.length < 100) return records;
  }
}

function createCell(text, className = "") {
  // Usa textContent para insertar los valores de la API como texto, no como HTML.
  const cell = document.createElement("td");
  if (className) cell.className = className;
  cell.textContent = text ?? "—";
  return cell;
}

function localDateString(date = new Date()) {
  // Serializa la fecha local sin que la conversión UTC cambie el día.
  const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return localDate.toISOString().slice(0, 10);
}

function renderBooks() {
  // Filtra y reconstruye filas y estadísticas de la vista del catálogo.
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
    if (!pagesApiNotConfigured) {
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
    }

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
  document.querySelector("#author-count").textContent = String(authors.length);
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
  // Carga el catálogo estático o combina los recursos de la API en vivo.
  hideNotice();
  try {
    if (pagesApiNotConfigured) {
      const response = await fetch("catalogo.json");
      if (!response.ok) {
        throw new Error(`Error ${response.status}: no se pudo cargar el catálogo.`);
      }
      ({ libros: books, autores: authors, categorias: categories } =
        await response.json());
      renderBooks();
      showNotice(
        `Catálogo estático: ${books.length} libros de ${authors.length} autores. Vista de solo lectura; los cambios requieren una API pública.`,
      );
      return;
    }
    [books, authors, categories] = await Promise.all([
      listAll("/libros"),
      listAll("/autores"),
      listAll("/categorias"),
    ]);
    renderBooks();
  } catch (error) {
    showNotice(`No se pudo cargar la colección: ${error.message}`);
  }
}

async function loadResource(resourceName) {
  // Carga el recurso seleccionado y sus dependencias para los formularios.
  const config = resources[resourceName];
  const managementNotice = document.querySelector("#management-notice");
  managementNotice.hidden = true;
  try {
    if (resourceName === "prestamos") {
      [loans, books, members] = await Promise.all([
        listAll(config.endpoint),
        listAll("/libros"),
        listAll("/socios"),
      ]);
    } else {
      const records = await listAll(config.endpoint);
      if (resourceName === "autores") authors = records;
      if (resourceName === "categorias") categories = records;
      if (resourceName === "socios") members = records;
    }
    renderManagement(resourceName);
  } catch (error) {
    managementNotice.textContent = `No se pudieron cargar ${config.title.toLocaleLowerCase("es")}: ${error.message}`;
    managementNotice.hidden = false;
  }
}

function setView(viewName) {
  // Sincroniza navegación, vista activa y datos que deben actualizarse.
  activeView = viewName;
  booksView.hidden = viewName !== "libros";
  managementView.hidden = viewName === "libros";
  for (const link of document.querySelectorAll(".nav-link[data-view]")) {
    const selected = link.dataset.view === viewName;
    link.classList.toggle("active", selected);
    if (selected) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  if (viewName === "libros") {
    loadBooks();
  } else {
    managementSearch.value = "";
    loadResource(viewName);
  }
}

function renderManagement(resourceName) {
  // Genera encabezados, filas, acciones y estado vacío para cada recurso.
  const config = resources[resourceName];
  const records = config.records();
  const query = managementSearch.value.trim().toLocaleLowerCase("es");
  const visibleRecords = records.filter((record) =>
    JSON.stringify(record).toLocaleLowerCase("es").includes(query),
  );
  const head = document.querySelector("#management-head");
  head.replaceChildren();
  for (const [label] of config.columns) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = label;
    head.append(cell);
  }
  const actionsHeading = document.createElement("th");
  actionsHeading.scope = "col";
  actionsHeading.className = "management-actions";
  actionsHeading.innerHTML = '<span class="visually-hidden">Acciones</span>';
  head.append(actionsHeading);

  managementList.replaceChildren();
  for (const record of visibleRecords) {
    const row = document.createElement("tr");
    for (const [, getValue] of config.columns) {
      row.append(createCell(String(getValue(record) ?? "—")));
    }
    const actions = document.createElement("td");
    actions.className = "management-actions";
    const actionGroup = document.createElement("div");
    actionGroup.className = "row-actions";
    if (record.estado !== "devuelto") {
      actionGroup.append(
        createActionButton("edit", record.id, `Editar ${config.singular}`, "✎"),
      );
      actionGroup.append(
        createActionButton("delete", record.id, `Eliminar ${config.singular}`, "⌫", true),
      );
      if (resourceName === "prestamos") {
        actionGroup.append(
          createActionButton("return", record.id, "Registrar devolución", "✓"),
        );
      }
    } else if (resourceName !== "prestamos") {
      actionGroup.append(
        createActionButton("edit", record.id, `Editar ${config.singular}`, "✎"),
      );
      actionGroup.append(
        createActionButton("delete", record.id, `Eliminar ${config.singular}`, "⌫", true),
      );
    }
    actions.append(actionGroup);
    row.append(actions);
    managementList.append(row);
  }

  document.querySelector("#management-title").firstChild.textContent = config.title;
  document.querySelector("#management-table-title").textContent = `Todos los registros`;
  document.querySelector("#management-table-description").textContent =
    `Administra ${config.title.toLocaleLowerCase("es")} de la biblioteca.`;
  document.querySelector("#management-description").textContent =
    `Crea, consulta y actualiza ${config.title.toLocaleLowerCase("es")}.`;
  document.querySelector("#add-record").innerHTML =
    `<span aria-hidden="true">＋</span> Añadir ${config.singular}`;
  document.querySelector("#management-count").textContent =
    `${visibleRecords.length} ${visibleRecords.length === 1 ? config.singular : `${config.singular}s`}`;
  document.querySelector("#management-empty-title").textContent =
    records.length ? "No encontramos registros" : `Aún no hay ${config.title.toLocaleLowerCase("es")}`;
  document.querySelector("#management-empty-description").textContent =
    records.length ? "Prueba con otro término de búsqueda." : `Añade el primer ${config.singular}.`;
  document.querySelector("#management-empty").hidden = visibleRecords.length !== 0;
  document.querySelector("#add-record").disabled =
    resourceName === "prestamos" && (books.length === 0 || !members.some((member) => member.activo));
}

function createActionButton(action, id, label, symbol, destructive = false) {
  // Construye un botón de acción con etiqueta accesible e ID del registro.
  const button = document.createElement("button");
  button.type = "button";
  button.className = `icon-button${destructive ? " delete-button" : ""}`;
  button.dataset.action = action;
  button.dataset.id = String(id);
  button.setAttribute("aria-label", label);
  button.title = label;
  button.textContent = symbol;
  return button;
}

function openBookDialog(book = null) {
  // Inicializa el formulario del libro con autores y categorías disponibles.
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

function openRecordDialog(record = null) {
  // Genera campos dinámicos según el recurso y el modo de creación o edición.
  const config = resources[activeView];
  activeRecordId = record?.id ?? null;
  const fields = activeRecordId !== null && config.editFields
    ? config.editFields
    : config.fields;
  recordFields.replaceChildren();
  document.querySelector("#record-dialog-title").textContent =
    `${record ? "Editar" : "Añadir"} ${config.singular}`;
  document.querySelector("#save-record").textContent =
    record ? "Guardar cambios" : `Guardar ${config.singular}`;
  recordError.hidden = true;

  for (const field of fields) {
    const label = document.createElement("label");
    const input = field.type === "reference" || field.type === "boolean"
      ? document.createElement("select")
      : document.createElement("input");
    input.id = `record-${field.name}`;
    input.name = field.name;
    input.required = Boolean(field.required);
    if (field.type === "reference" || field.type === "boolean") {
      const placeholder = new Option(`Selecciona ${field.label.toLocaleLowerCase("es")}`, "");
      input.add(placeholder);
      const options = field.type === "boolean"
        ? field.options
        : (field.source === "libros"
          ? books.map((book) => [String(book.id), book.titulo])
          : members.filter((member) => member.activo).map((member) => [String(member.id), member.nombre]));
      for (const [value, text] of options) input.add(new Option(text, value));
    } else {
      input.type = field.type;
      if (field.min !== undefined) input.min = String(field.min);
      if (field.max !== undefined) input.max = String(field.max);
      if (field.minLength !== undefined) input.minLength = field.minLength;
      if (field.maxLength !== undefined) input.maxLength = field.maxLength;
      if (field.value !== undefined) input.value = String(field.value);
    }
    if (record && record[field.name] !== undefined && record[field.name] !== null) {
      input.value = String(record[field.name]);
    }
    label.htmlFor = input.id;
    label.textContent = field.label;
    recordFields.append(label, input);
  }
  recordDialog.showModal();
  recordFields.querySelector("input, select")?.focus();
}

function buildRecordPayload(fields) {
  // Convierte los valores de formulario a los tipos que espera la API.
  const payload = {};
  for (const field of fields) {
    const value = document.querySelector(`#record-${field.name}`).value.trim();
    if (value === "") continue;
    if (field.type === "number" || field.type === "reference") {
      payload[field.name] = Number(value);
    } else if (field.type === "boolean") {
      payload[field.name] = value === "true";
    } else {
      payload[field.name] = value;
    }
  }
  return payload;
}

// Enlaces de la vista de libros y envío de su formulario.
document.querySelector("#add-book").addEventListener("click", () => openBookDialog());
document.querySelector("#empty-add-book").addEventListener("click", () => openBookDialog());
document.querySelector("#close-dialog").addEventListener("click", () => dialog.close());
document.querySelector("#cancel-dialog").addEventListener("click", () => dialog.close());
document.querySelector("#refresh-books").addEventListener("click", loadBooks);
searchInput.addEventListener("input", renderBooks);

form.addEventListener("submit", async (event) => {
  // Envía el libro nuevo o actualizado y mantiene el error en el diálogo.
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
  // Delegación de acciones para editar o eliminar filas del catálogo.
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const book = books.find((item) => item.id === Number(button.dataset.id));
  if (!book) return;

  if (button.dataset.action === "edit") {
    openBookDialog(book);
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

// Navegación y eventos compartidos de las pantallas de administración.
document.querySelectorAll(".nav-link[data-view]").forEach((link) => {
  link.addEventListener("click", () => setView(link.dataset.view));
});
document.querySelector("#add-record").addEventListener("click", () => openRecordDialog());
document.querySelector("#refresh-records").addEventListener("click", () => loadResource(activeView));
managementSearch.addEventListener("input", () => renderManagement(activeView));
document.querySelector("#close-record-dialog").addEventListener("click", () => recordDialog.close());
document.querySelector("#cancel-record-dialog").addEventListener("click", () => recordDialog.close());

recordForm.addEventListener("submit", async (event) => {
  // Guarda altas y cambios de los recursos administrados desde el formulario dinámico.
  event.preventDefault();
  const config = resources[activeView];
  const fields = activeRecordId !== null && config.editFields ? config.editFields : config.fields;
  const saveButton = document.querySelector("#save-record");
  saveButton.disabled = true;
  recordError.hidden = true;
  try {
    const path = activeRecordId === null
      ? config.endpoint
      : `${config.endpoint}/${activeRecordId}`;
    await apiRequest(path, {
      method: activeRecordId === null ? "POST" : "PATCH",
      body: JSON.stringify(buildRecordPayload(fields)),
    });
    recordDialog.close();
    await loadResource(activeView);
  } catch (error) {
    recordError.textContent = error.message;
    recordError.hidden = false;
  } finally {
    saveButton.disabled = false;
  }
});

managementList.addEventListener("click", async (event) => {
  // Aplica las acciones de edición, eliminación o devolución sobre la fila elegida.
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const config = resources[activeView];
  const record = config.records().find((item) => item.id === Number(button.dataset.id));
  if (!record) return;

  if (button.dataset.action === "edit") {
    openRecordDialog(record);
    return;
  }
  if (button.dataset.action === "delete") {
    const label = activeView === "prestamos"
      ? `¿Eliminar el préstamo de "${record.libro.titulo}" a ${record.socio.nombre}?`
      : `¿Eliminar este ${config.singular}?`;
    if (!window.confirm(label)) return;
    try {
      await apiRequest(`${config.endpoint}/${record.id}`, { method: "DELETE" });
      await loadResource(activeView);
    } catch (error) {
      document.querySelector("#management-notice").textContent =
        `No se pudo eliminar ${config.singular}: ${error.message}`;
      document.querySelector("#management-notice").hidden = false;
    }
    return;
  }
  if (button.dataset.action === "return") {
    if (!window.confirm(`¿Registrar la devolución de "${record.libro.titulo}"?`)) return;
    try {
      await apiRequest(`${config.endpoint}/${record.id}/devolucion`, {
        method: "POST",
        body: JSON.stringify({ fecha_devolucion: localDateString() }),
      });
      await loadResource(activeView);
    } catch (error) {
      document.querySelector("#management-notice").textContent =
        `No se pudo registrar la devolución: ${error.message}`;
      document.querySelector("#management-notice").hidden = false;
    }
  }
});

document.querySelector("#add-record").hidden = pagesApiNotConfigured;
document.querySelector("#refresh-records").hidden = pagesApiNotConfigured;
loadBooks();
