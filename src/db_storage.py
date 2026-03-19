import sqlite3
import datetime
import os
from config import config

DATABASE_PATH = None

def get_db_path():
    """Get database file path."""
    global DATABASE_PATH
    if DATABASE_PATH is None:
        base_path = config.get("BASE_PATH", "./data")
        DATABASE_PATH = os.path.join(base_path, "uwash.db")

        # Ensure directory exists
        os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)

    return DATABASE_PATH

def init_database():
    """Initialize database tables."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()

    # Timers table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS timers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            house TEXT NOT NULL,
            machine_name TEXT NOT NULL,
            curr_user TEXT NOT NULL,
            start_time INTEGER NOT NULL,
            end_time INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(house, machine_name)
        )
    ''')

    # House preferences table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS house_preferences (
            user_id TEXT PRIMARY KEY,
            house TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Alarms table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alarms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            curr_user TEXT NOT NULL,
            machine_house_name TEXT NOT NULL,
            end_timestamp INTEGER NOT NULL,
            chat_id TEXT NOT NULL,
            thread_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()
    print(f"[Database] Initialized at {get_db_path()}")

def set_laundry_timer(house: str, machine_name: str, curr_user: str, end_time: datetime.datetime,
                     chat_id: int = None, thread_id: int = None, start_time: datetime.datetime = None):
    """Set a laundry timer."""
    if start_time is None:
        start_time = datetime.datetime.now()

    start_timestamp = int(start_time.timestamp())
    end_timestamp = int(end_time.timestamp())

    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()

    # Insert or replace timer
    cursor.execute('''
        INSERT OR REPLACE INTO timers (house, machine_name, curr_user, start_time, end_time)
        VALUES (?, ?, ?, ?, ?)
    ''', (house, machine_name, curr_user, start_timestamp, end_timestamp))

    # Add alarm if chat_id provided
    if chat_id is not None:
        cursor.execute('''
            INSERT INTO alarms (curr_user, machine_house_name, end_timestamp, chat_id, thread_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (curr_user, f"{house} {machine_name}", end_timestamp, str(chat_id), str(thread_id) if thread_id else None))

    conn.commit()
    conn.close()

def get_laundry_timer(house: str, machine_name: str) -> tuple[str, datetime.datetime, datetime.datetime]:
    """Get laundry timer for a machine."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()

    cursor.execute('''
        SELECT curr_user, start_time, end_time
        FROM timers
        WHERE house = ? AND machine_name = ?
    ''', (house, machine_name))

    result = cursor.fetchone()
    conn.close()

    if result:
        curr_user, start_timestamp, end_timestamp = result
        start_time = datetime.datetime.fromtimestamp(start_timestamp) if start_timestamp else None
        end_time = datetime.datetime.fromtimestamp(end_timestamp)
        return (curr_user, end_time, start_time)

    return ("", None, None)

def set_laundry_timer_sensor(house: str, machine_name: str, end_time: datetime.datetime):
    """Set timer from hardware sensor."""
    set_laundry_timer(house, machine_name, "sensor", end_time)

def clear_laundry_timer(house: str, machine_name: str):
    """Clear a laundry timer."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()

    cursor.execute('DELETE FROM timers WHERE house = ? AND machine_name = ?', (house, machine_name))

    conn.commit()
    conn.close()

def write_house(user_id: int, house: str):
    """Store user's house preference."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()

    cursor.execute('''
        INSERT OR REPLACE INTO house_preferences (user_id, house)
        VALUES (?, ?)
    ''', (str(user_id), house))

    conn.commit()
    conn.close()

def get_house(user_id: int) -> str:
    """Get user's house preference."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()

    cursor.execute('SELECT house FROM house_preferences WHERE user_id = ?', (str(user_id),))
    result = cursor.fetchone()
    conn.close()

    return result[0] if result else None

def check_alarms() -> list[tuple[str, str, str, str]]:
    """Check for due alarms and return them."""
    now_timestamp = int(datetime.datetime.now().timestamp())

    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()

    # Get due alarms
    cursor.execute('''
        SELECT curr_user, chat_id, thread_id, machine_house_name
        FROM alarms
        WHERE end_timestamp <= ?
    ''', (now_timestamp,))

    due_alarms = cursor.fetchall()

    # Remove processed alarms
    if due_alarms:
        cursor.execute('DELETE FROM alarms WHERE end_timestamp <= ?', (now_timestamp,))

    conn.commit()
    conn.close()

    return due_alarms

def read_timers():
    """Initialize database - compatibility function."""
    init_database()

def read_house():
    """Initialize database - compatibility function."""
    init_database()

# Initialize on import
if __name__ != "__main__":
    init_database()