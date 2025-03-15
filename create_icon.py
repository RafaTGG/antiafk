from PIL import Image, ImageDraw
import os

# Cria um ícone simples
icon_size = 256
icon = Image.new('RGBA', (icon_size, icon_size), color=(0, 0, 0, 0))

# Desenha um círculo azul com borda
draw = ImageDraw.Draw(icon)
draw.ellipse((10, 10, icon_size-10, icon_size-10), fill=(0, 120, 212), outline=(255, 255, 255), width=5)

# Adiciona as iniciais "AFK" no centro
font_size = 120
draw.text((icon_size//2 - font_size//2, icon_size//2 - font_size//2), "AFK", fill=(255, 255, 255), stroke_width=3, stroke_fill=(0, 80, 160))

# Salva como ICO
icon.save("afk_icon.ico", format="ICO")
print("Ícone criado com sucesso!") 