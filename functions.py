# functions.py

import os
import subprocess
import threading
from tkinter import filedialog
import functions
from datetime import datetime
import tkinter as tk

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

def process_video(log_file_path):
    try:
        process_video_safe(log_file_path)
    except Exception as e:
        update_terminal_output(f"Error occurred: {str(e)}", log_file_path)

import subprocess

def process_video_safe(log_file_path):
    global video_path, save_folder

    if not video_path or not save_folder:
        update_terminal_output("Error: Please select a video and save location first.", log_file_path)
        return

    btn_process.configure(bg="blue")
    output_path = os.path.join(save_folder, "output_video.mp4")
    temp_audio = os.path.join(save_folder, "temp_audio.wav")
    silence_log = os.path.join(save_folder, "silence_log.txt")
    segment_list = os.path.join(save_folder, "segments.txt")

    # Ensure the log file exists and open it in append mode
    with open(log_file_path, 'a') as log_file:
        log_file.write("Starting processing...\n")
        update_terminal_output("Starting processing...", log_file_path)

        fps, bitrate, total_frames = get_video_properties(video_path)
        log_file.write(f"Video FPS: {fps}, Bitrate: {bitrate}, Total Frames: {total_frames}\n")
        update_terminal_output(f"Video FPS: {fps}, Bitrate: {bitrate}, Total Frames: {total_frames}", log_file_path)

        log_file.write("Extracting audio...\n")
        update_terminal_output("Extracting audio...", log_file_path)
        subprocess.run(["ffmpeg", "-i", video_path, "-q:a", "0", "-map", "a", temp_audio, "-y"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        log_file.write("Detecting silence...\n")
        update_terminal_output("Detecting silence...", log_file_path)
        subprocess.run(["ffmpeg", "-i", temp_audio, "-af", "silencedetect=noise=-45dB:d=1.0",  # Adjusted dB and duration
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

        log_file.write(f"Detected {len(silent_ranges)} silent segments.\n")
        update_terminal_output(f"Detected {len(silent_ranges)} silent segments.", log_file_path)

        speaking_segments = []
        last_end = 0
        duration = get_video_duration(video_path)
        buffer_time = 1.75  # Increased buffer time to include more of the speech

        for start, end in silent_ranges:
            adjusted_start = max(0, last_end)
            adjusted_end = min(start + buffer_time, duration)  # Increase buffer time for more speech inclusion
            if adjusted_start < adjusted_end:
                speaking_segments.append((adjusted_start, adjusted_end))
            last_end = end

        if last_end < duration:
            speaking_segments.append((last_end, duration))

        with open(segment_list, "w") as f:
            processed_frames = 0
            for i, (start, end) in enumerate(speaking_segments):
                segment_file = os.path.join(save_folder, f"segment_{i}.mp4")
                log_file.write(f"Creating segment {i + 1}/{len(speaking_segments)}...\n")
                update_terminal_output(f"Creating segment {i + 1}/{len(speaking_segments)}...", log_file_path)

                # Run ffmpeg command to create video segments and capture output
                process = subprocess.Popen(
                    ["ffmpeg", "-i", video_path, "-ss", str(start), "-to", str(end),
                     "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                     "-c:a", "aac", "-b:a", "128k", segment_file, "-y"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )

                for line in process.stderr:
                    log_file.write(line)  # Write ffmpeg stderr (processing logs) to log file
                    update_terminal_output(line.strip(), log_file_path)  # Update terminal output

                segment_frames = (end - start) * fps
                processed_frames += segment_frames
                f.write(f"file '{segment_file.replace('\\', '/')}'\n")

        log_file.write("Merging segments...\n")
        update_terminal_output("Merging segments...", log_file_path)

        # Merging segments and capturing ffmpeg logs
        process = subprocess.Popen(
            ["ffmpeg", "-f", "concat", "-safe", "0", "-i", segment_list,
             "-c:v", "libx264", "-preset", "fast", "-crf", "18",
             "-c:a", "aac", "-b:a", "128k", output_path, "-y"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

        for line in process.stderr:
            log_file.write(line)  # Write ffmpeg stderr (processing logs) to log file
            update_terminal_output(line.strip(), log_file_path)  # Update terminal output

        process.wait()
        log_file.write(f"Processing complete. Output saved as {output_path}\n")
        update_terminal_output(f"Processing complete. Output saved as {output_path}", log_file_path)

        btn_process.configure(bg="green")
        os.startfile(save_folder)

        # Clean up
        os.remove(temp_audio)
        os.remove(segment_list)
        for i in range(len(speaking_segments)):
            os.remove(os.path.join(save_folder, f"segment_{i}.mp4"))


def create_log_file(video_path):
    """
    Create a log file with the same name as the video file in the same directory.
    If a log file already exists, it appends new logs.
    """
    # Get the directory and video file name
    video_dir = os.path.dirname(video_path)
    video_filename = os.path.splitext(os.path.basename(video_path))[0]  # Get filename without extension
    log_filename = f"{video_filename}_log_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"  # Adding a timestamp to avoid overwriting

    log_file_path = os.path.join(video_dir, log_filename)

    return log_file_path

def write_to_log(log_file_path, text):
    """
    Write the provided text to the log file.
    """
    with open(log_file_path, "a") as log_file:  # Append to file
        log_file.write(text + "\n")

def update_terminal_output(text, log_file_path=None):
    """
    Update the terminal output widget and log the text to a file if provided.
    """
    # Update the Text widget (terminal box)
    functions.terminal_box.config(state=tk.NORMAL)
    functions.terminal_box.insert(tk.END, text + "\n")
    functions.terminal_box.config(state=tk.DISABLED)
    
    # Write to log file if a log path is provided
    if log_file_path:
        write_to_log(log_file_path, text)

def start_processing():
    if video_path and save_folder:
        # Create the log file
        log_file_path = create_log_file(video_path)
        
        # Log initial information
        update_terminal_output(f"Video path: {video_path}", log_file_path)
        update_terminal_output(f"Save folder: {save_folder}", log_file_path)
        update_terminal_output("Start processing button clicked.", log_file_path)  # Add this
        
        # Update the button appearance
        btn_process.configure(bg="blue")
        
        # Start processing in a separate thread
        threading.Thread(target=process_video, args=(log_file_path,)).start()
    else:
        # Log an error if the video or save folder is missing
        update_terminal_output("Missing video or save folder.", log_file_path)

