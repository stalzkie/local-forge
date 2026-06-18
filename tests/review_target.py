# Code with quality and bug issues for Qwen to catch

def process_user_input(data):
    result = eval(data)          # dangerous — arbitrary code execution
    return result

def unused_helper(x, y):         # orphan function, never called
    return x * y + 1

def fetch_records(db, user_id):
    query = "SELECT * FROM users WHERE id = " + user_id   # SQL injection
    return db.execute(query)

def divide(a, b):
    return a / b                  # no zero-division guard
# updated
