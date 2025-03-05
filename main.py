import customtkinter as ctk
from tkinter import filedialog
from moviepy import VideoFileClip, concatenate_videoclips
from pydub import AudioSegment, silence
import os
import platform


def process_video(video_path, save_folder):
    output_path = os.path.join(save_folder, "output_video.mp4")
    
    # Load video and extract audio
    video = VideoFileClip(video_path)
    audio_path = "temp_audio.wav"
    video.audio.write_audiofile(audio_path, codec='pcm_s16le')
    
    # Load audio using pydub
    audio = AudioSegment.from_wav(audio_path)
    
    # Compute dynamic silence threshold
    average_loudness = audio.dBFS  # Get the average loudness
    silence_thresh = average_loudness - 10  # Set silence threshold 10 dB lower
    
    # Detect silence with the new threshold
    silent_ranges = silence.detect_silence(audio, min_silence_len=700, silence_thresh=silence_thresh)
    
    # Print for debugging
    print(f"Audio Loudness: {average_loudness} dBFS")
    print(f"Using Silence Threshold: {silence_thresh} dBFS")
    print("Detected Silent Parts:", silent_ranges)
    
    # Convert silent ranges to seconds
    silent_ranges = [(start / 1000, stop / 1000) for start, stop in silent_ranges]
    
    # Cut out silent parts
    final_clips = []
    start_time = 0
    for start, stop in silent_ranges:
        if start_time < start:
            final_clips.append(video.subclipped(start_time, start))
        start_time = stop
    
    if start_time < video.duration:
        final_clips.append(video.subclipped(start_time, video.duration))
    
    # Merge clips and export
    if not final_clips:
        print("No speaking parts detected, keeping original video.")
        final_video = video  # Keep the original video if no speech is found
    else:
        final_video = concatenate_videoclips(final_clips)
    
    final_video.write_videofile(output_path, codec='libx264')
    
    # Cleanup
    os.remove(audio_path)
    print("Processing complete. Output saved as", output_path)
    
    btn_process.configure(fg_color="green")  # Change button color to green when done
    
    # Open output folder
    if platform.system() == "Windows":
        os.startfile(save_folder)
    elif platform.system() == "Darwin":  # macOS
        os.system(f"open {save_folder}")
    else:  # Linux
        os.system(f"xdg-open {save_folder}")


def upload_file():
    global video_path
    video_path = filedialog.askopenfilename(filetypes=[("Video files", "*.mp4;*.avi;*.mov")])
    if video_path:
        btn_upload.configure(fg_color="green")  # Change button color to green


def save_to():
    global save_folder
    save_folder = filedialog.askdirectory()
    if save_folder:
        btn_save_to.configure(fg_color="green")  # Change button color to green


def start_processing():
    if video_path and save_folder:
        btn_process.configure(fg_color="blue")  # Reset button to blue before processing
        process_video(video_path, save_folder)


# GUI Setup
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

root = ctk.CTk()
root.title("Video Silence Cutter")
root.geometry("400x200")

video_path = ""
save_folder = ""

btn_upload = ctk.CTkButton(root, text="Upload Video", command=upload_file)
btn_upload.pack(pady=10)

btn_save_to = ctk.CTkButton(root, text="Save To", command=save_to)
btn_save_to.pack(pady=10)

btn_process = ctk.CTkButton(root, text="Start Processing", command=start_processing)
btn_process.pack(pady=20)

root.mainloop()
