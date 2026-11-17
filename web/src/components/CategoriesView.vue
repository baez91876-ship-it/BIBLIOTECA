<script setup>
import { onMounted, ref } from "vue";
import { api, isStaff, listAll } from "../api.js";

const emit = defineEmits(["changed"]);
const items = ref([]);
const loading = ref(true);
const error = ref("");
const editingId = ref(null);
const form = ref({ nombre: "", descripcion: "" });
const busy = ref(false);

async function load() {
  loading.value = true;
  try {
    items.value = await listAll("/categorias");
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

function reset() {
  editingId.value = null;
  form.value = { nombre: "", descripcion: "" };
}

function edit(category) {
  editingId.value = category.id;
  form.value = { nombre: category.nombre, descripcion: category.descripcion ?? "" };
}

async function save() {
  busy.value = true;
  error.value = "";
  try {
    const body = JSON.stringify({
      nombre: form.value.nombre,
      descripcion: form.value.descripcion || null,
    });
    await api(editingId.value ? `/categorias/${editingId.value}` : "/categorias", {
      method: editingId.value ? "PATCH" : "POST",
      body,
    });
    reset();
    await load();
    emit("changed");
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}

async function remove(category) {
  if (!confirm(`¿Eliminar la categoría "${category.nombre}"? Los libros no se borran.`)) return;
  error.value = "";
  try {
    await api(`/categorias/${category.id}`, { method: "DELETE" });
    if (editingId.value === category.id) reset();
    await load();
    emit("changed");
  } catch (e) {
    error.value = e.message;
  }
}

onMounted(load);
</script>

<template>
  <section class="heading">
    <div>
      <p class="eyebrow">ADMINISTRACIÓN</p>
      <h1>Categorías<span>.</span></h1>
    </div>
  </section>

  <form v-if="isStaff()" class="inline-form" aria-label="Formulario de categoría" @submit.prevent="save">
    <label>Nombre
      <input v-model="form.nombre" required minlength="3" maxlength="50" name="nombre">
    </label>
    <label>Descripción
      <input v-model="form.descripcion" maxlength="200" name="descripcion">
    </label>
    <button type="submit" :disabled="busy">{{ editingId ? "Guardar cambios" : "Añadir categoría" }}</button>
    <button v-if="editingId" type="button" class="secondary" @click="reset">Cancelar</button>
  </form>

  <p v-if="error" class="error" role="alert">{{ error }}</p>
  <p v-if="loading">Cargando…</p>
  <p v-else-if="!items.length" id="empty-categories">Aún no hay categorías.</p>

  <ul class="grid">
    <li v-for="c in items" :key="c.id" class="card category-card">
      <div>
        <h3>{{ c.nombre }}</h3>
        <p class="muted">{{ c.descripcion || "Sin descripción" }}</p>
        <div v-if="isStaff()" class="actions">
          <button class="secondary" @click="edit(c)">Editar</button>
          <button class="danger" @click="remove(c)">Eliminar</button>
        </div>
      </div>
    </li>
  </ul>
</template>
