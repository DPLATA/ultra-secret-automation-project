"""
Author: silverboy

This script provides a function to extract the source URL of a video_scraper from a given web page URL.
It uses the requests library to fetch the HTML content from the URL and BeautifulSoup for HTML parsing.
"""

import requests
from bs4 import BeautifulSoup

def get_video_src_from_url(url):
    """
    Extracts the source URL of a video_scraper from a given web page URL.

    Parameters:
    url (str): The URL of the web page containing the video_scraper.

    Returns:
    str: The source URL of the video_scraper if found, or an error message if the video_scraper source cannot be retrieved.
    """
    try:
        # Send an HTTP GET request to the provided URL
        response = requests.get(url)

        # Check if the request was successful (status code 200)
        if response.status_code == 200:
            # Get the HTML content from the response
            html_content = response.text

            # Parse the HTML content with BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')

            # Find the video_scraper tag with the ID "sporty"
            video_tag = soup.find('video', id='sporty')

            if video_tag:
                # Find the source tag within the video_scraper tag
                source_tag = video_tag.find('source')

                if source_tag:
                    # Get the src attribute from the source tag
                    src_attribute = source_tag['src']

                    if src_attribute:
                        return src_attribute
                    else:
                        return "The source tag does not have a src attribute."
                else:
                    return "Source tag not found within the video_scraper tag."
            else:
                return "Video tag with id 'sporty' not found."
        else:
            return f"Failed to retrieve the HTML. Status code: {response.status_code}"
    except Exception as e:
        return f"An error occurred: {str(e)}"
