# from moviepy.editor import VideoFileClip, concatenate_videoclips
#
# # Load the video clips
# clip1 = VideoFileClip("videos/Marcus Stroman/745746/landscape/ball/Slider/Marcus Stroman - Julio Rodríguez - NYY vs. SEA #5 e8dcb59e-393d-466f-b551-731e7edfe59d.mp4").set_fps(24)
# clip2 = VideoFileClip("videos/Marcus Stroman/745746/landscape/ball/Slider/Marcus Stroman - Julio Rodríguez - NYY vs. SEA #41 d509982f-be0d-41be-970a-5d3287af6102.mp4").set_fps(24)
#
# # Set the duration for the transition (in seconds)
# transition_duration = 1
#
# # Fade-in transition for clip2
# clip2_fadein = clip2.crossfadein(transition_duration)
#
# # Concatenate the clips with the transition
# final_clip = concatenate_videoclips([clip1, clip2_fadein])
#
# # Save the final clip
# final_clip.write_videofile("path_to_output.mp4", codec="libx264", fps=24)


"""
This good
"""

# import subprocess
#
# # Input video paths
# clip1_path = "videos/Marcus Stroman/745746/landscape/ball/Slider/Marcus Stroman - Julio Rodríguez - NYY vs. SEA #5 e8dcb59e-393d-466f-b551-731e7edfe59d.mp4"
# clip2_path = "videos/Marcus Stroman/745746/landscape/ball/Slider/Marcus Stroman - Julio Rodríguez - NYY vs. SEA #41 d509982f-be0d-41be-970a-5d3287af6102.mp4"
#
# # Output video path
# output_path = "output.mp4"
#
# # ffmpeg command to concatenate the videos with a crossfade transition
# ffmpeg_command = [
#     "ffmpeg",
#     "-i", clip1_path,
#     "-i", clip2_path,
#     "-filter_complex", "[0:v]fade=out:st=5:d=1:alpha=1[v0];[1:v]fade=in:st=0:d=1:alpha=1[v1];[v0][0:a][v1][1:a]concat=n=2:v=1:a=1[v]",
#     "-map", "[v]",
#     "-c:v", "libx264",
#     "-crf", "18",
#     "-preset", "veryfast",
#     output_path
# ]
#
# # Run the ffmpeg command
# subprocess.run(ffmpeg_command)

"""
End of good
"""

import os
import subprocess

def generate_urls(base_path, call, pitch_type):
    urls = []
    for root, dirs, files in os.walk(base_path):
        if root.endswith(f"/{call}/{pitch_type}"):
            for file in files:
                relative_path = os.path.relpath(root, base_path)
                url = os.path.join(base_path, relative_path, file)
                urls.append(url)
    return urls

# Base path where the videos are located
base_path = "videos/Marcus Stroman/745411/landscape"

# Call and pitch type
call = "strike"
pitch_type = "Sinker"

# Generate the list of URLs
urls = generate_urls(base_path, call, pitch_type)

# Output text file path
concat_file_path = "concat.txt"

# Write the list of URLs to the text file
with open(concat_file_path, "w") as f:
    for url in urls:
        f.write("file '%s'\n" % url)

# Output video path
output_path = "Marcus Stroman strikes sinkers Padres.mp4"

# ffmpeg command to concatenate the clips
ffmpeg_command = [
    "ffmpeg",
    "-y",  # Overwrite output file if it exists
    "-f", "concat",
    "-safe", "0",
    "-i", concat_file_path,
    "-c", "copy",
    output_path
]

# Run the ffmpeg command
subprocess.run(ffmpeg_command)

# Remove the temporary concat file
os.remove(concat_file_path)
