<script setup>
import { ref } from "vue";
import { login } from "../api.js";

defineProps({ notice: { type: String, default: "" } });
const email = ref("");
const password = ref("");
const error = ref("");
const busy = ref(false);

async function submit() {
  busy.value = true;
  error.value = "";
  try {
    await login(email.value, password.value);
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <main class="login-view">
    <form class="dialog login-panel" aria-label="Iniciar sesión" @submit.prevent="submit">
      <h1>Iniciar sesión</h1>
      <label>Correo electrónico
        <input v-model="email" type="email" required autocomplete="username" id="login-email" autofocus>
      </label>
      <label>Contraseña
        <input v-model="password" type="password" required autocomplete="current-password" id="login-password">
      </label>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="notice" role="status">{{ notice }}</p>
      <div class="actions">
        <button type="submit" :disabled="busy">Entrar</button>
      </div>
    </form>
  </main>
</template>
