import pathlib
from PIL import Image

def main():
    assets_dir = pathlib.Path("msix_layout/Assets")
    assets_dir.mkdir(parents=True, exist_ok=True)

    # Use the 256x256 icon as a base
    base_img_path = pathlib.Path("images/icon_256.png")
    if not base_img_path.exists():
        print("Run generate_icon.py first!")
        return

    base_img = Image.open(base_img_path).convert("RGBA")

    # StoreLogo.png (50x50)
    base_img.resize((50, 50), Image.Resampling.LANCZOS).save(assets_dir / "StoreLogo.png")
    
    # Square150x150Logo.png
    base_img.resize((150, 150), Image.Resampling.LANCZOS).save(assets_dir / "Square150x150Logo.png")
    
    # Square44x44Logo.png
    base_img.resize((44, 44), Image.Resampling.LANCZOS).save(assets_dir / "Square44x44Logo.png")

    # SplashScreen.png (620x300 - place icon in middle)
    splash = Image.new("RGBA", (620, 300), (0, 166, 80, 255))
    splash_icon = base_img.resize((150, 150), Image.Resampling.LANCZOS)
    splash.paste(splash_icon, (235, 75), splash_icon)
    splash.save(assets_dir / "SplashScreen.png")

    print("MSIX assets generated in msix_layout/Assets")

if __name__ == "__main__":
    main()
