# ==========================================================
# Geog 777 - Project 1 Interactive GUI
# Author: Sonja Sebree — connects to aa2 backend
# ==========================================================

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, DISABLED, NORMAL
from PIL import Image, ImageTk
import subprocess, traceback, os
import aa2  # ArcPy backend

IMAGE_FOLDER = aa2.RESULTS_FOLDER
current_display = None
current_img = None

# ----------------------------------------------------------
# FUNCTIONS
# ----------------------------------------------------------
def run_analysis(k_str):
    StartButton.configure(text="Processing...", state=DISABLED)
    StartButton.update_idletasks()
    global moranReport, olsReport

    try:
        k = float(k_str)
        if k <= 1:
            raise ValueError("k must be > 1")
    except Exception as e:
        messagebox.showerror("Invalid Input", f"Enter a number > 1.\n{e}")
        StartButton.configure(text="Submit k-value", state=NORMAL)
        return

    try:
        # Project all source data to GDB before analysis
        wells, tracts, counties = aa2.prepare_inputs()

        lblIDW.configure(text="Step 1: Running IDW...")
        idw_out = aa2.idw(wells, counties, k)
        lblIDW.configure(text="Step 1: IDW done.")

        lblOLS.configure(text="Step 2: Zonal & OLS...")
        zonal_out = aa2.zonalStats(tracts, idw_out, k)
        ols_out = aa2.ols(zonal_out, k)
        lblOLS.configure(text="Step 2: OLS done.")

        lblMoran.configure(text="Step 3: Moran’s I...")
        moranReport = aa2.morans(ols_out, k)
        lblMoran.configure(text="Step 3: Moran done.")

        idwVwButton.configure(state=NORMAL)
        olsVwButton.configure(state=NORMAL)
        olsReportButton.configure(state=NORMAL)
        idwSvButton.configure(state=NORMAL)
        olsSvButton.configure(state=NORMAL)
        moranVwButton.configure(state=NORMAL)

        StartButton.configure(text="Done!", state=NORMAL)
    except Exception as e:
        tb = traceback.format_exc()
        print(tb)
        messagebox.showerror("Error", f"{e}")
        StartButton.configure(text="Submit k-value", state=NORMAL)

def display_image(path):
    global current_img
    if not os.path.exists(path):
        messagebox.showwarning("Missing Image", f"{path} not found.")
        return
    img = Image.open(path)
    img = img.resize((650, 750))
    current_img = ImageTk.PhotoImage(img)
    mapLabel.configure(image=current_img)
    mapLabel.image = current_img

def show_image(name, k):
    display_image(fr"{IMAGE_FOLDER}\{name}_{k}.png")

def save_image(name, k):
    filetypes = [("PNG", "*.png")]
    save_path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=filetypes)
    if save_path:
        src = fr"{IMAGE_FOLDER}\{name}_{k}.png"
        Image.open(src).save(save_path)

def open_report(path):
    if path: subprocess.Popen(path, shell=True)

def reset_view():
    display_image(fr"{IMAGE_FOLDER}\wells.png")
    for b in [idwVwButton, olsVwButton, olsSvButton, idwSvButton, olsReportButton, moranVwButton]:
        b.configure(state=DISABLED)
    lblIDW.configure(text="Step 1: IDW not started")
    lblOLS.configure(text="Step 2: OLS not started")
    lblMoran.configure(text="Step 3: Moran’s I not started")
    kEntry.delete(0, tk.END)
    StartButton.configure(text="Submit k-value", state=NORMAL)

# ----------------------------------------------------------
# WINDOW
# ----------------------------------------------------------
root = tk.Tk()
root.title("Geog 777 — Nitrate & Cancer Risk Explorer")
root.geometry("1400x950")
root.configure(bg="#f7f8fa")

style = ttk.Style()
style.theme_use("clam")
style.configure("TButton", font=("Segoe UI Semibold", 10), padding=6)
style.configure("TLabel", background="#f7f8fa", font=("Segoe UI", 10))

# LEFT COLUMN ------------------------------------------------
leftFrame = tk.Frame(root, bg="#f7f8fa")
leftFrame.grid(row=0, column=0, sticky="nsew", padx=(40,10), pady=30)

intro = (
    "Recently, a possible cancer risk has been identified in Wisconsin due to nitrate contamination in well water. "
    "However, the relationship between nitrate concentrations and cancer rates is not yet well understood. "
    "The Wisconsin Department of Natural Resources (WDNR) has gathered data on cancer occurrences across the state over a ten-year period, "
    "along with nitrate level measurements from a network of test wells. This combined dataset offers a valuable opportunity to explore how groundwater quality may relate to public health outcomes.\n\n"
    
    "This application allows you to explore that relationship interactively using inverse distance weighting (IDW) interpolation and spatial regression techniques. "
    "Because there is no established theory to determine the most appropriate value for the distance exponent *k*, you can adjust *k* yourself and observe how it affects the resulting maps and diagnostics. "
    "Enter a value for *k* greater than 1 to run interpolation, regression, and spatial autocorrelation analyses, and to visualize the results."
)

tk.Label(leftFrame, text=intro, wraplength=500, justify="left",
         font=("Segoe UI",11), bg="#f7f8fa", fg="#333").pack(anchor="w", pady=(0,20))

tk.Label(leftFrame, text="Enter k value (> 1):",
         font=("Segoe UI",10,"bold"), bg="#f7f8fa").pack(anchor="w", pady=(0,5))
kEntry = ttk.Entry(leftFrame, width=10); kEntry.pack(anchor="w", pady=(0,10))

btnRow = tk.Frame(leftFrame, bg="#f7f8fa"); btnRow.pack(anchor="w", pady=(0,20))
StartButton = ttk.Button(btnRow, text="Submit k-value", command=lambda: run_analysis(kEntry.get()))
StartButton.pack(side="left", padx=(0,8))
resetButton = ttk.Button(btnRow, text="Reset View", command=reset_view)
resetButton.pack(side="left")

feedbk = ttk.LabelFrame(leftFrame, text="Processing Status")
feedbk.pack(anchor="w", fill="x", pady=(10,10))
lblIDW   = tk.Label(feedbk, text="Step 1: IDW not started", bg="#fff", anchor="w"); lblIDW.pack(anchor="w", padx=10)
lblOLS   = tk.Label(feedbk, text="Step 2: OLS not started", bg="#fff", anchor="w"); lblOLS.pack(anchor="w", padx=10)
lblMoran = tk.Label(feedbk, text="Step 3: Moran’s I not started", bg="#fff", anchor="w"); lblMoran.pack(anchor="w", padx=10)

# RIGHT COLUMN ------------------------------------------------
rightFrame = tk.Frame(root, bg="#f7f8fa")
rightFrame.grid(row=0, column=1, sticky="nsew", padx=(10,40), pady=30)

mapLabel = tk.Label(rightFrame, bg="#eaeaea", relief="groove")
mapLabel.pack(expand=True, fill="both", padx=10, pady=10)
display_image(fr"{IMAGE_FOLDER}\wells.jpg")

# Buttons under map
btnContainer = tk.Frame(rightFrame, bg="#f7f8fa"); btnContainer.pack(pady=(5,10))

viewRow = tk.Frame(btnContainer, bg="#f7f8fa"); viewRow.pack(pady=5)
wellsButton = ttk.Button(viewRow, text="View Wells", command=lambda: display_image(fr"{IMAGE_FOLDER}\wells.jpg"))
wellsButton.grid(row=0, column=0, padx=8)
idwVwButton = ttk.Button(viewRow, text="View IDW Map", command=lambda: show_image("IDW", kEntry.get()), state=DISABLED)
idwVwButton.grid(row=0, column=1, padx=8)
olsVwButton = ttk.Button(viewRow, text="View OLS Map", command=lambda: show_image("OLS", kEntry.get()), state=DISABLED)
olsVwButton.grid(row=0, column=2, padx=8)
moranVwButton = ttk.Button(viewRow, text="View Moran’s I Report", command=lambda: open_report(moranReport), state=DISABLED)
moranVwButton.grid(row=0, column=3, padx=8)

saveRow = tk.Frame(btnContainer, bg="#f7f8fa"); saveRow.pack(pady=5)
idwSvButton = ttk.Button(saveRow, text="Save IDW Map to PNG",
                         command=lambda: save_image("IDW", kEntry.get()), state=DISABLED)
idwSvButton.grid(row=0, column=0, padx=8)
olsSvButton = ttk.Button(saveRow, text="Save OLS Map to PNG",
                         command=lambda: save_image("OLS", kEntry.get()), state=DISABLED)
olsSvButton.grid(row=0, column=1, padx=8)
olsReportButton = ttk.Button(saveRow, text="Open OLS Report",
                             command=lambda: open_report(fr"{IMAGE_FOLDER}\olsReport_{kEntry.get()}.pdf"), state=DISABLED)
olsReportButton.grid(row=0, column=2, padx=8)

root.grid_columnconfigure(0, weight=1, minsize=500)
root.grid_columnconfigure(1, weight=2, minsize=700)
root.grid_rowconfigure(0, weight=1)
root.mainloop()
