<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import { api } from "../api.js";

const props = defineProps({
  book: { type: Object, default: null },
  authors: { type: Array, required: true },
  categories: { type: Array, required: true },
});
const emit = defineEmits(["close", "saved"]);

const form = reactive({
  titulo: props.book?.titulo ?? "",
  isbn: props.book?.isbn ?? "",
  anio_publicacion: props.book?.anio_publicacion ?? new Date().getFullYear(),
  ejemplares: props.book?.ejemplares ?? 1,
  autor_id: props.book?.autor.id ?? "",
  categoria_ids: props.book?.categorias.map((c) => c.id) ?? [],
});
const file = ref(null);
const preview = ref(null);
const error = ref("");
const busy = ref(false);
const savedId = ref(props.book?.id ?? null);

const coverSrc = computed(() => preview.value ?? props.book?.portada_url ?? null);

watch(file, (value, _old, onCleanup) => {
  if (!value) {
    preview.value = null;
    return;
  }
  const url = URL.createObjectURL(value);
  preview.value = url;
  onCleanup(() => URL.revokeObjectURL(url));
});
onBeforeUnmount(() => { file.value = null; });

function pickFile(event) {
  file.value = event.target.files[0] ?? null;
}

async function submit() {
  busy.value = true;
  error.value = "";
  try {
    // El libro se guarda una sola vez; un reintento solo repite la portada.
    if (!savedId.value || props.book) {
      const saved = await api(props.book ? `/libros/${props.book.id}` : "/libros", {
        method: props.book ? "PATCH" : "POST",
        body: JSON.stringify({ ...form, autor_id: Number(form.autor_id) }),
      });
      savedId.value = saved.id;
    }
    if (file.value) {
      const data = new FormData();
      data.append("archivo", file.value);
      await api(`/libros/${savedId.value}/portada`, { method: "POST", body: data });
    }
    emit("saved");
  } catch (e) {
    error.value = file.value && savedId.value
      ? `El libro se guardó, pero la portada falló: ${e.message}`
      : e.message;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="overlay" @click.self="emit('close')">
    <form class="dialog" aria-label="Formulario de libro" @submit.prevent="submit">
      <h2>{{ book ? "Editar libro" : "Nuevo libro" }}</h2>
      <label>Título <input v-model="form.titulo" required maxlength="150" name="titulo"></label>
      <label>ISBN (13 dígitos)
        <input v-model="form.isbn" required pattern="\d{13}" name="isbn">
      </label>
      <div class="row">
        <label>Año
          <input v-model.number="form.anio_publicacion" type="number" min="1450" required name="anio">
        </label>
        <label>Ejemplares
          <input v-model.number="form.ejemplares" type="number" min="1" max="50" required name="ejemplares">
        </label>
      </div>
      <label>Autor
        <select v-model="form.autor_id" required name="autor">
          <option value="" disabled>Selecciona…</option>
          <option v-for="a in authors" :key="a.id" :value="a.id">{{ a.nombre }}</option>
        </select>
      </label>
      <fieldset>
        <legend>Categorías (1 a 5)</legend>
        <label v-for="c in categories" :key="c.id" class="check">
          <input v-model="form.categoria_ids" type="checkbox" :value="c.id"> {{ c.nombre }}
        </label>
      </fieldset>
      <label>Portada (JPEG, PNG o WebP, máx. 5 MiB)
        <input type="file" accept="image/jpeg,image/png,image/webp" @change="pickFile">
      </label>
      <img v-if="coverSrc" :src="coverSrc" alt="Vista previa de la portada" class="preview">
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <div class="actions">
        <button type="button" class="secondary" @click="emit('close')">Cancelar</button>
        <button type="submit" :disabled="busy || !form.categoria_ids.length">Guardar</button>
      </div>
    </form>
  </div>
</template>
