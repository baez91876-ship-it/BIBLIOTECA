import { afterEach, describe, expect, it, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import App from "../src/App.vue";
import { clearSession, session } from "../src/api.js";

const book = {
  id: 1, titulo: "Rayuela", isbn: "9788437604572", anio_publicacion: 1963,
  ejemplares: 3, disponibles: 2, portada_url: null,
  autor: { id: 1, nombre: "Julio Cortázar" }, categorias: [{ id: 1, nombre: "Novela" }],
};

function mockApi(extra = {}) {
  globalThis.fetch = vi.fn(async (url, options = {}) => {
    const path = String(url);
    if (extra[path]) return extra[path](options);
    const items = path.includes("/libros") ? [book]
      : path.includes("/autores") ? [book.autor] : book.categorias;
    return new Response(JSON.stringify({ items, total: items.length, skip: 0, limit: 100 }));
  });
}

afterEach(() => { clearSession(); vi.restoreAllMocks(); });

describe("catálogo de libros", () => {
  it("lista y filtra libros", async () => {
    mockApi();
    const wrapper = mount(App);
    await flushPromises();
    expect(wrapper.text()).toContain("Rayuela");
    await wrapper.find("#search").setValue("zzz");
    expect(wrapper.find("#empty-state").exists()).toBe(true);
    expect(wrapper.find("#add-book").exists()).toBe(false);
  });

  it("inicia sesión y muestra acciones de personal", async () => {
    mockApi({
      "/api/v1/auth/login": () => new Response(JSON.stringify({ access_token: "a", refresh_token: "r" })),
      "/api/v1/auth/me": () => new Response(JSON.stringify({ nombre: "Ana", rol: "bibliotecario" })),
    });
    const wrapper = mount(App);
    await flushPromises();
    await wrapper.find("#login-button").trigger("click");
    await wrapper.find("#login-email").setValue("a@b.co");
    await wrapper.find("#login-password").setValue("secreto12345");
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(session.user.rol).toBe("bibliotecario");
    expect(wrapper.find("#add-book").exists()).toBe(true);
  });

  it("lista categorías en su sección", async () => {
    mockApi();
    const wrapper = mount(App);
    await flushPromises();
    await wrapper.find("#tab-categorias").trigger("click");
    await flushPromises();
    expect(wrapper.find(".category-card").text()).toContain("Novela");
  });

  it("edita únicamente los ejemplares", async () => {
    let payload;
    mockApi({
      "/api/v1/libros/1": (options) => {
        payload = JSON.parse(options.body);
        return new Response(JSON.stringify(book));
      },
    });
    session.user = { rol: "administrador" };
    const wrapper = mount(App);
    await flushPromises();
    await wrapper.find('input[aria-label="Ejemplares de Rayuela"]').setValue(5);
    await wrapper.find(".copies-form").trigger("submit");
    await flushPromises();
    expect(payload).toEqual({ ejemplares: 5 });
  });

  it("muestra el error de la API al fallar el login", async () => {
    mockApi({
      "/api/v1/auth/login": () => new Response(JSON.stringify({ detail: "Credenciales inválidas" }), { status: 401 }),
    });
    const wrapper = mount(App);
    await flushPromises();
    await wrapper.find("#login-button").trigger("click");
    await wrapper.find("#login-email").setValue("a@b.co");
    await wrapper.find("#login-password").setValue("x");
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(wrapper.find(".dialog .error").text()).toBe("Credenciales inválidas");
  });
});
