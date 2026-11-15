import os
import base64
from PIL import Image

src_path = r'C:/Users/Doniyor/.gemini/antigravity/brain/d3303df3-b596-4f0b-b111-31a8c10ebf1d/.user_uploaded/media_1794776377657_0600612a.png'
im = Image.open(src_path).convert('RGBA')

out_dir = r'static/icons'
os.makedirs(out_dir, exist_ok=True)

# 1. logo.png (Original transparent 628x628)
logo_path = os.path.join(out_dir, 'logo.png')
im.save(logo_path, 'PNG')
print("Saved logo.png")

# 2. icon-512.png
im_512 = im.resize((512, 512), Image.Resampling.LANCZOS)
im_512.save(os.path.join(out_dir, 'icon-512.png'), 'PNG')
print("Saved icon-512.png")

# 3. icon-192.png
im_192 = im.resize((192, 192), Image.Resampling.LANCZOS)
im_192.save(os.path.join(out_dir, 'icon-192.png'), 'PNG')
print("Saved icon-192.png")

# 4. Maskable 512x512
maskable_512 = Image.new('RGBA', (512, 512), (11, 15, 25, 255))
im_scaled_512 = im.resize((400, 400), Image.Resampling.LANCZOS)
maskable_512.paste(im_scaled_512, (56, 56), im_scaled_512)
maskable_512.save(os.path.join(out_dir, 'icon-maskable-512.png'), 'PNG')
print("Saved icon-maskable-512.png")

# 5. Maskable 192x192
maskable_192 = Image.new('RGBA', (192, 192), (11, 15, 25, 255))
im_scaled_192 = im.resize((150, 150), Image.Resampling.LANCZOS)
maskable_192.paste(im_scaled_192, (21, 21), im_scaled_192)
maskable_192.save(os.path.join(out_dir, 'icon-maskable-192.png'), 'PNG')
print("Saved icon-maskable-192.png")

# 6. Favicon 48x48 and 32x32
im_48 = im.resize((48, 48), Image.Resampling.LANCZOS)
im_48.save(os.path.join(out_dir, 'favicon.png'), 'PNG')

# 7. SVG wrapper
with open(os.path.join(out_dir, 'icon-512.png'), 'rb') as f:
    b64_str = base64.b64encode(f.read()).decode('utf-8')

svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="100%" height="100%">
  <image href="data:image/png;base64,{b64_str}" width="512" height="512" />
</svg>'''

with open(os.path.join(out_dir, 'icon.svg'), 'w', encoding='utf-8') as f:
    f.write(svg_content)
print("Saved icon.svg")
