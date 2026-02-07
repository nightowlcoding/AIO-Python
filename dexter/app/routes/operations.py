from ..models import Employee
# Employee Management
@operations.route('/employees')
@login_required
def employees():
    employees = Employee.query.filter_by(company_id=current_user.company_id).all()
    return render_template('employees.html', employees=employees)

@operations.route('/employees/delete/<int:employee_id>', methods=['POST'])
@login_required
def delete_employee(employee_id):
    employee = Employee.query.filter_by(id=employee_id, company_id=current_user.company_id).first_or_404()
    db.session.delete(employee)
    db.session.commit()
    flash('Employee deleted.', 'success')
    return redirect(url_for('operations.employees'))

@operations.route('/employees/archive/<int:employee_id>', methods=['POST'])
@login_required
def archive_employee(employee_id):
    employee = Employee.query.filter_by(id=employee_id, company_id=current_user.company_id).first_or_404()
    employee.is_archived = True
    db.session.commit()
    flash('Employee archived.', 'info')
    return redirect(url_for('operations.employees'))
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from ..models import db, DailyLog, LogEntry, CashDrawer, Location
from datetime import datetime
import json

operations = Blueprint('operations', __name__)

def get_safe_location(location_id):
    return Location.query.filter_by(id=location_id, company_id=current_user.company_id).first()

@operations.route('/')
@operations.route('/dashboard')
@login_required
def dashboard():
    today = datetime.utcnow().date()
    todays_sales = db.session.query(db.func.sum(DailyLog.total_sales))\
        .filter(DailyLog.company_id == current_user.company_id)\
        .filter(DailyLog.date == today).scalar() or 0.0
    return render_template('dashboard.html', sales=todays_sales)

@operations.route('/daily-log', methods=['GET', 'POST'])
@login_required
def daily_log():
    if request.method == 'POST':
        try:
            location_id = request.form.get('location_id')
            if not get_safe_location(location_id):
                flash("Invalid Location", "danger")
                return redirect(url_for('operations.dashboard'))

            log_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
            shift = request.form.get('shift')
            
            log = DailyLog.query.filter_by(location_id=location_id, date=log_date, shift=shift).first()
            if not log:
                log = DailyLog(company_id=current_user.company_id, location_id=location_id, date=log_date, shift=shift)
                db.session.add(log)
            
            log.notes = request.form.get('notes')
            log.deposit_amount = float(request.form.get('deposit_amount', 0))
            
            # Simple implementation: Delete old entries and re-add (for prototype)
            for entry in log.entries:
                db.session.delete(entry)
                
            # In a real app, you would parse the dynamic form rows here.
            # For this scaffold, we just save the main log details.
            
            if log.drawer:
                db.session.delete(log.drawer)
            
            drawer = CashDrawer(log=log, total_count=float(request.form.get('drawer_total', 0)))
            db.session.add(drawer)

            db.session.commit()
            flash("Daily Log Saved Successfully", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('operations.dashboard'))

    locations = Location.query.filter_by(company_id=current_user.company_id).all()
    return render_template('daily_log.html', locations=locations)
