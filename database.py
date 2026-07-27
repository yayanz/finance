import os
import sqlite3

# Use werkzeug for password hashing (more secure than raw SHA-256)
from werkzeug.security import generate_password_hash, check_password_hash

# Detect if we're using PostgreSQL (Render sets DATABASE_URL) or SQLite (local dev)
DATABASE_URL = os.environ.get('DATABASE_URL')

if DATABASE_URL:
    import psycopg2
    from psycopg2.extras import RealDictCursor


class FinanceDB:
    def __init__(self, db_path='instance/finance.db'):
        """Initialize the database connection"""
        self.db_path = db_path
        self.use_postgres = DATABASE_URL is not None
        if not self.use_postgres:
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.init_database()

    def get_connection(self):
        """Get database connection"""
        if self.use_postgres:
            conn = psycopg2.connect(DATABASE_URL)
            conn.autocommit = False
            return conn
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn

    def _placeholder(self):
        """Return the correct placeholder for the current DB"""
        return '%s' if self.use_postgres else '?'

    def init_database(self):
        """Create all tables if they don't exist"""
        conn = self.get_connection()
        cursor = conn.cursor()

        if self.use_postgres:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS categories (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    color TEXT DEFAULT '#3b82f6',
                    user_id INTEGER NOT NULL REFERENCES users (id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users (id),
                    category_id INTEGER NOT NULL REFERENCES categories (id),
                    amount DECIMAL(10,2) NOT NULL,
                    description TEXT,
                    transaction_type TEXT CHECK (transaction_type IN ('income', 'expense')) NOT NULL,
                    date DATE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS budgets (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users (id),
                    category_id INTEGER NOT NULL REFERENCES categories (id),
                    amount DECIMAL(10,2) NOT NULL,
                    month_year TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, category_id, month_year)
                )
            ''')
        else:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    color TEXT DEFAULT '#3b82f6',
                    user_id INTEGER NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    category_id INTEGER NOT NULL,
                    amount DECIMAL(10,2) NOT NULL,
                    description TEXT,
                    transaction_type TEXT CHECK (transaction_type IN ('income', 'expense')) NOT NULL,
                    date DATE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (category_id) REFERENCES categories (id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS budgets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    category_id INTEGER NOT NULL,
                    amount DECIMAL(10,2) NOT NULL,
                    month_year TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (category_id) REFERENCES categories (id),
                    UNIQUE(user_id, category_id, month_year)
                )
            ''')

        conn.commit()
        conn.close()
        print("Database tables created successfully!")

    def hash_password(self, password):
        """Hash password using werkzeug's secure hashing"""
        return generate_password_hash(password)

    def verify_password(self, password, password_hash):
        """Verify password against stored hash"""
        # Support both old SHA-256 hashes and new werkzeug hashes
        if password_hash.startswith(('pbkdf2:', 'scrypt:')):
            return check_password_hash(password_hash, password)
        else:
            # Legacy SHA-256 fallback
            import hashlib
            return hashlib.sha256(password.encode()).hexdigest() == password_hash

    def create_user(self, username, email, password):
        """Create a new user account"""
        conn = self.get_connection()
        cursor = conn.cursor()
        ph = self._placeholder()

        try:
            password_hash = self.hash_password(password)
            cursor.execute(
                f'INSERT INTO users (username, email, password_hash) VALUES ({ph}, {ph}, {ph})',
                (username, email, password_hash)
            )

            if self.use_postgres:
                cursor.execute('SELECT LASTVAL()')
                user_id = cursor.fetchone()[0]
            else:
                user_id = cursor.lastrowid

            default_categories = [
                ('Food & Dining', '#ef4444'),
                ('Transportation', '#3b82f6'),
                ('Shopping', '#8b5cf6'),
                ('Entertainment', '#10b981'),
                ('Bills & Utilities', '#f59e0b'),
                ('Healthcare', '#ec4899'),
                ('Education', '#06b6d4'),
                ('Travel', '#84cc16'),
                ('Income', '#22c55e'),
                ('Other', '#6b7280')
            ]

            for category_name, color in default_categories:
                cursor.execute(
                    f'INSERT INTO categories (name, color, user_id) VALUES ({ph}, {ph}, {ph})',
                    (category_name, color, user_id)
                )

            conn.commit()
            print(f"User '{username}' created successfully with default categories!")
            return user_id

        except Exception as e:
            print(f"Error creating user: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()

    def verify_user(self, username, password):
        """Verify user login credentials"""
        conn = self.get_connection()
        cursor = conn.cursor()
        ph = self._placeholder()

        cursor.execute(
            f'SELECT id, username, email, password_hash FROM users WHERE username = {ph}',
            (username,)
        )

        if self.use_postgres:
            row = cursor.fetchone()
            if row:
                user_data = {'id': row[0], 'username': row[1], 'email': row[2]}
                stored_hash = row[3]
            else:
                conn.close()
                return None
        else:
            row = cursor.fetchone()
            if row:
                user_data = dict(row)
                stored_hash = row['password_hash']
            else:
                conn.close()
                return None

        conn.close()

        if self.verify_password(password, stored_hash):
            return user_data
        return None

    def add_transaction(self, user_id, category_id, amount, description, transaction_type, date):
        """Add a new transaction"""
        conn = self.get_connection()
        cursor = conn.cursor()
        ph = self._placeholder()

        cursor.execute(
            f'INSERT INTO transactions (user_id, category_id, amount, description, transaction_type, date) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})',
            (user_id, category_id, amount, description, transaction_type, date)
        )

        conn.commit()
        conn.close()
        print("Transaction added successfully!")

    def get_transactions(self, user_id, limit=None):
        """Get user's transactions with category names"""
        conn = self.get_connection()
        cursor = conn.cursor()
        ph = self._placeholder()

        query = f'''
            SELECT t.*, c.name as category_name, c.color as category_color
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = {ph}
            ORDER BY t.date DESC
        '''

        if limit:
            query += f' LIMIT {limit}'

        cursor.execute(query, (user_id,))

        if self.use_postgres:
            columns = [desc[0] for desc in cursor.description]
            transactions = [dict(zip(columns, row)) for row in cursor.fetchall()]
        else:
            transactions = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return transactions

    def get_transactions_by_date_range(self, user_id, start_date, end_date):
        """Get user's transactions filtered by a custom date range"""
        conn = self.get_connection()
        cursor = conn.cursor()
        ph = self._placeholder()

        query = f'''
            SELECT t.*, c.name as category_name, c.color as category_color
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = {ph} AND t.date >= {ph} AND t.date <= {ph}
            ORDER BY t.date DESC
        '''

        cursor.execute(query, (user_id, start_date, end_date))

        if self.use_postgres:
            columns = [desc[0] for desc in cursor.description]
            transactions = [dict(zip(columns, row)) for row in cursor.fetchall()]
        else:
            transactions = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return transactions

    def get_categories(self, user_id):
        """Get user's categories"""
        conn = self.get_connection()
        cursor = conn.cursor()
        ph = self._placeholder()

        cursor.execute(
            f'SELECT * FROM categories WHERE user_id = {ph} ORDER BY name',
            (user_id,)
        )

        if self.use_postgres:
            columns = [desc[0] for desc in cursor.description]
            categories = [dict(zip(columns, row)) for row in cursor.fetchall()]
        else:
            categories = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return categories

    def get_spending_by_category(self, user_id, start_date=None, end_date=None):
        """Get spending breakdown by category"""
        conn = self.get_connection()
        cursor = conn.cursor()
        ph = self._placeholder()

        query = f'''
            SELECT c.name, c.color, SUM(t.amount) as total_amount
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = {ph} AND t.transaction_type = 'expense'
        '''
        params = [user_id]

        if start_date:
            query += f' AND t.date >= {ph}'
            params.append(start_date)

        if end_date:
            query += f' AND t.date <= {ph}'
            params.append(end_date)

        query += ' GROUP BY c.id, c.name, c.color ORDER BY total_amount DESC'

        cursor.execute(query, params)

        if self.use_postgres:
            columns = [desc[0] for desc in cursor.description]
            spending = [dict(zip(columns, row)) for row in cursor.fetchall()]
        else:
            spending = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return spending

    def _build_summary(self, results):
        """Build a summary dict from query results"""
        summary = {'income': 0, 'expenses': 0}
        for row in results:
            row_dict = dict(row) if not isinstance(row, dict) else row
            if row_dict.get('transaction_type') == 'income':
                summary['income'] = float(row_dict.get('total') or 0)
            else:
                summary['expenses'] = float(row_dict.get('total') or 0)
        summary['balance'] = summary['income'] - summary['expenses']
        return summary

    def get_monthly_summary(self, user_id, year, month):
        """Get monthly income vs expenses summary"""
        conn = self.get_connection()
        cursor = conn.cursor()
        ph = self._placeholder()

        cursor.execute(f'''
            SELECT transaction_type, SUM(amount) as total
            FROM transactions
            WHERE user_id = {ph}
            AND EXTRACT(YEAR FROM date) = {ph}
            AND EXTRACT(MONTH FROM date) = {ph}
            GROUP BY transaction_type
        ''' if self.use_postgres else f'''
            SELECT transaction_type, SUM(amount) as total
            FROM transactions
            WHERE user_id = {ph}
            AND strftime('%Y', date) = {ph}
            AND strftime('%m', date) = {ph}
            GROUP BY transaction_type
        ''', (user_id, str(year), f"{month:02d}"))

        results = cursor.fetchall()
        conn.close()
        return self._build_summary(results)

    def get_quarterly_summary(self, user_id, year, quarter):
        """Get quarterly income vs expenses summary"""
        import calendar
        start_month = (quarter - 1) * 3 + 1
        end_month = start_month + 2
        last_day = calendar.monthrange(year, end_month)[1]
        start_date = f"{year}-{start_month:02d}-01"
        end_date = f"{year}-{end_month:02d}-{last_day:02d}"
        return self.get_custom_range_summary(user_id, start_date, end_date)

    def get_custom_range_summary(self, user_id, start_date, end_date):
        """Get income vs expenses summary for a custom date range"""
        conn = self.get_connection()
        cursor = conn.cursor()
        ph = self._placeholder()

        cursor.execute(f'''
            SELECT transaction_type, SUM(amount) as total
            FROM transactions
            WHERE user_id = {ph} AND date >= {ph} AND date <= {ph}
            GROUP BY transaction_type
        ''', (user_id, start_date, end_date))

        results = cursor.fetchall()
        conn.close()
        return self._build_summary(results)


if __name__ == '__main__':
    db = FinanceDB()
    print("Database setup complete! Ready to build the app!")
