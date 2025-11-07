"""
Build script for Fansly AI Chat Bot
Creates standalone .exe file using PyInstaller
"""

import subprocess
import sys
import os

def build_exe():
    """Build executable file with PyInstaller"""
    
    print("=" * 60)
    print("Fansly AI Chat Bot - Build Script")
    print("=" * 60)
    
    # Check if PyInstaller is available
    try:
        import PyInstaller
        print("[OK] PyInstaller found")
    except ImportError:
        print("[ERROR] PyInstaller not found. Install: pip install pyinstaller")
        return False
    
    # Check if spec file exists
    spec_file = "main.spec"
    if not os.path.exists(spec_file):
        print(f"[ERROR] Spec file {spec_file} not found")
        return False
    
    print(f"\n[INFO] Starting build with {spec_file}...")
    print("   Parameters: --onefile --windowed")
    
    try:
        # Run PyInstaller with spec file
        result = subprocess.run(
            ['pyinstaller', '--clean', spec_file],
            check=True,
            capture_output=False,
            text=True
        )
        
        print("\n[SUCCESS] Build completed successfully!")
        print(f"[INFO] Executable file: dist/Fansly_AI_ChatBot.exe")
        print("\n[INFO] To test, run:")
        print("   dist\\Fansly_AI_ChatBot.exe")
        
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Build error: {e}")
        return False
    except FileNotFoundError:
        print("\n[ERROR] PyInstaller not found in PATH")
        print("   Install: pip install pyinstaller")
        return False
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = build_exe()
    sys.exit(0 if success else 1)