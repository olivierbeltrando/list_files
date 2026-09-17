#!/usr/bin/env python3

import logging
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

import list_files


logging.basicConfig(
    format="%(asctime)-15s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ListFilesApp(ttk.Frame):

    def __init__(self, master: tk.Tk) -> None:
        super().__init__(master, padding=15)

        self.search_name = tk.StringVar()
        self.directory = tk.StringVar()
        self.status = tk.StringVar(value="Waiting")
        self.simple_search = tk.BooleanVar(value=True)
        self.result_location = tk.IntVar(value=1)

        self.create_widgets()

        self.pack(fill="both", expand=True)
        master.bind("<Return>", self.process)

    def create_widgets(self) -> None:
        self.columnconfigure(1, weight=1)

        # Search label
        ttk.Label(
            self,
            text="Search name:"
        ).grid(row=0, column=0, sticky="w", padx=(0, 10), pady=5)

        search_entry = ttk.Entry(
            self,
            textvariable=self.search_name
        )
        search_entry.grid(
            row=0,
            column=1,
            columnspan=2,
            sticky="ew",
            pady=5,
        )
        search_entry.focus()

        # Source directory
        ttk.Label(
            self,
            text="Directory:"
        ).grid(row=1, column=0, sticky="w", padx=(0, 10), pady=5)

        ttk.Entry(
            self,
            textvariable=self.directory,
            state="readonly",
        ).grid(row=1, column=1, sticky="ew", pady=5)

        ttk.Button(
            self,
            text="Browse…",
            command=self.select_directory,
        ).grid(row=1, column=2, padx=(10, 0), pady=5)

        # Search options
        options = ttk.LabelFrame(
            self,
            text="Search options",
            padding=10,
        )
        options.grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(10, 5),
        )

        ttk.Checkbutton(
            options,
            text="Only search the selected folder (not subfolders)",
            variable=self.simple_search,
        ).pack(anchor="w")

        # Output location
        output = ttk.LabelFrame(
            self,
            text="Output location",
            padding=10,
        )
        output.grid(
            row=3,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=5,
        )

        ttk.Radiobutton(
            output,
            text="Store result.csv in my home directory",
            variable=self.result_location,
            value=1,
        ).pack(anchor="w")

        ttk.Radiobutton(
            output,
            text="Store result.csv in the selected directory",
            variable=self.result_location,
            value=2,
        ).pack(anchor="w")

        # Run button
        self.run_button = ttk.Button(
            self,
            text="Generate file list",
            command=self.process,
        )
        self.run_button.grid(
            row=4,
            column=0,
            columnspan=3,
            pady=(15, 5),
        )

        # Status
        ttk.Label(
            self,
            textvariable=self.status,
        ).grid(
            row=5,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(5, 0),
        )

    def select_directory(self) -> None:
        selected_directory = filedialog.askdirectory(
            parent=self.master,
            title="Select a directory to analyse",
        )

        # Keep the previous value if the dialog is cancelled.
        if selected_directory:
            self.directory.set(selected_directory)
            self.status.set("Ready")

    def get_output_path(self, source_directory: Path) -> Path:
        if self.result_location.get() == 1:
            output_directory = Path.home()
        else:
            output_directory = source_directory

        return output_directory / "result.csv"

    def process(self, event: tk.Event | None = None) -> None:
        source_directory = Path(self.directory.get())

        if not self.directory.get():
            self.status.set("Please select a directory")
            return

        if not source_directory.is_dir():
            self.status.set("The selected directory does not exist")
            return

        output_file = self.get_output_path(source_directory)

        self.run_button.configure(state="disabled")
        self.status.set("Searching…")
        self.master.configure(cursor="watch")
        self.master.update_idletasks()

        started_at = time.perf_counter()

        try:
            files = list_files.find_files(
                str(source_directory),
                self.search_name.get(),
                _simpleSearch=self.simple_search.get(),
            )

            # Keeping the existing function name from list_files.py.
            list_files.write_cvs(files, output_file)

            elapsed_ms = round(
                (time.perf_counter() - started_at) * 1000
            )

            self.status.set(
                f"{len(files)} files written to {output_file} "
                f"in {elapsed_ms} ms"
            )

        except Exception as error:
            logger.exception("An error occurred while generating the file list")
            self.status.set(f"Error: {error}")

        finally:
            self.run_button.configure(state="normal")
            self.master.configure(cursor="")


def main() -> None:
    root = tk.Tk()
    root.title("Generate file list")
    root.minsize(width=550, height=330)

    ListFilesApp(root)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt detected. Clean exit")


if __name__ == "__main__":
    main()
