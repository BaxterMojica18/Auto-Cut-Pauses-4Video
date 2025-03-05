import tkinter as tk
from tkinter import filedialog
from moviepy import VideoFileClip, concatenate_videoclips
from pydub import AudioSegment, silence
import os

def process_video(video_path):
    output_path = "output_video.mp4"
    
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

def upload_file():
    file_path = filedialog.askopenfilename(filetypes=[("Video files", "*.mp4;*.avi;*.mov")])
    if file_path:
        process_video(file_path)

# GUI Setup
root = tk.Tk()
root.title("Video Silence Cutter")
btn_upload = tk.Button(root, text="Upload Video", command=upload_file)
btn_upload.pack(pady=20)
root.mainloop()
