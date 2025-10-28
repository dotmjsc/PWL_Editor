#!/usr/bin/env python3
"""
Build automation for the PWL Editor.
Author: markus(at)schrodt.at
AI Tools: Claude Sonnet 4 (Anthropic); GPT-5 (OpenAI) - Code development and architecture
License: GPL-3.0-or-later

This script builds the PWL Editor using PyInstaller and organizes the output
into version-specific folders with examples included.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

# Ensure project root and src are on sys.path so package imports resolve
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from version import get_version

def run_command(cmd, cwd=None):
    """Run a shell command and return success status"""
    try:
        print(f"Running: {cmd}")
        result = subprocess.run(cmd, shell=True, cwd=cwd, check=True, 
                              capture_output=True, text=True)
        print(f"Success: {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        print(f"Output: {e.stdout}")
        print(f"Error: {e.stderr}")
        return False

def clean_build_dirs():
    """Clean previous build directories"""
    # Determine the project root directory
    current_dir = os.getcwd()
    if current_dir.endswith('src'):
        project_root = Path("..").resolve()
    else:
        project_root = Path(".").resolve()
        
    dirs_to_clean = ['build', 'dist', '__pycache__']
    for dir_name in dirs_to_clean:
        target_dir = project_root / dir_name
        if target_dir.exists():
            print(f"Cleaning {target_dir}...")
            try:
                # On Windows, files might be locked, so we retry
                for i in range(3):
                    try:
                        shutil.rmtree(target_dir)
                        break
                    except PermissionError:
                        if i < 2:
                            import time
                            time.sleep(1)
                        else:
                            print(f"Warning: Could not remove {target_dir}")
            except Exception as e:
                print(f"Warning: Could not clean {target_dir}: {e}")

def create_version_folder(version):
    """Create version-specific folder in versions directory"""
    # Determine the project root directory
    current_dir = os.getcwd()
    if current_dir.endswith('src'):
        versions_dir = Path("../versions")
    else:
        versions_dir = Path("versions")
    
    versions_dir.mkdir(exist_ok=True)
    
    version_folder = versions_dir / f"PWL_Editor_v{version}"
    if version_folder.exists():
        print(f"Removing existing version folder: {version_folder}")
        shutil.rmtree(version_folder)
    
    version_folder.mkdir()
    return version_folder

def copy_examples(version_folder):
    """Copy examples folder to version folder"""
    # Determine the project root directory
    current_dir = os.getcwd()
    if current_dir.endswith('src'):
        examples_src = Path("../examples")
    else:
        examples_src = Path("examples")
    
    examples_dst = version_folder / "examples"
    
    if examples_src.exists():
        print(f"Copying examples to {examples_dst}")
        shutil.copytree(examples_src, examples_dst)
    else:
        print("Warning: examples folder not found")

def copy_docs(version_folder):
    """Copy documentation files to version folder"""
    docs_to_copy = ["README.md", "CHANGELOG.md"]
    
    # Determine the project root directory
    current_dir = os.getcwd()
    if current_dir.endswith('src'):
        project_root = Path("..")
    else:
        project_root = Path(".")
    
    for doc in docs_to_copy:
        doc_path = project_root / doc
        if doc_path.exists():
            dst = version_folder / doc
            print(f"Copying {doc} to {dst}")
            shutil.copy2(doc_path, dst)

def build_executable():
    """Build the executable using PyInstaller"""
    print("\n=== Building PWL Editor Executable ===")
    
    # Determine if we're running from src/ or from root
    current_dir = os.getcwd()
    if current_dir.endswith('src'):
        # Running from src directory (command line: cd src; python build.py)
        os.chdir('..')  # Go to parent directory
        target_script = "src/pwl_gui.py"
    else:
        # Running from root directory (VS Code play button)
        target_script = "src/pwl_gui.py"
    
    try:
        # PyInstaller command - with proper numpy support
        cmd = [
            "pyinstaller",
            "--onefile",
            "--windowed",
            "--name=PWL_Editor",
            "--hidden-import=tkinter",
            "--hidden-import=matplotlib.pyplot",
            "--hidden-import=numpy",
            "--hidden-import=si_prefix",
            "--collect-data=tkinter",
            "--collect-submodules=numpy",
            "--collect-data=numpy",
            target_script
        ]
        
        return run_command(" ".join(cmd))
    finally:
        # Return to original directory if we changed it
        if current_dir.endswith('src'):
            os.chdir('src')

def create_zip_archive(version_folder):
    """Create a zip archive of the version folder"""
    import zipfile
    
    zip_name = f"{version_folder.name}.zip"
    zip_path = version_folder.parent / zip_name
    
    print(f"Creating zip archive: {zip_path}")
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in version_folder.rglob('*'):
            if file_path.is_file():
                # Create relative path for archive
                arcname = file_path.relative_to(version_folder.parent)
                zipf.write(file_path, arcname)
                
    print(f"✅ Created zip archive: {zip_path}")
    return zip_path

def main():
    """Main build process"""
    print("PWL Editor Build Script")
    print("=" * 40)
    
    # Get current version
    version = get_version()
    print(f"Building version: {version}")
    
    # Step 1: Clean previous builds
    print("\n1. Cleaning previous builds...")
    clean_build_dirs()
    
    # Step 2: Build executable
    print("\n2. Building executable...")
    if not build_executable():
        print("Build failed!")
        return False
    
    # Step 3: Create version folder
    print("\n3. Creating version folder...")
    version_folder = create_version_folder(version)
    print(f"Created: {version_folder}")
    
    # Step 4: Copy executable
    print("\n4. Copying executable...")
    # Determine the project root directory
    current_dir = os.getcwd()
    if current_dir.endswith('src'):
        exe_src = Path("../dist") / "PWL_Editor.exe"
    else:
        exe_src = Path("dist") / "PWL_Editor.exe"
    
    exe_dst = version_folder / "PWL_Editor.exe"
    
    if exe_src.exists():
        shutil.copy2(exe_src, exe_dst)
        print(f"Copied executable to {exe_dst}")
    else:
        print("Error: Executable not found in dist folder")
        return False
    
    # Step 5: Copy examples
    print("\n5. Copying examples...")
    copy_examples(version_folder)
    
    # Step 6: Copy documentation
    print("\n6. Copying documentation...")
    copy_docs(version_folder)
    
    # Step 7: Create zip archive
    print("\n7. Creating zip archive...")
    zip_path = create_zip_archive(version_folder)
    
    # Step 8: Clean up build artifacts
    print("\n8. Cleaning up build artifacts...")
    clean_build_dirs()
    
    print("\n" + "=" * 40)
    print(f"✅ Build completed successfully!")
    print(f"📁 Output folder: {version_folder}")
    print(f"🚀 Executable: {version_folder}/PWL_Editor.exe")
    print(f"📦 Zip archive: {zip_path}")
    print("=" * 40)
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
