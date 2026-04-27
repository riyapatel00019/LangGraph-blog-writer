from pathlib import Path
from db import save_blog


def extract_title(md_text, fallback):
    for line in md_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def migrate():
    files = list(Path(".").glob("*.md"))

    if not files:
        print("No markdown files found")
        return

    for f in files:
        try:
            content = f.read_text(encoding="utf-8")
            title = extract_title(content, f.stem)

            print(f"Saving: {title}")
            save_blog(title, content, "demo-user")

        except Exception as e:
            print(f"Error with {f.name}:", e)


if __name__ == "__main__":
    migrate()