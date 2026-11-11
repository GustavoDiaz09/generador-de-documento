/* Interfaz del generador de protocolos.
 * Habla con Python mediante window.pywebview.api y recibe progreso por
 * window.appEvento(evento) (ver generador/api.py).
 */
(() => {
  "use strict";

  const N_OBJETIVOS = 3;
  const CONCEPTOS = { min: 8, max: 12 };
  const N_RESUMEN = 3;

  const $ = (id) => document.getElementById(id);
  const estado = {
    ruta: "",
    texto: false,
    ocupado: { extraer: false, ia: false, modelos: false, generar: false },
    ultimoDocx: "",
  };

  // ---------- comunicacion con Python ----------
  function esperarApi() {
    if (window.pywebview && window.pywebview.api) return Promise.resolve();
    return new Promise((resolve) =>
      window.addEventListener("pywebviewready", () => resolve(), { once: true }));
  }

  async function llamar(metodo, ...args) {
    await esperarApi();
    return window.pywebview.api[metodo](...args);
  }

  // ---------- utilidades de DOM ----------
  function el(tag, attrs = {}, ...hijos) {
    const nodo = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") nodo.className = v;
      else if (k === "text") nodo.textContent = v;
      else if (k.startsWith("on")) nodo.addEventListener(k.slice(2), v);
      else nodo.setAttribute(k, v);
    }
    for (const h of hijos) nodo.append(h);
    return nodo;
  }

  function estadoTexto(msg) { $("estado-texto").textContent = msg; }

  function toast(mensaje, tipo = "info") {
    const t = el("div", { class: `toast ${tipo}`, role: "status", text: mensaje });
    $("toasts").append(t);
    setTimeout(() => t.remove(), tipo === "error" ? 7000 : 4500);
  }

  function log(mensaje, nivel = "info") {
    const reg = $("registro");
    reg.append(el("div", { class: `linea-log ${nivel}`, text: mensaje }));
    reg.scrollTop = reg.scrollHeight;
  }

  function setChip(id, actual, minimo, maximo = minimo) {
    const chip = $(id);
    const ok = actual >= minimo && actual <= maximo;
    chip.textContent = minimo === maximo ? `${actual} / ${minimo}` : `${actual} / ${minimo}–${maximo}`;
    chip.classList.toggle("ok", ok);
    chip.classList.toggle("falta", !ok && actual > 0);
  }

  // ---------- pasos ----------
  function irA(paso) {
    document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("activo", p.id === `paso-${paso}`));
    document.querySelectorAll(".paso").forEach((b) => {
      const n = Number(b.dataset.paso);
      b.classList.toggle("activo", n === paso);
      b.classList.toggle("completo", n < paso);
      if (n === paso) b.setAttribute("aria-current", "step"); else b.removeAttribute("aria-current");
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // ---------- tema ----------
  function aplicarTema(tema) {
    document.documentElement.dataset.tema = tema;
    $("btn-tema").textContent = tema === "oscuro" ? "Modo claro" : "Modo oscuro";
  }

  // ---------- objetivos, conceptos y resumen ----------
  function crearObjetivos(valores = []) {
    const lista = $("lista-objetivos");
    lista.replaceChildren();
    for (let i = 0; i < N_OBJETIVOS; i++) {
      const input = el("input", { type: "text", "aria-label": `Objetivo ${i + 1}`, placeholder: `Objetivo ${i + 1}` });
      input.value = valores[i] || "";
      input.addEventListener("input", actualizarChips);
      lista.append(el("div", { class: "fila-objetivo" }, el("span", { class: "num", text: String(i + 1) }), input));
    }
  }

  function filaConcepto(termino = "", definicion = "") {
    const t = el("input", { type: "text", "aria-label": "Término", placeholder: "Término" });
    const d = el("input", { type: "text", "aria-label": "Definición", placeholder: "Definición", class: "campo-valor" });
    t.value = termino; d.value = definicion;
    t.addEventListener("input", actualizarChips);
    d.addEventListener("input", actualizarChips);
    const quitar = el("button", {
      class: "btn-icono", type: "button", "aria-label": "Quitar concepto", text: "×",
      onclick: () => { fila.remove(); actualizarChips(); },
    });
    const fila = el("div", { class: "fila-concepto" }, t, d, quitar);
    return fila;
  }

  function cargarConceptos(lista = []) {
    const tabla = $("tabla-conceptos");
    tabla.replaceChildren(
      el("div", { class: "cabecera-tabla", role: "row" },
        el("span", { text: "Término" }), el("span", { class: "col-valor", text: "Definición" }), el("span", { text: "" })),
    );
    lista.forEach((c) => tabla.append(filaConcepto(c.termino || "", c.definicion || "")));
    actualizarChips();
  }

  function seccionResumen(subtitulo = "Nueva sección", parrafos = []) {
    const sub = el("input", { type: "text", "aria-label": "Subtítulo de la sección", placeholder: "Subtítulo" });
    sub.value = subtitulo;
    const txt = el("textarea", { rows: "4", "aria-label": "Párrafos (uno por línea)", placeholder: "Un párrafo por línea" });
    txt.value = parrafos.join("\n");
    sub.addEventListener("input", actualizarChips);
    txt.addEventListener("input", actualizarChips);
    const quitar = el("button", {
      class: "btn-icono", type: "button", "aria-label": "Quitar sección", text: "×",
      onclick: () => { sec.remove(); actualizarChips(); },
    });
    const sec = el("div", { class: "seccion-resumen" },
      el("header", {}, sub, quitar), txt);
    return sec;
  }

  function cargarResumen(lista = []) {
    const cont = $("lista-resumen");
    cont.replaceChildren();
    lista.forEach((s) => cont.append(seccionResumen(s.subtitulo || "", s.parrafos || [])));
    actualizarChips();
  }

  // ---------- lectura / escritura del formulario ----------
  function leerContenido() {
    const lineas = (txt) => txt.split("\n").map((l) => l.trim()).filter(Boolean);
    const conceptos = [...$("tabla-conceptos").querySelectorAll(".fila-concepto")].map((f) => {
      const [t, d] = f.querySelectorAll("input");
      return { termino: t.value.trim(), definicion: d.value.trim() };
    }).filter((c) => c.termino || c.definicion);
    const resumen = [...$("lista-resumen").querySelectorAll(".seccion-resumen")].map((s) => ({
      subtitulo: s.querySelector("input").value.trim(),
      parrafos: lineas(s.querySelector("textarea").value),
    }));
    const objetivos = [...$("lista-objetivos").querySelectorAll("input")].map((i) => i.value.trim()).filter(Boolean);
    return {
      descripcion: $("descripcion").value.trim(),
      palabras_claves: $("palabras").value.trim(),
      objetivos,
      conceptos,
      resumen,
      conclusiones: $("conclusiones").value.trim(),
      bibliografia: lineas($("bibliografia").value).join("\n"),
    };
  }

  function escribirContenido(c) {
    $("descripcion").value = c.descripcion || "";
    $("palabras").value = c.palabras_claves || "";
    crearObjetivos(c.objetivos || []);
    cargarConceptos(c.conceptos || []);
    cargarResumen(c.resumen || []);
    $("conclusiones").value = c.conclusiones || "";
    $("bibliografia").value = c.bibliografia || "";
    actualizarChips();
  }

  function actualizarChips() {
    const c = leerContenido();
    setChip("chip-objetivos", c.objetivos.length, N_OBJETIVOS);
    setChip("chip-conceptos", c.conceptos.length, CONCEPTOS.min, CONCEPTOS.max);
    setChip("chip-resumen", c.resumen.length, N_RESUMEN);
    const listo = c.objetivos.length === N_OBJETIVOS
      && c.conceptos.length >= CONCEPTOS.min && c.conceptos.length <= CONCEPTOS.max
      && c.resumen.length === N_RESUMEN && c.descripcion && c.conclusiones;
    const chip = $("chip-listo");
    chip.textContent = listo ? "Listo para generar" : "Faltan datos en el paso 2";
    chip.classList.toggle("ok", !!listo);
    chip.classList.toggle("falta", !listo);
  }

  // ---------- configuracion de IA ----------
  function leerConfig() {
    return {
      proveedor: $("proveedor").value,
      modelo: $("modelo").value.trim(),
      clave: $("clave").value.trim(),
      base_url: $("base-url").value.trim(),
      recordar: $("recordar").checked,
    };
  }

  let timerGuardar = null;
  function guardarConfigDiferido() {
    clearTimeout(timerGuardar);
    timerGuardar = setTimeout(async () => {
      const r = await llamar("guardar_config", leerConfig());
      if (r && !r.ok) toast(r.mensaje, "error");
    }, 400);
  }

  // ---------- acciones ----------
  function setOcupado(clave, boton, ocupado, textoOcupado) {
    estado.ocupado[clave] = ocupado;
    if (!boton) return;
    if (ocupado) { boton.dataset.texto = boton.textContent; boton.textContent = textoOcupado; boton.disabled = true; }
    else { boton.textContent = boton.dataset.texto || boton.textContent; boton.disabled = false; }
  }

  async function elegirPdf() {
    const r = await llamar("seleccionar_pdf");
    if (!r) return;
    estado.ruta = r.ruta;
    estado.texto = false;
    const dz = $("dropzone");
    dz.classList.remove("cargado");
    $("dz-titulo").textContent = r.nombre;
    $("dz-sub").textContent = r.ruta;
    if (r.unidad) $("unidad").value = r.unidad;
    $("btn-extraer").disabled = false;
    $("extraer-info").textContent = "";
    estadoTexto(`Módulo seleccionado: ${r.nombre}`);
  }

  async function extraer() {
    setOcupado("extraer", $("btn-extraer"), true, "Extrayendo…");
    estadoTexto("Extrayendo texto del PDF…");
    const r = await llamar("extraer_texto", estado.ruta);
    if (r && !r.ok) { setOcupado("extraer", $("btn-extraer"), false); toast(r.mensaje, "error"); }
  }

  async function redactar() {
    if (!estado.texto) { toast("Primero extrae el texto del módulo.", "error"); irA(1); return; }
    setOcupado("ia", $("btn-redactar"), true, "Redactando…");
    estadoTexto("Redactando contenido con IA…");
    irA(3);
    const opts = { unidad: $("unidad").value, materia: $("materia").value, ...leerConfig() };
    const r = await llamar("redactar", opts);
    if (r && !r.ok) { setOcupado("ia", $("btn-redactar"), false); toast(r.mensaje, "error"); }
  }

  async function generar() {
    const contenido = leerContenido();
    const errores = (await llamar("validar", contenido)) || [];
    if (errores.length) {
      irA(2);
      toast(errores.join(" "), "error");
      return;
    }
    setOcupado("generar", $("btn-generar"), true, "Generando…");
    $("resultado").hidden = true;
    estadoTexto("Generando protocolo…");
    const r = await llamar("generar", contenido, $("unidad").value, $("materia").value);
    if (r && !r.ok) { setOcupado("generar", $("btn-generar"), false); toast(r.errores.join(" "), "error"); }
  }

  async function cargarJson() {
    const r = await llamar("cargar_json");
    if (!r) return;
    if (!r.ok) { toast(r.mensaje, "error"); return; }
    escribirContenido(r.contenido);
    toast("Contenido cargado.", "ok");
  }

  async function guardarJson() {
    const r = await llamar("guardar_json", leerContenido());
    if (r && r.ok) toast("JSON guardado.", "ok");
    else if (r && !r.ok) toast(r.mensaje, "error");
  }

  function vaciar() {
    $("descripcion").value = "";
    $("palabras").value = "";
    $("conclusiones").value = "";
    $("bibliografia").value = "";
    crearObjetivos([]);
    cargarConceptos([]);
    cargarResumen([]);
    toast("Formulario vaciado.", "ok");
  }

  async function verModelos() {
    setOcupado("modelos", $("btn-modelos"), true, "Consultando…");
    estadoTexto("Consultando modelos disponibles…");
    const cfg = leerConfig();
    const r = await llamar("listar_modelos", cfg);
    if (r && !r.ok) setOcupado("modelos", $("btn-modelos"), false);
  }

  let modeloSeleccionado = null;
  function mostrarModelos(nombres) {
    const lista = $("lista-modelos");
    lista.replaceChildren();
    modeloSeleccionado = null;
    $("btn-usar-modelo").disabled = true;
    nombres.forEach((n) => {
      const li = el("li", { role: "option", "aria-selected": "false", text: n });
      li.addEventListener("click", () => {
        lista.querySelectorAll("li").forEach((x) => x.setAttribute("aria-selected", "false"));
        li.setAttribute("aria-selected", "true");
        modeloSeleccionado = n;
        $("btn-usar-modelo").disabled = false;
      });
      li.addEventListener("dblclick", () => { modeloSeleccionado = n; usarModelo(); });
      lista.append(li);
    });
    $("modelos-info").textContent = `${nombres.length} modelos disponibles. Selecciona uno.`;
    $("dlg-modelos").showModal();
  }

  function usarModelo() {
    if (!modeloSeleccionado) return;
    $("modelo").value = modeloSeleccionado;
    $("dlg-modelos").close();
    guardarConfigDiferido();
    toast(`Modelo: ${modeloSeleccionado}`, "ok");
  }

  // ---------- eventos desde Python ----------
  window.appEvento = (ev) => {
    switch (ev.tipo) {
      case "log":
        log(ev.mensaje, ev.nivel);
        if (ev.nivel === "info") estadoTexto(ev.mensaje);
        break;
      case "extraido":
        estado.texto = true;
        setOcupado("extraer", $("btn-extraer"), false);
        $("dropzone").classList.add("cargado");
        $("dz-sub").textContent = `${ev.caracteres.toLocaleString("es")} caracteres extraídos`;
        $("extraer-info").textContent = ev.ocr ? "PDF escaneado: se usó OCR." : "";
        $("chip-ocr").hidden = !ev.ocr;
        $("tarjeta-vista").hidden = false;
        $("vista-resumen").textContent = ev.biblio.length
          ? `Bibliografía detectada: ${ev.biblio.length} referencias.`
          : "No se detectó bibliografía en el módulo.";
        $("vista-texto").textContent = ev.vista;
        log(`Texto extraído (${ev.caracteres} caracteres).`, "ok");
        estadoTexto("Texto extraído.");
        break;
      case "contenido":
        escribirContenido(ev.contenido);
        setOcupado("ia", $("btn-redactar"), false);
        irA(2);
        toast("Contenido redactado. Revísalo antes de generar.", "ok");
        estadoTexto("Contenido redactado.");
        break;
      case "falta_clave":
        setOcupado("ia", $("btn-redactar"), false);
        irA(3);
        $("clave").focus();
        toast("Falta la clave de API. Pégala aquí o define la variable de entorno.", "error");
        estadoTexto("Sin clave de API.");
        break;
      case "modelos":
        setOcupado("modelos", $("btn-modelos"), false);
        mostrarModelos(ev.nombres);
        estadoTexto("Listo.");
        break;
      case "listo":
        setOcupado("generar", $("btn-generar"), false);
        estado.ultimoDocx = ev.ruta;
        $("resultado-nombre").textContent = ev.nombre;
        $("resultado").hidden = false;
        toast("Protocolo generado correctamente.", "ok");
        estadoTexto("Protocolo generado correctamente.");
        break;
      case "error":
        log(ev.mensaje, "error");
        if (ev.contexto === "extraer") setOcupado("extraer", $("btn-extraer"), false);
        if (ev.contexto === "ia") setOcupado("ia", $("btn-redactar"), false);
        if (ev.contexto === "modelos") setOcupado("modelos", $("btn-modelos"), false);
        if (ev.contexto === "generar" || ev.contexto === "verificar") setOcupado("generar", $("btn-generar"), false);
        toast(ev.mensaje, "error");
        estadoTexto("Error.");
        break;
      default:
        break;
    }
  };

  // ---------- arranque ----------
  function poblarProveedores(lista, actual) {
    const sel = $("proveedor");
    sel.replaceChildren(...lista.map((p) => el("option", { value: p, text: p })));
    sel.value = lista.includes(actual) ? actual : "auto";
  }

  async function iniciar() {
    await esperarApi();
    const datos = await llamar("inicio");
    aplicarTema(datos.tema);
    $("materia").value = datos.materia;
    poblarProveedores(datos.proveedores, datos.config.proveedor);
    $("modelo").value = datos.config.modelo;
    $("clave").value = datos.config.clave;
    $("base-url").value = datos.config.base_url;
    $("recordar").checked = datos.config.recordar;
    crearObjetivos([]);
    cargarConceptos([]);
    cargarResumen([]);
    actualizarChips();
    estadoTexto("Listo.");
  }

  function enlazar() {
    $("btn-tema").addEventListener("click", async () => {
      const nuevo = document.documentElement.dataset.tema === "oscuro" ? "claro" : "oscuro";
      aplicarTema(nuevo);
      await llamar("set_tema", nuevo);
    });

    document.querySelectorAll("[data-paso]").forEach((b) => b.addEventListener("click", () => irA(Number(b.dataset.paso))));
    document.querySelectorAll("[data-ir]").forEach((b) => b.addEventListener("click", () => irA(Number(b.dataset.ir))));

    $("dropzone").addEventListener("click", elegirPdf);
    $("btn-extraer").addEventListener("click", extraer);
    $("btn-redactar").addEventListener("click", redactar);
    $("btn-generar").addEventListener("click", generar);
    $("btn-cargar-json").addEventListener("click", cargarJson);
    $("btn-guardar-json").addEventListener("click", guardarJson);
    $("btn-vaciar").addEventListener("click", vaciar);
    $("btn-add-concepto").addEventListener("click", () => {
      $("tabla-conceptos").append(filaConcepto());
      actualizarChips();
    });
    $("btn-add-seccion").addEventListener("click", () => {
      $("lista-resumen").append(seccionResumen("Nueva sección", []));
      actualizarChips();
    });
    ["descripcion", "palabras", "conclusiones", "bibliografia"].forEach((id) =>
      $(id).addEventListener("input", actualizarChips));

    $("btn-modelos").addEventListener("click", verModelos);
    $("btn-usar-modelo").addEventListener("click", usarModelo);
    $("btn-cerrar-modelos").addEventListener("click", () => $("dlg-modelos").close());

    $("btn-ver-clave").addEventListener("click", (e) => {
      const input = $("clave");
      const oculta = input.type === "password";
      input.type = oculta ? "text" : "password";
      e.currentTarget.textContent = oculta ? "Ocultar" : "Mostrar";
    });

    ["proveedor", "modelo", "clave", "base-url", "recordar"].forEach((id) =>
      $(id).addEventListener(id === "recordar" || id === "proveedor" ? "change" : "input", guardarConfigDiferido));

    $("btn-abrir-salida").addEventListener("click", () => llamar("abrir_salida"));
    $("btn-abrir-docx").addEventListener("click", () => {
      if (estado.ultimoDocx) llamar("abrir_archivo", estado.ultimoDocx);
    });
  }

  enlazar();
  iniciar().catch((e) => toast(`No se pudo iniciar: ${e}`, "error"));
})();
