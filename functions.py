# functions.py

import os
import subprocess
import threading
from tkinter import filedialog

# Shared state
video_path = ""
save_folder = ""
terminal_box = None
btn_upload = None
btn_save_to = None
btn_process = None
lbl_video_path = None
lbl_save_path = None



def upload_file(canvas, text_id):
    global video_path
    file_path = filedialog.askopenfilename(filetypes=[("Video files", "*.mp4 *.mov *.avi")])
    if file_path:
        video_path = file_path
        canvas.itemconfig(text_id, text=file_path.split("/")[-1])  # Display filename only



def save_to(canvas, text_id):
    global save_path  # <--- This should be:
    global save_folder
    folder_path = filedialog.askdirectory()
    if folder_path:
        save_folder = folder_path
        canvas.itemconfig(text_id, text=folder_path.split("/")[-1])


def update_terminal(text):
    if terminal_box:
        terminal_box.configure(state="normal")
        terminal_box.insert("end", text + "\n")
        terminal_box.see("end")
        terminal_box.configure(state="disabled")


def get_video_duration(video_path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    return float(result.stdout.strip())


def get_video_properties(video_path):
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
    try:
        process_video_safe()
    except Exception as e:
        update_terminal(f"Error occurred: {str(e)}")


def process_video_safe():
    global video_path, save_folder

    if not video_path or not save_folder:
        update_terminal("Error: Please select a video and save location first.")
        return

    btn_process.configure(bg="blue")
    output_path = os.path.join(save_folder, "output_video.mp4")
    temp_audio = os.path.join(save_folder, "temp_audio.wav")
    silence_log = os.path.join(save_folder, "silence_log.txt")
    segment_list = os.path.join(save_folder, "segments.txt")

    update_terminal("Starting processing...")
    fps, bitrate, total_frames = get_video_properties(video_path)
    update_terminal(f"Video FPS: {fps}, Bitrate: {bitrate}, Total Frames: {total_frames}")

    update_terminal("Extracting audio...")
    subprocess.run(["ffmpeg", "-i", video_path, "-q:a", "0", "-map", "a", temp_audio, "-y"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    update_terminal("Detecting silence...")
    subprocess.run(["ffmpeg", "-i", temp_audio, "-af", "silencedetect=noise=-30dB:d=0.7",
                    "-f", "null", "-"], stderr=open(silence_log, "w"))

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

            f.write(f"file '{segment_file.replace('\\', '/')}'\n")

    update_terminal("Merging segments...")
    process = subprocess.Popen(["ffmpeg", "-f", "concat", "-safe", "0", "-i", segment_list,
                                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                                "-c:a", "aac", "-b:a", "128k", output_path, "-y"],
                               stderr=subprocess.PIPE, text=True)

    for line in process.stderr:
        update_terminal(line.strip())
        if "frame=" in line:
            for part in line.strip().split():
                if part.startswith("frame="):
                    try:
                        current_frame = int(part.split("=")[1])
                    except ValueError:
                        pass

    process.wait()
    update_terminal(f"Processing complete. Output saved as {output_path}")
    btn_process.configure(bg="green")
    os.startfile(save_folder)

    os.remove(temp_audio)
    os.remove(silence_log)
    os.remove(segment_list)
    for i in range(len(speaking_segments)):
        os.remove(os.path.join(save_folder, f"segment_{i}.mp4"))


def start_processing():
    if video_path and save_folder:
        update_terminal(f"Video path: {video_path}")
        update_terminal(f"Save folder: {save_folder}")
        update_terminal("Start processing button clicked.")  # Add this
        btn_process.configure(bg="blue")
        threading.Thread(target=process_video).start()
    else:
        update_terminal("Missing video or save folder.")  # Also useful
