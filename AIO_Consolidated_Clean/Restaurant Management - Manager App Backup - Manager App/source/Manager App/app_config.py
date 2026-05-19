"""
Unified configuration for Manager App
Provides consistent styling, colors, and button configurations
"""

# Color Scheme
COLORS = {
    # Primary colors
    'primary': '#1976D2',           # Blue - main actions
    'primary_hover': '#1565C0',
    'primary_active': '#0D47A1',
    
    # Secondary colors
    'secondary': '#388E3C',         # Green - success/positive actions
    'secondary_hover': '#2E7D32',
    'secondary_active': '#1B5E20',
    
    # Accent colors
    'accent': '#F57C00',            # Orange - warnings/important
    'accent_hover': '#E64A19',
    'accent_active': '#D84315',
    
    # Neutral colors
    'neutral': '#616161',           # Gray - neutral actions
    'neutral_hover': '#424242',
    'neutral_active': '#212121',
    
    # Danger colors
    'danger': '#D32F2F',            # Red - delete/danger
    'danger_hover': '#C62828',
    'danger_active': '#B71C1C',
    
    # Background colors
    'bg_primary': '#FFFFFF',        # White
    'bg_secondary': '#F5F5F5',      # Light gray
    'bg_tertiary': '#E0E0E0',       # Medium gray
    'bg_dark': '#2C2C2C',           # Dark gray
    
    # Text colors
    'text': '#000000',              # Black
    'text_secondary': '#424242',    # Dark gray
    'text_light': '#757575',        # Medium gray
}

# Button Styles
BUTTON_STYLES = {
    'primary': {
        'bg': COLORS['primary'],
        'fg': COLORS['text'],
        'activebackground': COLORS['primary_active'],
        'activeforeground': COLORS['text'],
        'hover': COLORS['primary_hover'],
        'font': ('Arial', 12, 'bold'),
        'relief': 'flat',
        'cursor': 'hand2',
        'padx': 20,
        'pady': 10
    },
    'secondary': {
        'bg': COLORS['secondary'],
        'fg': COLORS['text'],
        'activebackground': COLORS['secondary_active'],
        'activeforeground': COLORS['text'],
        'hover': COLORS['secondary_hover'],
        'font': ('Arial', 12, 'bold'),
        'relief': 'flat',
        'cursor': 'hand2',
        'padx': 20,
        'pady': 10
    },
    'accent': {
        'bg': COLORS['accent'],
        'fg': COLORS['text'],
        'activebackground': COLORS['accent_active'],
        'activeforeground': COLORS['text'],
        'hover': COLORS['accent_hover'],
        'font': ('Arial', 12, 'bold'),
        'relief': 'flat',
        'cursor': 'hand2',
        'padx': 20,
        'pady': 10
    },
    'neutral': {
        'bg': COLORS['neutral'],
        'fg': COLORS['text'],
        'activebackground': COLORS['neutral_active'],
        'activeforeground': COLORS['text'],
        'hover': COLORS['neutral_hover'],
        'font': ('Arial', 11, 'bold'),
        'relief': 'flat',
        'cursor': 'hand2',
        'padx': 15,
        'pady': 8
    },
    'danger': {
        'bg': COLORS['danger'],
        'fg': COLORS['text'],
        'activebackground': COLORS['danger_active'],
        'activeforeground': COLORS['text'],
        'hover': COLORS['danger_hover'],
        'font': ('Arial', 11, 'bold'),
        'relief': 'flat',
        'cursor': 'hand2',
        'padx': 15,
        'pady': 8
    },
    'large': {
        'font': ('Arial', 14, 'bold'),
        'height': 3,
        'width': 18,
        'padx': 10,
        'pady': 15
    },
    'small': {
        'font': ('Arial', 10, 'bold'),
        'padx': 10,
        'pady': 5
    }
}

# Window Configuration
WINDOW_CONFIG = {
    'width': 360,
    'height': 800,
    'resizable': False,
    'bg': COLORS['bg_primary']
}

# Header Configuration
HEADER_CONFIG = {
    'height': 80,
    'bg': COLORS['bg_dark'],
    'fg': COLORS['text'],
    'font': ('Arial', 20, 'bold')
}

# Fonts
FONTS = {
    'header': ('Arial', 20, 'bold'),
    'title': ('Arial', 16, 'bold'),
    'subtitle': ('Arial', 14, 'bold'),
    'button': ('Arial', 12, 'bold'),
    'label': ('Arial', 11),
    'entry': ('Arial', 11),
    'body': ('Arial', 11),
    'body_bold': ('Arial', 11, 'bold'),
    'small': ('Arial', 9),
    'small_bold': ('Arial', 9, 'bold')
}


def create_button(parent, text, command, style='primary', size='normal', **kwargs):
    """
    Create a standardized button with consistent styling
    
    Args:
        parent: Parent widget
        text: Button text
        command: Button command/callback
        style: Button style ('primary', 'secondary', 'accent', 'neutral', 'danger')
        size: Button size ('normal', 'large', 'small')
        **kwargs: Additional button configuration
    
    Returns:
        tk.Button: Configured button widget
    """
    import tkinter as tk
    
    # Get base style
    btn_config = BUTTON_STYLES.get(style, BUTTON_STYLES['primary']).copy()
    hover_color = btn_config.pop('hover', btn_config['bg'])
    
    # Apply size modifiers
    if size == 'large':
        btn_config.update(BUTTON_STYLES['large'])
    elif size == 'small':
        btn_config.update(BUTTON_STYLES['small'])
    
    # Override with custom kwargs
    btn_config.update(kwargs)
    
    # Create button
    button = tk.Button(parent, text=text, command=command, **btn_config)
    
    # Add hover effects
    base_color = btn_config['bg']
    button.bind("<Enter>", lambda e: button.config(bg=hover_color))
    button.bind("<Leave>", lambda e: button.config(bg=base_color))
    
    return button


def create_header(parent, text):
    """Create a standardized header"""
    import tkinter as tk
    
    header_frame = tk.Frame(parent, bg=HEADER_CONFIG['bg'], height=HEADER_CONFIG['height'])
    header_frame.pack(fill="x")
    header_frame.pack_propagate(False)
    
    label = tk.Label(
        header_frame,
        text=text,
        font=HEADER_CONFIG['font'],
        bg=HEADER_CONFIG['bg'],
        fg=HEADER_CONFIG['fg']
    )
    label.pack(pady=20)
    
    return header_frame


def setup_scrollable_frame(parent):
    """Create a standardized scrollable content area"""
    import tkinter as tk
    from tkinter import Canvas, Scrollbar
    
    canvas_frame = tk.Frame(parent, bg=COLORS['bg_primary'])
    canvas_frame.pack(fill="both", expand=True)
    
    canvas = Canvas(canvas_frame, bg=COLORS['bg_primary'], highlightthickness=0)
    scrollbar = Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
    content_frame = tk.Frame(canvas, bg=COLORS['bg_primary'])
    
    content_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    
    canvas.create_window((0, 0), window=content_frame, anchor="nw", width=320)
    canvas.configure(yscrollcommand=scrollbar.set)
    
    canvas.pack(side="left", fill="both", expand=True, padx=20, pady=20)
    scrollbar.pack(side="right", fill="y", pady=20, padx=(0, 5))
    
    # Enable mousewheel scrolling
    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    canvas.bind_all("<MouseWheel>", _on_mousewheel)
    
    return content_frame, canvas
