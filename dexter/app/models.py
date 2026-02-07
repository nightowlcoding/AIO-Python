class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(100))
    is_archived = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

from . import db
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

class Company(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    locations = db.relationship('Location', backref='company', lazy=True)
    users = db.relationship('User', backref='company', lazy=True)

class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    daily_logs = db.relationship('DailyLog', backref='location', lazy=True)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(20), default='manager')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class DailyLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    shift = db.Column(db.String(20), default='Day')
    notes = db.Column(db.Text)
    total_sales = db.Column(db.Float, default=0.0)
    deposit_amount = db.Column(db.Float, default=0.0)
    entries = db.relationship('LogEntry', backref='log', lazy=True, cascade="all, delete-orphan")
    drawer = db.relationship('CashDrawer', backref='log', uselist=False, cascade="all, delete-orphan")

class LogEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    daily_log_id = db.Column(db.Integer, db.ForeignKey('daily_log.id'), nullable=False)
    employee_name = db.Column(db.String(100))
    cash_sales = db.Column(db.Float, default=0.0)
    cc_tips = db.Column(db.Float, default=0.0)
    credit_total = db.Column(db.Float, default=0.0)
    food_sales = db.Column(db.Float, default=0.0)
    beer_sales = db.Column(db.Float, default=0.0)
    liquor_sales = db.Column(db.Float, default=0.0)
    wine_sales = db.Column(db.Float, default=0.0)

class CashDrawer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    daily_log_id = db.Column(db.Integer, db.ForeignKey('daily_log.id'), nullable=False)
    total_count = db.Column(db.Float, default=0.0)
