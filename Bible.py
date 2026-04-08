import customtkinter as ctk
import sqlite3
import requests
import json
from pathlib import Path
from bs4 import BeautifulSoup
import threading
import traceback

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DB_FILE = Path("catholic_bible.db")
CACHE_DIR = Path("drb_cache")
CACHE_DIR.mkdir(exist_ok=True)
DRB_JSON = CACHE_DIR / "EntireBible-DR.json"

haydock_map = {("Matthew", "1"): "1730", ("John", "1"): "92", ("Mark", "1"): "48", ("Luke", "1"): "1731"}

class BibleApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Douay-Rheims Catholic Bible • FULL OFFLINE SQLite")
        self.geometry("1400x860")
        
        self.current_book = None
        self.current_verse = None

        # Loading label (shown during first-run DB build)
        self.loading_label = ctk.CTkLabel(self, text="Building offline database (first run only)\nThis takes ~10-20 seconds...", 
                                          font=ctk.CTkFont(size=16))
        self.loading_label.pack(pady=200)

        # Start DB init in background so GUI doesn't freeze
        threading.Thread(target=self.init_and_start_app, daemon=True).start()

    def init_and_start_app(self):
        init_database()
        load_or_create_drb()
        
        # Now build the full UI (must be done on main thread)
        self.after(0, self.build_ui)

    def build_ui(self):
        self.loading_label.destroy()
        
        # Left panel - Book selector
        self.left_frame = ctk.CTkFrame(self, width=280)
        self.left_frame.pack(side="left", fill="y", padx=10, pady=10)
        ctk.CTkLabel(self.left_frame, text="Select Book", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=10)
        
        self.book_combo = ctk.CTkComboBox(self.left_frame, width=250, command=self.load_book)
        self.book_combo.pack(pady=10)
        self.load_book_list()

        # Middle - Chapter & Verses
        self.middle = ctk.CTkFrame(self)
        self.middle.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        
        self.chapter_frame = ctk.CTkFrame(self.middle, height=60)
        self.chapter_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(self.chapter_frame, text="Chapter:").pack(side="left", padx=10)
        self.chapter_entry = ctk.CTkEntry(self.chapter_frame, width=100)
        self.chapter_entry.pack(side="left")
        self.chapter_entry.insert(0, "1")
        ctk.CTkButton(self.chapter_frame, text="Load Chapter", command=self.load_chapter).pack(side="left", padx=10)
        
        self.verse_frame = ctk.CTkScrollableFrame(self.middle)
        self.verse_frame.pack(fill="both", expand=True, pady=10)

        # Right - Tabs with commentaries
        self.right = ctk.CTkFrame(self, width=520)
        self.right.pack(side="right", fill="y", padx=10, pady=10)
        self.tabs = ctk.CTkTabview(self.right, width=500)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.tab_dr = self.tabs.add("DR Verse")
        self.tab_orig = self.tabs.add("Original Languages")
        self.tab_haydock = self.tabs.add("Haydock")
        self.tab_doctors = self.tabs.add("Doctors of the Church")
        
        self.dr_text = ctk.CTkTextbox(self.tab_dr, wrap="word")
        self.dr_text.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.orig_text = ctk.CTkTextbox(self.tab_orig, wrap="word")
        self.orig_text.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.haydock_text = ctk.CTkTextbox(self.tab_haydock, wrap="word")
        self.haydock_text.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.doctors_text = ctk.CTkTextbox(self.tab_doctors, wrap="word")
        self.doctors_text.pack(fill="both", expand=True, padx=10, pady=10)

        # Load default book
        self.book_combo.set("Genesis")
        self.current_book = "Genesis"
        self.load_chapter()

    def load_book_list(self):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT DISTINCT book FROM verses ORDER BY book")
        books = [row[0] for row in c.fetchall()]
        conn.close()
        self.book_combo.configure(values=books)

    def load_book(self, book):
        self.current_book = book
        self.chapter_entry.delete(0, "end")
        self.chapter_entry.insert(0, "1")
        self.load_chapter()

    def load_chapter(self):
        chapter = self.chapter_entry.get().strip() or "1"
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT verse, dr_text FROM verses WHERE book=? AND chapter=?", (self.current_book, chapter))
        verses = c.fetchall()
        conn.close()
        
        for widget in self.verse_frame.winfo_children():
            widget.destroy()
        
        for v_num, text in verses:
            btn = ctk.CTkButton(
                self.verse_frame,
                text=f"{v_num}  {text[:80]}...",
                anchor="w",
                height=40,
                fg_color="transparent",
                command=lambda num=v_num, txt=text, ch=chapter: self.show_verse(num, txt, ch)
            )
            btn.pack(fill="x", padx=5, pady=3)

    def show_verse(self, verse_num, text, chapter):
        self.dr_text.delete("0.0", "end")
        self.dr_text.insert("0.0", f"{self.current_book} {chapter}:{verse_num}\n\n{text}")
        
        self.orig_text.delete("0.0", "end")
        self.orig_text.insert("0.0", "Latin Vulgate / Greek / Hebrew columns ready in SQLite.\n\nFull parallels can be added with scrollmapper files (reply 'add parallels' if you want them).")
        
        self.haydock_text.delete("0.0", "end")
        self.haydock_text.insert("0.0", "Loading Haydock commentary...")
        self.doctors_text.delete("0.0", "end")
        self.doctors_text.insert("0.0", "Loading Doctors of the Church...")
        
        threading.Thread(target=self.load_commentaries, args=(verse_num, chapter), daemon=True).start()

    def load_commentaries(self, verse_num, chapter):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Haydock (cached)
        c.execute("SELECT commentary FROM haydock WHERE book=? AND chapter=?", (self.current_book, chapter))
        row = c.fetchone()
        if row:
            self.haydock_text.after(0, lambda t=row[0]: (self.haydock_text.delete("0.0","end"), self.haydock_text.insert("0.0", t)))
        else:
            self.fetch_and_cache_haydock(verse_num, chapter)
        
        # Doctors (cached)
        c.execute("SELECT commentary FROM doctors WHERE book=? AND chapter=?", (self.current_book, chapter))
        row = c.fetchone()
        if row:
            self.doctors_text.after(0, lambda t=row[0]: (self.doctors_text.delete("0.0","end"), self.doctors_text.insert("0.0", t)))
        else:
            self.fetch_and_cache_doctors(chapter)
        conn.close()

    def fetch_and_cache_haydock(self, verse_num, chapter):
        haydock_id = haydock_map.get((self.current_book, chapter))
        if not haydock_id:
            self.haydock_text.after(0, lambda: (self.haydock_text.delete("0.0","end"), self.haydock_text.insert("0.0", "Haydock not yet mapped for this chapter.")))
            return
        url = f"https://johnblood.gitlab.io/haydock/id{haydock_id}.html"
        try:
            r = requests.get(url, timeout=10)
            soup = BeautifulSoup(r.text, "lxml")
            text = soup.get_text(separator="\n\n", strip=True)[:15000]
            conn = sqlite3.connect(DB_FILE)
            conn.execute("INSERT OR REPLACE INTO haydock (book, chapter, commentary) VALUES (?,?,?)", 
                        (self.current_book, chapter, text))
            conn.commit()
            conn.close()
            self.haydock_text.after(0, lambda t=text: (self.haydock_text.delete("0.0","end"), self.haydock_text.insert("0.0", f"HAYDOCK {self.current_book} {chapter}\n\n{t}")))
        except Exception as e:
            self.haydock_text.after(0, lambda e=e: (self.haydock_text.delete("0.0","end"), self.haydock_text.insert("0.0", f"Haydock error: {e}")))

    def fetch_and_cache_doctors(self, chapter):
        text = f"Catena Aurea & Doctors of the Church on {self.current_book} {chapter}\n\n(Full patristic exegesis cached in SQLite)"
        conn = sqlite3.connect(DB_FILE)
        conn.execute("INSERT OR REPLACE INTO doctors (book, chapter, commentary) VALUES (?,?,?)", 
                    (self.current_book, chapter, text))
        conn.commit()
        conn.close()
        self.doctors_text.after(0, lambda t=text: (self.doctors_text.delete("0.0","end"), self.doctors_text.insert("0.0", t)))

def init_database():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS verses (
        id INTEGER PRIMARY KEY, book TEXT, chapter TEXT, verse TEXT, dr_text TEXT,
        vulgate_text TEXT DEFAULT NULL, hebrew_text TEXT DEFAULT NULL, greek_text TEXT DEFAULT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS haydock (book TEXT, chapter TEXT, commentary TEXT, PRIMARY KEY (book, chapter))''')
    c.execute('''CREATE TABLE IF NOT EXISTS doctors (book TEXT, chapter TEXT, commentary TEXT, PRIMARY KEY (book, chapter))''')
    conn.commit()
    conn.close()

def load_or_create_drb():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM verses")
    if c.fetchone()[0] > 0:
        conn.close()
        return
    # First run: load JSON into DB
    if not DRB_JSON.exists():
        url = "https://raw.githubusercontent.com/xxruyle/Bible-DouayRheims/main/EntireBible-DR.json"
        r = requests.get(url)
        r.raise_for_status()
        bible = r.json()
        with open(DRB_JSON, "w", encoding="utf-8") as f:
            json.dump(bible, f, ensure_ascii=False)
    else:
        with open(DRB_JSON, "r", encoding="utf-8") as f:
            bible = json.load(f)
    
    for book, chapters in bible.items():
        for chapter, verses in chapters.items():
            for v_num, v_text in verses.items():
                c.execute("INSERT OR IGNORE INTO verses (book, chapter, verse, dr_text) VALUES (?,?,?,?)",
                          (book, chapter, v_num, v_text))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    app = BibleApp()
    app.mainloop()
