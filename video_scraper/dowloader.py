import urllib.request
import requests
import math
import csv
import os
from video_scraper.parser import get_video_src_from_url
from video_scraper.convert_video_to_9_16_aspect_ratio import convert_to_nine_sixteen_aspect_ratio
#from converter import convert_videos_to_portrait


def download_pitcher_videos(game_pk, pitcher_name, video_folder, team_id):
    """
    Downloads videos of a specific pitcher's performance from a baseball game.

    Parameters:
    game_pk (int): The unique identifier of the baseball game.
    pitcher_name (str): The name of the pitcher.
    video_folder (str): The folder where the videos will be saved.

    Returns:
    None
    """
    url = f"https://baseballsavant.mlb.com/gf?game_pk={game_pk}"

    # Send a GET request to the URL
    response = requests.get(url)

    # Check if the request was successful (status code 200)
    if response.status_code == 200:
        # Parse the JSON response
        data = response.json()

        team_name = 'team_home' if team_id == data['team_home_id'] else 'team_away'

        filtered_entries = [entry for entry in data[team_name] if entry['pitcher_name'] == pitcher_name]

        if filtered_entries:
            #csv_file = f"{pitcher_name}/{pitcher_name}.csv"
            csv_file = os.path.join(video_folder, f"{pitcher_name}.csv")

            # Create the directory if it doesn't exist
            os.makedirs(os.path.dirname(csv_file), exist_ok=True)

            counter = 0

            with open(csv_file, mode='a', newline='') as file:
                writer = csv.writer(file)

                for entry in filtered_entries:
                    pitcher_name = entry['pitcher_name']
                    team_fielding = entry['team_fielding']
                    team_batting = entry['team_batting']
                    batter_name = entry['batter_name']
                    pitch_name = entry['pitch_name']
                    start_speed = entry['start_speed']
                    call_name = entry['call_name']
                    #play_description = entry['des']
                    play_id = entry['play_id']

                    rounded_speed = math.ceil(start_speed) if start_speed % 1 >= 0.5 else math.floor(start_speed)

                    print(f"{pitcher_name} vs. {batter_name} {pitch_name} {rounded_speed} mph {call_name} #shorts")

                    url = f"https://baseballsavant.mlb.com/sporty-videos?playId={play_id}"
                    src = get_video_src_from_url(url)

                    # Construct the filename
                    filename = f'{pitcher_name} - {batter_name} - {team_fielding} vs. {team_batting} #{counter} {play_id}.mp4'

                    # Write the row to the CSV file
                    writer.writerow([filename, f"{pitcher_name} vs. {batter_name} {pitch_name} {rounded_speed} mph {call_name} #shorts"])

                    # Download the video
                    landscape_output_directory = os.path.join(video_folder, f"{game_pk}/landscape")
                    os.makedirs(landscape_output_directory, exist_ok=True)
                    urllib.request.urlretrieve(src, f"{landscape_output_directory}/{filename}")
                    counter += 1

                    portrait_output_directory = os.path.join(video_folder, f"{game_pk}/portrait")
                    os.makedirs(portrait_output_directory, exist_ok=True)
                    convert_to_nine_sixteen_aspect_ratio(f"{landscape_output_directory}/{filename}", portrait_output_directory)

        else:
            print(f"No data found for pitcher {pitcher_name} in game_pk {game_pk}")
    else:
        print(f"Failed to retrieve data for game_pk {game_pk}. Status code: {response.status_code}")
