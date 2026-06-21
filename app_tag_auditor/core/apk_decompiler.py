import os
import sys
import hashlib
import subprocess
from core.config import get_settings

class ApkDecompiler:
    """
    ApkDecompiler decompiles APK files using JADX command-line utility.
    Uses SHA1 file hashing to cache results and avoid redundant decompilation.
    """
    def __init__(self, jadx_path: str | None = None):
        self.settings = get_settings()
        self.jadx_path = jadx_path or self.settings.JADX_PATH

    def _hash_file(self, path: str) -> str:
        """Returns the SHA1 checksum of the file to use as a cache key."""
        h = hashlib.sha1()
        with open(path, "rb") as f:
            while chunk := f.read(8192):
                h.update(chunk)
        return h.hexdigest()

    def decompile(self, apk_path: str) -> str:
        """
        Decompiles an APK and returns the directory containing the java sources.
        """
        if not os.path.exists(apk_path):
            raise FileNotFoundError(f"APK file not found at: {apk_path}")
            
        cache_dir = os.path.join(self.settings.TEMP_STORAGE_DIR, "decompiled", self._hash_file(apk_path))
        sources_dir = os.path.join(cache_dir, "sources")
        
        # If cached sources directory exists and is not empty, skip decompile
        if os.path.exists(sources_dir) and os.listdir(sources_dir):
            return sources_dir

        os.makedirs(cache_dir, exist_ok=True)
        
        try:
            # Run JADX decompiler command
            subprocess.run(
                [self.jadx_path, "-d", cache_dir, apk_path],
                capture_output=True,
                check=True
            )
        except FileNotFoundError:
            raise RuntimeError(
                "jadx not found — install it (brew install jadx, or see github.com/skylot/jadx) "
                "and ensure it's on PATH or set JADX_PATH in .env."
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"jadx failed with exit code {e.returncode}: {e.stderr.decode('utf-8', errors='ignore')}"
            )
            
        if not os.path.exists(sources_dir):
            # Fallback: check if the sources were dumped directly in cache_dir,
            # or if jadx structure is different. Typically JADX puts it in cache_dir/sources.
            pass
            
        return sources_dir

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m core.apk_decompiler <path_to_apk>")
        sys.exit(1)
        
    apk = sys.argv[1]
    print(f"Decompiling {apk}...")
    try:
        decompiler = ApkDecompiler()
        out_dir = decompiler.decompile(apk)
        print(f"Decompilation complete. Sources at: {out_dir}")
        
        java_count = 0
        for root, dirs, files in os.walk(out_dir):
            for file in files:
                if file.endswith(".java"):
                    java_count += 1
        print(f"Found {java_count} .java file(s) in source directory.")
    except Exception as e:
        print(f"Error: {e}")
