
import tkinter as tk
from tkinter import ttk

class DebugWindow:
    def __init__(self, title="UsefulClicker Debug"):
        self.root = tk.Tk()
        self.root.title(title)
        self.text = tk.Text(self.root, wrap="none", width=120, height=40)
        self.text.pack(fill="both", expand=True)
        self.text.configure(font=("Consolas", 10))
        self.current_tag = "current"
        self.text.tag_configure(self.current_tag, background="yellow")
        self.root.update()

    def set_code(self, xml_text: str):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", xml_text)
        self.root.update()

    def highlight_range(self, start_idx: int, end_idx: int):
        # Clear old highlight
        self.text.tag_remove(self.current_tag, "1.0", "end")
        # Convert positions considering 0-based offsets
        # Rough mapping: find index by counting chars
        s = int(start_idx)
        e = int(end_idx)
        # Get current full text
        full = self.text.get("1.0", "end-1c")
        s_line = full.count("\n", 0, s) + 1
        s_col  = s - (full.rfind("\n", 0, s) + 1 if "\n" in full[:s] else 0) + 1
        e_line = full.count("\n", 0, e) + 1
        e_col  = e - (full.rfind("\n", 0, e) + 1 if "\n" in full[:e] else 0) + 1

        start = f"{s_line}.{s_col-1}"
        end   = f"{e_line}.{e_col-1}"
        self.text.tag_add(self.current_tag, start, end)
        self.text.see(start)
        self.root.update()

    def pulse(self):
        try:
            self.root.update()
        except tk.TclError:
            pass

    def mainloop(self):
        self.root.mainloop()
