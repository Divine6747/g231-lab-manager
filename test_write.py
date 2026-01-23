# manual_test.py
import sqlite3
import time

DB_NAME = '/home/imarinventory/g231-lab-manager/lab_assets.db'

print("=== Testing Database Operations ===")

# Test 1: Basic connection
try:
    conn = sqlite3.connect(DB_NAME, timeout=30, check_same_thread=False)
    conn.execute('PRAGMA journal_mode=WAL')
    print("✓ Database connection successful")
except Exception as e:
    print(f"✗ Connection failed: {e}")
    exit(1)

# Test 2: Read operation
try:
    cursor = conn.cursor()
    cursor.execute("SELECT id, zone, item_name FROM inventory LIMIT 3")
    rows = cursor.fetchall()
    print(f"✓ Read successful. Found {len(rows)} rows")
    for row in rows:
        print(f"  - ID {row[0]}: {row[1]} - {row[2]}")
except Exception as e:
    print(f"✗ Read failed: {e}")

# Test 3: Write operation
try:
    test_id = None
    cursor.execute(
        "INSERT INTO inventory (zone, item_name, identifier) VALUES (?, ?, ?)",
        ('TEST', 'Test Item', 'TEST-001')
    )
    conn.commit()
    test_id = cursor.lastrowid
    print(f"✓ Write successful. Created item ID: {test_id}")
except Exception as e:
    print(f"✗ Write failed: {e}")
    conn.rollback()

# Test 4: Update operation
if test_id:
    try:
        cursor.execute(
            "UPDATE inventory SET zone = ? WHERE id = ?",
            ('TEST2', test_id)
        )
        conn.commit()
        print(f"✓ Update successful for ID: {test_id}")
    except Exception as e:
        print(f"✗ Update failed: {e}")
        conn.rollback()

# Test 5: Cleanup
if test_id:
    try:
        cursor.execute("DELETE FROM inventory WHERE id = ?", (test_id,))
        conn.commit()
        print(f"✓ Cleanup successful")
    except Exception as e:
        print(f"✗ Cleanup failed: {e}")

conn.close()
print("=== Test Complete ===")
