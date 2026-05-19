def validate_url(url):
    # Basic validation for Instagram URLs
    if url.startswith("https://www.instagram.com/") and "/p/" in url:
        return True
    return False

def format_file_name(username, post_id):
    # Format the file name for saving the image
    return f"{username}_{post_id}.jpg"

def handle_exception(e):
    # Handle exceptions and return a user-friendly message
    return f"An error occurred: {str(e)}"