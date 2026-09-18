"""Interfaz grafica (Tkinter) del generador de protocolos.

Flujo en 3 pestanas: 1) definir el modulo PDF, 2) revisar/redactar el
contenido, 3) generar el DOCX. El trabajo pesado (extraccion, IA) corre
en hilos de fondo para no congelar la ventana.
"""
from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from core import ia_client, pdf_utils, protocol_builder, verificador  # noqa: E402

PLANTILLA = BASE / "plantilla" / "Protocolo_Plantilla.docx"
SALIDA = BASE / "salida"
CONFIG_IA = BASE / ".config_ia.json"
ICONO = BASE / "assets" / "iapp.ico"
NOMBRE_ESTUDIANTE = "Gustavo Alonso Díaz Mercado"


def _cargar_config() -> dict:
    """Config guardada de la IA (proveedor/modelo/clave), si existe."""
    try:
        import json
        if CONFIG_IA.exists():
            data = json.loads(CONFIG_IA.read_text(encoding="utf-8"))
            return {k: data[k] for k in ("proveedor", "modelo", "clave", "base_url")
                    if data.get(k)}
    except Exception:
        pass
    return {}


def _guardar_config(proveedor: str, modelo: str, clave: str, base_url: str = "") -> None:
    import json
    CONFIG_IA.write_text(
        json.dumps({"proveedor": proveedor, "modelo": modelo, "clave": clave,
                    "base_url": base_url},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")


class _ScrolledFrame(ttk.Frame):
    """Frame con scrollbar para formularios largos."""

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        barra = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=barra.set)
        self.canvas._sc = self  # marca para el gestor global de rueda
        self.canvas.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._ajustar)
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(
            self.inner_id, width=e.width))

    def _ajustar(self, _e):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def habilitar_rueda(self, widget=None):
        widget = widget or self
        widget.bind("<MouseWheel>", self._on_mousewheel, add="+")


class EditableList(ttk.Frame):
    """Arbol editable de pares clave-valor (conceptos)."""

    def __init__(self, master, columnas, **kw):
        super().__init__(master, **kw)
        self.columnas = columnas
        self.tree = ttk.Treeview(self, columns=columnas, show="headings",
                                 selectmode="browse")
        for c in columnas:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=280)
        self.tree.grid(row=0, column=0, columnspan=3, sticky="nsew")
        botones = ttk.Frame(self)
        botones.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Button(botones, text="+ Añadir", command=self._anadir).pack(side="left")
        ttk.Button(botones, text="Editar", command=self._editar).pack(side="left", padx=4)
        ttk.Button(botones, text="Eliminar", command=self._eliminar).pack(side="left")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._item_edicion = None

    def cargar(self, items):
        self.tree.delete(*self.tree.get_children())
        for item in items:
            self.tree.insert("", "end", values=[item.get(c, "") for c in self.columnas])

    def obtener(self):
        filas = []
        for iid in self.tree.get_children():
            valores = self.tree.item(iid, "values")
            filas.append({c: valores[k] for k, c in enumerate(self.columnas)})
        return filas

    def _seleccion(self):
        iid = self.tree.selection()
        return (self.tree.item(iid[0], "values") if iid else None)

    def _dialogo(self, titulo, valores_iniciales):
        win = tk.Toplevel(self)
        win.title(titulo)
        win.transient(self.winfo_toplevel())
        win.grab_set()
        campos = []
        for k, c in enumerate(self.columnas):
            ttk.Label(win, text=c).grid(row=k, column=0, sticky="w", padx=6, pady=4)
            var = tk.StringVar(value=valores_iniciales[k] if valores_iniciales else "")
            entry = ttk.Entry(win, textvariable=var, width=50)
            entry.grid(row=k, column=1, padx=6, pady=4)
            campos.append(var)
        resultado = {}

        def aceptar():
            resultado.update({c: v.get() for c, v in zip(self.columnas, campos)})
            win.destroy()
        win.bind("<Return>", lambda _e: aceptar())
        ttk.Button(win, text="Aceptar", command=aceptar).grid(
            row=len(self.columnas), column=1, sticky="e", padx=6, pady=6)
        win.wait_window()
        return resultado

    def _anadir(self):
        vals = self._dialogo(f"Añadir: {', '.join(self.columnas)}", None)
        if vals:
            self.tree.insert("", "end", values=[vals[c] for c in self.columnas])

    def _editar(self):
        sel = self._seleccion()
        if not sel:
            return
        vals = self._dialogo(f"Editar item", list(sel))
        if vals:
            iid = self.tree.selection()[0]
            self.tree.item(iid, values=[vals[c] for c in self.columnas])

    def _eliminar(self):
        for iid in self.tree.selection():
            self.tree.delete(iid)


class ResumenEditor(ttk.Frame):
    """Secciones de resumen: lista de subtitulos + area de parrafos."""

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.tree = ttk.Treeview(self, columns=("subtitulo",), show="headings",
                                 selectmode="browse", height=4)
        self.tree.heading("subtitulo", text="Subtítulo de la sección")
        self.tree.column("subtitulo", width=420)
        barra = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=barra.set)
        self.tree.grid(row=0, column=0, columnspan=2, sticky="nsew")
        barra.grid(row=0, column=2, sticky="ns")
        fila_botones = ttk.Frame(self)
        fila_botones.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Button(fila_botones, text="+ Sección", command=self._anadir).pack(side="left")
        ttk.Button(fila_botones, text="Renombrar", command=self._renombrar).pack(side="left", padx=4)
        ttk.Button(fila_botones, text="Eliminar", command=self._eliminar).pack(side="left")
        ttk.Label(self, text="Párrafos de la sección (uno por línea):").grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(6, 2))
        self.texto = tk.Text(self, height=5, wrap="word", font=("Segoe UI", 10))
        self.texto.grid(row=3, column=0, columnspan=3, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self._cargar_texto)
        self._indice = None

    def guardar_actual(self):
        if self._indice is not None and self.tree.exists(self._indice):
            self._data[self._indice]["parrafos"] = self._para_lista()

    def cargar(self, secciones):
        self.guardar_actual()
        self.tree.delete(*self.tree.get_children())
        self._data = {}
        for s in secciones:
            self._agregar_fila(s["subtitulo"], s.get("parrafos", []))

    def obtener(self):
        self.guardar_actual()
        return [
            {"subtitulo": fila["subtitulo"], "parrafos": list(fila["parrafos"])}
            for fila in self._data.values()
        ]

    def _para_lista(self):
        texto = self.texto.get("1.0", "end")
        return [ln.strip() for ln in texto.splitlines() if ln.strip()]

    def _agregar_fila(self, subtitulo, parrafos):
        iid = self.tree.insert("", "end", values=[subtitulo])
        self._data[iid] = {"subtitulo": subtitulo, "parrafos": list(parrafos)}
        return iid

    def _cargar_texto(self, _e):
        self.guardar_actual()
        self._indice = self.tree.selection()[0] if self.tree.selection() else None
        if self._indice:
            self.texto.delete("1.0", "end")
            self.texto.insert("1.0", "\n".join(self._data[self._indice]["parrafos"]))

    def _anadir(self):
        iid = self._agregar_fila("Nueva sección", [])
        self.tree.selection_set(iid)
        self._cargar_texto(None)

    def _renombrar(self):
        if not self.tree.selection():
            return
        iid = self.tree.selection()[0]
        var = tk.StringVar(value=self._data[iid]["subtitulo"])
        win = tk.Toplevel(self)
        win.title("Renombrar sección")
        win.transient(self.winfo_toplevel())
        ttk.Entry(win, textvariable=var, width=40).pack(padx=8, pady=8)
        def ok():
            self._data[iid]["subtitulo"] = var.get()
            self.tree.item(iid, values=[var.get()])
            win.destroy()
        ttk.Button(win, text="Aceptar", command=ok).pack(pady=(0, 8))
        win.grab_set()

    def _eliminar(self):
        for iid in self.tree.selection():
            self._data.pop(iid, None)
            self.tree.delete(iid)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Generador de Protocolos — Diseño De Sitio Web")
        self.geometry("880x700")
        self.minsize(760, 560)

        self.texto_modulo = ""
        self.usado_ocr = False
        self.cola = queue.Queue()
        self._hilos = []
        self._config = _cargar_config()

        ttk.Label(self, text="Generador de Protocolos Individuales",
                  font=("Segoe UI", 15, "bold")).pack(pady=(10, 2))
        ttk.Label(self, text="Modulo PDF  ->  redaccion (IA u manual)  ->  DOCX identico a la plantilla",
                  foreground="#555").pack(pady=(0, 8))

        self.pestanas = ttk.Notebook(self)
        self.pestanas.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self._crear_tab_modulo()
        self._crear_tab_contenido()
        self._crear_tab_generar()

        self.estado = ttk.Label(self, text="Listo.", anchor="w", relief="sunken",
                                padding=(6, 3))
        self.estado.pack(fill="x", side="bottom")

        self.protocol("WM_DELETE_WINDOW", self._al_cerrar)
        self.after(100, self._procesar_cola)
        self.bind_all("<MouseWheel>", self._rueda_global, add="+")

    def _rueda_global(self, event):
        """Scrolla el formulario sobre el que esta el cursor, sin pisar el
        scroll nativo de textos y listas."""
        widget = self.winfo_containing(event.x_root, event.y_root)
        if widget is None:
            return
        if isinstance(widget, (tk.Text, ttk.Treeview)):
            return  # esos ya scrollean su propio contenido
        sc = getattr(widget, "_sc", None)
        while widget is not None and sc is None:
            widget = widget.master
            sc = getattr(widget, "_sc", None)
        if sc is not None:
            sc._on_mousewheel(event)

    def _al_cerrar(self):
        self._guardar_config_si_pide()
        self.destroy()

    # ---------- Pestana 1: modulo ----------
    def _crear_tab_modulo(self):
        tab = ttk.Frame(self.pestanas, padding=14)
        self.pestanas.add(tab, text="  1. Módulo  ")

        ttk.Label(tab, text="Módulo (PDF de la unidad):").pack(anchor="w")
        fila = ttk.Frame(tab)
        fila.pack(fill="x", pady=(2, 8))
        self.ruta_modulo = tk.StringVar()
        ttk.Entry(fila, textvariable=self.ruta_modulo).pack(side="left", fill="x", expand=True)
        ttk.Button(fila, text="Seleccionar…", command=self._seleccionar_modulo).pack(side="left", padx=6)

        fila2 = ttk.Frame(tab)
        fila2.pack(fill="x", pady=(0, 8))
        ttk.Label(fila2, text="Unidad:").pack(side="left")
        self.unidad = tk.IntVar(value=1)
        ttk.Spinbox(fila2, from_=1, to=30, textvariable=self.unidad, width=5).pack(side="left", padx=4)
        ttk.Label(fila2, text="(se deduce del nombre 'Modulo N.pdf'; puedes cambiarlo)", foreground="#777").pack(side="left")

        fila3 = ttk.Frame(tab)
        fila3.pack(fill="x", pady=(0, 8))
        ttk.Label(fila3, text="Materia:").pack(side="left")
        self.materia = tk.StringVar(value=protocol_builder.MATERIA_POR_DEFECTO)
        ttk.Entry(fila3, textvariable=self.materia).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Label(fila3, text="(aparece en el título del documento y en el nombre del archivo)",
                  foreground="#777").pack(side="left")

        self.btn_extraer = ttk.Button(tab, text="Extraer texto del módulo", command=self._extraer_texto)
        self.btn_extraer.pack(anchor="w", pady=(0, 6))

        ttk.Label(tab, text="Vista previa del texto extraído:").pack(anchor="w")
        self.texto_vista = tk.Text(tab, height=14, wrap="word", state="disabled",
                                   font=("Consolas", 9))
        self.texto_vista.pack(fill="both", expand=True)

    def _seleccionar_modulo(self):
        ruta = filedialog.askopenfilename(
            title="Selecciona el módulo en PDF",
            filetypes=[("PDF", "*.pdf")])
        if not ruta:
            return
        self.ruta_modulo.set(ruta)
        unidad = pdf_utils.deducir_unidad(ruta)
        if unidad:
            self.unidad.set(unidad)

    def _extraer_texto(self):
        ruta = self.ruta_modulo.get()
        if not ruta or not Path(ruta).exists():
            messagebox.showerror("Módulo", "Selecciona primero el PDF del módulo.")
            return
        self.btn_extraer.configure(state="disabled")
        self._estado("Extrayendo texto del PDF…")
        self._async(self._run_extraer, ruta)

    def _run_extraer(self, ruta):
        texto, ocr = pdf_utils.extraer_texto(ruta)
        self.cola.put(("extraido", texto, ocr))

    # ---------- Pestana 2: contenido ----------
    def _crear_tab_contenido(self):
        contenedor = ttk.Frame(self.pestanas)
        self.pestanas.add(contenedor, text="  2. Revisar contenido  ")

        barra = ttk.Frame(contenedor, padding=(10, 6))
        barra.pack(fill="x")
        self.btn_ia = ttk.Button(barra, text="Redactar con IA", command=self._redactar_contenido)
        self.btn_ia.pack(side="left")
        ttk.Button(barra, text="Usar contenido ya redactado (.json)", command=self._cargar_json).pack(side="left", padx=6)
        ttk.Button(barra, text="Guardar JSON", command=self._guardar_json).pack(side="left", padx=6)
        ttk.Button(barra, text="Vaciar formulario", command=self._vaciar).pack(side="left", padx=6)

        sc = _ScrolledFrame(contenedor)
        sc.pack(fill="both", expand=True)
        f = sc.inner
        f.columnconfigure(0, weight=1)
        fila = [0]

        def titulo(texto):
            ttk.Label(f, text=texto, font=("Segoe UI", 10, "bold")).grid(
                row=fila[0], column=0, sticky="w", pady=(8, 3))
            fila[0] += 1

        def siguiente():
            r = fila[0]
            fila[0] += 1
            return r

        titulo("Descripción del texto")
        self.descripcion = tk.Text(f, height=4, wrap="word", font=("Segoe UI", 10))
        self.descripcion.grid(row=siguiente(), column=0, sticky="nsew")

        titulo("Palabras clave (separadas por comas)")
        self.palabras = tk.StringVar()
        ttk.Entry(f, textvariable=self.palabras).grid(row=siguiente(), column=0, sticky="nsew")

        titulo("Objetivos de las lecturas (3)")
        self.objetivos = [tk.StringVar() for _ in range(3)]
        for var in self.objetivos:
            ttk.Entry(f, textvariable=var).grid(row=siguiente(), column=0, sticky="nsew")

        titulo("Conceptos clave y definiciones")
        self.conceptos = EditableList(f, ("termino", "definicion"))
        self.conceptos.grid(row=siguiente(), column=0, sticky="nsew")
        self.conceptos.rowconfigure(0, weight=0)

        titulo("Resumen de las lecturas")
        self.resumen = ResumenEditor(f)
        self.resumen.grid(row=siguiente(), column=0, sticky="nsew")

        titulo("Conclusiones de la lectura")
        self.conclusiones = tk.Text(f, height=4, wrap="word", font=("Segoe UI", 10))
        self.conclusiones.grid(row=siguiente(), column=0, sticky="nsew")

        titulo("Bibliografía (una fuente por línea, máx. 5)")
        self.bibliografia = tk.Text(f, height=4, wrap="word", font=("Segoe UI", 10))
        self.bibliografia.grid(row=siguiente(), column=0, sticky="nsew")

    # ---------- Pestana 3: generar ----------
    def _crear_tab_generar(self):
        tab = ttk.Frame(self.pestanas, padding=14)
        self.pestanas.add(tab, text="  3. Generar  ")

        cfg = ttk.LabelFrame(tab, text=" Configuración de la IA (opcional si ya redactaste) ", padding=10)
        cfg.pack(fill="x")
        g = ttk.Frame(cfg)
        g.pack(fill="x")
        ttk.Label(g, text="Proveedor:").grid(row=0, column=0, sticky="w")
        self.proveedor = tk.StringVar(value=self._config.get("proveedor", "auto"))
        ttk.Combobox(g, textvariable=self.proveedor, state="readonly", width=16,
                     values=("auto", "openai", "openrouter", "groq",
                             "google", "personalizado")).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(g, text="Modelo:").grid(row=0, column=2, sticky="w")
        self.modelo = tk.StringVar(value=self._config.get("modelo", ""))
        ttk.Entry(g, textvariable=self.modelo, width=20).grid(row=0, column=3, sticky="w", padx=6)
        ttk.Button(g, text="Ver modelos", width=12, command=self._ver_modelos).grid(
            row=0, column=4, sticky="w", padx=6)
        ttk.Label(g, text="Clave API:").grid(row=0, column=5, sticky="w")
        self.clave = tk.StringVar(value=self._config.get("clave", ""))
        ttk.Entry(g, textvariable=self.clave, width=20, show="*").grid(row=0, column=6, sticky="w", padx=6)

        ttk.Label(g, text="URL base (solo 'personalizado'):").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.base_url = tk.StringVar(value=self._config.get("base_url", ""))
        ttk.Entry(g, textvariable=self.base_url, width=42).grid(row=1, column=1, columnspan=3, sticky="w", padx=6, pady=(6, 0))
        self.recordar = tk.BooleanVar(value=bool(self._config.get("clave")))
        ttk.Checkbutton(cfg, text="Recordar clave para próximas sesiones (se guarda en "
                                  "generador\\.config_ia.json, solo local)",
                        variable=self.recordar,
                        command=self._guardar_config_si_pide).pack(anchor="w", pady=(4, 0))
        ttk.Label(cfg, text="auto = OPENROUTER_API_KEY, OPENAI_API_KEY, GROQ_API_KEY o GEMINI_API_KEY "
                            "del entorno, o la clave guardada aquí. "
                            "Groq y Gemini (Google AI Studio) tienen nivel gratuito.",
                  foreground="#777", wraplength=820, justify="left").pack(anchor="w", pady=(4, 0))

        ttk.Label(tab, text="Registro de ejecución:").pack(anchor="w", pady=(10, 2))
        self.log = tk.Text(tab, height=10, wrap="word", state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)
        self.log.tag_configure("ok", foreground="#1a7f37")
        self.log.tag_configure("err", foreground="#c62828")

        botones = ttk.Frame(tab)
        botones.pack(fill="x", pady=(10, 0))
        self.btn_generar = ttk.Button(botones, text="Generar protocolo (DOCX)", command=self._generar)
        self.btn_generar.pack(side="left", padx=(0, 8))
        ttk.Button(botones, text="Abrir carpeta de salida",
                   command=self._abrir_salida).pack(side="left")

    # ---------- logica ----------
    def _estado(self, msg):
        self.estado.configure(text=msg)
        self.update_idletasks()

    def _log(self, msg, tag=""):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _async(self, fn, *args):
        hilo = threading.Thread(target=fn, args=args, daemon=True)
        hilo.start()
        self._hilos.append(hilo)

    def _redactar_contenido(self):
        if not self.texto_modulo:
            messagebox.showwarning("Contenido", "Primero extrae el texto del módulo en la pestaña 1.")
            self.pestanas.select(0)
            return
        self.btn_ia.configure(state="disabled")
        self._estado("Redactando contenido con IA…")
        self._async(self._run_ia)

    def _run_ia(self):
        unidad = self.unidad.get()
        materia = self.materia.get().strip() or protocol_builder.MATERIA_POR_DEFECTO
        texto = self.texto_modulo
        biblio = pdf_utils.extraer_bibliografia(texto)
        proveedor = self.proveedor.get()
        if proveedor == "personalizado":
            proveedor = None
        try:
            contenido = ia_client.redactar_contenido(
                texto, unidad, biblio,
                proveedor=proveedor if proveedor != "auto" else None,
                modelo=self.modelo.get() or None,
                clave=self.clave.get() or None,
                base_url=self.base_url.get().strip() or None,
                path_plantilla=str(PLANTILLA),
                materia=materia,
                progreso=lambda m: self.cola.put(("log", m)),
            )
        except ia_client.ErrorSinClave as e:
            self.cola.put(("log_err", str(e)))
            self.cola.put(("falta_clave", str(e)))
            return
        except Exception as e:
            self.cola.put(("log_err", f"Error de IA: {e}"))
            self.cola.put(("error", f"Error de IA: {e}"))
            return
        self.cola.put(("contenido", contenido))

    def _ver_modelos(self):
        self._estado("Consultando modelos disponibles…")
        self._async(self._run_modelos, self.proveedor.get(),
                    self.clave.get(), self.base_url.get().strip() or None)

    def _run_modelos(self, proveedor, clave, base_url):
        if proveedor == "personalizado":
            proveedor = None
        try:
            nombres = ia_client.lista_modelos(
                proveedor if proveedor != "auto" else None,
                clave=clave or None,
                base_url=base_url)
            self.cola.put(("modelos", nombres))
        except Exception as e:
            self.cola.put(("modelos_error", f"Error al listar modelos: {e}"))

    def _mostrar_modelos(self, nombres):
        win = tk.Toplevel(self)
        win.title("Modelos disponibles")
        win.transient(self.winfo_toplevel())
        win.grab_set()
        ttk.Label(win, text=f"{len(nombres)} modelos disponibles. "
                            "Selecciona uno o cierra:").pack(anchor="w", padx=8, pady=(8, 4))
        frame = ttk.Frame(win)
        frame.pack(fill="both", expand=True, padx=8)
        lista = tk.Listbox(frame, width=60, height=15, font=("Consolas", 10))
        barra = ttk.Scrollbar(frame, orient="vertical", command=lista.yview)
        lista.configure(yscrollcommand=barra.set)
        lista.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        for nombre in nombres:
            lista.insert("end", nombre)

        def usar():
            sel = lista.curselection()
            if sel:
                self.modelo.set(lista.get(sel[0]))
                self._guardar_config_si_pide()
                win.destroy()

        botones = ttk.Frame(win)
        botones.pack(fill="x", padx=8, pady=(4, 8))
        ttk.Button(botones, text="Usar este modelo", command=usar).pack(side="left")
        ttk.Button(botones, text="Cerrar", command=win.destroy).pack(side="left", padx=6)
        lista.bind("<Double-1>", lambda _e: usar())

    def _generar(self):
        try:
            contenido = self._contenido_desde_formulario()
            protocol_builder.validar_contenido(contenido)
        except ValueError as e:
            messagebox.showerror("Contenido incompleto", str(e))
            return
        self.btn_generar.configure(state="disabled")
        self._estado("Generando protocolo…")
        self._async(self._run_generar, contenido)

    def _run_generar(self, contenido):
        unidad = self.unidad.get()
        materia = self.materia.get().strip() or protocol_builder.MATERIA_POR_DEFECTO
        nombre = f"Protocolo Individual - {unidad}° Unidad - {materia} - {NOMBRE_ESTUDIANTE}.docx"
        salida = SALIDA / self._nombre_seguro(nombre)
        try:
            self.cola.put(("log", f"Ensamblando DOCX (unidad {unidad}, {materia})…"))
            ruta = protocol_builder.build_protocol(str(PLANTILLA), contenido, str(salida), unidad, materia)
            self.cola.put(("log", f"DOCX generado: {Path(ruta).name}"))
            self.cola.put(("log", "Verificando formato…"))
            errores = verificador.verificar(ruta, materia=materia)
            if errores:
                for e in errores:
                    self.cola.put(("log_err", "  - " + e))
                self.cola.put(("error", "El DOCX se generó pero la verificación encontró problemas."))
            else:
                self.cola.put(("log_ok", "Verificación OK: formato idéntico a la plantilla."))
                self.cola.put(("listo", str(salida)))
        except Exception as e:
            self.cola.put(("log_err", f"Error al generar: {e}"))
            self.cola.put(("error", f"Error al generar: {e}"))

    def _contenido_desde_formulario(self):
        self.resumen.guardar_actual()
        return {
            "descripcion": self.descripcion.get("1.0", "end").strip(),
            "palabras_claves": self.palabras.get().strip(),
            "objetivos": [v.get().strip() for v in self.objetivos if v.get().strip()],
            "conceptos": self.conceptos.obtener(),
            "resumen": self.resumen.obtener(),
            "conclusiones": self.conclusiones.get("1.0", "end").strip(),
            "bibliografia": "\n".join(
                ln.strip() for ln in self.bibliografia.get("1.0", "end").splitlines() if ln.strip()),
        }

    def _llenar_formulario(self, contenido):
        self.descripcion.delete("1.0", "end")
        self.descripcion.insert("1.0", contenido.get("descripcion", ""))
        self.palabras.set(contenido.get("palabras_claves", ""))
        objs = contenido.get("objetivos", []) or []
        for i, var in enumerate(self.objetivos):
            var.set(objs[i] if i < len(objs) else "")
        self.conceptos.cargar(contenido.get("conceptos", []))
        self.resumen.cargar(contenido.get("resumen", []))
        self.conclusiones.delete("1.0", "end")
        self.conclusiones.insert("1.0", contenido.get("conclusiones", ""))
        self.bibliografia.delete("1.0", "end")
        self.bibliografia.insert("1.0", contenido.get("bibliografia", ""))

    def _cargar_json(self):
        ruta = filedialog.askopenfilename(title="Contenido del protocolo",
                                          filetypes=[("JSON", "*.json")])
        if not ruta:
            return
        try:
            import json
            with open(ruta, encoding="utf-8") as f:
                contenido = json.load(f)
            self._llenar_formulario(contenido)
        except Exception as e:
            messagebox.showerror("JSON", f"No se pudo leer el JSON: {e}")

    def _guardar_json(self):
        ruta = filedialog.asksaveasfilename(title="Guardar contenido",
                                            defaultextension=".json",
                                            filetypes=[("JSON", "*.json")])
        if not ruta:
            return
        try:
            import json
            contenido = self._contenido_desde_formulario()
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump(contenido, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror("JSON", f"No se pudo guardar: {e}")

    def _vaciar(self):
        self.descripcion.delete("1.0", "end")
        self.palabras.set("")
        for var in self.objetivos:
            var.set("")
        self.conceptos.tree.delete(*self.conceptos.tree.get_children())
        self.resumen.cargar([])
        self.conclusiones.delete("1.0", "end")
        self.bibliografia.delete("1.0", "end")

    def _abrir_salida(self):
        import os
        SALIDA.mkdir(exist_ok=True)
        os.startfile(str(SALIDA))

    def _nombre_seguro(self, nombre: str) -> str:
        import re
        nombre = re.sub(r'[\\/:*?"<>|]', " ", nombre).strip()
        return nombre or "Protocolo.docx"

    def _guardar_config_si_pide(self):
        if getattr(self, "recordar", None) and self.recordar.get():
            try:
                _guardar_config(self.proveedor.get(), self.modelo.get(),
                                self.clave.get(), self.base_url.get().strip())
            except Exception:
                pass
        else:
            try:
                if CONFIG_IA.exists():
                    CONFIG_IA.unlink()
            except Exception:
                pass

    def _procesar_cola(self):
        try:
            while True:
                evento = self.cola.get_nowait()
                etiqueta = evento[0]
                if etiqueta == "log":
                    self._log(evento[1])
                elif etiqueta == "log_ok":
                    self._log(evento[1], "ok")
                elif etiqueta == "log_err":
                    self._log(evento[1], "err")
                elif etiqueta == "extraido":
                    _, texto, ocr = evento
                    self.texto_modulo = texto
                    self.usado_ocr = ocr
                    self._mostrar_vista(texto, ocr)
                    self._log("Texto extraído del módulo.")
                elif etiqueta == "contenido":
                    self._llenar_formulario(evento[1])
                    self.btn_ia.configure(state="normal")
                    self._log("Contenido redactado y cargado en la pestaña 2. Revísalo antes de generar.",
                              "ok")
                elif etiqueta == "modelos":
                    self._mostrar_modelos(evento[1])
                    self._estado("Listo.")
                elif etiqueta == "modelos_error":
                    self._estado("Error.")
                    messagebox.showerror("Modelos", evento[1])
                elif etiqueta == "falta_clave":
                    self.btn_ia.configure(state="normal")
                    self._estado("Sin clave de API.")
                    self.pestanas.select(2)
                    messagebox.showinfo(
                        "Clave de API necesaria",
                        "Para redactar con IA hace falta una clave.\n\n"
                        "1. Ve a la pestaña '3. Generar'.\n"
                        "2. Pega tu clave en 'Clave API' (o define OPENAI_API_KEY u "
                        "OPENROUTER_API_KEY como variable de entorno).\n"
                        "3. Marca 'Recordar clave para próximas sesiones' para no "
                        "repetirlo.\n\n"
                        "Si no tienes clave, puedes redactar el contenido a mano en "
                        "la pestaña 2 y generar igualmente.")
                elif etiqueta == "error":
                    self.btn_extraer.configure(state="normal")
                    self.btn_ia.configure(state="normal")
                    self.btn_generar.configure(state="normal")
                    self._estado("Error.")
                elif etiqueta == "listo":
                    self.btn_generar.configure(state="normal")
                    self._estado("Protocolo generado correctamente.")
                    if messagebox.askyesno("Listo", "¿Abrir el DOCX generado?"):
                        import os
                        os.startfile(evento[1])
        except queue.Empty:
            pass
        self.after(100, self._procesar_cola)

    def _mostrar_vista(self, texto, ocr):
        self.texto_vista.configure(state="normal")
        self.texto_vista.delete("1.0", "end")
        sufijo = "  [OCR: PDF escaneado reconocido]" if ocr else ""
        self.texto_vista.insert("1.0",
            f"{(len(texto))} caracteres extraídos{sufijo}\n\n" + texto[:600])
        self.texto_vista.configure(state="disabled")


def main():
    app = App()
    try:
        if ICONO.exists():
            app.iconbitmap(str(ICONO))
    except Exception:
        pass  # icono opcional; no debe tumbar la app
    app.mainloop()


if __name__ == "__main__":
    main()