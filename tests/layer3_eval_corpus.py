"""
LocalForge Layer 3 Eval Corpus — 150 labeled diffs
Each entry: id, language, category, should_flag, expected_categories, diff
"""

CORPUS = [

    # ── SQL INJECTION (10 TP + 5 TN) ─────────────────────────────────────────

    {
        "id": "sql_01",
        "language": "python",
        "category": "sql_injection",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/app/db.py b/app/db.py
--- a/app/db.py
+++ b/app/db.py
@@ -12,6 +12,10 @@
 def get_user(conn, username):
-    return conn.execute("SELECT * FROM users WHERE name = ?", (username,)).fetchone()
+    query = "SELECT * FROM users WHERE name = '" + username + "'"
+    return conn.execute(query).fetchone()
''',
    },
    {
        "id": "sql_02",
        "language": "python",
        "category": "sql_injection",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/reports/generator.py b/reports/generator.py
--- a/reports/generator.py
+++ b/reports/generator.py
@@ -34,4 +34,6 @@
 def fetch_report(db, report_id, user_id):
+    sql = f"SELECT * FROM reports WHERE id={report_id} AND owner={user_id}"
+    return db.execute(sql).fetchall()
''',
    },
    {
        "id": "sql_03",
        "language": "javascript",
        "category": "sql_injection",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/src/models/product.js b/src/models/product.js
--- a/src/models/product.js
+++ b/src/models/product.js
@@ -8,4 +8,5 @@
 async function searchProducts(db, term) {
+  const rows = await db.query("SELECT * FROM products WHERE name LIKE '%" + term + "%'");
+  return rows;
 }
''',
    },
    {
        "id": "sql_04",
        "language": "java",
        "category": "sql_injection",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/src/main/java/com/api/UserDao.java b/src/main/java/com/api/UserDao.java
--- a/src/main/java/com/api/UserDao.java
+++ b/src/main/java/com/api/UserDao.java
@@ -21,4 +21,5 @@
     public User findByEmail(Connection conn, String email) throws SQLException {
+        Statement stmt = conn.createStatement();
+        ResultSet rs = stmt.executeQuery("SELECT * FROM users WHERE email = '" + email + "'");
+        return rs.next() ? mapRow(rs) : null;
     }
''',
    },
    {
        "id": "sql_05",
        "language": "go",
        "category": "sql_injection",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/internal/store/users.go b/internal/store/users.go
--- a/internal/store/users.go
+++ b/internal/store/users.go
@@ -18,4 +18,5 @@
 func (s *Store) GetOrder(db *sql.DB, orderID string) (*Order, error) {
+	row := db.QueryRow("SELECT * FROM orders WHERE id = " + orderID)
+	var o Order
+	return &o, row.Scan(&o.ID, &o.Total, &o.Status)
 }
''',
    },
    {
        "id": "sql_06",
        "language": "php",
        "category": "sql_injection",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/api/search.php b/api/search.php
--- a/api/search.php
+++ b/api/search.php
@@ -5,3 +5,5 @@
+$query = "SELECT * FROM products WHERE category = '" . $_GET['cat'] . "'";
+$result = mysqli_query($conn, $query);
''',
    },
    {
        "id": "sql_07",
        "language": "python",
        "category": "sql_injection",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/analytics/queries.py b/analytics/queries.py
--- a/analytics/queries.py
+++ b/analytics/queries.py
@@ -44,4 +44,6 @@
 def get_events(db, start_date, end_date, user_filter):
+    where = f"WHERE created_at BETWEEN '{start_date}' AND '{end_date}'"
+    if user_filter:
+        where += f" AND user_id = '{user_filter}'"
+    return db.execute("SELECT * FROM events " + where).fetchall()
''',
    },
    {
        "id": "sql_08",
        "language": "typescript",
        "category": "sql_injection",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/src/repositories/invoiceRepo.ts b/src/repositories/invoiceRepo.ts
--- a/src/repositories/invoiceRepo.ts
+++ b/src/repositories/invoiceRepo.ts
@@ -22,4 +22,5 @@
   async getByCustomer(customerId: string): Promise<Invoice[]> {
+    const sql = `SELECT * FROM invoices WHERE customer_id = '${customerId}' ORDER BY created_at DESC`;
+    return this.db.raw(sql);
   }
''',
    },
    {
        "id": "sql_09",
        "language": "rust",
        "category": "sql_injection",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/src/db/queries.rs b/src/db/queries.rs
--- a/src/db/queries.rs
+++ b/src/db/queries.rs
@@ -31,4 +31,5 @@
 pub async fn find_session(pool: &PgPool, token: &str) -> Result<Session, sqlx::Error> {
+    let query = format!("SELECT * FROM sessions WHERE token = '{}'", token);
+    sqlx::query_as::<_, Session>(&query).fetch_one(pool).await
 }
''',
    },
    {
        "id": "sql_10",
        "language": "python",
        "category": "sql_injection",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/admin/dashboard.py b/admin/dashboard.py
--- a/admin/dashboard.py
+++ b/admin/dashboard.py
@@ -88,3 +88,5 @@
 def admin_search(db, table, column, value):
+    raw = f"SELECT * FROM {table} WHERE {column} = '{value}'"
+    return db.execute(raw).fetchall()
''',
    },
    # SQL TN
    {
        "id": "sql_tn_01",
        "language": "python",
        "category": "sql_injection",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/app/db.py b/app/db.py
--- a/app/db.py
+++ b/app/db.py
@@ -12,3 +12,4 @@
 def get_user(conn, username):
+    return conn.execute("SELECT * FROM users WHERE name = ?", (username,)).fetchone()
''',
    },
    {
        "id": "sql_tn_02",
        "language": "typescript",
        "category": "sql_injection",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/src/repo/userRepo.ts b/src/repo/userRepo.ts
--- a/src/repo/userRepo.ts
+++ b/src/repo/userRepo.ts
@@ -8,3 +8,5 @@
   async findById(id: number): Promise<User | null> {
+    const result = await this.db.query('SELECT * FROM users WHERE id = $1', [id]);
+    return result.rows[0] ?? null;
   }
''',
    },
    {
        "id": "sql_tn_03",
        "language": "go",
        "category": "sql_injection",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/internal/store/products.go b/internal/store/products.go
--- a/internal/store/products.go
+++ b/internal/store/products.go
@@ -14,3 +14,5 @@
 func (s *Store) ListProducts(db *sql.DB, limit int) ([]Product, error) {
+	rows, err := db.Query("SELECT id, name, price FROM products LIMIT $1", limit)
+	return scanProducts(rows), err
 }
''',
    },
    {
        "id": "sql_tn_04",
        "language": "java",
        "category": "sql_injection",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/src/main/java/com/api/OrderDao.java b/src/main/java/com/api/OrderDao.java
--- a/src/main/java/com/api/OrderDao.java
+++ b/src/main/java/com/api/OrderDao.java
@@ -18,4 +18,5 @@
     public List<Order> findByUser(Connection conn, long userId) throws SQLException {
+        PreparedStatement ps = conn.prepareStatement("SELECT * FROM orders WHERE user_id = ?");
+        ps.setLong(1, userId);
+        return mapOrders(ps.executeQuery());
     }
''',
    },
    {
        "id": "sql_tn_05",
        "language": "rust",
        "category": "sql_injection",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/src/db/orders.rs b/src/db/orders.rs
--- a/src/db/orders.rs
+++ b/src/db/orders.rs
@@ -22,3 +22,4 @@
 pub async fn get_orders(pool: &PgPool, user_id: i64) -> Result<Vec<Order>, sqlx::Error> {
+    sqlx::query_as!(Order, "SELECT * FROM orders WHERE user_id = $1", user_id).fetch_all(pool).await
 }
''',
    },

    # ── COMMAND INJECTION (10 TP + 5 TN) ──────────────────────────────────────

    {
        "id": "cmd_01",
        "language": "python",
        "category": "command_injection",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/utils/processor.py b/utils/processor.py
--- a/utils/processor.py
+++ b/utils/processor.py
@@ -18,3 +18,4 @@
 def convert_file(filename):
+    os.system("convert " + filename + " output.png")
''',
    },
    {
        "id": "cmd_02",
        "language": "python",
        "category": "command_injection",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/tasks/runner.py b/tasks/runner.py
--- a/tasks/runner.py
+++ b/tasks/runner.py
@@ -22,3 +22,4 @@
 def run_report(report_name, output_dir):
+    subprocess.run(f"python3 reports/{report_name}.py > {output_dir}/out.txt", shell=True)
''',
    },
    {
        "id": "cmd_03",
        "language": "javascript",
        "category": "command_injection",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/scripts/deploy.js b/scripts/deploy.js
--- a/scripts/deploy.js
+++ b/scripts/deploy.js
@@ -14,3 +14,5 @@
 function deploy(branch) {
+  const { execSync } = require('child_process');
+  execSync(`git checkout ${branch} && npm run build`);
 }
''',
    },
    {
        "id": "cmd_04",
        "language": "go",
        "category": "command_injection",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/internal/jobs/runner.go b/internal/jobs/runner.go
--- a/internal/jobs/runner.go
+++ b/internal/jobs/runner.go
@@ -28,4 +28,5 @@
 func runJob(jobName string) error {
+	cmd := exec.Command("bash", "-c", "run_job.sh " + jobName)
+	return cmd.Run()
 }
''',
    },
    {
        "id": "cmd_05",
        "language": "python",
        "category": "command_injection",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/api/export.py b/api/export.py
--- a/api/export.py
+++ b/api/export.py
@@ -41,3 +41,5 @@
 def export_csv(table_name):
+    cmd = f"psql -c 'COPY {table_name} TO STDOUT CSV' > /tmp/export.csv"
+    subprocess.call(cmd, shell=True)
''',
    },
    {
        "id": "cmd_06",
        "language": "ruby",
        "category": "command_injection",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/lib/image_processor.rb b/lib/image_processor.rb
--- a/lib/image_processor.rb
+++ b/lib/image_processor.rb
@@ -12,3 +12,4 @@
   def resize(filename, width, height)
+    `convert #{filename} -resize #{width}x#{height} #{filename}`
   end
''',
    },
    {
        "id": "cmd_07",
        "language": "java",
        "category": "command_injection",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/src/main/java/com/tools/ShellRunner.java b/src/main/java/com/tools/ShellRunner.java
--- a/src/main/java/com/tools/ShellRunner.java
+++ b/src/main/java/com/tools/ShellRunner.java
@@ -24,4 +24,5 @@
     public void executeScript(String scriptName) throws IOException {
+        Runtime.getRuntime().exec("bash -c ./scripts/" + scriptName + ".sh");
     }
''',
    },
    {
        "id": "cmd_08",
        "language": "typescript",
        "category": "command_injection",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/src/utils/files.ts b/src/utils/files.ts
--- a/src/utils/files.ts
+++ b/src/utils/files.ts
@@ -9,3 +9,5 @@
 export function compressFile(path: string): void {
+  const { execSync } = require("child_process");
+  execSync("gzip -f " + path);
 }
''',
    },
    {
        "id": "cmd_09",
        "language": "python",
        "category": "command_injection",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/integrations/webhook.py b/integrations/webhook.py
--- a/integrations/webhook.py
+++ b/integrations/webhook.py
@@ -55,4 +55,6 @@
 def handle_ping(payload):
+    host = payload.get("host", "localhost")
+    result = subprocess.check_output("ping -c 1 " + host, shell=True)
+    return result.decode()
''',
    },
    {
        "id": "cmd_10",
        "language": "go",
        "category": "command_injection",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/pkg/utils/shell.go b/pkg/utils/shell.go
--- a/pkg/utils/shell.go
+++ b/pkg/utils/shell.go
@@ -11,4 +11,5 @@
 func RunUserScript(scriptPath string, args string) (string, error) {
+	out, err := exec.Command("sh", "-c", scriptPath+" "+args).Output()
+	return string(out), err
 }
''',
    },
    # CMD TN
    {
        "id": "cmd_tn_01",
        "language": "python",
        "category": "command_injection",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/utils/processor.py b/utils/processor.py
--- a/utils/processor.py
+++ b/utils/processor.py
@@ -18,3 +18,4 @@
 def convert_file(filename):
+    subprocess.run(["convert", filename, "output.png"], check=True)
''',
    },
    {
        "id": "cmd_tn_02",
        "language": "go",
        "category": "command_injection",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/internal/jobs/runner.go b/internal/jobs/runner.go
--- a/internal/jobs/runner.go
+++ b/internal/jobs/runner.go
@@ -28,4 +28,5 @@
 func runJob(jobName string) error {
+	cmd := exec.Command("run_job.sh", jobName)
+	return cmd.Run()
 }
''',
    },
    {
        "id": "cmd_tn_03",
        "language": "javascript",
        "category": "command_injection",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/scripts/build.js b/scripts/build.js
--- a/scripts/build.js
+++ b/scripts/build.js
@@ -6,3 +6,5 @@
 function build() {
+  const { spawnSync } = require('child_process');
+  spawnSync('npm', ['run', 'build'], { stdio: 'inherit' });
 }
''',
    },
    {
        "id": "cmd_tn_04",
        "language": "python",
        "category": "command_injection",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/tasks/compress.py b/tasks/compress.py
--- a/tasks/compress.py
+++ b/tasks/compress.py
@@ -8,3 +8,4 @@
 def compress(path):
+    subprocess.run(["gzip", "-f", path], check=True)
''',
    },
    {
        "id": "cmd_tn_05",
        "language": "ruby",
        "category": "command_injection",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/lib/runner.rb b/lib/runner.rb
--- a/lib/runner.rb
+++ b/lib/runner.rb
@@ -7,3 +7,4 @@
   def run_tests
+    system("bundle", "exec", "rspec", "--format", "progress")
   end
''',
    },

    # ── XSS / OUTPUT INJECTION (8 TP + 4 TN) ─────────────────────────────────

    {
        "id": "xss_01",
        "language": "javascript",
        "category": "xss",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/src/components/Comment.jsx b/src/components/Comment.jsx
--- a/src/components/Comment.jsx
+++ b/src/components/Comment.jsx
@@ -14,3 +14,4 @@
 export function Comment({ text }) {
+  return <div dangerouslySetInnerHTML={{ __html: text }} />;
 }
''',
    },
    {
        "id": "xss_02",
        "language": "javascript",
        "category": "xss",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/public/search.js b/public/search.js
--- a/public/search.js
+++ b/public/search.js
@@ -22,3 +22,5 @@
 function renderResults(query, results) {
+  document.getElementById("header").innerHTML = "Results for: " + query;
+  document.getElementById("results").innerHTML = results.map(r => r.title).join("<br>");
 }
''',
    },
    {
        "id": "xss_03",
        "language": "python",
        "category": "xss",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/app/views.py b/app/views.py
--- a/app/views.py
+++ b/app/views.py
@@ -34,4 +34,5 @@
 def user_profile(request, username):
+    html = f"<h1>Profile: {username}</h1>"
+    return HttpResponse(html)
''',
    },
    {
        "id": "xss_04",
        "language": "php",
        "category": "xss",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/pages/profile.php b/pages/profile.php
--- a/pages/profile.php
+++ b/pages/profile.php
@@ -8,3 +8,4 @@
+echo "<p>Welcome, " . $_GET['name'] . "!</p>";
''',
    },
    {
        "id": "xss_05",
        "language": "typescript",
        "category": "xss",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/src/utils/render.ts b/src/utils/render.ts
--- a/src/utils/render.ts
+++ b/src/utils/render.ts
@@ -18,3 +18,5 @@
 export function renderMessage(container: HTMLElement, msg: string): void {
+  container.innerHTML = msg;
 }
''',
    },
    {
        "id": "xss_06",
        "language": "javascript",
        "category": "xss",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/src/admin/logs.js b/src/admin/logs.js
--- a/src/admin/logs.js
+++ b/src/admin/logs.js
@@ -31,3 +31,5 @@
 function displayLogs(logs) {
+  const logDiv = document.querySelector("#log-output");
+  logDiv.innerHTML = logs.map(l => `<span>${l.message}</span>`).join("");
 }
''',
    },
    {
        "id": "xss_07",
        "language": "python",
        "category": "xss",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/api/templates.py b/api/templates.py
--- a/api/templates.py
+++ b/api/templates.py
@@ -14,3 +14,5 @@
 def render_notification(user_msg):
+    template = "<div class='alert'>" + user_msg + "</div>"
+    return mark_safe(template)
''',
    },
    {
        "id": "xss_08",
        "language": "java",
        "category": "xss",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/src/main/java/com/web/SearchServlet.java b/src/main/java/com/web/SearchServlet.java
--- a/src/main/java/com/web/SearchServlet.java
+++ b/src/main/java/com/web/SearchServlet.java
@@ -28,4 +28,5 @@
     protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws IOException {
+        String q = req.getParameter("q");
+        resp.getWriter().write("<p>Search results for: " + q + "</p>");
     }
''',
    },
    # XSS TN
    {
        "id": "xss_tn_01",
        "language": "typescript",
        "category": "xss",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/src/components/Message.tsx b/src/components/Message.tsx
--- a/src/components/Message.tsx
+++ b/src/components/Message.tsx
@@ -8,3 +8,4 @@
 export function Message({ text }: { text: string }) {
+  return <div>{text}</div>;
 }
''',
    },
    {
        "id": "xss_tn_02",
        "language": "python",
        "category": "xss",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/app/views.py b/app/views.py
--- a/app/views.py
+++ b/app/views.py
@@ -34,4 +34,5 @@
 def user_profile(request, username):
+    return render(request, "profile.html", {"username": escape(username)})
''',
    },
    {
        "id": "xss_tn_03",
        "language": "javascript",
        "category": "xss",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/src/utils/dom.js b/src/utils/dom.js
--- a/src/utils/dom.js
+++ b/src/utils/dom.js
@@ -5,3 +5,5 @@
 function renderMessage(container, msg) {
+  const span = document.createElement("span");
+  span.textContent = msg;
+  container.appendChild(span);
 }
''',
    },
    {
        "id": "xss_tn_04",
        "language": "java",
        "category": "xss",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/src/main/java/com/web/SearchServlet.java b/src/main/java/com/web/SearchServlet.java
--- a/src/main/java/com/web/SearchServlet.java
+++ b/src/main/java/com/web/SearchServlet.java
@@ -28,4 +28,6 @@
     protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws IOException {
+        String q = StringEscapeUtils.escapeHtml4(req.getParameter("q"));
+        resp.getWriter().write("<p>Search results for: " + q + "</p>");
     }
''',
    },

    # ── HARDCODED SECRETS — non-regex (8 TP + 4 TN) ──────────────────────────

    {
        "id": "secret_01",
        "language": "python",
        "category": "hardcoded_secret",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/config/settings.py b/config/settings.py
--- a/config/settings.py
+++ b/config/settings.py
@@ -14,3 +14,5 @@
+DB_CONFIG = {
+    "host": "prod-db.internal",
+    "password": "Wj7#mK2$pL9qR",
+}
''',
    },
    {
        "id": "secret_02",
        "language": "javascript",
        "category": "hardcoded_secret",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/src/services/payment.js b/src/services/payment.js
--- a/src/services/payment.js
+++ b/src/services/payment.js
@@ -8,3 +8,5 @@
+const STRIPE_SECRET = "sk_live_" + "4eC39HqLyjWDarjtT1zdp7dc";
+const stripe = new Stripe(STRIPE_SECRET);
''',
    },
    {
        "id": "secret_03",
        "language": "go",
        "category": "hardcoded_secret",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/internal/auth/jwt.go b/internal/auth/jwt.go
--- a/internal/auth/jwt.go
+++ b/internal/auth/jwt.go
@@ -11,3 +11,4 @@
+const jwtSecret = "my-super-secret-signing-key-dont-share"
''',
    },
    {
        "id": "secret_04",
        "language": "java",
        "category": "hardcoded_secret",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/src/main/java/com/app/Config.java b/src/main/java/com/app/Config.java
--- a/src/main/java/com/app/Config.java
+++ b/src/main/java/com/app/Config.java
@@ -5,3 +5,5 @@
 public class Config {
+    public static final String ENCRYPTION_KEY = "AES256Key-32Characters1234567890";
+    public static final String DB_PASSWORD     = "Prod@2024#Secure!";
 }
''',
    },
    {
        "id": "secret_05",
        "language": "typescript",
        "category": "hardcoded_secret",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/src/config/auth.ts b/src/config/auth.ts
--- a/src/config/auth.ts
+++ b/src/config/auth.ts
@@ -3,3 +3,5 @@
+export const AUTH_CONFIG = {
+  jwtSecret: "f3cfe9ed8fae309f02079dbf",
+  refreshSecret: "a7b3c2d1e0f9g8h7",
+};
''',
    },
    {
        "id": "secret_06",
        "language": "python",
        "category": "hardcoded_secret",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/integrations/smtp.py b/integrations/smtp.py
--- a/integrations/smtp.py
+++ b/integrations/smtp.py
@@ -18,4 +18,6 @@
 def get_smtp_client():
+    return smtplib.SMTP_SSL("smtp.gmail.com", 465)
+    # TODO: move these out
+    USERNAME = "noreply@company.com"
+    PASSWORD = "CompanyEmail2024!"
''',
    },
    {
        "id": "secret_07",
        "language": "rust",
        "category": "hardcoded_secret",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/src/config.rs b/src/config.rs
--- a/src/config.rs
+++ b/src/config.rs
@@ -8,3 +8,5 @@
+pub const WEBHOOK_SECRET: &str = "whsec_live_oiJKHjk23nMzPqr8";
+pub const INTERNAL_API_KEY: &str = "int_prod_9fH2kL7mN3pQ";
''',
    },
    {
        "id": "secret_08",
        "language": "swift",
        "category": "hardcoded_secret",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/LocalForgeApp/Config.swift b/LocalForgeApp/Config.swift
--- a/LocalForgeApp/Config.swift
+++ b/LocalForgeApp/Config.swift
@@ -4,3 +4,5 @@
 struct APIConfig {
+    static let apiKey    = "prod_live_xK9mN2pQ7rS4tU1v"
+    static let secretKey = "sk_prod_ABCDEFGhijklmnop"
 }
''',
    },
    # SECRET TN
    {
        "id": "secret_tn_01",
        "language": "python",
        "category": "hardcoded_secret",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/config/settings.py b/config/settings.py
--- a/config/settings.py
+++ b/config/settings.py
@@ -14,3 +14,5 @@
+DB_CONFIG = {
+    "host": os.environ.get("DB_HOST", "localhost"),
+    "password": os.environ["DB_PASSWORD"],
+}
''',
    },
    {
        "id": "secret_tn_02",
        "language": "go",
        "category": "hardcoded_secret",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/internal/auth/jwt.go b/internal/auth/jwt.go
--- a/internal/auth/jwt.go
+++ b/internal/auth/jwt.go
@@ -11,3 +11,4 @@
+var jwtSecret = []byte(os.Getenv("JWT_SECRET"))
''',
    },
    {
        "id": "secret_tn_03",
        "language": "typescript",
        "category": "hardcoded_secret",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/src/config/auth.ts b/src/config/auth.ts
--- a/src/config/auth.ts
+++ b/src/config/auth.ts
@@ -3,3 +3,5 @@
+export const AUTH_CONFIG = {
+  jwtSecret: process.env.JWT_SECRET!,
+  refreshSecret: process.env.REFRESH_SECRET!,
+};
''',
    },
    {
        "id": "secret_tn_04",
        "language": "rust",
        "category": "hardcoded_secret",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/src/config.rs b/src/config.rs
--- a/src/config.rs
+++ b/src/config.rs
@@ -8,3 +8,5 @@
+pub fn webhook_secret() -> String {
+    std::env::var("WEBHOOK_SECRET").expect("WEBHOOK_SECRET must be set")
+}
''',
    },

    # ── DISABLED TLS / INSECURE CRYPTO (8 TP + 4 TN) ─────────────────────────

    {
        "id": "tls_01",
        "language": "python",
        "category": "insecure_tls",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/api/client.py b/api/client.py
--- a/api/client.py
+++ b/api/client.py
@@ -22,3 +22,4 @@
 def fetch_data(url):
+    return requests.get(url, verify=False).json()
''',
    },
    {
        "id": "tls_02",
        "language": "python",
        "category": "insecure_tls",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/utils/crypto.py b/utils/crypto.py
--- a/utils/crypto.py
+++ b/utils/crypto.py
@@ -6,3 +6,5 @@
 def hash_password(password):
+    return hashlib.md5(password.encode()).hexdigest()
''',
    },
    {
        "id": "tls_03",
        "language": "java",
        "category": "insecure_tls",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/src/main/java/com/net/HttpClient.java b/src/main/java/com/net/HttpClient.java
--- a/src/main/java/com/net/HttpClient.java
+++ b/src/main/java/com/net/HttpClient.java
@@ -18,5 +18,8 @@
     private SSLContext createInsecureContext() throws Exception {
+        TrustManager[] trustAll = new TrustManager[]{ new X509TrustManager() {
+            public void checkClientTrusted(X509Certificate[] c, String a) {}
+            public void checkServerTrusted(X509Certificate[] c, String a) {}
+            public X509Certificate[] getAcceptedIssuers() { return null; }
+        }};
+        SSLContext ctx = SSLContext.getInstance("TLS");
+        ctx.init(null, trustAll, new java.security.SecureRandom());
+        return ctx;
     }
''',
    },
    {
        "id": "tls_04",
        "language": "go",
        "category": "insecure_tls",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/internal/httpclient/client.go b/internal/httpclient/client.go
--- a/internal/httpclient/client.go
+++ b/internal/httpclient/client.go
@@ -14,4 +14,6 @@
 func NewClient() *http.Client {
+    tr := &http.Transport{
+        TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
+    }
+    return &http.Client{Transport: tr}
 }
''',
    },
    {
        "id": "tls_05",
        "language": "javascript",
        "category": "insecure_tls",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/src/api/client.js b/src/api/client.js
--- a/src/api/client.js
+++ b/src/api/client.js
@@ -8,3 +8,5 @@
 function makeRequest(url, data) {
+  process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";
+  return fetch(url, { method: "POST", body: JSON.stringify(data) });
 }
''',
    },
    {
        "id": "tls_06",
        "language": "python",
        "category": "insecure_tls",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/crypto/hashing.py b/crypto/hashing.py
--- a/crypto/hashing.py
+++ b/crypto/hashing.py
@@ -9,3 +9,5 @@
 def generate_token(user_id):
+    raw = str(user_id) + "salt"
+    return hashlib.sha1(raw.encode()).hexdigest()
''',
    },
    {
        "id": "tls_07",
        "language": "rust",
        "category": "insecure_tls",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/src/http/client.rs b/src/http/client.rs
--- a/src/http/client.rs
+++ b/src/http/client.rs
@@ -14,4 +14,6 @@
 pub fn build_client() -> reqwest::Client {
+    reqwest::Client::builder()
+        .danger_accept_invalid_certs(true)
+        .build()
+        .unwrap()
 }
''',
    },
    {
        "id": "tls_08",
        "language": "python",
        "category": "insecure_tls",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/services/crypto_util.py b/services/crypto_util.py
--- a/services/crypto_util.py
+++ b/services/crypto_util.py
@@ -8,5 +8,7 @@
 def encrypt_payload(data, key):
+    cipher = DES.new(key[:8], DES.MODE_ECB)
+    padded = data + (8 - len(data) % 8) * chr(8 - len(data) % 8)
+    return cipher.encrypt(padded.encode())
''',
    },
    # TLS TN
    {
        "id": "tls_tn_01",
        "language": "python",
        "category": "insecure_tls",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/api/client.py b/api/client.py
--- a/api/client.py
+++ b/api/client.py
@@ -22,3 +22,4 @@
 def fetch_data(url):
+    return requests.get(url, verify="/etc/ssl/certs/ca-bundle.crt").json()
''',
    },
    {
        "id": "tls_tn_02",
        "language": "go",
        "category": "insecure_tls",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/internal/httpclient/client.go b/internal/httpclient/client.go
--- a/internal/httpclient/client.go
+++ b/internal/httpclient/client.go
@@ -14,4 +14,5 @@
 func NewClient() *http.Client {
+    return &http.Client{Timeout: 30 * time.Second}
 }
''',
    },
    {
        "id": "tls_tn_03",
        "language": "python",
        "category": "insecure_tls",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/crypto/hashing.py b/crypto/hashing.py
--- a/crypto/hashing.py
+++ b/crypto/hashing.py
@@ -9,3 +9,5 @@
 def hash_password(password):
+    salt = bcrypt.gensalt()
+    return bcrypt.hashpw(password.encode(), salt)
''',
    },
    {
        "id": "tls_tn_04",
        "language": "rust",
        "category": "insecure_tls",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/src/http/client.rs b/src/http/client.rs
--- a/src/http/client.rs
+++ b/src/http/client.rs
@@ -14,4 +14,5 @@
 pub fn build_client() -> reqwest::Client {
+    reqwest::Client::builder().timeout(Duration::from_secs(30)).build().unwrap()
 }
''',
    },

    # ── PATH TRAVERSAL (6 TP + 3 TN) ─────────────────────────────────────────

    {
        "id": "path_01",
        "language": "python",
        "category": "path_traversal",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/api/files.py b/api/files.py
--- a/api/files.py
+++ b/api/files.py
@@ -14,3 +14,5 @@
 def download_file(request, filename):
+    path = "/var/uploads/" + filename
+    return open(path, "rb").read()
''',
    },
    {
        "id": "path_02",
        "language": "go",
        "category": "path_traversal",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/handlers/files.go b/handlers/files.go
--- a/handlers/files.go
+++ b/handlers/files.go
@@ -22,4 +22,6 @@
 func ServeFile(w http.ResponseWriter, r *http.Request) {
+    name := r.URL.Query().Get("name")
+    data, _ := os.ReadFile("/srv/files/" + name)
+    w.Write(data)
 }
''',
    },
    {
        "id": "path_03",
        "language": "java",
        "category": "path_traversal",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/src/main/java/com/api/FileController.java b/src/main/java/com/api/FileController.java
--- a/src/main/java/com/api/FileController.java
+++ b/src/main/java/com/api/FileController.java
@@ -18,4 +18,5 @@
     public byte[] getFile(@RequestParam String filename) throws IOException {
+        File f = new File("/var/app/uploads/" + filename);
+        return Files.readAllBytes(f.toPath());
     }
''',
    },
    {
        "id": "path_04",
        "language": "javascript",
        "category": "path_traversal",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/routes/files.js b/routes/files.js
--- a/routes/files.js
+++ b/routes/files.js
@@ -11,4 +11,5 @@
 router.get('/download', (req, res) => {
+  const filePath = path.join(__dirname, 'uploads', req.query.file);
+  res.sendFile(filePath);
 });
''',
    },
    {
        "id": "path_05",
        "language": "php",
        "category": "path_traversal",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/download.php b/download.php
--- a/download.php
+++ b/download.php
@@ -3,3 +3,5 @@
+$file = "/var/www/uploads/" . $_GET['file'];
+readfile($file);
''',
    },
    {
        "id": "path_06",
        "language": "python",
        "category": "path_traversal",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/app/storage.py b/app/storage.py
--- a/app/storage.py
+++ b/app/storage.py
@@ -28,4 +28,6 @@
 def read_template(template_name):
+    base = "/app/templates/"
+    with open(base + template_name) as f:
+        return f.read()
''',
    },
    # PATH TN
    {
        "id": "path_tn_01",
        "language": "python",
        "category": "path_traversal",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/api/files.py b/api/files.py
--- a/api/files.py
+++ b/api/files.py
@@ -14,5 +14,8 @@
 def download_file(request, filename):
+    safe = os.path.basename(filename)
+    path = os.path.join("/var/uploads", safe)
+    if not path.startswith("/var/uploads"):
+        raise PermissionError("Invalid path")
+    return open(path, "rb").read()
''',
    },
    {
        "id": "path_tn_02",
        "language": "go",
        "category": "path_traversal",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/handlers/files.go b/handlers/files.go
--- a/handlers/files.go
+++ b/handlers/files.go
@@ -22,6 +22,9 @@
 func ServeFile(w http.ResponseWriter, r *http.Request) {
+    name := filepath.Base(r.URL.Query().Get("name"))
+    safe := filepath.Join("/srv/files", name)
+    if !strings.HasPrefix(safe, "/srv/files/") {
+        http.Error(w, "forbidden", http.StatusForbidden)
+        return
+    }
+    http.ServeFile(w, r, safe)
 }
''',
    },
    {
        "id": "path_tn_03",
        "language": "java",
        "category": "path_traversal",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/src/main/java/com/api/FileController.java b/src/main/java/com/api/FileController.java
--- a/src/main/java/com/api/FileController.java
+++ b/src/main/java/com/api/FileController.java
@@ -18,5 +18,7 @@
     public byte[] getFile(@RequestParam String filename) throws IOException {
+        Path base = Paths.get("/var/app/uploads");
+        Path target = base.resolve(filename).normalize();
+        if (!target.startsWith(base)) throw new SecurityException("Path traversal detected");
+        return Files.readAllBytes(target);
     }
''',
    },

    # ── UNSAFE DESERIALIZATION (6 TP + 3 TN) ─────────────────────────────────

    {
        "id": "deser_01",
        "language": "python",
        "category": "unsafe_deserialization",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/cache/loader.py b/cache/loader.py
--- a/cache/loader.py
+++ b/cache/loader.py
@@ -11,3 +11,4 @@
 def load_session(data):
+    return pickle.loads(data)
''',
    },
    {
        "id": "deser_02",
        "language": "python",
        "category": "unsafe_deserialization",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/api/rpc.py b/api/rpc.py
--- a/api/rpc.py
+++ b/api/rpc.py
@@ -22,3 +22,5 @@
 def handle_request(raw_body):
+    payload = yaml.load(raw_body)
+    return dispatch(payload)
''',
    },
    {
        "id": "deser_03",
        "language": "java",
        "category": "unsafe_deserialization",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/src/main/java/com/cache/SessionCache.java b/src/main/java/com/cache/SessionCache.java
--- a/src/main/java/com/cache/SessionCache.java
+++ b/src/main/java/com/cache/SessionCache.java
@@ -18,4 +18,6 @@
     public Object deserialize(byte[] data) throws Exception {
+        ObjectInputStream ois = new ObjectInputStream(new ByteArrayInputStream(data));
+        return ois.readObject();
     }
''',
    },
    {
        "id": "deser_04",
        "language": "ruby",
        "category": "unsafe_deserialization",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/lib/session.rb b/lib/session.rb
--- a/lib/session.rb
+++ b/lib/session.rb
@@ -8,3 +8,4 @@
   def load_session(cookie)
+    Marshal.load(Base64.decode64(cookie))
   end
''',
    },
    {
        "id": "deser_05",
        "language": "python",
        "category": "unsafe_deserialization",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/workers/task.py b/workers/task.py
--- a/workers/task.py
+++ b/workers/task.py
@@ -31,3 +31,5 @@
 def process_task(message):
+    task = eval(message["code"])
+    return task()
''',
    },
    {
        "id": "deser_06",
        "language": "javascript",
        "category": "unsafe_deserialization",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/src/utils/config.js b/src/utils/config.js
--- a/src/utils/config.js
+++ b/src/utils/config.js
@@ -14,3 +14,5 @@
 function loadConfig(data) {
+  const config = eval("(" + data + ")");
+  return config;
 }
''',
    },
    # DESER TN
    {
        "id": "deser_tn_01",
        "language": "python",
        "category": "unsafe_deserialization",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/cache/loader.py b/cache/loader.py
--- a/cache/loader.py
+++ b/cache/loader.py
@@ -11,3 +11,4 @@
 def load_session(data):
+    return json.loads(data)
''',
    },
    {
        "id": "deser_tn_02",
        "language": "python",
        "category": "unsafe_deserialization",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/api/rpc.py b/api/rpc.py
--- a/api/rpc.py
+++ b/api/rpc.py
@@ -22,3 +22,5 @@
 def handle_request(raw_body):
+    payload = yaml.safe_load(raw_body)
+    return dispatch(payload)
''',
    },
    {
        "id": "deser_tn_03",
        "language": "java",
        "category": "unsafe_deserialization",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/src/main/java/com/cache/SessionCache.java b/src/main/java/com/cache/SessionCache.java
--- a/src/main/java/com/cache/SessionCache.java
+++ b/src/main/java/com/cache/SessionCache.java
@@ -18,4 +18,5 @@
     public SessionData deserialize(String json) {
+        return new ObjectMapper().readValue(json, SessionData.class);
     }
''',
    },

    # ── RACE CONDITIONS (6 TP + 3 TN) ────────────────────────────────────────

    {
        "id": "race_01",
        "language": "python",
        "category": "race_condition",
        "should_flag": True,
        "expected_categories": ["bug_risk"],
        "diff": '''\
diff --git a/workers/counter.py b/workers/counter.py
--- a/workers/counter.py
+++ b/workers/counter.py
@@ -8,5 +8,8 @@
+counter = 0
+
 def increment():
+    global counter
+    counter += 1
+    return counter
''',
    },
    {
        "id": "race_02",
        "language": "go",
        "category": "race_condition",
        "should_flag": True,
        "expected_categories": ["bug_risk"],
        "diff": '''\
diff --git a/internal/cache/store.go b/internal/cache/store.go
--- a/internal/cache/store.go
+++ b/internal/cache/store.go
@@ -12,6 +12,9 @@
+var cache = map[string]string{}
+
 func Set(key, value string) {
+    cache[key] = value
 }
+
 func Get(key string) string {
+    return cache[key]
 }
''',
    },
    {
        "id": "race_03",
        "language": "java",
        "category": "race_condition",
        "should_flag": True,
        "expected_categories": ["bug_risk"],
        "diff": '''\
diff --git a/src/main/java/com/api/RequestCounter.java b/src/main/java/com/api/RequestCounter.java
--- a/src/main/java/com/api/RequestCounter.java
+++ b/src/main/java/com/api/RequestCounter.java
@@ -6,5 +6,7 @@
 public class RequestCounter {
+    private static int count = 0;
+
+    public static void increment() {
+        count++;
+    }
 }
''',
    },
    {
        "id": "race_04",
        "language": "rust",
        "category": "race_condition",
        "should_flag": True,
        "expected_categories": ["bug_risk"],
        "diff": '''\
diff --git a/src/cache.rs b/src/cache.rs
--- a/src/cache.rs
+++ b/src/cache.rs
@@ -6,6 +6,9 @@
+use std::collections::HashMap;
+use std::sync::Arc;
+
+pub fn new_cache() -> Arc<HashMap<String, String>> {
+    Arc::new(HashMap::new())
+}
''',
    },
    {
        "id": "race_05",
        "language": "python",
        "category": "race_condition",
        "should_flag": True,
        "expected_categories": ["bug_risk"],
        "diff": '''\
diff --git a/api/rate_limiter.py b/api/rate_limiter.py
--- a/api/rate_limiter.py
+++ b/api/rate_limiter.py
@@ -14,6 +14,9 @@
+request_counts = {}
+
 def check_rate_limit(user_id):
+    count = request_counts.get(user_id, 0)
+    if count >= 100:
+        raise RateLimitError()
+    request_counts[user_id] = count + 1
''',
    },
    {
        "id": "race_06",
        "language": "go",
        "category": "race_condition",
        "should_flag": True,
        "expected_categories": ["bug_risk"],
        "diff": '''\
diff --git a/internal/jobs/pool.go b/internal/jobs/pool.go
--- a/internal/jobs/pool.go
+++ b/internal/jobs/pool.go
@@ -18,6 +18,9 @@
+var activeJobs int
+
 func startJob(fn func()) {
+    activeJobs++
+    go func() {
+        fn()
+        activeJobs--
+    }()
 }
''',
    },
    # RACE TN
    {
        "id": "race_tn_01",
        "language": "go",
        "category": "race_condition",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/internal/cache/store.go b/internal/cache/store.go
--- a/internal/cache/store.go
+++ b/internal/cache/store.go
@@ -12,6 +12,10 @@
+var (
+    mu    sync.RWMutex
+    cache = map[string]string{}
+)
+
 func Set(key, value string) {
+    mu.Lock()
+    defer mu.Unlock()
+    cache[key] = value
 }
''',
    },
    {
        "id": "race_tn_02",
        "language": "java",
        "category": "race_condition",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/src/main/java/com/api/RequestCounter.java b/src/main/java/com/api/RequestCounter.java
--- a/src/main/java/com/api/RequestCounter.java
+++ b/src/main/java/com/api/RequestCounter.java
@@ -6,5 +6,6 @@
 public class RequestCounter {
+    private static final AtomicInteger count = new AtomicInteger(0);
+    public static int increment() { return count.incrementAndGet(); }
 }
''',
    },
    {
        "id": "race_tn_03",
        "language": "rust",
        "category": "race_condition",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/src/cache.rs b/src/cache.rs
--- a/src/cache.rs
+++ b/src/cache.rs
@@ -6,5 +6,7 @@
+use std::collections::HashMap;
+use std::sync::{Arc, RwLock};
+
+pub fn new_cache() -> Arc<RwLock<HashMap<String, String>>> {
+    Arc::new(RwLock::new(HashMap::new()))
+}
''',
    },

    # ── OFF-BY-ONE / LOGIC BUGS (8 TP + 4 TN) ────────────────────────────────

    {
        "id": "logic_01",
        "language": "python",
        "category": "logic_bug",
        "should_flag": True,
        "expected_categories": ["bug_risk"],
        "diff": '''\
diff --git a/utils/pagination.py b/utils/pagination.py
--- a/utils/pagination.py
+++ b/utils/pagination.py
@@ -8,4 +8,6 @@
 def get_page(items, page, page_size):
+    start = page * page_size
+    end   = start + page_size + 1
+    return items[start:end]
''',
    },
    {
        "id": "logic_02",
        "language": "javascript",
        "category": "logic_bug",
        "should_flag": True,
        "expected_categories": ["bug_risk"],
        "diff": '''\
diff --git a/src/utils/array.js b/src/utils/array.js
--- a/src/utils/array.js
+++ b/src/utils/array.js
@@ -6,4 +6,6 @@
 function lastN(arr, n) {
+  const result = [];
+  for (let i = arr.length - n; i <= arr.length; i++) {
+    result.push(arr[i]);
+  }
+  return result;
 }
''',
    },
    {
        "id": "logic_03",
        "language": "go",
        "category": "logic_bug",
        "should_flag": True,
        "expected_categories": ["bug_risk"],
        "diff": '''\
diff --git a/pkg/retry/backoff.go b/pkg/retry/backoff.go
--- a/pkg/retry/backoff.go
+++ b/pkg/retry/backoff.go
@@ -14,5 +14,7 @@
 func Retry(fn func() error, maxAttempts int) error {
+    for i := 0; i <= maxAttempts; i++ {
+        if err := fn(); err == nil {
+            return nil
+        }
+    }
+    return fmt.Errorf("failed after %d attempts", maxAttempts)
 }
''',
    },
    {
        "id": "logic_04",
        "language": "python",
        "category": "logic_bug",
        "should_flag": True,
        "expected_categories": ["bug_risk"],
        "diff": '''\
diff --git a/auth/permissions.py b/auth/permissions.py
--- a/auth/permissions.py
+++ b/auth/permissions.py
@@ -18,4 +18,6 @@
 def is_admin(user):
+    if not user.role != "admin":
+        return True
+    return False
''',
    },
    {
        "id": "logic_05",
        "language": "rust",
        "category": "logic_bug",
        "should_flag": True,
        "expected_categories": ["bug_risk"],
        "diff": '''\
diff --git a/src/utils/slice.rs b/src/utils/slice.rs
--- a/src/utils/slice.rs
+++ b/src/utils/slice.rs
@@ -8,4 +8,6 @@
 pub fn chunk_vec<T: Clone>(v: &[T], size: usize) -> Vec<Vec<T>> {
+    (0..=v.len() / size)
+        .map(|i| v[i * size..(i + 1) * size].to_vec())
+        .collect()
 }
''',
    },
    {
        "id": "logic_06",
        "language": "java",
        "category": "logic_bug",
        "should_flag": True,
        "expected_categories": ["bug_risk"],
        "diff": '''\
diff --git a/src/main/java/com/api/Validator.java b/src/main/java/com/api/Validator.java
--- a/src/main/java/com/api/Validator.java
+++ b/src/main/java/com/api/Validator.java
@@ -14,4 +14,6 @@
     public boolean isValidAge(int age) {
+        if (age < 0 & age > 150) {
+            return false;
+        }
+        return true;
     }
''',
    },
    {
        "id": "logic_07",
        "language": "typescript",
        "category": "logic_bug",
        "should_flag": True,
        "expected_categories": ["bug_risk"],
        "diff": '''\
diff --git a/src/utils/date.ts b/src/utils/date.ts
--- a/src/utils/date.ts
+++ b/src/utils/date.ts
@@ -8,4 +8,6 @@
 export function isExpired(expiryDate: Date): boolean {
+  const now = new Date();
+  return now.getTime() < expiryDate.getTime();
 }
''',
    },
    {
        "id": "logic_08",
        "language": "python",
        "category": "logic_bug",
        "should_flag": True,
        "expected_categories": ["bug_risk"],
        "diff": '''\
diff --git a/billing/invoice.py b/billing/invoice.py
--- a/billing/invoice.py
+++ b/billing/invoice.py
@@ -32,5 +32,7 @@
 def apply_discount(total, discount_pct):
+    if discount_pct > 100:
+        discount_pct = 100
+    discount = total * discount_pct / 100
+    return total - discount
+    return total
''',
    },
    # LOGIC TN
    {
        "id": "logic_tn_01",
        "language": "python",
        "category": "logic_bug",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/utils/pagination.py b/utils/pagination.py
--- a/utils/pagination.py
+++ b/utils/pagination.py
@@ -8,4 +8,5 @@
 def get_page(items, page, page_size):
+    start = page * page_size
+    return items[start:start + page_size]
''',
    },
    {
        "id": "logic_tn_02",
        "language": "go",
        "category": "logic_bug",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/pkg/retry/backoff.go b/pkg/retry/backoff.go
--- a/pkg/retry/backoff.go
+++ b/pkg/retry/backoff.go
@@ -14,5 +14,7 @@
 func Retry(fn func() error, maxAttempts int) error {
+    for i := 0; i < maxAttempts; i++ {
+        if err := fn(); err == nil {
+            return nil
+        }
+    }
+    return fmt.Errorf("failed after %d attempts", maxAttempts)
 }
''',
    },
    {
        "id": "logic_tn_03",
        "language": "python",
        "category": "logic_bug",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/auth/permissions.py b/auth/permissions.py
--- a/auth/permissions.py
+++ b/auth/permissions.py
@@ -18,3 +18,4 @@
 def is_admin(user):
+    return user.role == "admin"
''',
    },
    {
        "id": "logic_tn_04",
        "language": "typescript",
        "category": "logic_bug",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/src/utils/date.ts b/src/utils/date.ts
--- a/src/utils/date.ts
+++ b/src/utils/date.ts
@@ -8,4 +8,5 @@
 export function isExpired(expiryDate: Date): boolean {
+  return new Date().getTime() > expiryDate.getTime();
 }
''',
    },

    # ── UNHANDLED EXCEPTIONS (6 TP + 3 TN) ───────────────────────────────────

    {
        "id": "exc_01",
        "language": "python",
        "category": "unhandled_exception",
        "should_flag": True,
        "expected_categories": ["bug_risk"],
        "diff": '''\
diff --git a/api/users.py b/api/users.py
--- a/api/users.py
+++ b/api/users.py
@@ -22,4 +22,6 @@
 def get_user_by_id(user_id):
+    result = db.query("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
+    return result["email"]
''',
    },
    {
        "id": "exc_02",
        "language": "javascript",
        "category": "unhandled_exception",
        "should_flag": True,
        "expected_categories": ["bug_risk"],
        "diff": '''\
diff --git a/src/api/fetch.js b/src/api/fetch.js
--- a/src/api/fetch.js
+++ b/src/api/fetch.js
@@ -8,4 +8,5 @@
 async function loadUser(id) {
+  const resp = await fetch(`/api/users/${id}`);
+  const data = await resp.json();
+  return data.user.profile.name;
 }
''',
    },
    {
        "id": "exc_03",
        "language": "go",
        "category": "unhandled_exception",
        "should_flag": True,
        "expected_categories": ["bug_risk"],
        "diff": '''\
diff --git a/internal/storage/files.go b/internal/storage/files.go
--- a/internal/storage/files.go
+++ b/internal/storage/files.go
@@ -18,4 +18,5 @@
 func ReadConfig(path string) []byte {
+    data, _ := os.ReadFile(path)
+    return data
 }
''',
    },
    {
        "id": "exc_04",
        "language": "java",
        "category": "unhandled_exception",
        "should_flag": True,
        "expected_categories": ["bug_risk"],
        "diff": '''\
diff --git a/src/main/java/com/api/Parser.java b/src/main/java/com/api/Parser.java
--- a/src/main/java/com/api/Parser.java
+++ b/src/main/java/com/api/Parser.java
@@ -14,4 +14,5 @@
     public int parseId(String value) {
+        return Integer.parseInt(value);
     }
''',
    },
    {
        "id": "exc_05",
        "language": "typescript",
        "category": "unhandled_exception",
        "should_flag": True,
        "expected_categories": ["bug_risk"],
        "diff": '''\
diff --git a/src/services/config.ts b/src/services/config.ts
--- a/src/services/config.ts
+++ b/src/services/config.ts
@@ -6,4 +6,5 @@
 export function loadConfig(raw: string): Config {
+  return JSON.parse(raw) as Config;
 }
''',
    },
    {
        "id": "exc_06",
        "language": "python",
        "category": "unhandled_exception",
        "should_flag": True,
        "expected_categories": ["bug_risk"],
        "diff": '''\
diff --git a/integrations/stripe.py b/integrations/stripe.py
--- a/integrations/stripe.py
+++ b/integrations/stripe.py
@@ -28,4 +28,5 @@
 def charge_customer(amount, token):
+    charge = stripe.Charge.create(amount=amount, currency="usd", source=token)
+    return charge["id"]
''',
    },
    # EXC TN
    {
        "id": "exc_tn_01",
        "language": "python",
        "category": "unhandled_exception",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/api/users.py b/api/users.py
--- a/api/users.py
+++ b/api/users.py
@@ -22,5 +22,8 @@
 def get_user_by_id(user_id):
+    result = db.query("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
+    if result is None:
+        raise NotFoundError(f"User {user_id} not found")
+    return result["email"]
''',
    },
    {
        "id": "exc_tn_02",
        "language": "go",
        "category": "unhandled_exception",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/internal/storage/files.go b/internal/storage/files.go
--- a/internal/storage/files.go
+++ b/internal/storage/files.go
@@ -18,5 +18,7 @@
 func ReadConfig(path string) ([]byte, error) {
+    data, err := os.ReadFile(path)
+    if err != nil {
+        return nil, fmt.Errorf("reading config %s: %w", path, err)
+    }
+    return data, nil
 }
''',
    },
    {
        "id": "exc_tn_03",
        "language": "typescript",
        "category": "unhandled_exception",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/src/services/config.ts b/src/services/config.ts
--- a/src/services/config.ts
+++ b/src/services/config.ts
@@ -6,6 +6,9 @@
 export function loadConfig(raw: string): Config {
+  try {
+    return JSON.parse(raw) as Config;
+  } catch (e) {
+    throw new Error(`Invalid config JSON: ${e}`);
+  }
 }
''',
    },

    # ── DEAD CODE / QUALITY (6 TP + 3 TN) ────────────────────────────────────

    {
        "id": "dead_01",
        "language": "python",
        "category": "dead_code",
        "should_flag": True,
        "expected_categories": ["quality"],
        "diff": '''\
diff --git a/utils/helpers.py b/utils/helpers.py
--- a/utils/helpers.py
+++ b/utils/helpers.py
@@ -44,6 +44,12 @@
+def _legacy_format_date(dt):
+    return dt.strftime("%Y/%m/%d")
+
+def format_date(dt):
+    return dt.strftime("%Y-%m-%d")
+
+def get_date_string(dt):
+    return format_date(dt)
''',
    },
    {
        "id": "dead_02",
        "language": "go",
        "category": "dead_code",
        "should_flag": True,
        "expected_categories": ["quality"],
        "diff": '''\
diff --git a/pkg/utils/strings.go b/pkg/utils/strings.go
--- a/pkg/utils/strings.go
+++ b/pkg/utils/strings.go
@@ -22,5 +22,10 @@
+func trimAndLower(s string) string {
+    return strings.TrimSpace(strings.ToLower(s))
+}
+
+func normalise(s string) string {
+    return strings.TrimSpace(strings.ToLower(s))
+}
''',
    },
    {
        "id": "dead_03",
        "language": "typescript",
        "category": "dead_code",
        "should_flag": True,
        "expected_categories": ["quality"],
        "diff": '''\
diff --git a/src/utils/format.ts b/src/utils/format.ts
--- a/src/utils/format.ts
+++ b/src/utils/format.ts
@@ -18,6 +18,10 @@
+export function formatCurrency(amount: number): string {
+  return `$${amount.toFixed(2)}`;
+}
+
+export function formatMoney(amount: number): string {
+  return `$${amount.toFixed(2)}`;
+}
''',
    },
    {
        "id": "dead_04",
        "language": "java",
        "category": "dead_code",
        "should_flag": True,
        "expected_categories": ["quality"],
        "diff": '''\
diff --git a/src/main/java/com/utils/StringUtils.java b/src/main/java/com/utils/StringUtils.java
--- a/src/main/java/com/utils/StringUtils.java
+++ b/src/main/java/com/utils/StringUtils.java
@@ -14,6 +14,11 @@
+    private static String legacyTrim(String s) {
+        return s == null ? "" : s.trim();
+    }
+
+    public static String sanitize(String s) {
+        if (s == null) return "";
+        return s.trim().toLowerCase();
+    }
''',
    },
    {
        "id": "dead_05",
        "language": "python",
        "category": "dead_code",
        "should_flag": True,
        "expected_categories": ["quality"],
        "diff": '''\
diff --git a/api/routes.py b/api/routes.py
--- a/api/routes.py
+++ b/api/routes.py
@@ -62,4 +62,8 @@
+@app.route("/api/v1/health")
+def health_check_v1():
+    return {"status": "ok"}
+
+@app.route("/api/v2/health")
+def health_check_v2():
+    return {"status": "ok"}
''',
    },
    {
        "id": "dead_06",
        "language": "rust",
        "category": "dead_code",
        "should_flag": True,
        "expected_categories": ["quality"],
        "diff": '''\
diff --git a/src/utils/format.rs b/src/utils/format.rs
--- a/src/utils/format.rs
+++ b/src/utils/format.rs
@@ -8,5 +8,9 @@
+fn format_bytes_old(n: u64) -> String {
+    format!("{} bytes", n)
+}
+
+pub fn format_bytes(n: u64) -> String {
+    format!("{:.2} KB", n as f64 / 1024.0)
+}
''',
    },
    # DEAD TN
    {
        "id": "dead_tn_01",
        "language": "python",
        "category": "dead_code",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/utils/helpers.py b/utils/helpers.py
--- a/utils/helpers.py
+++ b/utils/helpers.py
@@ -44,3 +44,5 @@
+def format_date(dt):
+    return dt.strftime("%Y-%m-%d")
''',
    },
    {
        "id": "dead_tn_02",
        "language": "go",
        "category": "dead_code",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/pkg/utils/strings.go b/pkg/utils/strings.go
--- a/pkg/utils/strings.go
+++ b/pkg/utils/strings.go
@@ -22,3 +22,5 @@
+func Normalise(s string) string {
+    return strings.TrimSpace(strings.ToLower(s))
+}
''',
    },
    {
        "id": "dead_tn_03",
        "language": "typescript",
        "category": "dead_code",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/src/utils/format.ts b/src/utils/format.ts
--- a/src/utils/format.ts
+++ b/src/utils/format.ts
@@ -18,3 +18,5 @@
+export function formatCurrency(amount: number): string {
+  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(amount);
+}
''',
    },

    # ── EDGE CASES (27) ───────────────────────────────────────────────────────

    # Removal-only diffs (should never flag)
    {
        "id": "edge_removal_01",
        "language": "python",
        "category": "edge_removal",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/config/settings.py b/config/settings.py
--- a/config/settings.py
+++ b/config/settings.py
@@ -14,5 +14,3 @@
-DB_CONFIG = {
-    "password": "Wj7#mK2$pL9qR",
-}
''',
    },
    {
        "id": "edge_removal_02",
        "language": "javascript",
        "category": "edge_removal",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/src/api/client.js b/src/api/client.js
--- a/src/api/client.js
+++ b/src/api/client.js
@@ -8,4 +8,2 @@
-  process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";
-  return fetch(url);
+  return fetch(url);
''',
    },
    {
        "id": "edge_removal_03",
        "language": "go",
        "category": "edge_removal",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/internal/db/queries.go b/internal/db/queries.go
--- a/internal/db/queries.go
+++ b/internal/db/queries.go
@@ -18,4 +18,2 @@
-    query := "SELECT * FROM users WHERE id = " + id
-    return db.QueryRow(query)
+    return db.QueryRow("SELECT * FROM users WHERE id = $1", id)
''',
    },
    {
        "id": "edge_removal_04",
        "language": "python",
        "category": "edge_removal",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/workers/task.py b/workers/task.py
--- a/workers/task.py
+++ b/workers/task.py
@@ -31,4 +31,2 @@
-    task = eval(message["code"])
-    return task()
+    return dispatch(json.loads(message["code"]))
''',
    },
    # Multi-file diffs
    {
        "id": "edge_multifile_01",
        "language": "python",
        "category": "multi_file",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/models/user.py b/models/user.py
--- a/models/user.py
+++ b/models/user.py
@@ -8,3 +8,5 @@
 class User:
+    def get_by_name(self, db, name):
+        return db.execute("SELECT * FROM users WHERE name = '" + name + "'").fetchone()
diff --git a/views/profile.py b/views/profile.py
--- a/views/profile.py
+++ b/views/profile.py
@@ -14,3 +14,5 @@
 def profile_view(request, username):
+    html = f"<h1>{username}</h1>"
+    return HttpResponse(html)
''',
    },
    {
        "id": "edge_multifile_02",
        "language": "go",
        "category": "multi_file",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/handlers/api.go b/handlers/api.go
--- a/handlers/api.go
+++ b/handlers/api.go
@@ -22,4 +22,5 @@
 func GetUser(w http.ResponseWriter, r *http.Request) {
+    id := r.URL.Query().Get("id")
+    row := db.QueryRow("SELECT * FROM users WHERE id = " + id)
 }
diff --git a/config/db.go b/config/db.go
--- a/config/db.go
+++ b/config/db.go
@@ -8,3 +8,4 @@
+const dbPassword = "prod_password_2024"
''',
    },
    {
        "id": "edge_multifile_03",
        "language": "python",
        "category": "multi_file",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/models/user.py b/models/user.py
--- a/models/user.py
+++ b/models/user.py
@@ -8,3 +8,5 @@
 class User:
+    def __repr__(self):
+        return f"User(id={self.id}, email={self.email})"
diff --git a/views/profile.py b/views/profile.py
--- a/views/profile.py
+++ b/views/profile.py
@@ -14,3 +14,5 @@
 def profile_view(request, username):
+    safe_name = escape(username)
+    return render(request, "profile.html", {"username": safe_name})
''',
    },
    # Obfuscated patterns
    {
        "id": "edge_obfuscated_01",
        "language": "python",
        "category": "obfuscated",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/utils/init.py b/utils/init.py
--- a/utils/init.py
+++ b/utils/init.py
@@ -6,4 +6,7 @@
+import base64
+_k = base64.b64decode("c2tfc2VjcmV0X2xpdmVfQUJDREVGR0hJSktM").decode()
+client = StripeClient(_k)
''',
    },
    {
        "id": "edge_obfuscated_02",
        "language": "javascript",
        "category": "obfuscated",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/src/config.js b/src/config.js
--- a/src/config.js
+++ b/src/config.js
@@ -4,3 +4,5 @@
+const _cfg = atob("QUtJQUlPU0ZPRE5ON0VYQU1QTEU=");
+const awsKey = _cfg;
''',
    },
    {
        "id": "edge_obfuscated_03",
        "language": "python",
        "category": "obfuscated",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/auth/bootstrap.py b/auth/bootstrap.py
--- a/auth/bootstrap.py
+++ b/auth/bootstrap.py
@@ -12,4 +12,6 @@
+parts = ["my-sup", "er-secre", "t-jwt-key"]
+JWT_SECRET = "".join(parts)
+app.config["JWT_SECRET"] = JWT_SECRET
''',
    },
    # Large diff — chunking behavior
    {
        "id": "edge_large_01",
        "language": "python",
        "category": "large_diff",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '\n'.join(
            ["diff --git a/api/views.py b/api/views.py",
             "--- a/api/views.py",
             "+++ b/api/views.py",
             "@@ -1,5 +1,100 @@"] +
            [f"+    # line {i}" for i in range(80)] +
            ["+def get_user(db, name):",
             "+    return db.execute(\"SELECT * FROM users WHERE name = '\" + name + \"'\").fetchone()"]
        ),
    },
    {
        "id": "edge_large_02",
        "language": "go",
        "category": "large_diff",
        "should_flag": False,
        "expected_categories": [],
        "diff": '\n'.join(
            ["diff --git a/internal/service/user.go b/internal/service/user.go",
             "--- a/internal/service/user.go",
             "+++ b/internal/service/user.go",
             "@@ -1,5 +1,100 @@"] +
            [f"+// comment line {i}" for i in range(90)] +
            ["+func GetUser(db *sql.DB, id int64) (*User, error) {",
             "+    return sqlx.Get(db, &User{}, \"SELECT * FROM users WHERE id = $1\", id)",
             "+}"]
        ),
    },
    # Clean code across all languages
    {
        "id": "edge_clean_py",
        "language": "python",
        "category": "clean",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/api/health.py b/api/health.py
--- a/api/health.py
+++ b/api/health.py
@@ -4,3 +4,5 @@
+@app.route("/health")
+def health():
+    return jsonify({"status": "ok", "version": "2.1.2"})
''',
    },
    {
        "id": "edge_clean_ts",
        "language": "typescript",
        "category": "clean",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/src/utils/logger.ts b/src/utils/logger.ts
--- a/src/utils/logger.ts
+++ b/src/utils/logger.ts
@@ -4,5 +4,8 @@
+export const logger = {
+  info:  (msg: string) => console.log(`[INFO]  ${msg}`),
+  warn:  (msg: string) => console.warn(`[WARN]  ${msg}`),
+  error: (msg: string) => console.error(`[ERROR] ${msg}`),
+};
''',
    },
    {
        "id": "edge_clean_go",
        "language": "go",
        "category": "clean",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/pkg/middleware/logging.go b/pkg/middleware/logging.go
--- a/pkg/middleware/logging.go
+++ b/pkg/middleware/logging.go
@@ -10,5 +10,9 @@
+func LoggingMiddleware(next http.Handler) http.Handler {
+    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
+        start := time.Now()
+        next.ServeHTTP(w, r)
+        log.Printf("%s %s %v", r.Method, r.URL.Path, time.Since(start))
+    })
+}
''',
    },
    {
        "id": "edge_clean_rust",
        "language": "rust",
        "category": "clean",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/src/models/user.rs b/src/models/user.rs
--- a/src/models/user.rs
+++ b/src/models/user.rs
@@ -8,5 +8,9 @@
+#[derive(Debug, serde::Serialize, serde::Deserialize)]
+pub struct User {
+    pub id:    i64,
+    pub email: String,
+    pub name:  String,
+}
''',
    },
    {
        "id": "edge_clean_java",
        "language": "java",
        "category": "clean",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/src/main/java/com/api/HealthController.java b/src/main/java/com/api/HealthController.java
--- a/src/main/java/com/api/HealthController.java
+++ b/src/main/java/com/api/HealthController.java
@@ -8,4 +8,7 @@
+@RestController
+public class HealthController {
+    @GetMapping("/health")
+    public Map<String, String> health() {
+        return Map.of("status", "ok");
+    }
+}
''',
    },
    {
        "id": "edge_clean_swift",
        "language": "swift",
        "category": "clean",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/Sources/App/Models/User.swift b/Sources/App/Models/User.swift
--- a/Sources/App/Models/User.swift
+++ b/Sources/App/Models/User.swift
@@ -4,5 +4,8 @@
+struct User: Codable {
+    let id:    Int
+    let email: String
+    let name:  String
+}
''',
    },
    # Refactor-only (rename, restructure — no security issues introduced)
    {
        "id": "edge_refactor_01",
        "language": "python",
        "category": "refactor",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/utils/db.py b/utils/db.py
--- a/utils/db.py
+++ b/utils/db.py
@@ -12,6 +12,8 @@
-def getUser(db, id):
-    cur = db.cursor()
-    cur.execute("SELECT * FROM users WHERE id = ?", (id,))
-    return cur.fetchone()
+def get_user(db, user_id: int):
+    return db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
''',
    },
    {
        "id": "edge_refactor_02",
        "language": "typescript",
        "category": "refactor",
        "should_flag": False,
        "expected_categories": [],
        "diff": '''\
diff --git a/src/services/auth.ts b/src/services/auth.ts
--- a/src/services/auth.ts
+++ b/src/services/auth.ts
@@ -14,7 +14,5 @@
-async function validateToken(token: string): Promise<boolean> {
-    try {
-        const decoded = jwt.verify(token, process.env.JWT_SECRET!);
-        return decoded !== null;
-    } catch {
-        return false;
-    }
-}
+const validateToken = async (token: string): Promise<boolean> => {
+    try { return jwt.verify(token, process.env.JWT_SECRET!) !== null; }
+    catch { return false; }
+};
''',
    },
    # Mixed: one file risky, one file clean
    {
        "id": "edge_mixed_01",
        "language": "python",
        "category": "mixed",
        "should_flag": True,
        "expected_categories": ["security"],
        "diff": '''\
diff --git a/api/health.py b/api/health.py
--- a/api/health.py
+++ b/api/health.py
@@ -4,3 +4,5 @@
+@app.route("/health")
+def health():
+    return jsonify({"status": "ok"})
diff --git a/api/search.py b/api/search.py
--- a/api/search.py
+++ b/api/search.py
@@ -22,3 +22,5 @@
 def search(db, query):
+    sql = "SELECT * FROM items WHERE name LIKE '%" + query + "%'"
+    return db.execute(sql).fetchall()
''',
    },
    {
        "id": "edge_mixed_02",
        "language": "go",
        "category": "mixed",
        "should_flag": True,
        "expected_categories": ["security", "bug_risk"],
        "diff": '''\
diff --git a/handlers/user.go b/handlers/user.go
--- a/handlers/user.go
+++ b/handlers/user.go
@@ -14,4 +14,7 @@
 func CreateUser(w http.ResponseWriter, r *http.Request) {
+    data, _ := io.ReadAll(r.Body)
+    query := "INSERT INTO users VALUES ('" + string(data) + "')"
+    db.Exec(query)
 }
diff --git a/handlers/health.go b/handlers/health.go
--- a/handlers/health.go
+++ b/handlers/health.go
@@ -8,3 +8,5 @@
 func Health(w http.ResponseWriter, r *http.Request) {
+    w.Header().Set("Content-Type", "application/json")
+    json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
 }
''',
    },
]
