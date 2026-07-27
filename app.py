from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from database import FinanceDB
from datetime import datetime, date
import calendar
import json
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-this-in-production')

db = FinanceDB()


def is_logged_in():
    return 'user_id' in session


def get_current_user():
    if is_logged_in():
        return {'id': session['user_id'], 'username': session['username']}
    return None


def get_quarter_date_range(year, quarter):
    """Return (start_date, end_date) strings for a given quarter."""
    start_month = (quarter - 1) * 3 + 1
    end_month = start_month + 2
    last_day = calendar.monthrange(year, end_month)[1]
    start_date = f"{year}-{start_month:02d}-01"
    end_date = f"{year}-{end_month:02d}-{last_day:02d}"
    return start_date, end_date


def format_period_label(period, year, month, quarter, start_date, end_date):
    """Return a human-readable label for the selected period."""
    if period == 'quarter':
        return f"Q{quarter} {year}"
    elif period == 'custom' and start_date and end_date:
        sd = datetime.strptime(start_date, '%Y-%m-%d').strftime('%b %d, %Y')
        ed = datetime.strptime(end_date, '%Y-%m-%d').strftime('%b %d, %Y')
        return f"{sd} - {ed}"
    else:
        return f"{calendar.month_name[month]} {year}"


@app.route('/')
def index():
    if is_logged_in():
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')

        if not username or not email or not password:
            return jsonify({'success': False, 'message': 'All fields are required'}), 400

        if len(password) < 6:
            return jsonify({'success': False, 'message': 'Password must be at least 6 characters'}), 400

        user_id = db.create_user(username, email, password)

        if user_id:
            session['user_id'] = user_id
            session['username'] = username
            return jsonify({'success': True, 'message': 'Account created successfully!'})
        else:
            return jsonify({'success': False, 'message': 'Username or email already exists'}), 400

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')

        user = db.verify_user(username, password)

        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            return jsonify({'success': True, 'message': 'Login successful!'})
        else:
            return jsonify({'success': False, 'message': 'Invalid username or password'}), 401

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully', 'info')
    return redirect(url_for('index'))


@app.route('/dashboard')
def dashboard():
    if not is_logged_in():
        return redirect(url_for('login'))

    user = get_current_user()

    # Parse period params
    period = request.args.get('period', 'month')
    now = datetime.now()
    year = request.args.get('year', now.year, type=int)
    month = request.args.get('month', now.month, type=int)
    quarter = request.args.get('quarter', (now.month - 1) // 3 + 1, type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    # Get summary based on period
    if period == 'quarter':
        start_date, end_date = get_quarter_date_range(year, quarter)
        summary = db.get_custom_range_summary(user['id'], start_date, end_date)
    elif period == 'custom' and start_date and end_date:
        summary = db.get_custom_range_summary(user['id'], start_date, end_date)
    else:
        period = 'month'
        summary = db.get_monthly_summary(user['id'], year, month)
        sd = f"{year}-{month:02d}-01"
        ed = f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"
        start_date = sd
        end_date = ed

    period_label = format_period_label(period, year, month, quarter, start_date, end_date)

    # Get recent transactions
    recent_transactions = db.get_transactions(user['id'], limit=10)

    # Get spending by category for the selected range
    spending_by_category = db.get_spending_by_category(user['id'], start_date, end_date)

    return render_template('dashboard.html',
                           user=user,
                           monthly_summary=summary,
                           recent_transactions=recent_transactions,
                           spending_by_category=spending_by_category,
                           current_month=calendar.month_name[month],
                           current_year=year,
                           period=period,
                           year=year,
                           month=month,
                           quarter=quarter,
                           start_date=start_date,
                           end_date=end_date,
                           period_label=period_label)


@app.route('/transactions')
def transactions():
    if not is_logged_in():
        return redirect(url_for('login'))

    user = get_current_user()

    # Support date range filtering
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if start_date and end_date:
        all_transactions = db.get_transactions_by_date_range(user['id'], start_date, end_date)
    else:
        all_transactions = db.get_transactions(user['id'])

    categories = db.get_categories(user['id'])

    return render_template('transactions.html',
                           user=user,
                           transactions=all_transactions,
                           categories=categories)


@app.route('/add_transaction', methods=['POST'])
def add_transaction():
    if not is_logged_in():
        return jsonify({'success': False, 'message': 'Not logged in'}), 401

    data = request.get_json()
    user = get_current_user()

    try:
        required_fields = ['category_id', 'amount', 'description', 'transaction_type', 'date']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'success': False, 'message': f'{field} is required'}), 400

        db.add_transaction(
            user_id=user['id'],
            category_id=int(data['category_id']),
            amount=float(data['amount']),
            description=data['description'],
            transaction_type=data['transaction_type'],
            date=data['date']
        )

        return jsonify({'success': True, 'message': 'Transaction added successfully!'})

    except Exception as e:
        print(f"Error adding transaction: {e}")
        return jsonify({'success': False, 'message': 'Error adding transaction'}), 500


@app.route('/api/categories')
def get_categories():
    if not is_logged_in():
        return jsonify({'error': 'Not logged in'}), 401

    user = get_current_user()
    categories = db.get_categories(user['id'])
    return jsonify(categories)


@app.route('/api/spending_by_category')
def api_spending_by_category():
    if not is_logged_in():
        return jsonify({'error': 'Not logged in'}), 401

    user = get_current_user()
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    spending_data = db.get_spending_by_category(user['id'], start_date, end_date)
    return jsonify(spending_data)


@app.route('/api/monthly_summary/<int:year>/<int:month>')
def api_monthly_summary(year, month):
    if not is_logged_in():
        return jsonify({'error': 'Not logged in'}), 401

    user = get_current_user()
    summary = db.get_monthly_summary(user['id'], year, month)
    return jsonify(summary)


@app.route('/api/quarterly_summary/<int:year>/<int:quarter>')
def api_quarterly_summary(year, quarter):
    if not is_logged_in():
        return jsonify({'error': 'Not logged in'}), 401

    user = get_current_user()
    summary = db.get_quarterly_summary(user['id'], year, quarter)
    return jsonify(summary)


@app.route('/api/custom_range_summary')
def api_custom_range_summary():
    if not is_logged_in():
        return jsonify({'error': 'Not logged in'}), 401

    user = get_current_user()
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if not start_date or not end_date:
        return jsonify({'error': 'start_date and end_date are required'}), 400

    summary = db.get_custom_range_summary(user['id'], start_date, end_date)
    return jsonify(summary)


@app.route('/api/transactions_by_date_range')
def api_transactions_by_date_range():
    if not is_logged_in():
        return jsonify({'error': 'Not logged in'}), 401

    user = get_current_user()
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if not start_date or not end_date:
        return jsonify({'error': 'start_date and end_date are required'}), 400

    transactions = db.get_transactions_by_date_range(user['id'], start_date, end_date)
    return jsonify(transactions)


@app.route('/reports')
def reports():
    if not is_logged_in():
        return redirect(url_for('login'))

    user = get_current_user()
    now = datetime.now()

    # Get last 6 months of data for trends
    monthly_data = []
    for i in range(6):
        m = now.month - i
        y = now.year
        if m <= 0:
            m += 12
            y -= 1

        summary = db.get_monthly_summary(user['id'], y, m)
        monthly_data.append({
            'month': calendar.month_name[m],
            'year': y,
            'summary': summary
        })

    monthly_data.reverse()

    return render_template('reports.html',
                           user=user,
                           monthly_data=monthly_data)


@app.route('/export_csv')
def export_csv():
    if not is_logged_in():
        return redirect(url_for('login'))

    from flask import make_response
    import csv
    import io

    user = get_current_user()
    transactions = db.get_transactions(user['id'])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Category', 'Description', 'Type', 'Amount'])

    for transaction in transactions:
        writer.writerow([
            transaction['date'],
            transaction['category_name'],
            transaction['description'],
            transaction['transaction_type'].title(),
            f"${transaction['amount']:.2f}"
        ])

    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=transactions_{user["username"]}.csv'

    return response


@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(error):
    return render_template('500.html'), 500


if __name__ == '__main__':
    db.init_database()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
