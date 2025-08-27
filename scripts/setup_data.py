from pathlib import Path
import zipfile
import sys

ROOT = Path(__file__).resolve().parents[1]
ZIP = ROOT / "data" / "openvgdb-29.0.sqlite.zip"
OUT = ROOT / "data" / "openvgdb-29.0.sqlite"

def main():
    if OUT.exists():
        print(f"[ok] already exists: {OUT}")
        return
    if not ZIP.exists():
        print(f"[err] missing zip: {ZIP}")
        sys.exit(1)
    with zipfile.ZipFile(ZIP, "r") as zf:
        # zip 내부 파일명이 다를 수 있으니 첫 항목을 OUT으로 추출
        names = zf.namelist()
        if not names:
            print("[err] empty zip")
            sys.exit(1)
        tmp = ROOT / "data" / names[0]
        zf.extract(names[0], ROOT / "data")
        tmp.rename(OUT)
    print(f"[ok] extracted to {OUT}")

if __name__ == "__main__":
    main()
