from pathlib import Path
import zipfile
import sys

ROOT = Path(__file__).resolve().parents[1]
ZIP = ROOT / "data" / "openvgdb.zip"
OUT = ROOT / "data" / "openvgdb.sqlite"

def main():
    if OUT.exists():
        print(f"[ok] already exists: {OUT}")
        return
    if not ZIP.exists():
        print(f"[err] missing zip: {ZIP}")
        sys.exit(1)
    with zipfile.ZipFile(ZIP, "r") as zf:
        # zip 안에 있는 첫 번째 파일을 꺼내서 openvgdb.sqlite로 저장
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
