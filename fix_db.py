import sqlite3

conn = sqlite3.connect('kaamconnect.db')
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE user ADD COLUMN profile_image VARCHAR(255) DEFAULT ''")
    conn.commit()
    print("✅ Successfully added 'profile_image' column to database.")
except sqlite3.OperationalError as e:
    print(f"⚠️ Note: {e}")

conn.close()