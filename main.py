import customtkinter as ctk
from tkinter import filedialog
import tkinter as tk
import os
import threading
import subprocess

# Global variables for paths
video_path = ""
save_folder = ""

def upload_file():
    global video_path
    video_path = filedialog.askopenfilename(filetypes=[("Video files", "*.mp4;*.avi;*.mov")])
    if video_path:
        btn_upload.configure(fg_color="green")
        lbl_video_path.configure(text=os.path.basename(video_path))  # Show file name

def save_to():
    global save_folder
    save_folder = filedialog.askdirectory()
    if save_folder:
        btn_save_to.configure(fg_color="green")
        lbl_save_path.configure(text=save_folder)  # Show folder path

def update_terminal(text):
    terminal_box.configure(state="normal")
    terminal_box.insert("end", text + "\n")
    terminal_box.see("end")  # Auto-scroll
    terminal_box.configure(state="disabled")

def get_video_duration(video_path):
    """Get video duration using ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    return float(result.stdout.strip())

def get_video_properties(video_path):
    """Extract FPS, bitrate, and total frames from video."""
    fps_result = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate",
        "-of", "default=noprint_wrappers=1:nokey=1", video_path
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    bitrate_result = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "format=bit_rate",
        "-of", "default=noprint_wrappers=1:nokey=1", video_path
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    frames_result = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-count_frames", "-show_entries", "stream=nb_read_frames",
        "-of", "default=noprint_wrappers=1:nokey=1", video_path
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    fps = eval(fps_result.stdout.strip())  
    bitrate = bitrate_result.stdout.strip()
    total_frames = int(frames_result.stdout.strip()) if frames_result.stdout.strip().isdigit() else None

    return fps, bitrate, total_frames


def process_video():
    """Process video and save it to selected folder."""
    if not video_path or not save_folder:
        update_terminal("Error: Please select a video and save location first.")
        return

    # Change the button color to indicate processing started
    btn_process.configure(fg_color="blue")

    output_path = os.path.join(save_folder, "output_video.mp4")
    temp_audio = os.path.join(save_folder, "temp_audio.wav")
    silence_log = os.path.join(save_folder, "silence_log.txt")
    segment_list = os.path.join(save_folder, "segments.txt")

    update_terminal("Starting processing...")

    # Get FPS, Bitrate, and Total Frames
    fps, bitrate, total_frames = get_video_properties(video_path)
    update_terminal(f"Video FPS: {fps}, Bitrate: {bitrate}, Total Frames: {total_frames}")

    # Extract audio
    update_terminal("Extracting audio...")
    subprocess.run(["ffmpeg", "-i", video_path, "-q:a", "0", "-map", "a", temp_audio, "-y"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Detect silence
    update_terminal("Detecting silence...")
    subprocess.run(["ffmpeg", "-i", temp_audio, "-af", "silencedetect=noise=-30dB:d=0.7",
                    "-f", "null", "-"], stderr=open(silence_log, "w"))

    # Read silence log
    silent_ranges = []
    with open(silence_log, "r") as log:
        lines = log.readlines()
        start_time = 0
        for line in lines:
            if "silence_start" in line:
                start_time = float(line.split(": ")[-1].strip())
            elif "silence_end" in line:
                stop_time = float(line.split("|")[0].split(": ")[-1].strip())
                silent_ranges.append((start_time, stop_time))

    update_terminal(f"Detected {len(silent_ranges)} silent segments.")

    # Process segments
    speaking_segments = []
    last_end = 0
    duration = get_video_duration(video_path)

    buffer_time = 1.5
    for start, end in silent_ranges:
        adjusted_start = max(0, last_end)
        adjusted_end = min(start + buffer_time, duration)

        if adjusted_start < adjusted_end:
            speaking_segments.append((adjusted_start, adjusted_end))

        last_end = end

    if last_end < duration:
        speaking_segments.append((last_end, duration))

    # Create video segments with progress tracking
    with open(segment_list, "w") as f:
        processed_frames = 0
        for i, (start, end) in enumerate(speaking_segments):
            segment_file = os.path.join(save_folder, f"segment_{i}.mp4")
            update_terminal(f"Creating segment {i + 1}/{len(speaking_segments)}...")

            subprocess.run(["ffmpeg", "-i", video_path, "-ss", str(start), "-to", str(end),
                            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                            "-c:a", "aac", "-b:a", "128k", segment_file, "-y"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            segment_frames = (end - start) * fps
            processed_frames += segment_frames
            if total_frames:
                progress_bar.set(processed_frames / total_frames)

            f.write(f"file '{segment_file.replace('\\', '/')}'\n")

    # Merge video with progress tracking
    update_terminal("Merging segments...")
    process = subprocess.Popen(["ffmpeg", "-f", "concat", "-safe", "0", "-i", segment_list,
                                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                                "-c:a", "aac", "-b:a", "128k", output_path, "-y"],
                               stderr=subprocess.PIPE, text=True)

    for line in process.stderr:
        update_terminal(line.strip())
        if "frame=" in line:
            parts = line.strip().split()
            for part in parts:
                if part.startswith("frame="):
                    try:
                        current_frame = int(part.split("=")[1])
                        if total_frames:
                            progress_bar.set(current_frame / total_frames)
                    except ValueError:
                        pass  

    process.wait()

    # Ensure progress bar reaches 100%
    progress_bar.set(1.0)
    
    # Update UI to indicate completion
    update_terminal(f"Processing complete. Output saved as {output_path}")
    btn_process.configure(fg_color="green")  # Turn button green
    os.startfile(save_folder)  # Open the output folder

    # Cleanup
    os.remove(temp_audio)
    os.remove(silence_log)
    os.remove(segment_list)
    for i in range(len(speaking_segments)):
        os.remove(os.path.join(save_folder, f"segment_{i}.mp4"))



def start_processing():
    if video_path and save_folder:
        btn_process.configure(fg_color="blue")
        progress_bar.set(0.0)
        threading.Thread(target=process_video).start()
        

import customtkinter as ctk

ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("green")

root = ctk.CTk()
root.title("Automatic Video Silence Remover")
root.geometry("800x500")

# Set custom icon
try:
    root.iconbitmap("Logo.ico")  # For Windows
except tk.TclError:
    print("Icon file not found or unsupported format. Please ensure the file is in .ico format.")


# ============== Sidebar ==============
sidebar = ctk.CTkFrame(root, width=350, corner_radius=0)
sidebar.pack(fill="y", side="left")

def show_home():
    edit_frame.pack_forget()
    home_frame.pack(fill="both", expand=True)

def show_edit():
    home_frame.pack_forget()
    edit_frame.pack(fill="both", expand=True)

btn_home = ctk.CTkButton(sidebar, text="Home", command=show_home, width=100)
btn_home.pack(pady=10)

btn_edit = ctk.CTkButton(sidebar, text="Edit", command=show_edit, width=100)
btn_edit.pack(pady=10)

# ============== Content Area ==============
content_frame = ctk.CTkFrame(root)
content_frame.pack(fill="both", expand=True)

# ============== Home Tab ==============
home_frame = ctk.CTkFrame(content_frame)
home_frame.pack(fill="both", expand=True)

lbl_home_title = ctk.CTkLabel(home_frame, text="Welcome to Automatic Video Silence Remover", font=("Arial", 16, "bold"))
lbl_home_title.pack(pady=10)

lbl_home_info = ctk.CTkLabel(
    home_frame,
    text=(
        "This program allows you to automatically remove silent parts from videos.\n\n"
        "How it works:\n"
        "1. Upload a video file.\n"
        "2. Choose a save location.\n"
        "3. Click 'Start Processing' to remove silent parts.\n"
        "4. View progress in the terminal and progress bar."
    ),
    justify="left"
)
lbl_home_info.pack(pady=10, padx=10)

# ============== Edit Tab ==============
edit_frame = ctk.CTkFrame(content_frame)

btn_upload = ctk.CTkButton(edit_frame, text="Upload Video", width=150, height=50, text_color="White")
btn_upload.grid(row=0, column=0, padx=10, pady=10, sticky="w")

lbl_video_path = ctk.CTkLabel(edit_frame, text="No file selected", anchor="w", width=150)
lbl_video_path.grid(row=0, column=1, padx=10, pady=10, sticky="w")

btn_save_to = ctk.CTkButton(edit_frame, text="Save To", width=150, height=50, text_color="White")
btn_save_to.grid(row=1, column=0, padx=10, pady=10, sticky="w")

lbl_save_path = ctk.CTkLabel(edit_frame, text="No folder selected", anchor="w", width=150)
lbl_save_path.grid(row=1, column=1, padx=10, pady=10, sticky="w")

terminal_box = ctk.CTkTextbox(edit_frame, height=150, width=500, state="disabled")
terminal_box.grid(row=0, column=2, rowspan=2, padx=10, pady=10, sticky="nsew")

progress_bar = ctk.CTkProgressBar(edit_frame, width=400)
progress_bar.grid(row=2, column=2, padx=10, pady=10, sticky="ew")

btn_process = ctk.CTkButton(edit_frame, text="Start Processing", width=75, height=50, text_color="White")
btn_process.grid(row=3, column=0, columnspan=3, pady=10, sticky="")

edit_frame.grid_rowconfigure(0, weight=1)
edit_frame.grid_rowconfigure(1, weight=1)
edit_frame.grid_columnconfigure(2, weight=1)

root.mainloop()
