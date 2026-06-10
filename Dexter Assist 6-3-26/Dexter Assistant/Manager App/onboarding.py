"""
Onboarding Wizard for new users
Professional first-time experience
"""
import tkinter as tk
from tkinter import ttk, messagebox
from app_config import COLORS, FONTS, create_button


class OnboardingWizard(tk.Toplevel):
    """Multi-step onboarding wizard"""
    
    def __init__(self, parent, company_name, user_name):
        super().__init__(parent)
        self.title("Welcome to Manager App")
        self.geometry("800x600")
        self.configure(bg=COLORS['bg_primary'])
        self.resizable(False, False)
        
        self.company_name = company_name
        self.user_name = user_name
        self.current_step = 0
        self.total_steps = 5
        
        # Center window
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')
        
        self.create_widgets()
        self.show_step(0)
        
        # Make modal
        self.transient(parent)
        self.grab_set()
    
    def create_widgets(self):
        """Create wizard layout"""
        # Progress bar at top
        progress_frame = tk.Frame(self, bg=COLORS['primary'], height=60)
        progress_frame.pack(fill="x")
        progress_frame.pack_propagate(False)
        
        self.progress_label = tk.Label(
            progress_frame,
            text="",
            font=('Arial', 12),
            bg=COLORS['primary'],
            fg="white"
        )
        self.progress_label.pack(pady=10)
        
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            mode='determinate',
            length=700
        )
        self.progress_bar.pack(pady=5)
        
        # Content area
        self.content_frame = tk.Frame(self, bg=COLORS['bg_primary'])
        self.content_frame.pack(fill="both", expand=True, padx=40, pady=30)
        
        # Navigation buttons at bottom
        nav_frame = tk.Frame(self, bg=COLORS['bg_secondary'], height=80)
        nav_frame.pack(fill="x", side="bottom")
        nav_frame.pack_propagate(False)
        
        button_frame = tk.Frame(nav_frame, bg=COLORS['bg_secondary'])
        button_frame.pack(expand=True)
        
        self.skip_btn = create_button(
            button_frame,
            "Skip Tour",
            self.skip_wizard,
            style="neutral",
            width=120
        )
        self.skip_btn.pack(side="left", padx=5)
        
        self.back_btn = create_button(
            button_frame,
            "← Back",
            self.previous_step,
            style="secondary",
            width=120
        )
        self.back_btn.pack(side="left", padx=5)
        
        self.next_btn = create_button(
            button_frame,
            "Next →",
            self.next_step,
            style="primary",
            width=120
        )
        self.next_btn.pack(side="left", padx=5)
    
    def show_step(self, step):
        """Show specific step"""
        # Clear content
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        
        # Update progress
        self.current_step = step
        self.progress_bar['value'] = ((step + 1) / self.total_steps) * 100
        self.progress_label['text'] = f"Step {step + 1} of {self.total_steps}"
        
        # Update buttons
        self.back_btn['state'] = 'normal' if step > 0 else 'disabled'
        
        if step == self.total_steps - 1:
            self.next_btn.configure(text="Get Started! 🚀")
        else:
            self.next_btn.configure(text="Next →")
        
        # Show step content
        if step == 0:
            self.step_welcome()
        elif step == 1:
            self.step_features()
        elif step == 2:
            self.step_daily_operations()
        elif step == 3:
            self.step_tips()
        elif step == 4:
            self.step_complete()
    
    def step_welcome(self):
        """Welcome step"""
        tk.Label(
            self.content_frame,
            text=f"Welcome to Manager App!",
            font=('Arial', 28, 'bold'),
            bg=COLORS['bg_primary'],
            fg=COLORS['primary']
        ).pack(pady=(20, 10))
        
        tk.Label(
            self.content_frame,
            text=f"Hi {self.user_name}! 👋",
            font=('Arial', 18),
            bg=COLORS['bg_primary'],
            fg=COLORS['text']
        ).pack(pady=10)
        
        info_text = f"""
You're now ready to manage {self.company_name} with ease.

Manager App is designed specifically for restaurant operations,
helping you track daily sales, manage cash, monitor employees,
and generate insightful reports.

Let's take a quick tour to get you started!
        """
        
        tk.Label(
            self.content_frame,
            text=info_text,
            font=FONTS['body'],
            bg=COLORS['bg_primary'],
            fg=COLORS['text'],
            justify="center"
        ).pack(pady=20)
        
        # Icon
        canvas = tk.Canvas(self.content_frame, width=100, height=100, 
                          bg=COLORS['bg_primary'], highlightthickness=0)
        canvas.pack(pady=20)
        canvas.create_oval(10, 10, 90, 90, fill=COLORS['primary'], outline="")
        canvas.create_text(50, 50, text="🏢", font=('Arial', 40))
    
    def step_features(self):
        """Features overview"""
        tk.Label(
            self.content_frame,
            text="Powerful Features",
            font=('Arial', 24, 'bold'),
            bg=COLORS['bg_primary'],
            fg=COLORS['primary']
        ).pack(pady=(10, 20))
        
        features = [
            ("📊 Daily Log", "Track sales, labor hours, and operational metrics"),
            ("💰 Cash Manager", "Monitor cash drawer and deductions"),
            ("👥 Employee Management", "Manage staff lists and performance"),
            ("📈 Reports", "Generate detailed analytics and summaries"),
            ("💾 Auto-Save", "Never lose data with automatic backups"),
            ("🔒 Secure", "Company-isolated data with role-based access")
        ]
        
        features_frame = tk.Frame(self.content_frame, bg=COLORS['bg_primary'])
        features_frame.pack(fill="both", expand=True, padx=40)
        
        for i, (title, desc) in enumerate(features):
            feature_frame = tk.Frame(features_frame, bg=COLORS['bg_secondary'], 
                                    relief="solid", bd=1)
            feature_frame.pack(fill="x", pady=8)
            
            tk.Label(
                feature_frame,
                text=title,
                font=('Arial', 14, 'bold'),
                bg=COLORS['bg_secondary'],
                fg=COLORS['text'],
                anchor="w"
            ).pack(fill="x", padx=15, pady=(10, 5))
            
            tk.Label(
                feature_frame,
                text=desc,
                font=FONTS['body'],
                bg=COLORS['bg_secondary'],
                fg=COLORS['text_secondary'],
                anchor="w",
                wraplength=600
            ).pack(fill="x", padx=15, pady=(0, 10))
    
    def step_daily_operations(self):
        """Daily operations guide"""
        tk.Label(
            self.content_frame,
            text="Your Daily Workflow",
            font=('Arial', 24, 'bold'),
            bg=COLORS['bg_primary'],
            fg=COLORS['primary']
        ).pack(pady=(10, 20))
        
        steps = [
            "1️⃣ Start your shift with the Daily Log",
            "2️⃣ Track sales, labor, and incidents throughout the day",
            "3️⃣ Record cash drawer counts in Cash Manager",
            "4️⃣ Review and save - auto-save has your back!",
            "5️⃣ Generate reports to analyze performance"
        ]
        
        steps_frame = tk.Frame(self.content_frame, bg=COLORS['bg_primary'])
        steps_frame.pack(fill="both", expand=True, padx=40)
        
        for step in steps:
            step_frame = tk.Frame(steps_frame, bg=COLORS['bg_primary'])
            step_frame.pack(fill="x", pady=10)
            
            tk.Label(
                step_frame,
                text=step,
                font=('Arial', 14),
                bg=COLORS['bg_primary'],
                fg=COLORS['text'],
                anchor="w"
            ).pack(fill="x", padx=20)
        
        tip_frame = tk.Frame(self.content_frame, bg=COLORS['accent'], 
                            relief="solid", bd=2)
        tip_frame.pack(fill="x", padx=40, pady=20)
        
        tk.Label(
            tip_frame,
            text="💡 Pro Tip: Use keyboard shortcuts for faster data entry!",
            font=('Arial', 12, 'bold'),
            bg=COLORS['accent'],
            fg="white",
            pady=15
        ).pack()
    
    def step_tips(self):
        """Tips and best practices"""
        tk.Label(
            self.content_frame,
            text="Tips for Success",
            font=('Arial', 24, 'bold'),
            bg=COLORS['bg_primary'],
            fg=COLORS['primary']
        ).pack(pady=(10, 20))
        
        tips = [
            ("🔐 Security First", "Keep your password secure and don't share account access"),
            ("💾 Trust Auto-Save", "The app saves every 5 minutes, but you can save manually anytime"),
            ("📋 Regular Backups", "Automatic backups are created - check Settings for restore options"),
            ("👥 Manage Your Team", "Assign appropriate roles to team members for better access control"),
            ("📞 Get Help", "Use the Help menu or contact support if you need assistance"),
            ("🎯 Customize Settings", "Visit Company Settings to personalize your experience")
        ]
        
        tips_frame = tk.Frame(self.content_frame, bg=COLORS['bg_primary'])
        tips_frame.pack(fill="both", expand=True, padx=40)
        
        for title, desc in tips:
            tip_frame = tk.Frame(tips_frame, bg=COLORS['bg_primary'])
            tip_frame.pack(fill="x", pady=8)
            
            tk.Label(
                tip_frame,
                text=title,
                font=('Arial', 13, 'bold'),
                bg=COLORS['bg_primary'],
                fg=COLORS['primary'],
                anchor="w"
            ).pack(fill="x")
            
            tk.Label(
                tip_frame,
                text=desc,
                font=FONTS['body'],
                bg=COLORS['bg_primary'],
                fg=COLORS['text_secondary'],
                anchor="w",
                wraplength=600
            ).pack(fill="x", padx=20)
    
    def step_complete(self):
        """Completion step"""
        tk.Label(
            self.content_frame,
            text="You're All Set! 🎉",
            font=('Arial', 28, 'bold'),
            bg=COLORS['bg_primary'],
            fg=COLORS['success']
        ).pack(pady=(40, 20))
        
        completion_text = f"""
{self.company_name} is ready to go!

You now have everything you need to efficiently manage
your restaurant operations.

Click "Get Started" to open your dashboard and begin
using Manager App.

We're here to help you succeed!
        """
        
        tk.Label(
            self.content_frame,
            text=completion_text,
            font=('Arial', 14),
            bg=COLORS['bg_primary'],
            fg=COLORS['text'],
            justify="center"
        ).pack(pady=20)
        
        # Success icon
        canvas = tk.Canvas(self.content_frame, width=120, height=120, 
                          bg=COLORS['bg_primary'], highlightthickness=0)
        canvas.pack(pady=30)
        canvas.create_oval(10, 10, 110, 110, fill=COLORS['success'], outline="")
        canvas.create_text(60, 60, text="✓", font=('Arial', 60, 'bold'), fill="white")
    
    def next_step(self):
        """Go to next step"""
        if self.current_step < self.total_steps - 1:
            self.show_step(self.current_step + 1)
        else:
            # Finish wizard
            self.finish_wizard()
    
    def previous_step(self):
        """Go to previous step"""
        if self.current_step > 0:
            self.show_step(self.current_step - 1)
    
    def skip_wizard(self):
        """Skip the wizard"""
        if messagebox.askyesno("Skip Tour", 
                              "Are you sure you want to skip the tour?\n\nYou can always access help from the menu."):
            self.destroy()
    
    def finish_wizard(self):
        """Complete the wizard"""
        self.destroy()


def show_onboarding(parent, company_name, user_name):
    """Show onboarding wizard"""
    wizard = OnboardingWizard(parent, company_name, user_name)
    parent.wait_window(wizard)
