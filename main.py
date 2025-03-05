import customtkinter as ctk
from tkinter import filedialog
import os
import platform
import threading
import subprocess


import os
import platform
import subprocess

def process_video(video_path, save_folder):
    output_path = os.path.join(save_folder, "output_video.mp4")
    temp_audio_path = "temp_audio.wav"
    silence_log = "silence_log.txt"
    temp_list_path = "segments.txt"

    # Get original FPS and bitrate
    fps, bitrate = get_video_properties(video_path)

    # Extract audio
    subprocess.run([
        "ffmpeg", "-i", video_path, "-q:a", "0", "-map", "a", temp_audio_path, "-y"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Detect silence
    subprocess.run([
        "ffmpeg", "-i", temp_audio_path, "-af", "silencedetect=noise=-30dB:d=0.7",
        "-f", "null", "-"
    ], stderr=open(silence_log, "w"))

    with open(silence_log, "r") as log:
        lines = log.readlines()

    silent_ranges = []
    start_time = 0

    for line in lines:
        if "silence_start" in line:
            start_time = float(line.split(": ")[-1].strip())
        elif "silence_end" in line:
            stop_time = float(line.split("|")[0].split(": ")[-1].strip())
            silent_ranges.append((start_time, stop_time))

    print("Detected silent ranges:", silent_ranges)  # Debugging output

    duration = get_video_duration(video_path)
    print(f"Video duration: {duration} seconds")  # Debugging output

    speaking_segments = []
    last_end = 0  # Start from the beginning of the video

    for start, end in silent_ranges:
        if last_end < start:  # There's a speaking part before the silence
            speaking_segments.append((last_end, start))
            print(f"Speaking segment: {last_end} to {start}")  # Debugging output
        last_end = end  # Update last_end to the end of the silent segment

    # Capture the final speaking segment (if any)
    if last_end < duration:
        speaking_segments.append((last_end, duration))
        print(f"Final speaking segment: {last_end} to {duration}")  # Debugging output

    # Write segments to a file for ffmpeg concat
    with open(temp_list_path, "w") as f:
        for i, (start, end) in enumerate(speaking_segments):
            segment_file = os.path.abspath(f"segment_{i}.mp4")  # Use absolute path
            print(f"Creating segment: {segment_file} from {start}s to {end}s")  # Debugging output
            subprocess.run([
                "ffmpeg", "-i", video_path, "-ss", str(start), "-to", str(end),
                "-vf", f"fps={fps},format=yuv420p",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-b:v", bitrate,
                "-c:a", "aac", "-b:a", "128k",
                segment_file, "-y"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # Ensure correct formatting for FFmpeg concat
            f.write(f"file '{segment_file.replace('\\', '/')}\n")  # Unix-style paths

    # Validate segments before merging
    if not os.path.exists(temp_list_path) or os.stat(temp_list_path).st_size == 0:
        print("Error: segments.txt is empty. No valid segments were created.")
        return

    # Merge segments
    merge_result = subprocess.run([
        "ffmpeg", "-f", "concat", "-safe", "0", "-i", temp_list_path,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-b:v", bitrate,
        "-c:a", "aac", "-b:a", "128k",
        output_path, "-y"
    ], stderr=subprocess.PIPE, text=True)

    # Check for errors in FFmpeg merge
    if "Invalid data found" in merge_result.stderr:
        print("Error: FFmpeg failed to process segments.txt. Check segment files.")
        return

    # Cleanup
    os.remove(temp_audio_path)
    os.remove(silence_log)
    os.remove(temp_list_path)
    for i in range(len(speaking_segments)):
        os.remove(f"segment_{i}.mp4")

    print("Processing complete. Output saved as", output_path)

def get_video_duration(video_path):
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", video_path
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return float(result.stdout.strip())

def get_video_properties(video_path):
    """Extract FPS and bitrate from video."""
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

    # Convert FPS from fraction (e.g., 30000/1001) to float
    fps = eval(fps_result.stdout.strip())  
    bitrate = bitrate_result.stdout.strip()

    return fps, bitrate


def upload_file():
    global video_path
    video_path = filedialog.askopenfilename(filetypes=[("Video files", "*.mp4;*.avi;*.mov")])
    if video_path:
        btn_upload.configure(fg_color="green")

def save_to():
    global save_folder
    save_folder = filedialog.askdirectory()
    if save_folder:
        btn_save_to.configure(fg_color="green")

def start_processing():
    if video_path and save_folder:
        btn_process.configure(fg_color="blue")
        progress_bar.set(0.0)
        threading.Thread(target=process_video, args=(video_path, save_folder)).start()

# GUI Setup
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

root = ctk.CTk()
root.title("Video Silence Cutter")
root.geometry("500x200")

video_path = ""
save_folder = ""

frame = ctk.CTkFrame(root)
frame.pack(pady=20, padx=20, fill="both", expand=True)

btn_frame = ctk.CTkFrame(frame)
btn_frame.grid(row=0, column=0, padx=10, pady=10, sticky="n")

progress_frame = ctk.CTkFrame(frame)
progress_frame.grid(row=0, column=1, padx=10, pady=10, sticky="n")

btn_upload = ctk.CTkButton(btn_frame, text="Upload Video", command=upload_file)
btn_upload.pack(pady=10)

btn_save_to = ctk.CTkButton(btn_frame, text="Save To", command=save_to)
btn_save_to.pack(pady=10)

btn_process = ctk.CTkButton(btn_frame, text="Start Processing", command=start_processing)
btn_process.pack(pady=20)

progress_bar = ctk.CTkProgressBar(progress_frame)
progress_bar.pack(pady=10, fill="x")
progress_bar.set(0.0)

root.mainloop()
