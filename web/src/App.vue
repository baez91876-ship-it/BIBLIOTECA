<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { api, isStaff, listAll, logout, session } from "./api.js";
import BookDialog from "./components/BookDialog.vue";
import CategoriesView from "./components/CategoriesView.vue";
import LoginDialog from "./components/LoginDialog.vue";

const view = ref("libros");
const books = ref([]);
const authors = ref([]);
const categories = ref([]);
const search = ref("");
const copiesSearch = ref("");
const loading = ref(true);
const notice = ref("");
const editing = ref(undefined); // undefined: cerrado, null: nuevo, objeto: edición
const copies = reactive({});
const savingCopies = ref(null);
const sessionNotice = ref("");
watch(() => session.user, (user, previous) => {
  if (user && !previous) onLogin();
  if (!user && previous) {
    sessionNotice.value = "Tu sesión terminó. Inicia sesión para continuar.";
    view.value = "libros";
    editing.value = undefined;
    books.value = [];
    authors.value = [];
    categories.value = [];
    search.value = "";
    copiesSearch.value = "";
  }
});

const visible = computed(() => {
  const q = search.value.trim().toLocaleLowerCase("es");
  return books.value.filter((b) =>
    `${b.titulo} ${b.autor.nombre}`.toLocaleLowerCase("es").includes(q),
  );
});
const visibleCopies = computed(() => {
  const q = copiesSearch.value.trim().toLocaleLowerCase("es");
  return books.value.filter((b) =>
    `${b.titulo} ${b.autor.nombre}`.toLocaleLowerCase("es").includes(q),
  );
});
const available = computed(() => books.value.reduce((n, b) => n + b.disponibles, 0));

async function load() {
  const user = session.user;
  loading.value = true;
  notice.value = "";
  try {
    const [loadedBooks, loadedAuthors, loadedCategories] = await Promise.all([
      listAll("/libros"),
      listAll("/autores"),
      listAll("/categorias"),
    ]);
    if (session.user !== user) return;
    books.value = loadedBooks;
    authors.value = loadedAuthors;
    categories.value = loadedCategories;
    for (const book of books.value) copies[book.id] = book.ejemplares;
  } catch (e) {
    if (session.user === user) notice.value = e.message;
  } finally {
    if (session.user === user) loading.value = false;
  }
}

async function saveCopies(book) {
  savingCopies.value = book.id;
  notice.value = "";
  try {
    await api(`/libros/${book.id}`, {
      method: "PATCH",
      body: JSON.stringify({ ejemplares: Number(copies[book.id]) }),
    });
    await load();
  } catch (e) {
    notice.value = `No se pudieron guardar los ejemplares: ${e.message}`;
  } finally {
    savingCopies.value = null;
  }
}

async function remove(book) {
  if (!confirm(`¿Eliminar "${book.titulo}"?`)) return;
  try {
    await api(`/libros/${book.id}`, { method: "DELETE" });
    await load();
  } catch (e) {
    notice.value = e.message;
  }
}

async function onLogin() {
  sessionNotice.value = "";
  view.value = "libros";
  await load();
}

async function onSaved() {
  editing.value = undefined;
  await load();
}

async function signOut() {
  await logout();
  view.value = "libros";
}

onMounted(() => {
  if (session.user) load();
});
</script>

<template>
  <LoginDialog v-if="!session.user" :notice="sessionNotice" />
  <template v-else>
  <header class="topbar">
    <a class="brand" href="./" aria-label="Inicio BIBLIOTECA">BIBLIOTECA<span>.</span></a>
    <div class="user">
      <span v-if="session.user" id="signed-in-user">{{ session.user.nombre }}</span>
      <button class="secondary" id="logout-button" @click="signOut">Cerrar sesión</button>
    </div>
  </header>

  <nav class="tabs" aria-label="Secciones">
    <button :class="{ active: view === 'libros' }" id="tab-libros" @click="view = 'libros'">Libros</button>
    <button :class="{ active: view === 'categorias' }" id="tab-categorias" @click="view = 'categorias'">Categorías</button>
    <button v-if="isStaff()" :class="{ active: view === 'ejemplares' }" id="tab-ejemplares" @click="view = 'ejemplares'">Ejemplares</button>
  </nav>

  <main v-if="view === 'categorias'">
    <CategoriesView @changed="load" />
  </main>

  <main v-else-if="view === 'ejemplares' && isStaff()">
    <section class="heading">
      <div>
        <p class="eyebrow">ADMINISTRACIÓN</p>
        <h1>Ejemplares<span>.</span></h1>
        <p class="stats">Consulta la disponibilidad y actualiza el inventario.</p>
      </div>
      <button class="secondary" @click="load">Actualizar lista</button>
    </section>
    <input v-model="copiesSearch" type="search" placeholder="Buscar título o autor" aria-label="Buscar ejemplares">
    <p v-if="notice" class="error" role="alert">{{ notice }}</p>
    <p v-if="loading">Cargando…</p>
    <p v-else-if="!visibleCopies.length">No hay libros que coincidan.</p>
    <ul class="grid">
      <li v-for="b in visibleCopies" :key="b.id" class="card">
        <div>
          <h3>{{ b.titulo }}</h3>
          <p>{{ b.autor.nombre }}</p>
          <p><strong>{{ b.disponibles }}</strong> de {{ b.ejemplares }} disponibles</p>
          <form class="copies-form" @submit.prevent="saveCopies(b)">
            <label>
              Ejemplares
              <input v-model.number="copies[b.id]" type="number" min="1" max="50" required
                :aria-label="`Ejemplares de ${b.titulo}`">
            </label>
            <button type="submit" class="secondary" :disabled="savingCopies !== null">Guardar ejemplares</button>
          </form>
        </div>
      </li>
    </ul>
  </main>

  <main v-else>
    <section class="heading">
      <div>
        <p class="eyebrow">TU ESPACIO DE LECTURA</p>
        <h1>La colección<span>.</span></h1>
        <p class="stats">{{ books.length }} libros · {{ available }} ejemplares disponibles</p>
      </div>
      <button v-if="isStaff()" id="add-book" @click="editing = null">Añadir libro</button>
    </section>

    <input v-model="search" id="search" type="search" placeholder="Buscar por título o autor" aria-label="Buscar libros">
    <p v-if="notice" class="error" role="alert">{{ notice }}</p>
    <p v-if="loading">Cargando…</p>
    <p v-else-if="!visible.length" id="empty-state">No hay libros que coincidan.</p>

    <ul class="grid">
      <li v-for="b in visible" :key="b.id" class="card book-card">
        <img v-if="b.portada_url" :src="b.portada_url" :alt="`Portada de ${b.titulo}`" class="cover" loading="lazy">
        <div v-else class="cover placeholder" aria-hidden="true">{{ b.titulo[0] }}</div>
        <div>
          <h3>{{ b.titulo }}</h3>
          <p>{{ b.autor.nombre }} · {{ b.anio_publicacion }}</p>
          <p class="muted">{{ b.categorias.map((c) => c.nombre).join(", ") }}</p>
          <p><strong>{{ b.disponibles }}</strong> de {{ b.ejemplares }} disponibles</p>
          <div v-if="isStaff()" class="actions">
            <button class="secondary" @click="editing = b">Editar</button>
            <button class="danger" @click="remove(b)">Eliminar</button>
          </div>
        </div>
      </li>
    </ul>
  </main>

  <BookDialog
    v-if="editing !== undefined"
    :book="editing"
    :authors="authors"
    :categories="categories"
    @close="editing = undefined"
    @saved="onSaved"
  />
  </template>
</template>
