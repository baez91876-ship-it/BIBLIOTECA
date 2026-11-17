<script setup>
import { ref } from "vue";
import { login } from "../api.js";

const emit = defineEmits(["close", "done"]);
const email = ref("");
const password = ref("");
const error = ref("");
const busy = ref(false);

async function submit() {
  busy.value = true;
  error.value = "";
  try {
    await login(email.value, password.value);
    emit("done");
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="overlay" @click.self="emit('close')">
    <form class="dialog" aria-label="Iniciar sesión" @submit.prevent="submit">
      <h2>Iniciar sesión</h2>
      <label>Correo electrónico
        <input v-model="email" type="email" required autocomplete="username" id="login-email">
      </label>
      <label>Contraseña
        <input v-model="password" type="password" required autocomplete="current-password" id="login-password">
      </label>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <div class="actions">
        <button type="button" class="secondary" @click="emit('close')">Cancelar</button>
        <button type="submit" :disabled="busy">Entrar</button>
      </div>
    </form>
  </div>
</template>
