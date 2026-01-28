from flask import Flask, render_template, request, Response, redirect, url_for, send_file, session, jsonify
import sqlite3, os, functools, platform, io, csv, json
import logging

app = Flask(__name__)

# --- CONFIGURATION ---
app.secret_key = 'lab_secret_key_2026'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, 'lab_assets.db')

# Enable logging for debugging
logging.basicConfig(level=logging.DEBUG)

# --- DATABASE HELPER ---
def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

# --- SECURITY ---
def check_auth(username, password):
    return username == 'admin' and password == 'G231_An_Cuan'

def requires_auth(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return Response('Login Required', 401, {'WWW-Authenticate': 'Basic realm="Login"'})
        return f(*args, **kwargs)
    return decorated

# --- DATABASE INITIALIZATION WITH CUSTOM COLUMNS ---
def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Create main inventory table
    cursor.execute('''CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        zone TEXT, 
        item_name TEXT, 
        identifier TEXT, 
        notes TEXT, 
        power_draw_amps REAL DEFAULT 0.0)''')
    
    # Create table to track custom columns
    cursor.execute('''CREATE TABLE IF NOT EXISTS custom_columns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        column_name TEXT UNIQUE,
        column_type TEXT DEFAULT 'TEXT',
        display_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Check if we need to seed data
    cursor.execute('SELECT COUNT(*) FROM inventory')
    if cursor.fetchone()[0] == 0:
        seed_data = [
            ('4', 'ifm O3D313 (1)', '00:02:01:40:2F:75', 'IP 67; 24V DC ToF Sensor', 2.4),
            ('4', 'ifm O3D313 (2)', 'Pending', 'IP 67; 24V DC', 2.4),
            ('4', 'Lucid Helios Flex', '223600163', 'HTP0035-001; FPD-Link III', 0.5),
            ('4', 'Mean Well DR-120-24', 'N/A', '120W 24V; 5A Max Output', 0.0),
            ('4', 'ifm OVP800', 'N/A', '3D processing system', 1.0),
            ('4', 'LF RFID System', 'N/A', 'Reader + 2 Antennas', 0.3)
        ]
        cursor.executemany('INSERT INTO inventory (zone, item_name, identifier, notes, power_draw_amps) VALUES (?,?,?,?,?)', seed_data)
        conn.commit()
    
    # Ensure all custom columns exist in inventory table
    cursor.execute('SELECT column_name, column_type FROM custom_columns')
    custom_cols = cursor.fetchall()
    for col_name, col_type in custom_cols:
        try:
            cursor.execute(f'ALTER TABLE inventory ADD COLUMN {col_name} {col_type}')
        except sqlite3.OperationalError:
            pass  # Column already exists
    
    conn.commit()
    conn.close()

def add_custom_column(column_name, column_type='TEXT', display_name=None):
    """Add a new custom column to the inventory table"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Clean column name for database
    clean_name = ''.join(c for c in column_name.lower() if c.isalnum() or c == '_')
    if not clean_name.startswith('custom_'):
        clean_name = 'custom_' + clean_name
    
    # Use display name for user interface
    if not display_name:
        display_name = column_name
    
    # Check if column already exists in custom_columns table
    cursor.execute('SELECT * FROM custom_columns WHERE column_name = ?', (clean_name,))
    if cursor.fetchone() is None:
        try:
            # Add to custom_columns table
            cursor.execute('INSERT INTO custom_columns (column_name, column_type, display_name) VALUES (?, ?, ?)', 
                          (clean_name, column_type, display_name))
            
            # Add column to inventory table
            try:
                cursor.execute(f'ALTER TABLE inventory ADD COLUMN {clean_name} {column_type}')
                # Initialize with empty values for existing rows
                cursor.execute(f'UPDATE inventory SET {clean_name} = ?', ('',))
                app.logger.info(f"Successfully added column {clean_name} with type {column_type}")
            except sqlite3.OperationalError as e:
                app.logger.warning(f"Column {clean_name} might already exist: {e}")
                # Column might already exist in table but not in custom_columns
            
            conn.commit()
            
        except Exception as e:
            conn.rollback()
            app.logger.error(f"Error adding custom column: {e}")
            raise
    else:
        app.logger.info(f"Column {clean_name} already exists in custom_columns table")
    
    conn.close()
    return clean_name, display_name

def delete_custom_column(column_name):
    """Mark a custom column for deletion (SQLite can't drop columns easily)"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Remove from custom_columns table
    cursor.execute('DELETE FROM custom_columns WHERE column_name = ?', (column_name,))
    
    # Note: In SQLite, we can't actually drop columns
    # Instead, we create a new table without the column and copy data
    # For simplicity, we'll just mark it as inactive in custom_columns
    
    conn.commit()
    conn.close()

def get_all_columns():
    """Get all column information including custom columns"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get custom columns with display names
    cursor.execute('SELECT column_name, display_name, column_type FROM custom_columns ORDER BY created_at')
    custom_cols = cursor.fetchall()
    
    # Get all column names from inventory table
    cursor.execute("PRAGMA table_info(inventory)")
    all_columns = [col[1] for col in cursor.fetchall()]
    
    conn.close()
    
    return custom_cols, all_columns

# --- INITIALIZATION ---
def initialize_app():
    if not os.path.exists(DB_NAME):
        init_db()
    else:
        # Ensure database is up to date
        conn = get_db()
        cursor = conn.cursor()
        
        # Check if custom_columns table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='custom_columns'")
        if not cursor.fetchone():
            # Create custom_columns table if it doesn't exist
            cursor.execute('''CREATE TABLE IF NOT EXISTS custom_columns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                column_name TEXT UNIQUE,
                column_type TEXT DEFAULT 'TEXT',
                display_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            conn.commit()
        
        conn.close()

# --- ROUTES ---

@app.route('/')
@requires_auth
def index():
    initialize_app()
    is_windows = platform.system() == 'Windows'
    conn = get_db()
    
    # Get custom columns with their types
    custom_cols, all_columns = get_all_columns()
    
    # Build SELECT query with all columns (excluding id for display)
    display_columns = [col for col in all_columns if col != 'id']
    select_clause = ', '.join(['id'] + display_columns)
    
    items = conn.execute(f'SELECT {select_clause} FROM inventory ORDER BY zone ASC, item_name ASC').fetchall()
    conn.close()
    
    # Check if we're coming from a save operation
    saved = request.args.get('saved')
    if saved and saved != 'false':
        # Ensure undo toast is shown
        session['show_undo'] = True
    
    return render_template('inventory.html', 
                         items=items, 
                         is_windows=is_windows,
                         custom_columns=custom_cols,  # This will include the custom columns
                         all_columns=display_columns)

@app.route('/add_item', methods=['POST'])
@requires_auth
def add_item():
    conn = get_db()
    cursor = conn.cursor()
    
    # Get custom columns
    custom_cols, all_columns = get_all_columns()
    
    # Prepare data for insertion
    data = {}
    core_fields = ['zone', 'item_name', 'identifier', 'notes', 'power_draw_amps']
    
    # Get core field values
    data['zone'] = request.form.get('zone', '')
    data['item_name'] = request.form.get('name', '')
    data['identifier'] = request.form.get('id_val', '')
    data['notes'] = request.form.get('notes', '')
    data['power_draw_amps'] = float(request.form.get('power', 0.0) or 0.0)
    
    # Get custom column values from form
    for col_name, display_name, col_type in custom_cols:
        value = request.form.get(col_name, '')
        # Convert based on column type
        if col_type in ['INTEGER', 'REAL']:
            try:
                value = float(value) if value else 0.0
            except ValueError:
                value = 0.0
        data[col_name] = value
    
    # Build SQL query
    columns = list(data.keys())
    placeholders = ['?'] * len(columns)
    values = [data[col] for col in columns]
    
    query = f"INSERT INTO inventory ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
    cursor.execute(query, values)
    conn.commit()
    conn.close()
    
    return redirect(url_for('index'))

@app.route('/add_column', methods=['POST'])
@requires_auth
def add_column():
    column_name = request.form.get('column_name', '').strip()
    column_type = request.form.get('column_type', 'TEXT')
    display_name = request.form.get('display_name', column_name)
    
    app.logger.info(f"Adding column: name={column_name}, type={column_type}, display={display_name}")
    
    if column_name:
        try:
            clean_name, display_name = add_custom_column(column_name, column_type, display_name)
            app.logger.info(f"Successfully added column: {clean_name} (display: {display_name})")
        except Exception as e:
            app.logger.error(f"Error in add_column route: {e}")
            return f"Error adding column: {str(e)}", 500
    
    return redirect(url_for('index'))

@app.route('/delete_column/<column_name>')
@requires_auth
def delete_column(column_name):
    delete_custom_column(column_name)
    return redirect(url_for('index'))

@app.route('/update', methods=['POST'])
@requires_auth
def update_item():
    item_id = request.form.get('id')
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get all columns
    custom_cols, all_columns = get_all_columns()
    
    # Filter out 'id' from update columns
    update_columns = [col for col in all_columns if col != 'id']
    
    # Collect update data
    update_data = {}
    for column in update_columns:
        if column in request.form:
            value = request.form.get(column)
            # Convert numeric fields
            if column == 'power_draw_amps':
                try:
                    value = float(value) if value else 0.0
                except ValueError:
                    value = 0.0
            elif column.startswith('custom_'):
                # Check column type for custom columns
                for col_name, display_name, col_type in custom_cols:
                    if col_name == column and col_type in ['INTEGER', 'REAL']:
                        try:
                            value = float(value) if value else 0.0
                        except ValueError:
                            value = 0.0
            update_data[column] = value
    
    # Save current state for undo
    old_row = cursor.execute('SELECT * FROM inventory WHERE id = ?', (item_id,)).fetchone()
    if old_row: 
        session['undo_data'] = dict(old_row)
    
    # Build and execute update query
    if update_data:
        set_clause = ', '.join([f'{k}=?' for k in update_data.keys()])
        values = list(update_data.values()) + [item_id]
        cursor.execute(f'UPDATE inventory SET {set_clause} WHERE id=?', values)
    
    conn.commit()
    conn.close()
    
    session['show_undo'] = True
    
    # Handle AJAX requests
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': 'Item updated successfully'})
    
    return redirect(url_for('index'))

@app.route('/undo')
@requires_auth
def undo():
    data = session.get('undo_data')
    if data:
        conn = get_db()
        cursor = conn.cursor()
        
        # Get all columns except id
        cursor.execute("PRAGMA table_info(inventory)")
        columns = [col[1] for col in cursor.fetchall() if col[1] != 'id']
        
        # Build restore query
        set_clause = ', '.join([f'{k}=?' for k in columns])
        values = [data.get(k, '') for k in columns] + [data['id']]
        
        cursor.execute(f'UPDATE inventory SET {set_clause} WHERE id=?', values)
        conn.commit()
        conn.close()
    
    session.pop('undo_data', None)
    session.pop('show_undo', None)
    return redirect(url_for('index'))

@app.route('/duplicate/<int:id>')
@requires_auth
def duplicate_item(id):
    conn = get_db()
    cursor = conn.cursor()
    
    # Get all columns
    cursor.execute("PRAGMA table_info(inventory)")
    columns = [col[1] for col in cursor.fetchall() if col[1] != 'id']
    
    # Get original item
    orig = cursor.execute(f'SELECT {", ".join(columns)} FROM inventory WHERE id = ?', (id,)).fetchone()
    
    if orig:
        # Prepare data for duplicate
        values = list(orig)
        # Modify item_name to indicate it's a copy
        item_name_index = columns.index('item_name')
        values[item_name_index] = values[item_name_index] + " (Copy)"
        
        # Insert duplicate
        placeholders = ', '.join(['?'] * len(columns))
        cursor.execute(f'INSERT INTO inventory ({", ".join(columns)}) VALUES ({placeholders})', values)
        conn.commit()
    
    conn.close()
    return redirect(url_for('index'))

@app.route('/bulk_update', methods=['POST'])
@requires_auth
def bulk_update():
    ids = request.form.getlist('item_ids')
    new_zone = request.form.get('new_zone')
    
    if ids and new_zone:
        conn = get_db()
        placeholders = ', '.join(['?'] * len(ids))
        conn.execute(f'UPDATE inventory SET zone = ? WHERE id IN ({placeholders})', [new_zone] + ids)
        conn.commit()
        conn.close()
    
    return redirect(url_for('index'))

@app.route('/delete/<int:id>')
@requires_auth
def delete_item(id):
    conn = get_db()
    conn.execute('DELETE FROM inventory WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

# --- DEBUG ROUTES ---
@app.route('/debug/columns')
@requires_auth
def debug_columns():
    """Debug route to see current database schema"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get inventory table schema
    cursor.execute("PRAGMA table_info(inventory)")
    inventory_columns = cursor.fetchall()
    
    # Get custom columns
    cursor.execute('SELECT * FROM custom_columns')
    custom_columns = cursor.fetchall()
    
    conn.close()
    
    return jsonify({
        'inventory_columns': [dict(zip(['cid', 'name', 'type', 'notnull', 'dflt_value', 'pk'], col)) 
                              for col in inventory_columns],
        'custom_columns': [dict(zip(['id', 'column_name', 'column_type', 'display_name', 'created_at'], col)) 
                           for col in custom_columns]
    })

# --- EXPORTS ---
@app.route('/download_backup')
@requires_auth
def download_backup():
    return send_file(DB_NAME, as_attachment=True)

@app.route('/download_csv')
@requires_auth
def download_csv():
    conn = get_db()
    cursor = conn.cursor()
    
    # Get all columns
    cursor.execute("PRAGMA table_info(inventory)")
    columns = [col[1] for col in cursor.fetchall() if col[1] != 'id']
    
    # Get custom column display names
    custom_cols, _ = get_all_columns()
    display_names = {}
    for col_name, display_name, _ in custom_cols:
        display_names[col_name] = display_name
    
    # Build header row with display names
    headers = []
    for col in columns:
        if col in display_names:
            headers.append(display_names[col])
        elif col == 'power_draw_amps':
            headers.append('Power (Amps)')
        elif col == 'item_name':
            headers.append('Item Name')
        else:
            headers.append(col.capitalize())
    
    items = cursor.execute(f'SELECT {", ".join(columns)} FROM inventory').fetchall()
    conn.close()
    
    # Create CSV
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(headers)
    for item in items:
        cw.writerow([item[col] for col in columns])
    
    return Response(si.getvalue(), mimetype="text/csv", 
                   headers={"Content-disposition": "attachment; filename=lab_audit.csv"})

if __name__ == '__main__':
    try:
        initialize_app()
        app.run(debug=True, use_reloader=True)
    except Exception as e:
        app.logger.error(f"Failed to start app: {e}")
        raise
