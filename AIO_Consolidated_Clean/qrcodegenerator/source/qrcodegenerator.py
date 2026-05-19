import tkinter as tk
from tkinter import filedialog, messagebox
import os

import qrcode
from PIL import Image, ImageTk


class QRCodeGeneratorApp:
	def __init__(self, root: tk.Tk) -> None:
		self.root = root
		self.root.title("QR Code & Image to STL Converter")
		self.root.geometry("500x620")
		self.root.resizable(False, False)

		self.generated_image = None
		self.qr_matrix = None
		self.uploaded_image = None
		self.preview_photo = None
		self.last_saved_path = ""

		self._build_ui()

	def _build_ui(self) -> None:
		# Create notebook-style tabs with frames
		self.tab_frame = tk.Frame(self.root)
		self.tab_frame.pack(fill="both", expand=True, padx=8, pady=8)

		# Tab buttons
		tab_button_frame = tk.Frame(self.root, relief="sunken", bd=1)
		tab_button_frame.pack(fill="x", padx=8, pady=(0, 8))

		qr_tab_btn = tk.Button(tab_button_frame, text="QR Generator", command=self._show_qr_tab)
		qr_tab_btn.pack(side="left", padx=2, pady=2)

		png_tab_btn = tk.Button(tab_button_frame, text="PNG to STL", command=self._show_png_tab)
		png_tab_btn.pack(side="left", padx=2, pady=2)

		# Build tab content
		self._build_qr_tab()
		self._build_png_tab()

		# Show QR tab by default
		self._show_qr_tab()

	def _build_qr_tab(self) -> None:
		self.qr_tab = tk.Frame(self.tab_frame)

		title = tk.Label(self.qr_tab, text="Website QR Code Generator", font=("Segoe UI", 14, "bold"))
		title.pack(anchor="w", pady=(0, 12))

		prompt = tk.Label(self.qr_tab, text="Enter website URL:", font=("Segoe UI", 10))
		prompt.pack(anchor="w")

		self.url_entry = tk.Entry(self.qr_tab, font=("Segoe UI", 10), width=50)
		self.url_entry.pack(fill="x", pady=(6, 12))
		self.url_entry.insert(0, "https://")

		button_row = tk.Frame(self.qr_tab)
		button_row.pack(fill="x", pady=(0, 6))

		button_row2 = tk.Frame(self.qr_tab)
		button_row2.pack(fill="x", pady=(0, 12))

		generate_btn = tk.Button(button_row, text="Generate QR", command=self.generate_qr)
		generate_btn.pack(side="left")

		save_btn = tk.Button(button_row, text="Save QR", command=self.save_qr)
		save_btn.pack(side="left", padx=(8, 0))

		export_stl_btn = tk.Button(button_row, text="Export STL", command=self.export_qr_stl)
		export_stl_btn.pack(side="left", padx=(8, 0))

		clear_btn = tk.Button(button_row, text="Clear", command=self.clear_qr_form)
		clear_btn.pack(side="left", padx=(8, 0))

		open_folder_btn = tk.Button(button_row2, text="Open Save Location", command=self.open_save_location)
		open_folder_btn.pack(side="left")

		copy_url_btn = tk.Button(button_row2, text="Copy URL", command=self.copy_url)
		copy_url_btn.pack(side="left", padx=(8, 0))

		copy_path_btn = tk.Button(button_row2, text="Copy Saved Path", command=self.copy_saved_path)
		copy_path_btn.pack(side="left", padx=(8, 0))

		self.qr_preview_label = tk.Label(
			self.qr_tab,
			text="QR preview will appear here",
			relief="groove",
			width=54,
			height=18,
			anchor="center",
		)
		self.qr_preview_label.pack(fill="both", expand=True)

	def _build_png_tab(self) -> None:
		self.png_tab = tk.Frame(self.tab_frame)

		title = tk.Label(self.png_tab, text="PNG to STL Converter", font=("Segoe UI", 14, "bold"))
		title.pack(anchor="w", pady=(0, 12))

		upload_btn = tk.Button(self.png_tab, text="Upload PNG Image", command=self.upload_png)
		upload_btn.pack(fill="x", pady=(0, 12))

		# STL options frame
		options_frame = tk.LabelFrame(self.png_tab, text="STL Export Options", padx=8, pady=8)
		options_frame.pack(fill="x", pady=(0, 12))

		tk.Label(options_frame, text="Export Mode:", font=("Segoe UI", 10)).pack(anchor="w")
		self.png_stl_mode = tk.StringVar(value="standard")
		tk.Radiobutton(options_frame, text="Standard (Black → Raised)", variable=self.png_stl_mode, value="standard").pack(anchor="w")
		tk.Radiobutton(options_frame, text="Inverted (Black → Recessed)", variable=self.png_stl_mode, value="inverted").pack(anchor="w")

		tk.Label(options_frame, text="Threshold (0-255, darker=raised):", font=("Segoe UI", 10)).pack(anchor="w", pady=(8, 0))
		self.threshold_var = tk.IntVar(value=128)
		threshold_scale = tk.Scale(options_frame, from_=0, to=255, orient="horizontal", variable=self.threshold_var)
		threshold_scale.pack(fill="x")

		tk.Label(options_frame, text="Height (mm):", font=("Segoe UI", 10)).pack(anchor="w", pady=(8, 0))
		self.png_height_var = tk.DoubleVar(value=2.0)
		height_spinbox = tk.Spinbox(options_frame, from_=0.5, to=10.0, increment=0.5, textvariable=self.png_height_var)
		height_spinbox.pack(fill="x")

		export_png_stl_btn = tk.Button(self.png_tab, text="Export PNG as STL", command=self.export_png_stl)
		export_png_stl_btn.pack(fill="x", pady=(0, 12))

		self.png_preview_label = tk.Label(
			self.png_tab,
			text="PNG preview will appear here",
			relief="groove",
			width=54,
			height=16,
			anchor="center",
		)
		self.png_preview_label.pack(fill="both", expand=True)

	def _show_qr_tab(self) -> None:
		self.qr_tab.tkraise()
		self.qr_tab.pack(fill="both", expand=True)
		if hasattr(self, "png_tab"):
			self.png_tab.pack_forget()

	def _show_png_tab(self) -> None:
		self.png_tab.tkraise()
		self.png_tab.pack(fill="both", expand=True)
		self.qr_tab.pack_forget()

	def _normalize_url(self, url: str) -> str:
		cleaned = url.strip()
		if not cleaned:
			return ""
		if not cleaned.startswith(("http://", "https://")):
			cleaned = f"https://{cleaned}"
		return cleaned

	def generate_qr(self) -> None:
		url = self._normalize_url(self.url_entry.get())
		if not url:
			messagebox.showerror("Missing URL", "Please enter a website URL.")
			return

		qr = qrcode.QRCode(version=1, box_size=10, border=4)
		qr.add_data(url)
		qr.make(fit=True)
		self.qr_matrix = qr.get_matrix()
		self.generated_image = qr.make_image(fill_color="black", back_color="white").convert("RGB")

		preview_image = self.generated_image.resize((280, 280))
		self.preview_photo = ImageTk.PhotoImage(preview_image)
		self.qr_preview_label.configure(image=self.preview_photo, text="")

	def save_qr(self) -> None:
		if self.generated_image is None:
			messagebox.showwarning("No QR Code", "Generate a QR code first.")
			return

		save_path = filedialog.asksaveasfilename(
			defaultextension=".png",
			filetypes=[("PNG Image", "*.png")],
			title="Save QR Code",
		)
		if not save_path:
			return

		self.generated_image.save(save_path)
		self.last_saved_path = save_path
		messagebox.showinfo("Saved", f"QR code saved to:\n{save_path}")

	def open_save_location(self) -> None:
		if not self.last_saved_path:
			messagebox.showwarning("No Saved File", "Save a QR code first, then open its location.")
			return

		folder_path = os.path.dirname(self.last_saved_path)
		if not os.path.isdir(folder_path):
			messagebox.showerror("Folder Not Found", "The saved folder could not be found.")
			return

		os.startfile(folder_path)

	def clear_qr_form(self) -> None:
		self.url_entry.delete(0, tk.END)
		self.url_entry.insert(0, "https://")
		self.generated_image = None
		self.qr_matrix = None
		self.preview_photo = None
		self.qr_preview_label.configure(image="", text="QR preview will appear here")

	def copy_url(self) -> None:
		url = self._normalize_url(self.url_entry.get())
		if not url:
			messagebox.showwarning("No URL", "Enter a website URL first.")
			return

		self.root.clipboard_clear()
		self.root.clipboard_append(url)
		self.root.update()
		messagebox.showinfo("Copied", "Website URL copied to clipboard.")

	def copy_saved_path(self) -> None:
		if not self.last_saved_path:
			messagebox.showwarning("No Saved File", "Save a file first.")
			return

		self.root.clipboard_clear()
		self.root.clipboard_append(self.last_saved_path)
		self.root.update()
		messagebox.showinfo("Copied", "Saved file path copied to clipboard.")

	def export_qr_stl(self) -> None:
		if self.qr_matrix is None:
			messagebox.showwarning("No QR Code", "Generate a QR code first.")
			return

		save_path = filedialog.asksaveasfilename(
			defaultextension=".stl",
			filetypes=[("STL File", "*.stl")],
			title="Export QR as STL",
		)
		if not save_path:
			return

		try:
			self._write_qr_stl(save_path, self.qr_matrix)
		except OSError as error:
			messagebox.showerror("Export Failed", f"Could not save STL:\n{error}")
			return

		self.last_saved_path = save_path
		messagebox.showinfo("Exported", f"STL exported to:\n{save_path}")

	def upload_png(self) -> None:
		file_path = filedialog.askopenfilename(
			filetypes=[("PNG Image", "*.png"), ("All Images", "*.jpg *.jpeg *.bmp *.gif")],
			title="Select PNG Image",
		)
		if not file_path:
			return

		try:
			self.uploaded_image = Image.open(file_path).convert("L")
		except Exception as error:
			messagebox.showerror("Load Failed", f"Could not load image:\n{error}")
			return

		preview_image = self.uploaded_image.copy()
		preview_image.thumbnail((280, 280))
		self.preview_photo = ImageTk.PhotoImage(preview_image)
		self.png_preview_label.configure(image=self.preview_photo, text="")

	def export_png_stl(self) -> None:
		if self.uploaded_image is None:
			messagebox.showwarning("No Image", "Upload a PNG image first.")
			return

		save_path = filedialog.asksaveasfilename(
			defaultextension=".stl",
			filetypes=[("STL File", "*.stl")],
			title="Export PNG as STL",
		)
		if not save_path:
			return

		try:
			mode = self.png_stl_mode.get()
			threshold = self.threshold_var.get()
			height = self.png_height_var.get()
			self._write_png_stl(save_path, self.uploaded_image, mode, threshold, height)
		except OSError as error:
			messagebox.showerror("Export Failed", f"Could not save STL:\n{error}")
			return

		self.last_saved_path = save_path
		messagebox.showinfo("Exported", f"PNG STL exported to:\n{save_path}")

	def _write_qr_stl(self, save_path: str, matrix) -> None:
		module_size = 1.0
		base_thickness = 1.2
		raised_height = 2.0

		rows = len(matrix)
		cols = len(matrix[0])

		triangles = []
		triangles.extend(self._box_triangles(0.0, 0.0, 0.0, cols * module_size, rows * module_size, base_thickness))

		for row_index, row in enumerate(matrix):
			for col_index, is_dark in enumerate(row):
				if not is_dark:
					continue
				x0 = col_index * module_size
				y0 = row_index * module_size
				x1 = x0 + module_size
				y1 = y0 + module_size
				triangles.extend(
					self._box_triangles(x0, y0, base_thickness, x1, y1, base_thickness + raised_height)
				)

		self._write_stl_file(save_path, triangles)

	def _write_png_stl(self, save_path: str, image: Image.Image, mode: str, threshold: int, height: float) -> None:
		"""Convert grayscale image to STL with standard or inverted mode."""
		base_thickness = 1.2
		pixel_size = 1.0

		width, image_height = image.size
		pixels = image.load()

		triangles = []
		triangles.extend(self._box_triangles(0.0, 0.0, 0.0, width * pixel_size, image_height * pixel_size, base_thickness))

		for row in range(image_height):
			for col in range(width):
				gray_value = pixels[col, row]

				# Standard: darker pixels (< threshold) are raised
				# Inverted: brighter pixels (> threshold) are raised
				if mode == "standard":
					should_raise = gray_value < threshold
				else:
					should_raise = gray_value >= threshold

				if not should_raise:
					continue

				x0 = col * pixel_size
				y0 = row * pixel_size
				x1 = x0 + pixel_size
				y1 = y0 + pixel_size
				triangles.extend(
					self._box_triangles(x0, y0, base_thickness, x1, y1, base_thickness + height)
				)

		self._write_stl_file(save_path, triangles)

	def _box_triangles(self, x0: float, y0: float, z0: float, x1: float, y1: float, z1: float):
		"""Generate 12 triangles for a box."""
		v000 = (x0, y0, z0)
		v100 = (x1, y0, z0)
		v110 = (x1, y1, z0)
		v010 = (x0, y1, z0)
		v001 = (x0, y0, z1)
		v101 = (x1, y0, z1)
		v111 = (x1, y1, z1)
		v011 = (x0, y1, z1)

		return [
			((0.0, 0.0, 1.0), v001, v101, v111),
			((0.0, 0.0, 1.0), v001, v111, v011),
			((0.0, 0.0, -1.0), v000, v110, v100),
			((0.0, 0.0, -1.0), v000, v010, v110),
			((1.0, 0.0, 0.0), v100, v110, v111),
			((1.0, 0.0, 0.0), v100, v111, v101),
			((-1.0, 0.0, 0.0), v000, v011, v010),
			((-1.0, 0.0, 0.0), v000, v001, v011),
			((0.0, 1.0, 0.0), v010, v111, v110),
			((0.0, 1.0, 0.0), v010, v011, v111),
			((0.0, -1.0, 0.0), v000, v100, v101),
			((0.0, -1.0, 0.0), v000, v101, v001),
		]

	def _write_stl_file(self, save_path: str, triangles) -> None:
		"""Write triangles to ASCII STL file."""
		with open(save_path, "w", encoding="utf-8") as stl_file:
			stl_file.write("solid model\n")
			for normal, v1, v2, v3 in triangles:
				stl_file.write(f"  facet normal {normal[0]} {normal[1]} {normal[2]}\n")
				stl_file.write("    outer loop\n")
				stl_file.write(f"      vertex {v1[0]} {v1[1]} {v1[2]}\n")
				stl_file.write(f"      vertex {v2[0]} {v2[1]} {v2[2]}\n")
				stl_file.write(f"      vertex {v3[0]} {v3[1]} {v3[2]}\n")
				stl_file.write("    endloop\n")
				stl_file.write("  endfacet\n")
			stl_file.write("endsolid model\n")


if __name__ == "__main__":
	app_root = tk.Tk()
	app = QRCodeGeneratorApp(app_root)
	app_root.mainloop()
