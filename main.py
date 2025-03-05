import customtkinter as ctk
from tkinter import filedialog
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

    output_path = os.path.join(save_folder, "output_video.mp4")
    temp_audio = os.path.join(save_folder, "temp_audio.wav")
    silence_log = os.path.join(save_folder, "silence_log.txt")
    segment_list = os.path.join(save_folder, "segments.txt")

    update_terminal("Starting processing...")

    # Get FPS and Bitrate
    fps, bitrate = get_video_properties(video_path)
    update_terminal(f"Video FPS: {fps}, Bitrate: {bitrate}")

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
    
    buffer_time = 1.5  # Add 2 seconds between cuts

    for start, end in silent_ranges:
        adjusted_start = max(0, last_end)  
        adjusted_end = min(start + buffer_time, duration)  # Extend the speaking segment by 2 sec

        if adjusted_start < adjusted_end:  # Ensure valid segment
            speaking_segments.append((adjusted_start, adjusted_end))
            print(f"Speaking segment: {adjusted_start} to {adjusted_end}")  # Debugging output

        last_end = end  # Move the reference point to the end of the silence
    
    if last_end < duration:
        speaking_segments.append((last_end, duration))

    # Create video segments
    with open(segment_list, "w") as f:
        for i, (start, end) in enumerate(speaking_segments):
            segment_file = os.path.join(save_folder, f"segment_{i}.mp4")
            update_terminal(f"Creating segment: {segment_file} from {start}s to {end}s")
            subprocess.run(["ffmpeg", "-i", video_path, "-ss", str(start), "-to", str(end),
                            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                            "-c:a", "aac", "-b:a", "128k", segment_file, "-y"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            f.write(f"file '{segment_file.replace('\\', '/')}'\n") 

    # Merge video
    update_terminal("Merging segments...")
    merge_result = subprocess.run(["ffmpeg", "-f", "concat", "-safe", "0", "-i", segment_list,
                                   "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                                   "-c:a", "aac", "-b:a", "128k", output_path, "-y"],
                                  stderr=subprocess.PIPE, text=True)

    if "Invalid data found" in merge_result.stderr:
        update_terminal("Error: FFmpeg failed to merge segments.")
        return

    # Cleanup
    os.remove(temp_audio)
    os.remove(silence_log)
    os.remove(segment_list)
    for i in range(len(speaking_segments)):
        os.remove(os.path.join(save_folder, f"segment_{i}.mp4"))

    update_terminal(f"Processing complete. Output saved as {output_path}")

def start_processing():
    if video_path and save_folder:
        btn_process.configure(fg_color="blue")
        progress_bar.set(0.0)
        threading.Thread(target=process_video).start()

# GUI Setup
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

root = ctk.CTk()
root.title("Video Silence Cutter")
root.geometry("1000x650")

# UI Components
frame = ctk.CTkFrame(root)
frame.pack(pady=20, padx=20, fill="both", expand=True)

btn_upload = ctk.CTkButton(frame, text="Upload Video", command=upload_file)
btn_upload.grid(row=0, column=0, padx=10, pady=10)
lbl_video_path = ctk.CTkLabel(frame, text="No file selected", anchor="w", width=300)
lbl_video_path.grid(row=0, column=1, padx=10)

btn_save_to = ctk.CTkButton(frame, text="Save To", command=save_to)
btn_save_to.grid(row=1, column=0, padx=10, pady=10)
lbl_save_path = ctk.CTkLabel(frame, text="No folder selected", anchor="w", width=300)
lbl_save_path.grid(row=1, column=1, padx=10)

btn_process = ctk.CTkButton(frame, text="Start Processing", command=start_processing)
btn_process.grid(row=2, column=0, columnspan=2, pady=10)

terminal_box = ctk.CTkTextbox(frame, height=200, width=600, state="disabled")
terminal_box.grid(row=3, column=0, columnspan=2, pady=10)

progress_bar = ctk.CTkProgressBar(frame, width=600)
progress_bar.grid(row=4, column=0, columnspan=2)

root.mainloop()
