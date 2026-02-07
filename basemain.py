#class is used for all kinds of people
import datetime as dt

#Base c;ass is used for all kinds of Members.
class Member:
    """The Member class attributes and methods are for everyone"""
    # By default, a new account expires in one year (365 days)
    expiry_days = 365

    #Initialized a member object.
    def __init__(self,first_name, last_name):
        # Attributes (instance variables) for everyone
        self.first_name = first_name
        self.last_name = last_name

    #Method in the Base Class
    def get_status(self):
        return f"{self.first_name} is a Member"
    
        # Calculate expiry date from today's date
        self.expiry_days = dt.date.today()  + dt.timedelta(days=self.expiry_days)
        #default secret code is nothing
        self.secret_code = ""
    #method in the base class
    def show_expiry(self):
        return f"{self.first_name} {self.last_name} expires on {self.expiry_days}"

# Subclass for Members
class Admin(Member):
    def get_status(self):
        return super().get_status()
    # Admin account don't expire for 100 years
    expiry_days = 365. * 100

    #subclass parameters
    def __init__(self, first_name, last_name, secret_code):
        #pass the Member parameters up to Member class
        super().__init__(first_name,last_name)
        #Assign  the remaining parameters to this Admin object
        self.secret_code = secret_code  


class User(Member):
    def get_status(self):
        return f"{self.first_name} is a Regular User"

# Outside the class now.
ann = Admin("Annie","Angst","PRESTRO")
print(ann.show_expiry())
print()
uli = User("Uli","Ungula")
print(uli.show_expiry())
