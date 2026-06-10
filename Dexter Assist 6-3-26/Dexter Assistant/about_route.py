# About/Landing page placeholder route for Dexter Assistant
from flask import Flask

# This file should be appended to the end of dexter_assistant.py if not already present.

def register_about_route(app):
    @app.route("/about")
    def about_landing():
        # Placeholder for a future advanced marketing/landing page
        return "<h1>Dexter Assistant</h1><p>All your restaurant management apps, one secure dashboard.<br>Contact: <a href='mailto:info@dexterassist.com'>info@dexterassist.com</a></p><p>More coming soon.</p>"
