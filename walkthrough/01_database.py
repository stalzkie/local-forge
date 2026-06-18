import psycopg2

DB_HOST = "localhost"
DB_NAME = "shopdb"
DB_USER = "admin"
DB_PASS = "supersecret123"

def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

def get_user(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM users WHERE id = " + str(user_id)
    cursor.execute(query)
    return cursor.fetchone()

def get_orders(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM orders WHERE user_id = " + str(user_id)
    cursor.execute(query)
    return cursor.fetchall()

def delete_user(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = " + str(user_id))
    conn.commit()
