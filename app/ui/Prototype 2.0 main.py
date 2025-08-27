import sys, os, json, zlib, sqlite3, zipfile, re
import py7zr
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout,
    QFileDialog, QMessageBox, QComboBox
)

CONFIG_FILE = "config.json"
CRC_CACHE = "crc_cache.json"
OPENVGDB_PATH = r"C:\PegasusTool\data\openvgdb.sqlite"
APPJS_PATH = r"C:\PegasusTool\data\app.js"

# ---------------------------
# app.js 파싱
# ---------------------------
def load_cores_from_appjs():
    if not os.path.exists(APPJS_PATH):
        return []
    with open(APPJS_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    matches = re.findall(r"\{[^}]+\}", content)
    cores = []
    for m in matches:
        fullname = re.search(r'fullname\s*:\s*"([^"]+)"', m)
        sysname = re.search(r'sysname\s*:\s*"([^"]+)"', m)
        exts = re.search(r'exts\s*:\s*"([^"]+)"', m)
        abbr = re.search(r'abbr\s*:\s*"([^"]+)"', m)
        core = re.search(r'core\s*:\s*"([^"]+)"', m)
        if fullname and core:
            cores.append({
                "fullname": fullname.group(1),
                "sysname": sysname.group(1) if sysname else "",
                "exts": [e.strip() for e in exts.group(1).split(",")] if exts else [],
                "abbr": abbr.group(1) if abbr else "",
                "core": core.group(1)
            })
    return cores

CORES = load_cores_from_appjs()

# ---------------------------
# 캐시
# ---------------------------
def load_cache():
    if os.path.exists(CRC_CACHE):
        with open(CRC_CACHE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(CRC_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)

# ---------------------------
# CRC 계산
# ---------------------------
def compute_crc(file_path, allowed_exts):
    cache = load_cache()
    mtime = os.path.getmtime(file_path)
    results = {}

    if file_path.lower().endswith(".zip"):
        with zipfile.ZipFile(file_path, "r") as z:
            valid_entries = [info for info in z.infolist()
                             if os.path.splitext(info.filename)[1].lower().strip(".") in allowed_exts]
            if not valid_entries:
                return {}
            info = max(valid_entries, key=lambda e: e.file_size)
            key = f"{file_path}:{info.filename}:{mtime}"
            if key in cache:
                results[info.filename] = cache[key]
            else:
                crc = "%08X" % info.CRC
                cache[key] = crc
                results[info.filename] = crc

    elif file_path.lower().endswith(".7z"):
        with py7zr.SevenZipFile(file_path, "r") as archive:
            valid_entries = [name for name, entry in archive.list().items()
                             if os.path.splitext(name)[1].lower().strip(".") in allowed_exts]
            if not valid_entries:
                return {}
            name = valid_entries[0]
            key = f"{file_path}:{name}:{mtime}"
            if key in cache:
                results[name] = cache[key]
            else:
                entry = archive.list()[name]
                if entry.crc is not None:
                    crc = "%08X" % entry.crc
                else:
                    with archive.read([name])[name] as f:
                        prev = 0
                        for chunk in iter(lambda: f.read(4096), b""):
                            prev = zlib.crc32(chunk, prev)
                        crc = "%08X" % (prev & 0xFFFFFFFF)
                cache[key] = crc
                results[name] = crc
    else:
        ext = os.path.splitext(file_path)[1].lower().strip(".")
        if ext not in allowed_exts:
            return {}
        key = f"{file_path}:{mtime}"
        if key in cache:
            return {os.path.basename(file_path): cache[key]}
        prev = 0
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                prev = zlib.crc32(chunk, prev)
        crc = "%08X" % (prev & 0xFFFFFFFF)
        cache[key] = crc
        results[os.path.basename(file_path)] = crc

    save_cache(cache)
    return results

# ---------------------------
# OpenVGDB 조회
# ---------------------------
def lookup_openvgdb(crc32):
    db = sqlite3.connect(OPENVGDB_PATH)
    cursor = db.cursor()
    cursor.execute("""
        SELECT rl.releaseTitleName, rl.releaseGenre, rl.releaseDeveloper, rl.releaseDescription, rl.TEMPsystemName
        FROM ROMs r
        JOIN RELEASES rl ON r.romID = rl.romID
        WHERE r.romHashCRC = ?
    """, (crc32,))
    row = cursor.fetchone()
    db.close()
    if row:
        return {
            "name": row[0],
            "genre": row[1],
            "developer": row[2],
            "description": row[3],
            "system": row[4]
        }
    return None

# ---------------------------
# PegasusTool GUI
# ---------------------------
class PegasusTool(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pegasus Metadata Manager (Prototype 2.0)")
        self.setGeometry(200, 200, 600, 500)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("실행 환경"))
        self.system_combo = QComboBox()
        self.system_combo.addItems(["PC (미구현)", "Android (RetroArch64)", "Android (Standalone)", "Raspberry Pi (미구현)", "Linux (미구현)"])
        layout.addWidget(self.system_combo)

        self.core_combo = QComboBox()
        layout.addWidget(QLabel("코어 선택"))
        layout.addWidget(self.core_combo)

        self.rom_label = QLabel("선택된 ROM 폴더: 없음")
        layout.addWidget(self.rom_label)
        btn_folder = QPushButton("ROM 폴더 선택")
        btn_folder.clicked.connect(self.select_folder)
        layout.addWidget(btn_folder)

        self.btn_generate = QPushButton("메타데이터 생성")
        self.btn_generate.clicked.connect(self.generate_metadata)
        layout.addWidget(self.btn_generate)

        self.btn_update = QPushButton("업데이트")
        self.btn_update.clicked.connect(self.update_metadata)
        layout.addWidget(self.btn_update)

        self.setLayout(layout)
        self.rom_folder = None
        self.cores_for_system = []

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "ROM 폴더 선택")
        if folder:
            self.rom_folder = folder
            self.rom_label.setText(f"선택된 ROM 폴더: {folder}")
            key = os.path.basename(folder).lower()

            # 기종 후보 찾기
            candidates = [c for c in CORES if c["abbr"] == key]
            if candidates:
                self.cores_for_system = candidates
                self.core_combo.clear()
                for c in candidates:
                    self.core_combo.addItem(c["fullname"])
            else:
                QMessageBox.warning(self, "경고", f"해당 폴더명({key})에 맞는 기종을 찾을 수 없습니다.")

    def process_rom(self, rom_path, exts):
        crc_map = compute_crc(rom_path, exts)
        if not crc_map:
            return None
        inner, crc = list(crc_map.items())[0]
        info = lookup_openvgdb(crc)
        return (inner, crc, info)

    def read_existing_games(self, out_file):
        games = []
        if not os.path.exists(out_file):
            return games
        with open(out_file, "r", encoding="utf-8") as f:
            block = []
            for line in f:
                if line.startswith("game:"):
                    if block:
                        games.append(block)
                        block = []
                block.append(line)
            if block:
                games.append(block)
        return games

    def write_metadata(self, out_file, append=False):
        if not self.cores_for_system:
            return
        chosen_name = self.core_combo.currentText()
        chosen = next((c for c in self.cores_for_system if c["fullname"] == chosen_name), None)
        if not chosen:
            return

        existing_games = self.read_existing_games(out_file)
        existing_files = [line for block in existing_games for line in block if line.startswith("file:")]

        if not append:
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(f"collection: {chosen['sysname']}\n")
                f.write(f"shortname: {chosen['abbr']}\n")
                f.write("extensions: " + ",".join(chosen["exts"]) + "\n")
                launch = f"""am start -n com.retroarch/.browser.retroactivity.RetroActivityFuture
  -e ROM {{file.path}}
  -e LIBRETRO /data/data/com.retroarch/cores/{chosen['core']}
  -e CONFIGFILE /storage/emulated/0/Android/data/com.retroarch/files/retroarch.cfg
  -e QUITFOCUS
  --activity-clear-task
  --activity-clear-top
  --activity-no-history"""
                f.write("launch: " + launch + "\n\n")
        else:
            with open(out_file, "a", encoding="utf-8") as f:
                f.write("\n# 업데이트된 게임 목록\n")

        # 신규 ROM만 추가
        for rom in os.listdir(self.rom_folder):
            rom_path = os.path.join(self.rom_folder, rom)
            if not os.path.isfile(rom_path):
                continue
            if any(f"file: {rom}" in ef for ef in existing_files):
                continue
            entry = self.process_rom(rom_path, chosen["exts"])
            if entry:
                inner, crc, info = entry
                name = info['name'] if info else os.path.splitext(inner)[0]
                with open(out_file, "a", encoding="utf-8") as f:
                    f.write(f"game: {name}\n")
                    f.write(f"file: {rom}\n")
                    f.write(f"developer: {info['developer'] if info else ''}\n")
                    f.write(f"description: {info['description'] if info else ''}\n\n")

    def generate_metadata(self):
        if not self.rom_folder:
            QMessageBox.warning(self, "오류", "ROM 폴더를 선택하세요.")
            return
        out_file = os.path.join(self.rom_folder, "metadata.pegasus.txt")
        self.write_metadata(out_file, append=False)
        QMessageBox.information(self, "완료", "metadata.pegasus.txt 생성 완료")

    def update_metadata(self):
        if not self.rom_folder:
            return
        out_file = os.path.join(self.rom_folder, "metadata.pegasus.txt")
        if not os.path.exists(out_file):
            QMessageBox.warning(self, "오류", "기존 metadata가 없습니다.")
            return
        self.write_metadata(out_file, append=True)
        QMessageBox.information(self, "완료", "신규 ROM만 추가되었습니다.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = PegasusTool()
    win.show()
    sys.exit(app.exec_())
