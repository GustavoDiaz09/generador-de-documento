"""Genera el icono de la app: documento con lapiz y la sigla "IaP".

Diseno premium flat: fondo degradado con brillo, hoja con sombra y doblez,
lapiz realista con degradado, chip con la sigla.
Salida: assets/iapp.ico (tamanyos 256..16) y assets/iapp.png (256 px).
Uso:  python generador/assets/crear_icono.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

S = 512
OUT = Path(__file__).resolve().parent


def fuente(tam: int) -> ImageFont.FreeTypeFont:
    for ruta in ("C:/Windows/Fonts/segoeuib.ttf",
                 "C:/Windows/Fonts/segoeuil.ttf",
                 "C:/Windows/Fonts/arialbd.ttf"):
        if Path(ruta).exists():
            return ImageFont.truetype(ruta, tam)
    return ImageFont.load_default()


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def redondeado(size, radio, color):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1),
                                          radio, fill=color)
    return img


def fondo_gradiente():
    img = Image.new("RGB", (S, S), (0, 0, 0))
    d = ImageDraw.Draw(img)
    c1, c2 = (52, 47, 138), (129, 60, 245)   # indigo -> violeta
    for y in range(S):
        for x in range(S):
            t = (x + y) / (2 * (S - 1))
            d.point((x, y), fill=lerp(c1, c2, t))
    mascara = redondeado((S, S), 108, "white")
    fondo = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    fondo.paste(img, (0, 0), mascara)
    # brillo superior izquierdo (gloss)
    brillo = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bd = ImageDraw.Draw(brillo)
    bd.ellipse((-160, -200, 460, 380), fill=(255, 255, 255, 34))
    bd.ellipse((-120, -150, 360, 300), fill=(255, 255, 255, 22))
    fondo.alpha_composite(brillo, (0, 0))
    # vineta en bordes inferiores
    vin = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(vin).ellipse((-240, 360, 760, 760), fill=(18, 10, 50, 120))
    fondo.alpha_composite(vin, (0, 0))
    # borde
    ImageDraw.Draw(fondo).rounded_rectangle((0, 0, S - 1, S - 1), 108,
                                            outline=(26, 22, 66, 255), width=8)
    return fondo


def hoja_documento():
    """Hoja con sombra ligera hacia el interior, raya de titulo y cuerpo."""
    capa = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    x0, y0, x1, y1 = 62, 118, 462, 402
    r = 24
    # borde inferior/fondo de la hoja (sombra suave hacia abajo)
    d.rounded_rectangle((x0 + 8, y0 + 14, x1 + 8, y1 + 14), r,
                        fill=(30, 26, 80, 70))
    # hoja
    d.rounded_rectangle((x0, y0, x1, y1), r, fill=(255, 255, 255, 255),
                        outline=(227, 233, 243, 255), width=4)
    # doblez de esquina (arriba-izquierda)
    d.polygon([(x0, y0 + 64), (x0, y0), (x0 + 64, y0)],
              fill=(244, 247, 251, 255))
    d.line([(x0, y0 + 64), (x0 + 64, y0)], fill=(214, 224, 240, 255), width=4)
    d.line([(x0 + 10, y0 + 64), (x0 + 64, y0 + 10)], fill=(255, 255, 255, 255),
           width=3)
    # titulo (barra de titulo + cuerpo de texto)
    d.rounded_rectangle((x0 + 34, y0 + 30, x1 - 34, y0 + 50), 10,
                        fill=(49, 46, 129, 255))
    for i, ancho in enumerate((170, 130, 150, 95)):
        xd = x1 - 96
        d.rounded_rectangle((xd - ancho, y0 + 62 + i * 26, xd,
                             y0 + 62 + i * 26 + 12), 6,
                            fill=(226, 232, 240, 255))
    # chip con la sigla
    cx0, cy0, cx1, cy1 = 70, 300, 258, 384
    ImageDraw.Draw(capa).rounded_rectangle((cx0 + 6, cy0 + 8, cx1 + 6, cy1 + 8),
                                           18, fill=(30, 26, 80, 60))
    d.rounded_rectangle((cx0, cy0, cx1, cy1), 18, fill=(255, 255, 255, 255),
                        outline=(226, 232, 240, 255), width=3)
    # barra de acento violeta a la izquierda del texto
    d.rounded_rectangle((cx0 + 20, cy0 + 24, cx0 + 28, cy0 + 60), 4,
                        fill=(129, 60, 245, 255))
    d.text(((cx0 + cx1) / 2 + 8, (cy0 + cy1) / 2), "IaP", font=fuente(84),
           fill=(30, 41, 59, 255), anchor="mm")
    return capa


def lapiz():
    """Lapiz horizontal (punta a la izquierda) con degradado, rotado 45 grados."""
    L, H = 440, 108
    pad, topad = 320, 140
    capa = Image.new("RGBA", (L + 2 * pad, H + 2 * topad), (0, 0, 0, 0))
    x0 = -L // 2 + pad
    y0 = -H // 2 + topad
    d = ImageDraw.Draw(capa)
    # goma
    d.rounded_rectangle((x0 + 168, y0 + 20, x0 + 220, y0 + 88), 18,
                        fill=(252, 165, 205, 255))
    d.rounded_rectangle((x0 + 168, y0 + 20, x0 + 206, y0 + 88), 18,
                        fill=(236, 123, 179, 255))
    # virola metalica con brillo
    d.rectangle((x0 + 150, y0 + 20, x0 + 196, y0 + 88), fill=(190, 200, 214, 255))
    d.rectangle((x0 + 150, y0 + 20, x0 + 196, y0 + 42), fill=(226, 232, 240, 255))
    for i in range(3):
        d.line([(x0 + 158 + i * 12, y0 + 20), (x0 + 158 + i * 12, y0 + 88)],
               fill=(120, 132, 152, 255), width=3)
    # cuerpo del lapiz (degradado)
    for dy in range(68):
        t = dy / 67
        d.line([(x0 + 34, y0 + 20 + dy), (x0 + 164, y0 + 20 + dy)],
               fill=lerp((250, 200, 90), (196, 118, 6), t), width=1)
    # borde inferior del cuerpo
    d.line([(x0 + 34, y0 + 86), (x0 + 164, y0 + 86)],
           fill=(150, 84, 6, 255), width=2)
    # cono de madera
    d.polygon([(x0 + 34, y0 + 20), (x0 + 34, y0 + 88),
               (x0 - 16, y0 + 66), (x0 - 46, y0 + 54), (x0 - 16, y0 + 42)],
              fill=(250, 214, 150, 255))
    d.polygon([(x0 + 34, y0 + 20), (x0 - 16, y0 + 42), (x0 - 46, y0 + 54),
               (x0 - 16, y0 + 50)], fill=(226, 172, 96, 255))
    # punta de grafito con brillo
    d.polygon([(x0 - 16, y0 + 44), (x0 - 16, y0 + 64), (x0 - 60, y0 + 54)],
              fill=(30, 41, 59, 255))
    d.line([(x0 - 22, y0 + 48), (x0 - 50, y0 + 53)],
           fill=(120, 132, 152, 200), width=3)
    capa = capa.crop(capa.getbbox())
    return capa.rotate(45, resample=Image.BICUBIC, expand=True)


def centrar_rotado(capa):
    """Recorta el contenido y lo centra en un lienzo de S x S."""
    capa = capa.crop(capa.getbbox())
    lienzo = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    lienzo.alpha_composite(capa, ((S - capa.width) // 2, (S - capa.height) // 2))
    return lienzo


def construir():
    fondo = fondo_gradiente()

    # sombra de la hoja (misma rotacion)
    sombra = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(sombra).rounded_rectangle((78, 134, 476, 414), 24,
                                             fill=(16, 10, 44, 160))
    sombra = sombra.filter(ImageFilter.GaussianBlur(6))
    sombra = centrar_rotado(sombra.rotate(-6, resample=Image.BICUBIC, expand=True))
    fondo.alpha_composite(sombra, (8, 12))

    hoja = centrar_rotado(
        hoja_documento().rotate(-6, resample=Image.BICUBIC, expand=True))
    fondo.alpha_composite(hoja, (0, 0))

    lpz = centrar_rotado(lapiz())
    fondo.alpha_composite(lpz, (0, 2))

    ico = fondo.resize((256, 256), Image.LANCZOS)
    ico.save(OUT / "iapp.png")
    ico.save(OUT / "iapp.ico",
             sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print("Icono generado:", OUT / "iapp.ico")


if __name__ == "__main__":
    construir()