<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { api, clearSession, isStaff, listAll, logout, session } from "./api.js";
import BookDialog from "./components/BookDialog.vue";
import CategoriesView from "./components/CategoriesView.vue";
import LoginDialog from "./components/LoginDialog.vue";

const view = ref("libros");
const books = ref([]);
const authors = ref([]);
const categories = ref([]);
const search = ref("");
const loading = ref(true);
const notice = ref("");
const showLogin = ref(false);
const editing = ref(undefined); // undefined: cerrado, null: nuevo, objeto: edición
const copies = reactive({});
const savingCopies = ref(null);

const visible = computed(() => {
  const q = search.value.trim().toLocaleLowerCase("es");
  return books.value.filter((b) =>
    `${b.titulo} ${b.autor.nombre}`.toLocaleLowerCase("es").includes(q),
  );
});
const available = computed(() => books.value.reduce((n, b) => n + b.disponibles, 0));

async function load() {
  loading.value = true;
  notice.value = "";
  try {
    [books.value, authors.value, categories.value] = await Promise.all([
      listAll("/libros"),
      listAll("/autores"),
      listAll("/categorias"),
    ]);
    for (const book of books.value) copies[book.id] = book.ejemplares;
  } catch (e) {
    notice.value = e.message;
  } finally {
    loading.value = false;
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
  showLogin.value = false;
  await load();
}

async function onSaved() {
  editing.value = undefined;
  await load();
}

async function signOut() {
  await logout();
}

onMounted(load);
</script>

<template>
  <header class="topbar">
    <a class="brand" href="./">Libreria<span>.</span></a>
    <div class="user">
      <span v-if="session.user" id="signed-in-user">{{ session.user.nombre }} · {{ session.user.rol }}</span>
      <button v-if="!session.user" id="login-button" @click="showLogin = true">Iniciar sesión</button>
      <button v-else class="secondary" id="logout-button" @click="signOut">Cerrar sesión</button>
    </div>
  </header>

  <nav class="tabs" aria-label="Secciones">
    <button :class="{ active: view === 'libros' }" id="tab-libros" @click="view = 'libros'">Libros</button>
    <button :class="{ active: view === 'categorias' }" id="tab-categorias" @click="view = 'categorias'">Categorías</button>
  </nav>

  <main v-if="view === 'categorias'">
    <CategoriesView @changed="load" />
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
          <form v-if="isStaff()" class="copies-form" @submit.prevent="saveCopies(b)">
            <label>
              Ejemplares
              <input v-model.number="copies[b.id]" type="number" min="1" max="50" required
                :aria-label="`Ejemplares de ${b.titulo}`">
            </label>
            <button type="submit" class="secondary" :disabled="savingCopies !== null">Guardar ejemplares</button>
          </form>
          <div v-if="isStaff()" class="actions">
            <button class="secondary" @click="editing = b">Editar</button>
            <button class="danger" @click="remove(b)">Eliminar</button>
          </div>
        </div>
      </li>
    </ul>
  </main>

  <LoginDialog v-if="showLogin" @close="showLogin = false" @done="onLogin" />
  <BookDialog
    v-if="editing !== undefined"
    :book="editing"
    :authors="authors"
    :categories="categories"
    @close="editing = undefined"
    @saved="onSaved"
  />
</template>
