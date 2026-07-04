import os

# Files and directories we absolutely do NOT want to read
IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    ".dart_tool",
    "build",
    "ios",
    "android",
    ".idea",
    ".vscode",
}
IGNORE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".mp3",
    ".wav",
    ".mp4",
    ".mov",
    ".pyc",
    ".pyd",
    ".db",
    ".sqlite3",
    ".exe",
    ".dll",
}

output_file = "repomix-output.txt"

print("⏳ Scanning and packing source code... please wait.")

with open(output_file, "w", encoding="utf-8") as outfile:
    for root, dirs, files in os.walk("."):
        # Modify dirs in-place to skip ignored directories
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

        for file in files:
            _, ext = os.path.splitext(file)
            if ext.lower() in IGNORE_EXTENSIONS or file == output_file or file == "pack_code.py":
                continue

            file_path = os.path.join(root, file)

            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as infile:
                    content = infile.read()

                # Write a clear header for the AI to know which file it is reading
                outfile.write(f"\n\n--- FILE: {file_path} ---\n\n")
                outfile.write(content)
            except Exception as e:
                # Skip files that can't be read (binaries, etc.)
                continue

print(f"🎉 Success! Your code has been packed into: {output_file}")
