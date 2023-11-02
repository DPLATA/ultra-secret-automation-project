import cv2
import os

def convert_to_nine_sixteen_aspect_ratio(input_video, output_directory):

    # Extract the base filename without extension
    base_filename = os.path.splitext(os.path.basename(input_video))[0]

    # Open the input video file
    cap = cv2.VideoCapture(input_video)

    # Get the original video dimensions
    original_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    original_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Define the output dimensions (9:16 portrait)
    output_width = original_height * 9 // 16
    output_height = original_height

    os.makedirs(output_directory, exist_ok=True)

    # Create a VideoWriter object to save the output
    output_video = os.path.join(output_directory, f'{base_filename}.mp4')
    # Create a VideoWriter object to save the output
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # Video codec
    out = cv2.VideoWriter(output_video, fourcc, 30.0, (output_width, output_height))

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Calculate the cropping area for the middle of the frame
        crop_x = (original_width - output_width) // 2
        cropped_frame = frame[:, crop_x:crop_x + output_width]

        # Write the cropped frame to the output video
        out.write(cropped_frame)

    cap.release()
    out.release()
    cv2.destroyAllWindows()
