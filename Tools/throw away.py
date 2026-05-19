from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors

def create_quiz_pdf(filename):
    c = canvas.Canvas(filename, pagesize=letter)
    width, height = letter

    # Title
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, height - 50, "Big House Burgers Training Quiz")

    # Instructions
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 80, "Please select the best answer for each question.")

    # Questions Data
    questions = [
        ("1. On which specific holiday was Big House Burgers founded in 2003?", 
         ["a) Independence Day", "b) Halloween", "c) Thanksgiving", "d) New Year's Eve"]),
        ("2. Which app must employees use to manage their work schedule?", 
         ["a) HotSchedules", "b) Zoom", "c) Sling", "d) When I Work"]),
        ("3. What is the immediate consequence for a 'No Call, No Show'?", 
         ["a) Verbal warning", "b) Written write-up", "c) One week suspension", "d) Automatic termination"]),
        ("4. Which specific items are included in the 'Deluxe' burger topping keyword?", 
         ["a) Chili, cheddar cheese, red onions", "b) Bacon, avocado, grilled mushrooms, cheese", 
          "c) Refried beans, chorizo, pepper jack", "d) Grilled jalapeno, buffalo sauce, cheddar"]),
        ("5. What is the required cooking temperature for all burgers?", 
         ["a) Medium Rare", "b) Medium", "c) Medium Well", "d) Well Done"]),
        ("6. Which NFL team jersey is depicted in the manual for Sunday dress code?", 
         ["a) Houston Texans", "b) Dallas Cowboys", "c) Green Bay Packers", "d) Kansas City Chiefs"]),
        ("7. What are the two standard sides served with all Seafood Items?", 
         ["a) Mashed Potatoes & Green Beans", "b) French Fries & Coleslaw", 
          "c) Tater Tots & Side Salad", "d) Onion Rings & Elote"]),
        ("8. How many 'write-ups' lead to termination after the probationary period?", 
         ["a) One", "b) Two", "c) Three", "d) Four"]),
        ("9. Which three standard ingredients come on most sandwich items (e.g. BLT)?", 
         ["a) Mayo, Lettuce, Tomato", "b) Mustard, Pickle, Onion", 
          "c) Ranch, Lettuce, Tomato", "d) Mayo, Pickle, Tomato"]),
        ("10. What mixture of ingredients is used on the Burger A La Mexicana?", 
         ["a) Chili and cheddar cheese", "b) Refried beans mixed with chorizo", 
          "c) Grilled onions and bell peppers", "d) Buffalo sauce and jalapenos"])
    ]

    y_position = height - 120

    # Loop to draw questions
    for i, (question, options) in enumerate(questions, 1):
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y_position, question)
        y_position -= 20
        
        c.setFont("Helvetica", 12)
        for option in options:
            c.drawString(70, y_position, option)
            y_position -= 15
        
        y_position -= 15  # Extra space between questions
        
        # Start new page if space is low
        if y_position < 100:
            c.showPage()
            y_position = height - 50

    # Answer Key Page
    c.showPage()
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, height - 50, "Answer Key")
    
    answers = [
        "1. b) Halloween",
        "2. c) Sling",
        "3. d) Automatic termination",
        "4. b) Bacon, avocado, grilled mushrooms, and choice of cheese",
        "5. d) Well Done",
        "6. b) Dallas Cowboys",
        "7. b) French Fries and Coleslaw",
        "8. c) Three",
        "9. a) Mayo, Lettuce, Tomato",
        "10. b) Refried beans mixed with chorizo"
    ]
    
    y_position = height - 100
    c.setFont("Helvetica", 12)
    for answer in answers:
        c.drawString(50, y_position, answer)
        y_position -= 20

    c.save()
    print(f"PDF '{filename}' created successfully.")

# Run the function
create_quiz_pdf("C:/Users/arnol/OneDrive/Desktop/Big_House_Burgers_Quiz.pdf")