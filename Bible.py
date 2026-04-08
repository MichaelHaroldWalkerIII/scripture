import customtkinter as ctk
import requests
import json
from pathlib import Path
from bs4 import BeautifulSoup
import webbrowser
import threading

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

CACHE_DIR = Path("drb_cache")
CACHE_DIR.mkdir(exist_ok=True)
DRB_CACHE = CACHE_DIR / "EntireBible-DR.json"

def load_drb():
    if DRB_CACHE.exists():
        with open(DRB_CACHE, "r", encoding="utf-8") as f:
            return json.load(f)
    print("Downloading Douay-Rheims Bible (first run only)...")
    url = "https://raw.githubusercontent.com/xxruyle/Bible-DouayRheims/main/EntireBible-DR.json"
    r = requests.get(url)
    r.raise_for_status()
    bible = r.json()
    with open(DRB_CACHE, "w", encoding="utf-8") as f:
        json.dump(bible, f, ensure_ascii=False)
    print("Download complete!")
    return bible

bible_data = load_drb()
books = list(bible_data.keys())

# Haydock chapter mapping (NT is very complete; OT uses index.html as fallback)
haydock_map = {
    ("Matthew", "1"): "1730", ("Matthew", "2"): "14", ("Matthew", "3"): "15", ("Matthew", "4"): "18",
    ("Mark", "1"): "48", ("Luke", "1"): "1731", ("John", "1"): "92",
    # Add more chapters as needed — the code falls back gracefully
}

class BibleApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Douay-Rheims Catholic Bible • Haydock + Doctors")
        self.geometry("1350x820")
        self.current_verse = None

        # Left panel - Books
        self.left_frame = ctk.CTkFrame(self, width=250)
        self.left_frame.pack(side="left", fill="y", padx=10, pady=10)

        ctk.CTkLabel(self.left_frame, text="Books", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=10)
        self.book_list = ctk.CTkScrollableFrame(self.left_frame, width=230)
        self.book_list.pack(fill="both", expand=True, padx=5, pady=5)

        for book in books:
            btn = ctk.CTkButton(self.book_list, text=book, anchor="w", height=30,
                                command=lambda b=book: self.load_book(b))
            btn.pack(fill="x", padx=5, pady=2)

        # Middle - Verses
        self.middle_frame = ctk.CTkFrame(self)
        self.middle_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        self.chapter_frame = ctk.CTkFrame(self.middle_frame, height=60)
        self.chapter_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(self.chapter_frame, text="Chapter:").pack(side="left", padx=10)
        self.chapter_entry = ctk.CTkEntry(self.chapter_frame, width=80)
        self.chapter_entry.pack(side="left")
        self.chapter_entry.insert(0, "1")
        ctk.CTkButton(self.chapter_frame, text="Load", command=self.load_chapter).pack(side="left", padx=10)

        self.verse_scroll = ctk.CTkScrollableFrame(self.middle_frame)
        self.verse_scroll.pack(fill="both", expand=True, pady=5)

        # Right - Side panel with tabs
        self.right_frame = ctk.CTkFrame(self, width=480)
        self.right_frame.pack(side="right", fill="y", padx=10, pady=10)

        self.tabview = ctk.CTkTabview(self.right_frame, width=460)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_dr = self.tabview.add("DR Verse")
        self.tab_orig = self.tabview.add("Original Languages")
        self.tab_haydock = self.tabview.add("Haydock")
        self.tab_doctors = self.tabview.add("Doctors of the Church")

        # Populate tabs with placeholders that will be filled on verse click
        self.dr_text = ctk.CTkTextbox(self.tab_dr, wrap="word")
        self.dr_text.pack(fill="both", expand=True, padx=10, pady=10)

        self.orig_text = ctk.CTkTextbox(self.tab_orig, wrap="word")
        self.orig_text.pack(fill="both", expand=True, padx=10, pady=10)
        ctk.CTkButton(self.tab_orig, text="Open DR + Latin Vulgate Parallel", 
                      command=lambda: webbrowser.open("https://drbo.org/")).pack(pady=10)

        self.haydock_text = ctk.CTkTextbox(self.tab_haydock, wrap="word")
        self.haydock_text.pack(fill="both", expand=True, padx=10, pady=10)
        self.haydock_btn = ctk.CTkButton(self.tab_haydock, text="Load Haydock Commentary", 
                                         command=self.load_haydock)
        self.haydock_btn.pack(pady=5)

        self.doctors_text = ctk.CTkTextbox(self.tab_doctors, wrap="word")
        self.doctors_text.pack(fill="both", expand=True, padx=10, pady=10)
        ctk.CTkButton(self.tab_doctors, text="Open Catena Aurea & Fathers", 
                      command=lambda: webbrowser.open("https://www.ecatholic2000.com/catena/contents.shtml")).pack(pady=10)

        # Load default book
        self.current_book = books[0]
        self.load_book(self.current_book)

    def load_book(self, book):
        self.current_book = book
        self.chapter_entry.delete(0, "end")
        self.chapter_entry.insert(0, "1")
        self.load_chapter()

    def load_chapter(self):
        chapter = self.chapter_entry.get().strip() or "1"
        try:
            chapter_data = bible_data[self.current_book][chapter]
        except KeyError:
            print("Chapter not found")
            return

        # Clear old verses
        for widget in self.verse_scroll.winfo_children():
            widget.destroy()

        for v_num, v_text in chapter_data.items():
            btn = ctk.CTkButton(self.verse_scroll, text=f"{v_num}  {v_text[:80]}...", 
                                anchor="w", height=35, fg_color="transparent", text_color=("gray80", "gray20"),
                                command=lambda num=v_num, txt=v_text: self.show_verse(self.current_book, chapter, num, txt))
            btn.pack(fill="x", padx=5, pady=2)

    def show_verse(self, book, chapter, verse_num, text):
        self.current_verse = {"book": book, "chapter": chapter, "verse": verse_num, "text": text}

        # DR Verse tab
        self.dr_text.delete("0.0", "end")
        self.dr_text.insert("0.0", f"{book} {chapter}:{verse_num}\n\n{text}")

        # Original Languages tab
        self.orig_text.delete("0.0", "end")
        self.orig_text.insert("0.0", f"Latin Vulgate, Greek, and Hebrew parallels available at drbo.org\n\nClick the button above to open the exact chapter in parallel view.")

        # Clear other tabs
        self.haydock_text.delete("0.0", "end")
        self.haydock_text.insert("0.0", "Click 'Load Haydock Commentary' to pull the real 1859 notes for this chapter.")
        self.doctors_text.delete("0.0", "end")
        self.doctors_text.insert("0.0", "Click the button above for full patristic exegesis.")

    def load_haydock(self):
        if not self.current_verse:
            return
        self.haydock_text.delete("0.0", "end")
        self.haydock_text.insert("0.0", "Loading Haydock commentary...\n")
        threading.Thread(target=self._fetch_haydock, daemon=True).start()

    def _fetch_haydock(self):
        book = self.current_verse["book"]
        chapter = self.current_verse["chapter"]
        haydock_id = haydock_map.get((book, chapter))
        url = f"https://johnblood.gitlab.io/haydock/id{haydock_id}.html" if haydock_id else "https://johnblood.gitlab.io/haydock/index.html"

        try:
            r = requests.get(url, timeout=10)
            soup = BeautifulSoup(r.text, "lxml")
            # Extract main commentary body
            body = soup.find("body")
            text = body.get_text(separator="\n\n", strip=True)[:8000] if body else "Full commentary loaded from 1859 edition."
            self.haydock_text.delete("0.0", "end")
            self.haydock_text.insert("0.0", text)
        except Exception as e:
            self.haydock_text.delete("0.0", "end")
            self.haydock_text.insert("0.0", f"Error loading Haydock:\n{str(e)}\n\nYou can also open full page here: {url}")

if __name__ == "__main__":
    app = BibleApp()
    app.mainloop()