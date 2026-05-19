import tkinter as tk
from tkinter import filedialog, messagebox
import fitz  # PyMuPDF
import os

def extract_images_from_pdf():
    # 1. Ask the user to select a PDF file
    pdf_path = filedialog.askopenfilename(
        title="Select a PDF File",
        filetypes=[("PDF Files", "*.pdf")]
    )
    
    if not pdf_path:
        return  # User canceled the selection

    # 2. Ask the user to select a destination folder for the images
    output_dir = filedialog.askdirectory(
        title="Select Destination Folder for Images"
    )
    
    if not output_dir:
        return  # User canceled the selection

    try:
        # 3. Open the PDF and extract images
        pdf_document = fitz.open(pdf_path)
        image_count = 0

        for page_index in range(len(pdf_document)):
            page = pdf_document[page_index]
            image_list = page.get_images(full=True)

            for image_index, img in enumerate(image_list, start=1):
                xref = img[0]
                base_image = pdf_document.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                # Create a clear filename: e.g., page1_img1.png
                image_name = f"page{page_index + 1}_img{image_index}.{image_ext}"
                image_filepath = os.path.join(output_dir, image_name)
                
                # Save the image to the selected folder
                with open(image_filepath, "wb") as image_file:
                    image_file.write(image_bytes)
                    
                image_count += 1

        pdf_document.close()
        
        # 4. Show success message
        if image_count > 0:
            messagebox.showinfo("Success", f"Successfully extracted {image_count} images to:\n{output_dir}")
        else:
            messagebox.showinfo("Result", "No images were found in the selected PDF.")

    except Exception as e:
        messagebox.showerror("Error", f"An error occurred while processing the PDF:\n{str(e)}")

# --- GUI Setup ---
root = tk.Tk()
root.title("PDF Image Extractor")
root.geometry("350x150")
root.eval('tk::PlaceWindow . center') # Center the window

instruction_label = tk.Label(root, text="Click below to select a PDF and extract its images.", pady=15)
instruction_label.pack()

extract_button = tk.Button(root, text="Select PDF & Extract Images", command=extract_images_from_pdf, padx=10, pady=5)
extract_button.pack()

# Run the application
root.mainloop()