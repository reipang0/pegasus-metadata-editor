import sys, os, re, sqlite3, json, zlib, zipfile
import py7zr
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QFileDialog, QMessageBox, QComboBox, QListWidget, QLineEdit, QTextEdit
)

OPENVGDB_PATH = r"C:\PegasusTool\data\openvgdb.sqlite"
APPJS_PATH = r"C:\PegasusTool\data\app.js"
CRC_CACHE = "crc_cache.json"

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
# 수동 매핑 창
# ---------------------------
class ManualMappingWindow(QWidget):
    def __init__(self, metadata_file):
        super().__init__()
        self.setWindowTitle("수동 매핑")
        self.setGeometry(300, 200, 800, 500)
        self.metadata_file = metadata_file

        layout = QHBoxLayout()
        self.unmapped_list = QListWidget()
        layout.addWidget(self.unmapped_list)

        right_layout = QVBoxLayout()
        self.search_box = QLineEdit()
        self.search_btn = QPushButton("검색")
        self.search_btn.clicked.connect(self.do_search)
        right_layout.addWidget(self.search_box)
        right_layout.addWidget(self.search_btn)

        self.result_list = QListWidget()
        right_layout.addWidget(self.result_list)

        self.select_btn = QPushButton("선택 → 매핑")
        self.select_btn.clicked.connect(self.do_map)
        right_layout.addWidget(self.select_btn)

        layout.addLayout(right_layout)
        self.setLayout(layout)

        self.load_unmapped()

    def load_unmapped(self):
        with open(self.metadata_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        current_game = None
        for line in lines:
            if line.startswith("game:") and len(line.strip().split(":",1)[1])==0:
                current_game = line
            if line.startswith("file:") and current_game:
                rom = line.split(":",1)[1].strip()
                self.unmapped_list.addItem(rom)

    def do_search(self):
        self.result_list.clear()
        kw = self.search_box.text().strip()
        if not kw:
            return
        results = search_openvgdb(kw)
        for r in results:
            self.result_list.addItem(f"{r[0]} | {r[3]} | {r[1]}")

    def do_map(self):
        rom_item = self.unmapped_list.currentItem()
        sel_item = self.result_list.currentItem()
        if not rom_item or not sel_item:
            return
        rom = rom_item.text()
        game, sysname, genre = sel_item.text().split(" | ")
        lines = []
        with open(self.metadata_file,"r",encoding="utf-8") as f:
            lines=f.readlines()
        new_lines=[]
        for line in lines:
            if line.startswith("file:") and rom in line:
                new_lines.append(f"game: {game}\n")
                new_lines.append(line)
                new_lines.append(f"developer: \n")
                new_lines.append(f"description: {genre}\n\n")
            else:
                new_lines.append(line)
        with open(self.metadata_file,"w",encoding="utf-8") as f:
            f.writelines(new_lines)
        rom_item.setText(rom + " (매핑완료)")

def search_openvgdb(keyword):
    db = sqlite3.connect(OPENVGDB_PATH)
    cursor = db.cursor()
    cursor.execute("""
        SELECT rl.releaseTitleName, rl.releaseGenre, rl.releaseDeveloper, rl.TEMPsystemName
        FROM RELEASES rl
        WHERE rl.releaseTitleName LIKE ?
        LIMIT 20
    """, (f"%{keyword}%",))
    results = cursor.fetchall()
    db.close()
    return results

# ---------------------------
# 데이터 편집 창
# ---------------------------
class DataEditWindow(QWidget):
    def __init__(self, metadata_file):
        super().__init__()
        self.setWindowTitle("데이터 편집")
        self.setGeometry(350, 200, 900, 500)
        self.metadata_file = metadata_file

        layout = QHBoxLayout()
        self.game_list = QListWidget()
        layout.addWidget(self.game_list)
        self.game_list.itemClicked.connect(self.load_details)

        self.fields = {}
        right_layout = QVBoxLayout()
        for field in ["game","developer","publisher","genre","tag","summary","description","players","release","rating"]:
            lbl = QLabel(field)
            edit = QLineEdit()
            self.fields[field]=edit
            right_layout.addWidget(lbl)
            right_layout.addWidget(edit)
        self.save_btn = QPushButton("저장")
        self.save_btn.clicked.connect(self.save_data)
        right_layout.addWidget(self.save_btn)

        layout.addLayout(right_layout)
        self.setLayout(layout)

        self.load_games()

    def load_games(self):
        with open(self.metadata_file,"r",encoding="utf-8") as f:
            lines=f.readlines()
        for line in lines:
            if line.startswith("game:"):
                name=line.split(":",1)[1].strip()
                self.game_list.addItem(name)

    def load_details(self,item):
        gname=item.text()
        with open(self.metadata_file,"r",encoding="utf-8") as f:
            lines=f.readlines()
        block=[]
        capture=False
        for line in lines:
            if line.startswith("game:"):
                capture=(gname in line)
                block=[]
            if capture:
                block.append(line)
        for field in self.fields:
            self.fields[field].setText("")
        for l in block:
            for field in self.fields:
                if l.startswith(field+":"):
                    self.fields[field].setText(l.split(":",1)[1].strip())

    def save_data(self):
        gname=self.fields["game"].text()
        lines=[]
        with open(self.metadata_file,"r",encoding="utf-8") as f:
            lines=f.readlines()
        new_lines=[]
        capture=False
        for line in lines:
            if line.startswith("game:"):
                capture=(gname in line)
            if capture:
                replaced=False
                for field,val in self.fields.items():
                    if line.startswith(field+":"):
                        new_lines.append(f"{field}: {val.text()}\n")
                        replaced=True
                        break
                if not replaced:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        with open(self.metadata_file,"w",encoding="utf-8") as f:
            f.writelines(new_lines)
        QMessageBox.information(self,"저장","메타데이터가 갱신되었습니다.")

# ---------------------------
# 메인 윈도우
# ---------------------------
class PegasusTool(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pegasus Metadata Manager (Prototype 2.1)")
        self.setGeometry(200, 200, 600, 500)

        layout = QVBoxLayout()
        btn_row1 = QHBoxLayout()
        self.btn_generate = QPushButton("메타데이터 생성")
        self.btn_generate.clicked.connect(self.generate_metadata)
        self.btn_update = QPushButton("업데이트")
        self.btn_update.clicked.connect(self.update_metadata)
        btn_row1.addWidget(self.btn_generate)
        btn_row1.addWidget(self.btn_update)

        btn_row2 = QHBoxLayout()
        self.btn_manual = QPushButton("수동 매핑")
        self.btn_manual.clicked.connect(self.open_manual_mapping)
        self.btn_edit = QPushButton("데이터 편집")
        self.btn_edit.clicked.connect(self.open_data_edit)
        btn_row2.addWidget(self.btn_manual)
        btn_row2.addWidget(self.btn_edit)

        layout.addLayout(btn_row1)
        layout.addLayout(btn_row2)

        self.rom_folder=None
        self.setLayout(layout)

    def generate_metadata(self):
        QMessageBox.information(self,"생성","(Stub) 메타데이터 생성 실행")

    def update_metadata(self):
        QMessageBox.information(self,"업데이트","(Stub) 업데이트 실행")

    def open_manual_mapping(self):
        if not self.rom_folder:
            self.rom_folder = QFileDialog.getExistingDirectory(self,"ROM 폴더 선택")
        if not self.rom_folder:
            return
        meta_file = os.path.join(self.rom_folder,"metadata.pegasus.txt")
        if not os.path.exists(meta_file):
            QMessageBox.warning(self,"오류","metadata.pegasus.txt가 없습니다.")
            return
        self.mmw = ManualMappingWindow(meta_file)
        self.mmw.show()

    def open_data_edit(self):
        if not self.rom_folder:
            self.rom_folder = QFileDialog.getExistingDirectory(self,"ROM 폴더 선택")
        if not self.rom_folder:
            return
        meta_file = os.path.join(self.rom_folder,"metadata.pegasus.txt")
        if not os.path.exists(meta_file):
            QMessageBox.warning(self,"오류","metadata.pegasus.txt가 없습니다.")
            return
        self.dew = DataEditWindow(meta_file)
        self.dew.show()

if __name__=="__main__":
    app=QApplication(sys.argv)
    win=PegasusTool()
    win.show()
    sys.exit(app.exec_())
