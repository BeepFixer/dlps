import json
import os
import base64
import csv
import re
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from urllib.parse import urlparse, parse_qs, unquote, urljoin

import requests
from bs4 import BeautifulSoup

APP_TITLE = "Dead Link Plunder Skip - v01.00 | by BeepFixer"


def decode_b64(value):
    if not value:
        return None
    value = unquote(value.strip())
    value += "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value).decode("utf-8", errors="replace").strip()
    except Exception:
        return None


def decode_destination(url):
    """Decode a Base64 destination in the URL query parameter named 'url'."""
    try:
        encoded = parse_qs(urlparse(url).query).get("url", [None])[0]
        decoded = decode_b64(encoded)
        if decoded and decoded.startswith(("http://", "https://")):
            return decoded
    except Exception:
        pass
    return url


def find_spoiler_identifier(spoiler):
    """Get the closest preceding paragraph outside a spoiler block."""
    for paragraph in spoiler.find_all_previous("p"):
        if paragraph.find_parent(class_="su-spoiler"):
            continue
        value = paragraph.get_text(" ", strip=True)
        if value:
            return value
    return "(no preceding paragraph label)"



def find_source_text_line(anchor):
    """Return the readable text line containing this link, with URLs omitted."""
    paragraph = anchor.find_parent("p")
    if paragraph:
        return paragraph.get_text(" ", strip=True)

    # Fallback for markup that uses list items or divs instead of paragraphs.
    for parent in anchor.parents:
        if getattr(parent, "name", None) in ("li", "div"):
            if "su-spoiler-content" in (parent.get("class") or []):
                break
            text = parent.get_text(" ", strip=True)
            if text:
                return text

    return anchor.get_text(" ", strip=True) or "(no surrounding text line)"

def extract_download_spoiler_links(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    results, seen = [], set()
    diagnostics = {
        "page_title": soup.title.get_text(" ", strip=True) if soup.title else "(no title)",
        "spoiler_wrappers": len(soup.select(".su-spoiler")),
        "spoiler_titles": len(soup.select(".su-spoiler-title")),
        "spoiler_contents": len(soup.select(".su-spoiler-content")),
        "secure_data_blocks": len(soup.select(".secure-data")),
        "all_page_links": len(soup.select("a[href]")),
        "matching_spoilers": 0,
    }

    # Inspect every spoiler block with a title and content. Titles vary
    # between pages (for example, "Link Download", "Link Mirror 2", etc.).
    for spoiler in soup.select(".su-spoiler"):
        title = spoiler.select_one(".su-spoiler-title")
        content = spoiler.select_one(".su-spoiler-content")
        if not title or not content:
            continue

        title_text = title.get_text(" ", strip=True)
        diagnostics["matching_spoilers"] += 1
        spoiler_identifier = find_spoiler_identifier(spoiler)

        # Usually anchors are already present. Some pages put the spoiler
        # HTML inside Base64 .secure-data[data-payload], so inspect that too.
        anchors = list(content.select("a[href]"))
        for secure in content.select(".secure-data[data-payload]"):
            decoded_html = decode_b64(secure.get("data-payload"))
            if decoded_html:
                payload_soup = BeautifulSoup(decoded_html, "html.parser")
                anchors.extend(payload_soup.select("a[href]"))

        for anchor in anchors:
            href = (anchor.get("href") or "").strip()
            if not href:
                continue
            original = urljoin(page_url, href)
            if original in seen:
                continue
            seen.add(original)

            label = anchor.get_text(" ", strip=True)
            if not label:
                img = anchor.select_one("img[alt]")
                label = img.get("alt", "").strip() if img else ""
            if not label:
                label = "(no visible link text)"

            results.append({
                "section_title": title_text,
                "spoiler_identifier": spoiler_identifier,
                "label": label,
                "destination_url": decode_destination(original),
                "source_line": find_source_text_line(anchor),
            })

    return results, diagnostics



class LinkExtractorApp:
    COLUMNS = ("open", "copy", "label", "source_line", "destination", "identifier", "section")
    INFO = {
        "open": ("Open URL", 85), "copy": ("Copy URL", 85), "label": ("Storage", 150),
        "source_line": ("Source text line", 300), "destination": ("Decoded destination URL", 430),
        "identifier": ("Spoiler / Version", 190), "section": ("Spoiler Title", 150),
    }

    def __init__(self, root):
        self.root = root
        self.root.title("Dead Link Plunder Skip - v01.00 | by BeepFixer")
        self.settings_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                          "deadlink_plunder_skip_settings.json")
        self.settings = self.defaults()
        self.load_settings(False)
        self.set_bomb_icon()
        root.geometry("1420x720")
        root.minsize(820, 500)
        self.results = []
        self.status = tk.StringVar(value="Paste a webpage URL, then click Extract links.")
        self.build_ui()
        self.apply_columns()

    def defaults(self):
        return {"column_order": list(self.COLUMNS), "visible_columns": list(self.COLUMNS)}

    def set_bomb_icon(self):
        icon = tk.PhotoImage(width=32, height=32)

        def px(x, y, color):
            icon.put(color, to=(x, y, x + 1, y + 1))

        black = "#19191c"
        dark_gray = "#2d2d32"
        white = "#f5f5f5"

        # Flag rectangle with frayed right edge
        for y in range(4, 28):
            for x in range(1, 31):
                if x == 30 and y in (6, 7, 13, 14, 15, 21, 22, 25):
                    continue
                if x == 29 and y in (14, 22):
                    continue
                px(x, y, black)

        # Top highlight border
        for x in range(1, 30):
            px(x, 4, dark_gray)

        # Skull
        skull_rows = [
            (8,  "      XXXX      "),
            (9,  "    XXXXXXXX    "),
            (10, "   XXXXXXXXXX   "),
            (11, "   XXXXXXXXXX   "),
            (12, "   XX  XX  XX   "),
            (13, "   XX  XX  XX   "),
            (14, "    XXXXXXXX    "),
            (15, "     XX  XX     "),
            (16, "      XXXX      "),
            (17, "     X X X      "),
        ]
        for y, row in skull_rows:
            for i, ch in enumerate(row):
                if ch == "X":
                    px(8 + i, y, white)

        # Crossbones
        bones = [
            (7, 17), (8, 17), (7, 18), (8, 18),
            (9, 18), (10, 19), (11, 19), (12, 20), (13, 20), (14, 21), (15, 21),
            (16, 22), (17, 22), (18, 23), (19, 23), (20, 24), (21, 24),
            (22, 24), (23, 24), (22, 25), (23, 25),
            (22, 17), (23, 17), (22, 18), (23, 18),
            (21, 18), (20, 19), (19, 19), (18, 20), (17, 20), (16, 21), (15, 21),
            (14, 22), (13, 22), (12, 23), (11, 23), (10, 24), (9, 24),
            (7, 24), (8, 24), (7, 25), (8, 25),
        ]
        for x, y in bones:
            px(x, y, white)

        self._window_icon = icon
        self.root.iconphoto(True, icon)

    def build_ui(self):
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Dead Link Plunder Skip - v01.00 | by BeepFixer",
                  font=("TkDefaultFont", 13, "bold")).pack(anchor="w", pady=(0, 10))
        ttk.Label(outer, text="Source webpage URL:").pack(anchor="w")
        row = ttk.Frame(outer)
        row.pack(fill="x", pady=(4, 10))
        self.url_entry = ttk.Entry(row, font=("TkDefaultFont", 13))
        self.url_entry.pack(side="left", fill="x", expand=True, ipady=5)
        self.url_entry.bind("<Return>", lambda _e: self.start_extract())
        self.extract_button = ttk.Button(row, text="Extract links", command=self.start_extract)
        self.extract_button.pack(side="left", padx=(8, 0))
        ttk.Label(outer, text=(
            "Links from all titled spoiler blocks are shown, whatever their title. "
            "Storage shows the link text from the webpage; Source text line shows its surrounding text. "
            "Use Open URL or Copy URL at the left of each row for its decoded destination."
        )).pack(anchor="w", pady=(0, 8))

        # Left-align headings and result cells; make headings bold.
        tree_style = ttk.Style(self.root)
        tree_style.configure(
            "Plunder.Treeview.Heading",
            font=("TkDefaultFont", 10, "bold"),
            anchor="w",
        )
        tree_style.configure(
            "Plunder.Treeview",
            font=("TkDefaultFont", 10),
        )

        self.tree = ttk.Treeview(
            outer, columns=self.COLUMNS, show="headings", height=17,
            style="Plunder.Treeview"
        )
        for col in self.COLUMNS:
            heading, width = self.INFO[col]
            self.tree.heading(col, text=heading, anchor="w")
            self.tree.column(
                col, width=width, anchor="w",
                stretch=col in ("destination", "source_line")
            )
        ys = ttk.Scrollbar(outer, orient="vertical", command=self.tree.yview)
        xs = ttk.Scrollbar(outer, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree.bind("<Motion>", self.on_tree_motion)
        self.tree.pack(side="top", fill="both", expand=True)
        ys.pack(side="right", fill="y")
        xs.pack(fill="x")
        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(actions, text="Copy selected destinations", command=self.copy_selected).pack(side="left")
        ttk.Button(actions, text="Copy all destinations", command=self.copy_all).pack(side="left", padx=6)
        ttk.Button(actions, text="Save results…", command=self.save_results).pack(side="left")
        ttk.Button(actions, text="Settings", command=self.open_settings).pack(side="left", padx=(6, 0))
        ttk.Label(outer, textvariable=self.status, wraplength=1100).pack(anchor="w", pady=(10, 0))

    def apply_columns(self):
        order = [c for c in self.settings["column_order"] if c in self.COLUMNS]
        order += [c for c in self.COLUMNS if c not in order]
        visible = [c for c in order if c in self.settings["visible_columns"]]
        self.tree.configure(displaycolumns=tuple(visible))

    def save_settings(self, notify=True):
        try:
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
            if notify:
                self.status.set("Settings saved.")
        except OSError as exc:
            messagebox.showerror("Settings save failed", str(exc))

    def load_settings(self, notify=True):
        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            order, visible = data.get("column_order", []), data.get("visible_columns", [])
            if not isinstance(order, list) or not isinstance(visible, list):
                raise ValueError("Invalid settings format.")
            order = [c for c in order if c in self.COLUMNS]
            order += [c for c in self.COLUMNS if c not in order]
            visible = [c for c in visible if c in self.COLUMNS]
            self.settings = {"column_order": order, "visible_columns": visible}
            if notify:
                self.status.set("Settings loaded.")
            return True
        except FileNotFoundError:
            self.settings = self.defaults()
            return False
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self.settings = self.defaults()
            if notify:
                messagebox.showwarning("Could not load settings", str(exc))
            return False

    def open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("Dead Link Plunder Skip - Settings")
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)
        frame = ttk.Frame(win, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Column order (top to bottom):").grid(
            row=0, column=0, columnspan=2, sticky="w")
        lb = tk.Listbox(frame, height=len(self.COLUMNS), exportselection=False, width=31)
        lb.grid(row=1, column=0, rowspan=5, sticky="nsew", pady=(5, 8))
        show_var = tk.BooleanVar(value=True)
        check = ttk.Checkbutton(frame, text="Show selected column", variable=show_var)
        check.grid(row=1, column=1, sticky="w", padx=(10, 0), pady=(5, 8))
        order = list(self.settings["column_order"])
        visible = set(self.settings["visible_columns"])

        def refresh(index=None):
            lb.delete(0, "end")
            for col in order:
                lb.insert("end", ("✓  " if col in visible else "–  ") + self.INFO[col][0])
            if index is not None and order:
                index = max(0, min(index, len(order)-1))
                lb.selection_set(index)
                lb.activate(index)
                show_var.set(order[index] in visible)

        def selected():
            cur = lb.curselection()
            return cur[0] if cur else None

        def selection_changed(_event=None):
            i = selected()
            if i is not None:
                show_var.set(order[i] in visible)

        def toggle():
            i = selected()
            if i is None:
                return
            if show_var.get():
                visible.add(order[i])
            else:
                visible.discard(order[i])
            refresh(i)

        check.configure(command=toggle)

        def move(delta):
            i = selected()
            if i is not None and 0 <= i + delta < len(order):
                j = i + delta
                order[i], order[j] = order[j], order[i]
                refresh(j)

        def save_and_close():
            self.settings = {"column_order": list(order),
                             "visible_columns": [c for c in order if c in visible]}
            self.apply_columns()
            self.save_settings()
            win.destroy()

        def load_into_dialog():
            if self.load_settings(False):
                order[:] = self.settings["column_order"]
                visible.clear()
                visible.update(self.settings["visible_columns"])
                refresh(0)
            else:
                messagebox.showinfo("No saved settings", "No saved settings file was found.")

        def reset():
            d = self.defaults()
            order[:] = d["column_order"]
            visible.clear()
            visible.update(d["visible_columns"])
            refresh(0)

        lb.bind("<<ListboxSelect>>", selection_changed)
        ttk.Button(frame, text="Move up", command=lambda: move(-1)).grid(
            row=2, column=1, sticky="ew", padx=(10, 0), pady=3)
        ttk.Button(frame, text="Move down", command=lambda: move(1)).grid(
            row=3, column=1, sticky="ew", padx=(10, 0), pady=3)
        ttk.Button(frame, text="Save Settings", command=save_and_close).grid(
            row=6, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(frame, text="Load Settings", command=load_into_dialog).grid(
            row=6, column=1, sticky="ew", padx=(8, 0), pady=(4, 0))
        ttk.Button(frame, text="Reset to Defaults", command=reset).grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(frame, text="Close", command=win.destroy).grid(
            row=8, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        refresh(0)

    def start_extract(self):
        url = self.url_entry.get().strip()
        if not url.startswith(("http://", "https://")):
            messagebox.showwarning("Invalid URL", "Enter a complete URL beginning with http:// or https://.")
            return
        self.extract_button.configure(state="disabled")
        self.status.set("Fetching webpage…")
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.results = []
        threading.Thread(target=self._worker, args=(url,), daemon=True).start()

    def _worker(self, page_url):
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            response = requests.get(page_url, headers=headers, timeout=30, allow_redirects=True)
            response.raise_for_status()
            found, diag = extract_download_spoiler_links(response.text, response.url)
            diag["http_status"] = response.status_code
            self.root.after(0, self._show_results, found, diag, None)
        except requests.RequestException as exc:
            self.root.after(0, self._show_results, [], None, f"Request failed: {exc}")
        except Exception as exc:
            self.root.after(0, self._show_results, [], None, f"Extraction error: {exc}")

    def _show_results(self, found, diag, error):
        self.extract_button.configure(state="normal")
        self.results = found
        if error:
            self.status.set(error)
            messagebox.showerror("Fetch error", error)
            return
        for item in found:
            row = {
                "open": "Open URL", "copy": "Copy URL", "label": item["label"],
                "source_line": item["source_line"], "destination": item["destination_url"],
                "identifier": item["spoiler_identifier"], "section": item["section_title"],
            }
            self.tree.insert("", "end", values=tuple(row[c] for c in self.COLUMNS))
        if found:
            self.status.set(f"Found {len(found)} link(s) across {diag['matching_spoilers']} "
                            f"spoiler block(s). HTTP {diag['http_status']}.")
        else:
            self.status.set(
                f"No matching links. HTTP {diag['http_status']}; "
                f"spoilers={diag['spoiler_wrappers']}, titles={diag['spoiler_titles']}, "
                f"contents={diag['spoiler_contents']}, secure-data={diag['secure_data_blocks']}, "
                f"all page links={diag['all_page_links']}. "
                "The server may have returned different HTML or JavaScript-loaded content."
            )

    def _destination_for_row(self, row_id):
        return self.tree.item(row_id, "values")[self.COLUMNS.index("destination")]

    def _logical_column_at_event(self, event):
        shown = self.tree["displaycolumns"]
        if isinstance(shown, str):
            shown = (shown,)
        if shown == ("#all",):
            shown = self.COLUMNS
        col = self.tree.identify_column(event.x)
        try:
            return shown[int(col[1:])-1]
        except (ValueError, IndexError):
            return None

    def on_tree_click(self, event):
        row_id = self.tree.identify_row(event.y)
        col = self._logical_column_at_event(event)
        if row_id and col in ("open", "copy"):
            url = self._destination_for_row(row_id)
            if col == "open":
                self.open_destination(url)
            else:
                self._copy(url)
                self.status.set("Copied destination URL to clipboard.")
            return "break"

    def on_tree_motion(self, event):
        col = self._logical_column_at_event(event)
        self.tree.configure(cursor="hand2" if col in ("open", "copy") else "")

    def open_destination(self, url):
        url = (url or "").strip()
        if not url.startswith(("http://", "https://")):
            messagebox.showwarning("Invalid destination", "This row does not contain a valid web URL.")
            return
        try:
            webbrowser.open(url, new=2)
            self.status.set(f"Opening destination in your browser: {url}")
        except Exception as exc:
            messagebox.showerror("Could not open URL", str(exc))

    def _copy(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def copy_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Nothing selected", "Select one or more rows first.")
            return
        self._copy("\n".join(self._destination_for_row(i) for i in selected))
        self.status.set(f"Copied {len(selected)} destination URL(s).")

    def copy_all(self):
        if not self.results:
            messagebox.showinfo("No results", "Extract links first.")
            return
        self._copy("\n".join(x["destination_url"] for x in self.results))
        self.status.set(f"Copied all {len(self.results)} destination URL(s).")

    def save_results(self):
        if not self.results:
            messagebox.showinfo("No results", "Extract links first.")
            return
        path = filedialog.asksaveasfilename(
            title="Save extracted links", defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            if path.lower().endswith(".txt"):
                with open(path, "w", encoding="utf-8") as f:
                    for x in self.results:
                        f.write(f"Version: {x['spoiler_identifier']}\n")
                        f.write(f"Spoiler: {x['section_title']}\n")
                        f.write(f"Link text: {x['label']}\n")
                        f.write(f"Destination: {x['destination_url']}\n")
                        f.write(f"Source text line: {x['source_line']}\n\n")
            else:
                with open(path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=[
                        "spoiler_identifier", "section_title", "label", "destination_url", "source_line"
                    ])
                    writer.writeheader()
                    writer.writerows(self.results)
            self.status.set(f"Saved {len(self.results)} result(s) to {path}")
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc))


if __name__ == "__main__":
    root = tk.Tk()
    LinkExtractorApp(root)
    root.mainloop()
