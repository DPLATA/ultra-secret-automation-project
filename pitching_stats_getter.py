"""
Author: silverboy

This script demonstrates how to use the pybaseball library to retrieve pitching statistics for a specific player for specific dates range.
"""

import os
from pybaseball import playerid_lookup, statcast_pitcher
from video_scraper.dowloader import download_pitcher_videos


# Function to retrieve pitching statistics for a player in a given season
def get_pitching_stats(player_name, start_date, end_date):
    """
    Retrieves pitching statistics for a specific player in a given dates range and returns the pitching stats dataframe and a list of unique game_pk values.

    Parameters:
    player_name (str): The full name of the player (e.g., "Marcus Stroman").
    start_date (str): The start date of the season in 'YYYY-MM-DD' format.
    end_date (str): The end date of the season in 'YYYY-MM-DD' format.

    Returns:
    tuple: A tuple containing two elements:
        - pandas.DataFrame: A DataFrame containing pitching statistics for the specified player.
        - list: A list of unique game_pk values from the pitching statistics DataFrame.
    """
    # Look up the player's player ID
    player_info = playerid_lookup(player_name.split()[1], player_name.split()[0])
    mlbam_id = player_info["key_mlbam"].iloc[0]

    # Retrieve pitching statistics for the player
    pitching_stats = statcast_pitcher(start_date, end_date, mlbam_id)

    # Extract unique values in the 'game_pk' column
    unique_game_pks = pitching_stats['game_pk'].unique()

    return pitching_stats, unique_game_pks




if __name__ == "__main__":
    # Input for player name
    player_name = input("Enter the player's full name (e.g., Marcus Stroman): ")

    # Set the start and end dates for the 2023 MLB season
    start_date = '2023-03-01'
    end_date = '2023-09-30'  # Adjust the end date as needed

    # Retrieve pitching statistics for the specified player and get unique game_pk values
    pitching_stats, unique_game_pks = get_pitching_stats(player_name, start_date, end_date)

    video_folder = os.path.join("videos", player_name)
    os.makedirs(video_folder, exist_ok=True)
    team_id = 112
    # for game_pk in unique_game_pks:
    #     download_pitcher_videos(game_pk, player_name, video_folder, team_id)
    download_count = 0
    for game_pk in unique_game_pks:
        if download_count < 2:
            download_pitcher_videos(game_pk, player_name, video_folder, team_id)
            download_count += 1
        else:
            break
