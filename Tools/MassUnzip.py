"""Mass extract archives from files or folders into a target directory."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path, PurePosixPath
import shutil
import sys
import zipfile
import tkinter as tk
from tkinter import filedialog, messagebox

try:
	import py7zr
except ImportError:  # pragma: no cover - optional dependency
	py7zr = None

try:
	import rarfile
except ImportError:  # pragma: no cover - optional dependency
	rarfile = None


def _is_within_directory(base_dir: Path, target_path: Path) -> bool:
	try:
		target_path.resolve().relative_to(base_dir.resolve())
		return True
	except ValueError:
		return False


def _ensure_safe_paths(dest_dir: Path, names: list[str], archive_path: Path) -> None:
	for name in names:
		member_path = dest_dir / name
		if not _is_within_directory(dest_dir, member_path):
			raise RuntimeError(
				f"Blocked path traversal in {archive_path}: {name}"
			)


def _find_archives(input_paths: list[Path], extensions: set[str]) -> list[Path]:
	archives: list[Path] = []
	for path in input_paths:
		if path.is_file() and path.suffix.lower() in extensions:
			archives.append(path)
		elif path.is_dir():
			for ext in extensions:
				archives.extend(path.rglob(f"*{ext}"))
	return archives


def _find_files(input_paths: list[Path], extensions: set[str]) -> list[Path]:
	files: list[Path] = []
	for path in input_paths:
		if path.is_file() and path.suffix.lower() in extensions:
			files.append(path)
		elif path.is_dir():
			for ext in extensions:
				files.extend(path.rglob(f"*{ext}"))
	return files


def _unique_dest_dir(base_dir: Path, name: str) -> Path:
	candidate = base_dir / name
	if not candidate.exists():
		return candidate
	counter = 1
	while True:
		candidate = base_dir / f"{name}_{counter}"
		if not candidate.exists():
			return candidate
		counter += 1


def _parse_args(argv: list[str]) -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description=(
			"Mass extract zip/7z/rar files from one or more files/folders into a target folder."
		)
	)
	parser.set_defaults(recursive=True, delete_archives=True)
	parser.add_argument(
		"inputs",
		nargs="+",
		help="Archive files or folders to scan for archives.",
	)
	parser.add_argument(
		"-o",
		"--output",
		required=True,
		help="Destination folder for extracted files.",
	)
	parser.add_argument(
		"--flat",
		action="store_true",
		help="Extract all archives directly into the output folder.",
	)
	parser.add_argument(
		"--overwrite",
		action="store_true",
		help="Allow overwriting existing files while extracting.",
	)
	parser.add_argument(
		"--dry-run",
		action="store_true",
		help="List what would be extracted without writing files.",
	)
	parser.add_argument(
		"--recursive",
		action="store_true",
		help="Extract nested archives inside extracted folders.",
	)
	parser.add_argument(
		"--no-recursive",
		action="store_false",
		dest="recursive",
		help="Do not extract nested archives.",
	)
	parser.add_argument(
		"--extensions",
		help=(
			"Comma-separated list of extensions to scan (default: zip,7z,rar). "
			"Example: --extensions zip,7z"
		),
	)
	parser.add_argument(
		"--copy-extensions",
		help=(
			"Comma-separated list of non-archive extensions to copy instead of extract. "
			"Example: --copy-extensions stl,3mf"
		),
	)
	parser.add_argument(
		"--delete-archives",
		action="store_true",
		help="Delete archives after successful extraction.",
	)
	parser.add_argument(
		"--keep-archives",
		action="store_false",
		dest="delete_archives",
		help="Keep archives after extraction.",
	)
	parser.add_argument(
		"--report-path",
		help="Optional path for CSV report (default: output/unzip_report.csv).",
	)
	return parser.parse_args(argv)

def _normalize_extensions(raw_extensions: str | None) -> set[str]:
	if not raw_extensions:
		return {".zip", ".7z", ".rar"}
	items = []
	for part in raw_extensions.split(","):
		part = part.strip().lower()
		if not part:
			continue
		items.append(part if part.startswith(".") else f".{part}")
	return set(items)


def _normalize_copy_extensions(raw_extensions: str | None) -> set[str]:
	if not raw_extensions:
		return {".stl", ".3mf"}
	items = []
	for part in raw_extensions.split(","):
		part = part.strip().lower()
		if not part:
			continue
		items.append(part if part.startswith(".") else f".{part}")
	return set(items)


def _get_archive_type(path: Path) -> str:
	ext = path.suffix.lower()
	if ext == ".zip":
		return "zip"
	if ext == ".7z":
		return "7z"
	if ext == ".rar":
		return "rar"
	return "unknown"


def _list_members(archive_path: Path, archive_type: str) -> list[str]:
	if archive_type == "zip":
		with zipfile.ZipFile(archive_path) as zip_file:
			return [member.filename for member in zip_file.infolist()]
	if archive_type == "7z":
		if py7zr is None:
			raise RuntimeError("py7zr is not installed. Run: pip install py7zr")
		with py7zr.SevenZipFile(archive_path, mode="r") as seven_file:
			return list(seven_file.getnames())
	if archive_type == "rar":
		if rarfile is None:
			raise RuntimeError("rarfile is not installed. Run: pip install rarfile")
		with rarfile.RarFile(archive_path) as rar_file:
			return list(rar_file.namelist())
	raise RuntimeError(f"Unsupported archive type: {archive_path}")


def _zip_member_map(
	zip_file: zipfile.ZipFile,
) -> list[tuple[zipfile.ZipInfo, str]]:
	members = zip_file.infolist()
	parts_list = [PurePosixPath(member.filename).parts for member in members]
	top_levels = {parts[0] for parts in parts_list if parts}
	drop_two = len(top_levels) == 1

	mapped: list[tuple[zipfile.ZipInfo, str]] = []
	for member in members:
		parts = PurePosixPath(member.filename).parts
		if not parts:
			continue
		if drop_two:
			if len(parts) >= 3:
				new_parts = parts[2:]
			elif len(parts) == 2:
				new_parts = parts[1:]
			else:
				new_parts = parts
		else:
			new_parts = parts
		if not new_parts:
			continue
		mapped.append((member, "/".join(new_parts)))
	return mapped


def _extract_archive(
	archive_path: Path,
	archive_type: str,
	dest_dir: Path,
	allow_overwrite: bool,
	dry_run: bool,
) -> tuple[str, str]:
	try:
		if archive_type == "zip":
			with zipfile.ZipFile(archive_path) as zip_file:
				mapped = _zip_member_map(zip_file)
				names = [name for _, name in mapped]
				_ensure_safe_paths(dest_dir, names, archive_path)

				if not allow_overwrite:
					for member, name in mapped:
						if member.is_dir():
							continue
						target = dest_dir / name
						if target.exists():
							return "skipped", f"existing file: {target}"

				if dry_run:
					file_count = sum(1 for member, _ in mapped if not member.is_dir())
					return "dry-run", f"{file_count} file(s)"

				for member, name in mapped:
					target = dest_dir / name
					if member.is_dir():
						target.mkdir(parents=True, exist_ok=True)
						continue
					target.parent.mkdir(parents=True, exist_ok=True)
					with zip_file.open(member) as src, target.open("wb") as dst:
						shutil.copyfileobj(src, dst)

				file_count = sum(1 for member, _ in mapped if not member.is_dir())
				return "extracted", f"{file_count} file(s)"
		if archive_type == "7z":
			if py7zr is None:
				return "error", "py7zr is not installed"
			names = _list_members(archive_path, archive_type)
			_ensure_safe_paths(dest_dir, names, archive_path)

			if not allow_overwrite:
				for name in names:
					target = dest_dir / name
					if target.exists():
						return "skipped", f"existing file: {target}"

			if dry_run:
				return "dry-run", f"{len(names)} member(s)"
			with py7zr.SevenZipFile(archive_path, mode="r") as seven_file:
				seven_file.extractall(path=dest_dir)
			return "extracted", f"{len(names)} member(s)"
		if archive_type == "rar":
			if rarfile is None:
				return "error", "rarfile is not installed"
			names = _list_members(archive_path, archive_type)
			_ensure_safe_paths(dest_dir, names, archive_path)

			if not allow_overwrite:
				for name in names:
					target = dest_dir / name
					if target.exists():
						return "skipped", f"existing file: {target}"

			if dry_run:
				return "dry-run", f"{len(names)} member(s)"
			with rarfile.RarFile(archive_path) as rar_file:
				rar_file.extractall(dest_dir)
			return "extracted", f"{len(names)} member(s)"
		return "error", f"Unsupported archive type: {archive_path}"
	except Exception as exc:  # pragma: no cover - runtime errors
		return "error", str(exc)


def _extract_nested_archives(
	root_dir: Path,
	extensions: set[str],
	allow_overwrite: bool,
	dry_run: bool,
	delete_archives: bool,
	report_rows: list[dict[str, str]],
) -> tuple[int, int, int, int]:
	extracted = 0
	skipped = 0
	errors = 0
	dry_runs = 0
	seen: set[Path] = set()

	while True:
		candidates = [
			p
			for p in root_dir.rglob("*")
			if p.is_file() and p.suffix.lower() in extensions and p not in seen
		]
		if not candidates:
			break

		for archive_path in candidates:
			seen.add(archive_path)
			archive_type = _get_archive_type(archive_path)
			dest_dir = archive_path.parent

			status, details = _extract_archive(
				archive_path,
				archive_type,
				dest_dir,
				allow_overwrite,
				dry_run,
			)

			if status == "extracted":
				extracted += 1
				if delete_archives and not dry_run:
					try:
						archive_path.unlink()
					except OSError:
						pass
			elif status == "skipped":
				skipped += 1
			elif status == "dry-run":
				dry_runs += 1
			else:
				errors += 1

			report_rows.append(
				{
					"timestamp": datetime.now().isoformat(timespec="seconds"),
					"archive_path": str(archive_path),
					"archive_type": archive_type,
					"destination": str(dest_dir),
					"status": f"nested-{status}",
					"details": details,
				}
			)

	return extracted, skipped, dry_runs, errors


def main(argv: list[str]) -> int:
	args = _parse_args(argv)
	input_paths = [Path(p).expanduser() for p in args.inputs]
	output_dir = Path(args.output).expanduser()
	output_dir.mkdir(parents=True, exist_ok=True)
	report_path = (
		Path(args.report_path).expanduser()
		if args.report_path
		else output_dir / "unzip_report.csv"
	)

	missing = [str(p) for p in input_paths if not p.exists()]
	if missing:
		print("These input paths do not exist:")
		for path in missing:
			print(f"  - {path}")
		return 2

	extensions = _normalize_extensions(args.extensions)
	archives = _find_archives(input_paths, extensions)
	copy_extensions = _normalize_copy_extensions(args.copy_extensions)
	files_to_copy = _find_files(input_paths, copy_extensions)
	if not archives and not files_to_copy:
		print("No archives or copyable files found in the provided inputs.")
		return 1

	extracted = 0
	skipped = 0
	errors = 0
	dry_runs = 0
	report_rows: list[dict[str, str]] = []

	for index, archive_path in enumerate(archives, start=1):
		print(f"Processing archive {index}/{len(archives)}: {archive_path}")
		archive_type = _get_archive_type(archive_path)
		dest_dir = output_dir if args.flat else _unique_dest_dir(
			output_dir, archive_path.stem
		)
		if not args.dry_run:
			dest_dir.mkdir(parents=True, exist_ok=True)

		status, details = _extract_archive(
			archive_path,
			archive_type,
			dest_dir,
			args.overwrite,
			args.dry_run,
		)

		if status == "extracted":
			extracted += 1
			if args.delete_archives and not args.dry_run:
				try:
					archive_path.unlink()
				except OSError:
					pass
		elif status == "skipped":
			skipped += 1
			if not args.flat and not args.dry_run and not any(dest_dir.iterdir()):
				dest_dir.rmdir()
		elif status == "dry-run":
			dry_runs += 1
		else:
			errors += 1

		report_rows.append(
			{
				"timestamp": datetime.now().isoformat(timespec="seconds"),
				"archive_path": str(archive_path),
				"archive_type": archive_type,
				"destination": str(dest_dir),
				"status": status,
				"details": details,
			}
		)

		if status == "extracted" and args.recursive and not args.dry_run:
			rec_extracted, rec_skipped, rec_dry, rec_errors = _extract_nested_archives(
				dest_dir,
				extensions,
				args.overwrite,
				args.dry_run,
				args.delete_archives,
				report_rows,
			)
			extracted += rec_extracted
			skipped += rec_skipped
			dry_runs += rec_dry
			errors += rec_errors

	for index, file_path in enumerate(files_to_copy, start=1):
		print(f"Processing file {index}/{len(files_to_copy)}: {file_path}")
		dest_dir = output_dir if args.flat else _unique_dest_dir(
			output_dir, file_path.stem
		)
		dest_path = dest_dir / file_path.name

		if not args.dry_run:
			dest_dir.mkdir(parents=True, exist_ok=True)

		if not args.overwrite and dest_path.exists():
			skipped += 1
			status = "skipped"
			details = f"existing file: {dest_path}"
		elif args.dry_run:
			dry_runs += 1
			status = "dry-run"
			details = "copy"
		else:
			shutil.copy2(file_path, dest_path)
			extracted += 1
			status = "copied"
			details = "copied"

		report_rows.append(
			{
				"timestamp": datetime.now().isoformat(timespec="seconds"),
				"archive_path": str(file_path),
				"archive_type": file_path.suffix.lower().lstrip("."),
				"destination": str(dest_path),
				"status": status,
				"details": details,
			}
		)

	print(
		"Found "
		f"{len(archives)} archive(s) and {len(files_to_copy)} copy file(s). "
		f"Extracted/copied {extracted}, skipped {skipped}, "
		f"dry-run {dry_runs}, errors {errors}."
	)

	report_path.parent.mkdir(parents=True, exist_ok=True)
	with report_path.open("w", newline="", encoding="utf-8") as report_file:
		writer = csv.DictWriter(
			report_file,
			fieldnames=[
				"timestamp",
				"archive_path",
				"archive_type",
				"destination",
				"status",
				"details",
			],
		)
		writer.writeheader()
		writer.writerows(report_rows)

	print(f"Report written to: {report_path}")
	return 0


def _pick_inputs(listbox: tk.Listbox) -> None:
	paths = filedialog.askopenfilenames(
		title="Select archive files",
		filetypes=[
			("Archive files", "*.zip *.7z *.rar"),
			("Copy files", "*.stl *.3mf"),
			("All files", "*.*"),
		],
	)
	for path in paths:
		if path and path not in listbox.get(0, tk.END):
			listbox.insert(tk.END, path)


def _pick_folder(listbox: tk.Listbox) -> None:
	path = filedialog.askdirectory(title="Select folder to scan")
	if path and path not in listbox.get(0, tk.END):
		listbox.insert(tk.END, path)


def _remove_selected(listbox: tk.Listbox) -> None:
	selected = listbox.curselection()
	for index in reversed(selected):
		listbox.delete(index)


def _run_from_gui(
	listbox: tk.Listbox,
	output_var: tk.StringVar,
	ext_var: tk.StringVar,
	copy_var: tk.StringVar,
	flat_var: tk.BooleanVar,
	overwrite_var: tk.BooleanVar,
	dry_run_var: tk.BooleanVar,
	recursive_var: tk.BooleanVar,
	delete_archives_var: tk.BooleanVar,
) -> None:
	inputs = list(listbox.get(0, tk.END))
	output = output_var.get().strip()
	if not inputs or not output:
		messagebox.showerror("Missing inputs", "Please select inputs and output.")
		return

	argv = inputs + ["-o", output]
	if flat_var.get():
		argv.append("--flat")
	if overwrite_var.get():
		argv.append("--overwrite")
	if dry_run_var.get():
		argv.append("--dry-run")
	if ext_var.get().strip():
		argv.extend(["--extensions", ext_var.get().strip()])
	if copy_var.get().strip():
		argv.extend(["--copy-extensions", copy_var.get().strip()])
	if recursive_var.get():
		argv.append("--recursive")
	else:
		argv.append("--no-recursive")
	if delete_archives_var.get():
		argv.append("--delete-archives")
	else:
		argv.append("--keep-archives")

	try:
		exit_code = main(argv)
		if exit_code == 0:
			messagebox.showinfo("Done", "Extraction finished successfully.")
		else:
			messagebox.showwarning(
				"Finished with warnings",
				"Completed with non-zero exit code. Check console output.",
			)
	except Exception as exc:  # pragma: no cover - GUI runtime errors
		messagebox.showerror("Error", str(exc))


def launch_gui() -> None:
	root = tk.Tk()
	root.title("Mass Unzip")
	root.geometry("720x520")

	inputs_frame = tk.LabelFrame(root, text="Inputs")
	inputs_frame.pack(fill="both", padx=12, pady=10, expand=True)

	listbox = tk.Listbox(inputs_frame, height=10, selectmode=tk.EXTENDED)
	listbox.pack(fill="both", padx=10, pady=10, expand=True)

	buttons_frame = tk.Frame(inputs_frame)
	buttons_frame.pack(fill="x", padx=10, pady=(0, 10))

	tk.Button(buttons_frame, text="Add Files", command=lambda: _pick_inputs(listbox)).pack(
		side="left", padx=(0, 8)
	)
	tk.Button(buttons_frame, text="Add Folder", command=lambda: _pick_folder(listbox)).pack(
		side="left", padx=(0, 8)
	)
	tk.Button(buttons_frame, text="Remove Selected", command=lambda: _remove_selected(listbox)).pack(
		side="left"
	)

	output_frame = tk.LabelFrame(root, text="Output")
	output_frame.pack(fill="x", padx=12, pady=10)

	output_var = tk.StringVar()
	output_entry = tk.Entry(output_frame, textvariable=output_var)
	output_entry.pack(side="left", fill="x", padx=10, pady=10, expand=True)

	def _pick_output() -> None:
		path = filedialog.askdirectory(title="Select output folder")
		if path:
			output_var.set(path)

	tk.Button(output_frame, text="Browse", command=_pick_output).pack(
		side="left", padx=(0, 10), pady=10
	)

	options_frame = tk.LabelFrame(root, text="Options")
	options_frame.pack(fill="x", padx=12, pady=10)

	flat_var = tk.BooleanVar()
	overwrite_var = tk.BooleanVar()
	dry_run_var = tk.BooleanVar()
	recursive_var = tk.BooleanVar(value=True)
	delete_archives_var = tk.BooleanVar(value=True)
	options_row = tk.Frame(options_frame)
	options_row.pack(fill="x", padx=10, pady=8)

	tk.Checkbutton(options_row, text="Flat output", variable=flat_var).pack(
		side="left", padx=(0, 12)
	)
	tk.Checkbutton(options_row, text="Overwrite", variable=overwrite_var).pack(
		side="left", padx=(0, 12)
	)
	tk.Checkbutton(options_row, text="Dry run", variable=dry_run_var).pack(
		side="left"
	)
	tk.Checkbutton(options_row, text="Recursive", variable=recursive_var).pack(
		side="left", padx=(12, 0)
	)
	tk.Checkbutton(options_row, text="Delete archives", variable=delete_archives_var).pack(
		side="left", padx=(12, 0)
	)

	ext_row = tk.Frame(options_frame)
	ext_row.pack(fill="x", padx=10, pady=(0, 10))
	tk.Label(ext_row, text="Extensions (comma-separated)").pack(
		side="left", padx=(0, 10)
	)
	ext_var = tk.StringVar(value="zip,7z,rar")
	tk.Entry(ext_row, textvariable=ext_var, width=30).pack(side="left")

	copy_row = tk.Frame(options_frame)
	copy_row.pack(fill="x", padx=10, pady=(0, 10))
	tk.Label(copy_row, text="Copy extensions (comma-separated)").pack(
		side="left", padx=(0, 10)
	)
	copy_var = tk.StringVar(value="stl,3mf")
	tk.Entry(copy_row, textvariable=copy_var, width=30).pack(side="left")

	run_frame = tk.Frame(root)
	run_frame.pack(fill="x", padx=12, pady=10)
	tk.Button(
		run_frame,
		text="Run",
		command=lambda: _run_from_gui(
			listbox,
			output_var,
			ext_var,
			copy_var,
			flat_var,
			overwrite_var,
			dry_run_var,
			recursive_var,
			delete_archives_var,
		),
	).pack(side="right")

	root.mainloop()


if __name__ == "__main__":
	if len(sys.argv) == 1:
		launch_gui()
	else:
		raise SystemExit(main(sys.argv[1:]))
