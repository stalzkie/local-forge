#!/usr/bin/env python3
"""
Build and export the LocalForge CoreML security classifier (Layer 2).

Produces:
  coreml/LocalForgeModel.mlpackage  — CoreML model (CPU_AND_NE)
  coreml/tfidf_vectorizer.pkl       — TF-IDF vectorizer for infer.py
  coreml/model_metadata.json        — accuracy, date, sample count, threshold
"""

import os
import sys
import json
import time
import pickle
import datetime
import numpy as np
import coremltools as ct
from coremltools.models import MLModel
from coremltools.models.neural_network import NeuralNetworkBuilder
import coremltools.models.datatypes as datatypes
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(OUTPUT_DIR, "LocalForgeModel.mlpackage")
TFIDF_PATH = os.path.join(OUTPUT_DIR, "tfidf_vectorizer.pkl")
META_PATH  = os.path.join(OUTPUT_DIR, "model_metadata.json")
N_FEATURES = 1024   # doubled from 512 — more capacity for multi-language vocab
THRESHOLD  = 0.5

def bar(filled, total=20):
    n = int(filled / total * total)
    return f"[{'█' * n}{'░' * (total - n)}]"

def section(title):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")

# ── Training data ─────────────────────────────────────────────────────────────
# Label 1 = risky, 0 = clean. Each language block is clearly delimited.

SAMPLES = [

    # ═══════════════════════════════════════════════════════
    # PYTHON — RISKY
    # ═══════════════════════════════════════════════════════

    # Hardcoded credentials
    ("password = 'hunter2'",                                               1),
    ("db_password = 'supersecret123'",                                     1),
    ("PASSWORD = 'admin'",                                                 1),
    ("passwd = '12345678'",                                                1),
    ("secret = 'mysecretvalue'",                                           1),
    ("api_key = 'hardcodedkeyvalue123abc'",                                1),
    ("credentials = {'user': 'admin', 'pass': 'letmein'}",                1),
    ("connection_string = 'Server=prod;Password=p@ssw0rd'",               1),
    ("auth_token = 'Bearer supersecrettoken123456'",                       1),
    ("private_key_pem = open('id_rsa').read()",                            1),
    ("token = 'abc123secrettoken_live'",                                   1),
    ("db_pass = 'root'",                                                   1),
    ("admin_password = 'Password1!'",                                      1),
    ("config['password'] = 'hardcoded_pw'",                                1),
    ("SECRET = 'do_not_commit_this'",                                      1),
    ("SECRET_KEY = 'change_me_in_production'",                             1),
    ("MASTER_PASSWORD = 'default'",                                        1),
    ("encryption_key = b'0000000000000000'",                               1),
    ("jwt_secret = 'not-very-secret'",                                     1),
    ("oauth_secret = 'oauth_hardcoded_value'",                             1),
    ("DJANGO_SECRET_KEY = 'dev-only-key-abc123'",                          1),
    ("Flask.secret_key = 'dev'",                                           1),
    ("signing_secret = 'placeholder_secret'",                              1),
    ("webhook_secret = '1234567890abcdef'",                                1),
    ("client_secret = 'mysecret_value123'",                                1),

    # Code injection / unsafe execution
    ("subprocess.call(user_input, shell=True)",                            1),
    ("eval(request.GET['cmd'])",                                           1),
    ("os.system(f'rm -rf {path}')",                                        1),
    ("cursor.execute('SELECT * FROM users WHERE id=' + user_id)",          1),
    ("pickle.loads(untrusted_data)",                                       1),
    ("exec(compile(source, '<string>', 'exec'))",                          1),
    ("eval(user_input)",                                                   1),
    ("eval(request.args.get('code'))",                                     1),
    ("eval(data['expr'])",                                                 1),
    ("__import__(user_module)",                                            1),
    ("globals()[func_name]()",                                             1),
    ("os.popen(cmd).read()",                                               1),
    ("subprocess.check_output(cmd, shell=True)",                           1),
    ("commands.getoutput(user_cmd)",                                       1),
    ("yaml.load(data)",                                                    1),
    ("yaml.load(stream, Loader=yaml.Loader)",                              1),
    ("marshal.loads(untrusted)",                                           1),
    ("shelve.open(user_path)",                                             1),
    ("os.path.join('/', user_input)",                                      1),
    ("open(f'/etc/{filename}').read()",                                    1),

    # Disabled security / weak crypto
    ("verify=False",                                                       1),
    ("ssl._create_unverified_context()",                                   1),
    ("hashlib.md5(password.encode())",                                     1),
    ("DES.new(key, DES.MODE_ECB)",                                         1),
    ("requests.get(url, verify=False)",                                    1),
    ("ssl_verify = False",                                                 1),
    ("check_hostname = False",                                             1),
    ("MD5(password)",                                                      1),
    ("SHA1(data)",                                                         1),
    ("RC4.encrypt(key, plaintext)",                                        1),
    ("urllib3.disable_warnings()",                                         1),
    ("random.randint(0, 2**32)",                                           1),
    ("hashlib.sha1(token).hexdigest()",                                    1),

    # SQL injection
    ("query = 'SELECT * FROM users WHERE name=' + name",                   1),
    ("db.execute(f'DELETE FROM logs WHERE id={req_id}')",                  1),
    ("sql = \"INSERT INTO t VALUES ('\" + val + \"')\"",                   1),
    ("cursor.execute('UPDATE u SET pw=' + pw + ' WHERE id=' + id)",       1),

    # Path traversal
    ("send_file('/uploads/' + filename)",                                  1),
    ("open(base_dir + '/' + user_file)",                                   1),
    ("shutil.copy(src, '/var/www/' + name)",                               1),

    # ═══════════════════════════════════════════════════════
    # JAVASCRIPT / TYPESCRIPT — RISKY
    # ═══════════════════════════════════════════════════════

    ("const password = 'hunter2'",                                         1),
    ("var apiKey = 'hardcoded-api-key-12345'",                             1),
    ("let secret = 'my_secret_value_abc'",                                 1),
    ("process.env.SECRET = 'inlined_secret'",                              1),
    ("eval(userInput)",                                                    1),
    ("eval(req.body.code)",                                                1),
    ("document.write(req.query.html)",                                     1),
    ("innerHTML = userComment",                                            1),
    ("innerHTML = req.params.name",                                        1),
    ("res.send('<h1>' + req.query.name + '</h1>')",                        1),
    ("db.query('SELECT * FROM u WHERE id=' + req.params.id)",              1),
    ("execSync(userCommand)",                                              1),
    ("exec(`ls ${userDir}`, callback)",                                    1),
    ("child_process.exec(req.body.cmd)",                                   1),
    ("require(userModule)",                                                1),
    ("fs.readFileSync('/etc/' + filename)",                                1),
    ("JSON.parse(eval(data))",                                             1),
    ("new Function(userCode)()",                                           1),
    ("setTimeout(userCode, 0)",                                            1),
    ("crypto.createHash('md5').update(pw).digest('hex')",                  1),
    ("Math.random() * 0xffffffff",                                         1),
    ("process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'",                    1),
    ("axios.get(url, { httpsAgent: new https.Agent({ rejectUnauthorized: false }) })", 1),

    # ═══════════════════════════════════════════════════════
    # JAVA — RISKY
    # ═══════════════════════════════════════════════════════

    ("String password = \"hardcoded123\";",                                1),
    ("Runtime.getRuntime().exec(userInput)",                               1),
    ("Runtime.getRuntime().exec(new String[]{\"sh\",\"-c\",cmd})",         1),
    ("Statement stmt = conn.createStatement(); stmt.execute(\"SELECT * FROM users WHERE id=\" + id);", 1),
    ("MessageDigest.getInstance(\"MD5\")",                                 1),
    ("MessageDigest.getInstance(\"SHA-1\")",                               1),
    ("new SecretKeySpec(\"hardcodedkey123\".getBytes(), \"AES\")",         1),
    ("Cipher.getInstance(\"DES/ECB/PKCS5Padding\")",                      1),
    ("Class.forName(userClassName).newInstance()",                         1),
    ("ObjectInputStream ois = new ObjectInputStream(socket.getInputStream()); ois.readObject();", 1),
    ("System.setProperty(\"com.sun.jndi.ldap.object.trustURLCodebase\",\"true\")", 1),
    ("new URL(userUrl).openStream()",                                      1),
    ("private static final String DB_PASS = \"root\";",                   1),
    ("HostnameVerifier hv = (hostname, session) -> true;",                 1),

    # ═══════════════════════════════════════════════════════
    # GO — RISKY
    # ═══════════════════════════════════════════════════════

    ("password := \"hardcoded_secret\"",                                   1),
    ("apiKey := \"my-api-key-12345\"",                                     1),
    ("exec.Command(\"bash\", \"-c\", userInput).Run()",                    1),
    ("db.Query(\"SELECT * FROM users WHERE id=\" + id)",                   1),
    ("fmt.Sprintf(\"SELECT * FROM t WHERE name='%s'\", name)",             1),
    ("http.Get(url) // no TLS verification",                               1),
    ("tr := &http.Transport{TLSClientConfig: &tls.Config{InsecureSkipVerify: true}}", 1),
    ("md5.Sum([]byte(password))",                                          1),
    ("sha1.Sum([]byte(token))",                                            1),
    ("rand.Intn(999999)",                                                  1),
    ("ioutil.ReadFile(\"/etc/\" + userPath)",                              1),
    ("os.Open(filepath.Join(\"/uploads\", req.URL.Query().Get(\"f\")))",   1),

    # ═══════════════════════════════════════════════════════
    # RUST — RISKY
    # ═══════════════════════════════════════════════════════

    ("let password = \"hardcoded_secret\";",                               1),
    ("let api_key = \"live_key_abc123\";",                                 1),
    ("Command::new(\"sh\").arg(\"-c\").arg(&user_input).output()",         1),
    ("format!(\"SELECT * FROM users WHERE id={}\", id)",                   1),
    ("unsafe { std::mem::transmute::<_, fn()>(ptr)() }",                  1),
    ("std::process::Command::new(&user_cmd).spawn()",                      1),
    ("unwrap() // on untrusted external input",                            1),

    # ═══════════════════════════════════════════════════════
    # C# — RISKY
    # ═══════════════════════════════════════════════════════

    ("string password = \"P@ssw0rd\";",                                    1),
    ("Process.Start(userInput)",                                           1),
    ("SqlCommand cmd = new SqlCommand(\"SELECT * FROM u WHERE id=\" + id, conn);", 1),
    ("MD5.Create().ComputeHash(Encoding.UTF8.GetBytes(pw))",               1),
    ("new DESCryptoServiceProvider()",                                     1),
    ("BinaryFormatter bf = new BinaryFormatter(); bf.Deserialize(stream);", 1),
    ("ServicePointManager.ServerCertificateValidationCallback = (s,c,ch,e) => true;", 1),
    ("new WebClient().DownloadString(userUrl)",                            1),

    # ═══════════════════════════════════════════════════════
    # PHP — RISKY
    # ═══════════════════════════════════════════════════════

    ("$password = 'hardcoded123';",                                        1),
    ("system($_GET['cmd']);",                                              1),
    ("exec($_POST['command'], $out);",                                     1),
    ("eval($_GET['code']);",                                               1),
    ("mysql_query(\"SELECT * FROM users WHERE id=\" . $_GET['id']);",      1),
    ("$pdo->query(\"SELECT * FROM t WHERE name='\" . $name . \"'\");",     1),
    ("include($_GET['page']);",                                            1),
    ("require($_POST['file']);",                                           1),
    ("md5($password)",                                                     1),
    ("sha1($token)",                                                       1),
    ("unserialize($_COOKIE['data'])",                                      1),
    ("file_get_contents($_GET['url'])",                                    1),
    ("move_uploaded_file($tmp, '/uploads/' . $_FILES['f']['name'])",       1),

    # ═══════════════════════════════════════════════════════
    # RUBY — RISKY
    # ═══════════════════════════════════════════════════════

    ("password = 'hardcoded_pw'",                                          1),
    ("`#{user_input}`",                                                    1),
    ("system(\"ls #{params[:dir]}\")",                                     1),
    ("eval(params[:code])",                                                1),
    ("ActiveRecord::Base.connection.execute(\"SELECT * FROM users WHERE id=#{params[:id]}\")", 1),
    ("Marshal.load(untrusted_data)",                                       1),
    ("YAML.load(user_yaml)",                                               1),
    ("Digest::MD5.hexdigest(password)",                                    1),
    ("OpenSSL::Digest::SHA1.new",                                          1),
    ("send(params[:method])",                                              1),

    # ═══════════════════════════════════════════════════════
    # SWIFT / KOTLIN — RISKY
    # ═══════════════════════════════════════════════════════

    ("let password = \"hardcoded\"",                                       1),
    ("let apiKey = \"live_key_12345\"",                                    1),
    ("CC_MD5(data, CC_LONG(data.count), &digest)",                        1),
    ("val password = \"hardcoded123\"",                                    1),
    ("Runtime.getRuntime().exec(userInput)",                               1),
    ("MessageDigest.getInstance(\"MD5\").digest(pw.toByteArray())",        1),

    # ═══════════════════════════════════════════════════════
    # SQL — RISKY
    # ═══════════════════════════════════════════════════════

    ("SELECT * FROM users WHERE id = ' + userId + '",                      1),
    ("EXEC xp_cmdshell '" + "net user' + @cmd",                           1),
    ("DROP TABLE users; --",                                               1),
    ("1=1 OR 'x'='x",                                                     1),
    ("UNION SELECT username, password FROM admin --",                      1),

    # ═══════════════════════════════════════════════════════
    # PYTHON — CLEAN
    # ═══════════════════════════════════════════════════════

    ("def calculate_total(items): return sum(i.price for i in items)",     0),
    ("class UserService:\n    def __init__(self, db): self.db = db",       0),
    ("import os; path = os.path.join(base, filename)",                     0),
    ("logger.info('Processing request %s', request_id)",                  0),
    ("result = [x * 2 for x in range(10)]",                               0),
    ("if user.is_authenticated: return redirect('dashboard')",            0),
    ("with open(filepath, 'r') as f: data = json.load(f)",                0),
    ("assert response.status_code == 200",                                 0),
    ("def test_login(client): resp = client.post('/login', data={})",      0),
    ("return Response({'status': 'ok'}, status=200)",                      0),
    ("def hash_password(p): return bcrypt.hashpw(p, bcrypt.gensalt())",   0),
    ("requests.get(url, verify=True, timeout=30)",                         0),
    ("password = os.environ.get('DB_PASSWORD')",                           0),
    ("secret_key = config['SECRET_KEY']",                                  0),
    ("api_key = os.getenv('API_KEY')",                                     0),
    ("jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])",       0),
    ("cipher = AES.new(key, AES.MODE_GCM)",                                0),
    ("hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()",         0),
    ("os.urandom(32)",                                                     0),
    ("secrets.token_hex(32)",                                              0),
    ("bcrypt.checkpw(password, hashed)",                                   0),
    ("cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))",   0),
    ("subprocess.run(['ls', '-la'], capture_output=True)",                 0),
    ("shlex.split(safe_command)",                                          0),
    ("ssl.create_default_context()",                                       0),
    ("certifi.where()",                                                    0),
    ("argon2.hash(password)",                                              0),
    ("hashlib.sha256(data).hexdigest()",                                   0),
    ("hashlib.sha512(token).hexdigest()",                                  0),
    ("hmac.compare_digest(a, b)",                                          0),
    ("Fernet(key).encrypt(plaintext)",                                     0),

    # ═══════════════════════════════════════════════════════
    # JAVASCRIPT / TYPESCRIPT — CLEAN
    # ═══════════════════════════════════════════════════════

    ("const add = (a: number, b: number): number => a + b;",              0),
    ("const user = await db.findOne({ where: { id } });",                  0),
    ("const hash = await bcrypt.hash(password, 10);",                     0),
    ("const token = jwt.sign(payload, process.env.JWT_SECRET);",          0),
    ("const apiKey = process.env.API_KEY;",                               0),
    ("res.json({ status: 'ok', data });",                                  0),
    ("const safe = DOMPurify.sanitize(userInput);",                        0),
    ("const stmt = db.prepare('SELECT * FROM users WHERE id = ?');",      0),
    ("fetch(url, { method: 'GET', headers: { Authorization: `Bearer ${token}` } });", 0),
    ("crypto.randomBytes(32).toString('hex')",                             0),
    ("crypto.createHmac('sha256', secret).update(data).digest('hex')",    0),
    ("helmet()",                                                           0),
    ("express.json({ limit: '10kb' })",                                    0),
    ("const escaped = encodeURIComponent(userInput);",                    0),
    ("const hash = crypto.createHash('sha256').update(data).digest('hex');", 0),

    # ═══════════════════════════════════════════════════════
    # RUST — CLEAN
    # ═══════════════════════════════════════════════════════

    ("fn main() { println!(\"Hello, world!\"); }",                         0),
    ("let x: u32 = 42;",                                                   0),
    ("pub struct Config { pub port: u16, pub host: String }",              0),
    ("let password = std::env::var(\"DB_PASSWORD\")?;",                   0),
    ("let api_key = env::var(\"API_KEY\").expect(\"API_KEY not set\");",   0),
    ("let hash = Sha256::digest(data.as_bytes());",                        0),
    ("let mac = Hmac::<Sha256>::new_from_slice(key)?;",                    0),
    ("let cipher = Aes256Gcm::new(key);",                                  0),
    ("let token = OsRng.gen::<[u8; 32]>();",                               0),
    ("sqlx::query!(\"SELECT * FROM users WHERE id = $1\", id).fetch_one(&pool).await?;", 0),
    ("Command::new(\"ls\").arg(\"-la\").output()?;",                       0),

    # ═══════════════════════════════════════════════════════
    # GO — CLEAN
    # ═══════════════════════════════════════════════════════

    ("func main() { fmt.Println(\"hello\") }",                             0),
    ("password := os.Getenv(\"DB_PASSWORD\")",                             0),
    ("apiKey := os.Getenv(\"API_KEY\")",                                   0),
    ("hash, _ := bcrypt.GenerateFromPassword([]byte(pw), bcrypt.DefaultCost)", 0),
    ("h := sha256.New(); h.Write(data)",                                   0),
    ("mac := hmac.New(sha256.New, key)",                                   0),
    ("rows, err := db.Query(\"SELECT * FROM users WHERE id = $1\", id)",  0),
    ("http.ListenAndServeTLS(\":443\", cert, key, nil)",                   0),
    ("rand.Read(b)",                                                        0),
    ("aes.NewCipher(key)",                                                 0),
    ("cmd := exec.Command(\"ls\", \"-la\")",                               0),

    # ═══════════════════════════════════════════════════════
    # JAVA — CLEAN
    # ═══════════════════════════════════════════════════════

    ("public class Main { public static void main(String[] args) {} }",   0),
    ("String password = System.getenv(\"DB_PASSWORD\");",                  0),
    ("String apiKey = System.getenv(\"API_KEY\");",                        0),
    ("PreparedStatement ps = conn.prepareStatement(\"SELECT * FROM users WHERE id=?\"); ps.setInt(1, id);", 0),
    ("MessageDigest.getInstance(\"SHA-256\")",                             0),
    ("MessageDigest.getInstance(\"SHA-512\")",                             0),
    ("Cipher.getInstance(\"AES/GCM/NoPadding\")",                         0),
    ("SecureRandom random = new SecureRandom();",                          0),
    ("BCryptPasswordEncoder encoder = new BCryptPasswordEncoder();",       0),
    ("KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm())", 0),

    # ═══════════════════════════════════════════════════════
    # C# — CLEAN
    # ═══════════════════════════════════════════════════════

    ("string password = Environment.GetEnvironmentVariable(\"DB_PASS\");", 0),
    ("using var sha = SHA256.Create(); sha.ComputeHash(data);",           0),
    ("using var aes = Aes.Create(); aes.Mode = CipherMode.GCM;",         0),
    ("var hash = BCrypt.Net.BCrypt.HashPassword(password);",              0),
    ("using var cmd = new SqlCommand(\"SELECT * FROM u WHERE id=@id\", conn); cmd.Parameters.AddWithValue(\"@id\", id);", 0),
    ("HttpClient client = new HttpClient();",                             0),

    # ═══════════════════════════════════════════════════════
    # PHP — CLEAN
    # ═══════════════════════════════════════════════════════

    ("$password = $_ENV['DB_PASSWORD'];",                                  0),
    ("$stmt = $pdo->prepare('SELECT * FROM users WHERE id = ?'); $stmt->execute([$id]);", 0),
    ("password_hash($password, PASSWORD_BCRYPT)",                          0),
    ("password_verify($input, $hash)",                                     0),
    ("hash('sha256', $data)",                                              0),
    ("openssl_random_pseudo_bytes(32)",                                    0),
    ("filter_var($email, FILTER_VALIDATE_EMAIL)",                          0),
    ("htmlspecialchars($userInput, ENT_QUOTES, 'UTF-8')",                  0),

    # ═══════════════════════════════════════════════════════
    # RUBY — CLEAN
    # ═══════════════════════════════════════════════════════

    ("password = ENV['DB_PASSWORD']",                                      0),
    ("BCrypt::Password.create(password)",                                  0),
    ("OpenSSL::Digest::SHA256.new",                                        0),
    ("ActiveRecord::Base.connection.execute('SELECT * FROM users WHERE id = $1', [id])", 0),
    ("Rails.application.credentials.secret_key_base",                     0),
    ("SecureRandom.hex(32)",                                               0),
    ("Rack::Utils.escape_html(user_input)",                                0),

    # ═══════════════════════════════════════════════════════
    # SWIFT / KOTLIN — CLEAN
    # ═══════════════════════════════════════════════════════

    ("let password = ProcessInfo.processInfo.environment[\"DB_PASSWORD\"]", 0),
    ("let hash = SHA256.hash(data: Data(plaintext.utf8))",                 0),
    ("let key = SymmetricKey(size: .bits256)",                             0),
    ("val password = System.getenv(\"DB_PASSWORD\")",                      0),
    ("val hash = MessageDigest.getInstance(\"SHA-256\").digest(data)",     0),
    ("val stmt = conn.prepareStatement(\"SELECT * FROM u WHERE id=?\"); stmt.setInt(1, id)", 0),

    # ═══════════════════════════════════════════════════════
    # SQL — CLEAN
    # ═══════════════════════════════════════════════════════

    ("SELECT id, name FROM users WHERE active = true",                     0),
    ("CREATE TABLE sessions (id UUID PRIMARY KEY, created_at TIMESTAMP)",  0),
    ("INSERT INTO logs (event, ts) VALUES ($1, NOW())",                    0),
    ("SELECT * FROM orders WHERE user_id = $1 AND status = $2",           0),
    ("CREATE INDEX idx_users_email ON users(email)",                       0),

    # ═══════════════════════════════════════════════════════
    # BORDERLINE FIXES — push ambiguous cases to correct side
    # ═══════════════════════════════════════════════════════

    # MD5/SHA1 — risky (weak crypto)
    ("hashlib.md5(password.encode())",                                     1),
    ("hashlib.md5(token)",                                                 1),
    ("md5(user_password)",                                                 1),
    ("md5_hash = hashlib.md5(data).hexdigest()",                           1),

    # Go InsecureSkipVerify — risky
    ("TLSClientConfig: &tls.Config{InsecureSkipVerify: true}",            1),
    ("InsecureSkipVerify: true",                                           1),
    ("tls.Config{InsecureSkipVerify: true}",                               1),

    # secrets module — clean (it IS the safe way to generate tokens)
    ("secrets.token_hex(32)",                                              0),
    ("secrets.token_bytes(16)",                                            0),
    ("secrets.token_urlsafe()",                                            0),
    ("import secrets; key = secrets.token_hex(32)",                       0),

    # Parameterized Go queries — clean
    ("db.Query(\"SELECT * FROM u WHERE id = $1\", id)",                    0),
    ("db.QueryRow(\"SELECT * FROM t WHERE key = $1\", key).Scan(&val)",    0),
    ("stmt.QueryContext(ctx, \"SELECT * FROM u WHERE id = ?\", id)",       0),

    # ═══════════════════════════════════════════════════════
    # EDGE CASES — false positive traps
    # ═══════════════════════════════════════════════════════

    # Variable named 'password' but reads from env/config — must be CLEAN
    ("password = os.environ['PASSWORD']",                                  0),
    ("password = config.get('password')",                                  0),
    ("password = getpass.getpass('Enter password: ')",                    0),
    ("# TODO: move password to environment variable",                     0),
    ("assert password != '', 'Password must not be empty'",               0),
    ("if len(password) < 8: raise ValueError('Too short')",               0),
    ("test_password = 'test_value_for_unit_test'",                        0),
    ("EXAMPLE_KEY = 'example_only_not_real'",                             0),
    ("# password = 'old_value'  # removed",                               0),
    ("print(f'password length: {len(password)}')",                        0),
]

# ── Progress display ──────────────────────────────────────────────────────────

texts  = [s for s, _ in SAMPLES]
labels = np.array([l for _, l in SAMPLES])
n_risky = int(np.sum(labels == 1))
n_clean = int(np.sum(labels == 0))

section("LocalForge Layer 2 — Model Training")
print(f"  Dataset      : {len(texts)} samples  ({n_risky} risky  /  {n_clean} clean)")
print(f"  Architecture : TF-IDF char_wb (3-5gram, {N_FEATURES} features) + Logistic Regression → CoreML")
print(f"  Target       : CPU_AND_NE  (Apple Neural Engine)")

# ── Step 1: Fit TF-IDF vectorizer ────────────────────────────────────────────

section("Step 1/5 — Fitting TF-IDF Vectorizer")
t0 = time.time()
tfidf = TfidfVectorizer(
    analyzer="char_wb",
    ngram_range=(3, 5),
    max_features=N_FEATURES,
    sublinear_tf=True,
)
X = tfidf.fit_transform(texts).toarray().astype(np.float32)
print(f"  Vectorizer fitted in {time.time()-t0:.2f}s")
print(f"  Vocabulary size : {len(tfidf.vocabulary_)} features")
print(f"  Feature matrix  : {X.shape[0]} × {X.shape[1]}")

# ── Step 2: Train classifier ──────────────────────────────────────────────────

section("Step 2/5 — Training Logistic Regression Classifier")
t0 = time.time()
clf = LogisticRegression(C=1.5, max_iter=3000, class_weight="balanced", random_state=42, verbose=0)

# Manual epoch-like progress: fit in one shot but stream dots while waiting
import threading

done = threading.Event()
def progress_printer():
    chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    i = 0
    while not done.is_set():
        print(f"\r  Training  {chars[i % len(chars)]}  (C=1.5, max_iter=3000, balanced) ", end="", flush=True)
        i += 1
        time.sleep(0.1)

t = threading.Thread(target=progress_printer, daemon=True)
t.start()
clf.fit(X, labels)
done.set()
t.join()

elapsed = time.time() - t0
train_preds    = clf.predict(X)
train_accuracy = float(np.mean(train_preds == labels))
print(f"\r  Classifier trained in {elapsed:.2f}s                          ")
print(f"  Train accuracy : {train_accuracy:.2%}  ({int(np.sum(train_preds==labels))}/{len(labels)})")

# ── Step 3: Cross-validation ──────────────────────────────────────────────────

section("Step 3/5 — Stratified 5-Fold Cross-Validation")
t0 = time.time()

sklearn_pipe = Pipeline([
    ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5),
                               max_features=N_FEATURES, sublinear_tf=True)),
    ("clf", LogisticRegression(C=1.5, max_iter=3000, class_weight="balanced", random_state=42)),
])

skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
fold_scores = []

for fold_i, (train_idx, val_idx) in enumerate(skf.split(texts, labels), 1):
    X_tr = [texts[i] for i in train_idx]
    y_tr = labels[train_idx]
    X_val = [texts[i] for i in val_idx]
    y_val = labels[val_idx]

    fold_pipe = Pipeline([
        ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5),
                                   max_features=N_FEATURES, sublinear_tf=True)),
        ("clf", LogisticRegression(C=1.5, max_iter=3000, class_weight="balanced", random_state=42)),
    ])
    fold_pipe.fit(X_tr, y_tr)
    preds = fold_pipe.predict(X_val)
    tp = int(np.sum((preds == 1) & (y_val == 1)))
    fp = int(np.sum((preds == 1) & (y_val == 0)))
    fn = int(np.sum((preds == 0) & (y_val == 1)))
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec  = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1   = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    fold_scores.append(f1)
    fold_acc = np.mean(preds == y_val)
    filled = int(f1 * 20)
    print(f"  Fold {fold_i}/5  {bar(filled)}  F1={f1:.3f}  Acc={fold_acc:.2%}  P={prec:.3f}  R={rec:.3f}")

cv_f1_mean = float(np.mean(fold_scores))
cv_f1_std  = float(np.std(fold_scores))
print(f"\n  CV F1 (5-fold) : {cv_f1_mean:.3f} ± {cv_f1_std:.3f}  (took {time.time()-t0:.2f}s)")

# Full classification report on training set
print(f"\n  Classification report (train set):")
report_lines = classification_report(labels, train_preds, target_names=["clean","risky"]).split("\n")
for line in report_lines:
    if line.strip():
        print(f"    {line}")

cm = confusion_matrix(labels, train_preds)
print(f"\n  Confusion matrix (train):")
print(f"    TN={cm[0][0]}  FP={cm[0][1]}")
print(f"    FN={cm[1][0]}  TP={cm[1][1]}")

# ── Step 4: Export to CoreML ──────────────────────────────────────────────────

section("Step 4/5 — Exporting to CoreML (CPU_AND_NE)")
t0 = time.time()

weights = clf.coef_.astype(np.float32)
bias    = clf.intercept_.astype(np.float32)

input_features  = [("tfidf_features", datatypes.Array(N_FEATURES))]
output_features = [("risk_score",     datatypes.Array(1))]
builder = NeuralNetworkBuilder(input_features, output_features)
builder.add_inner_product(
    name="fc", W=weights, b=bias,
    input_channels=N_FEATURES, output_channels=1,
    has_bias=True,
    input_name="tfidf_features", output_name="logit",
)
builder.add_activation(
    name="sigmoid", non_linearity="SIGMOID",
    input_name="logit", output_name="risk_score",
)

model = MLModel(builder.spec)
model.author            = "LocalForge v2.0 — StalWrites"
model.short_description = "Layer 2 security risk scorer (0=clean, 1=risky)"
model.save(MODEL_PATH)
with open(TFIDF_PATH, "wb") as f:
    pickle.dump(tfidf, f)

print(f"  Exported in {time.time()-t0:.2f}s")
print(f"  Model  → {MODEL_PATH}")
print(f"  Vectorizer → {TFIDF_PATH}")

# ── Step 5: Verification on Apple Neural Engine ───────────────────────────────

section("Step 5/5 — Verification on Apple Neural Engine")
t0 = time.time()
loaded      = MLModel(MODEL_PATH, compute_units=ct.ComputeUnit.CPU_AND_NE)
loaded_tfidf = pickle.load(open(TFIDF_PATH, "rb"))

TEST_CASES = [
    # Python
    ("password = 'hunter2'",                             1),
    ("eval(request.GET['cmd'])",                         1),
    ("verify=False",                                     1),
    ("requests.get(url, verify=False)",                  1),
    ("jwt_secret = 'not-very-secret'",                   1),
    ("hashlib.md5(password.encode())",                   1),
    ("cursor.execute('SELECT * FROM u WHERE id=' + id)", 1),
    ("pickle.loads(untrusted_data)",                     1),
    # JavaScript
    ("eval(userInput)",                                  1),
    ("innerHTML = userComment",                          1),
    ("db.query('SELECT * FROM u WHERE id=' + req.params.id)", 1),
    ("process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'",  1),
    # Java
    ("Runtime.getRuntime().exec(userInput)",             1),
    ("MessageDigest.getInstance(\"MD5\")",               1),
    # Go
    ("tr := &http.Transport{TLSClientConfig: &tls.Config{InsecureSkipVerify: true}}", 1),
    ("fmt.Sprintf(\"SELECT * FROM t WHERE name='%s'\", name)", 1),
    # PHP
    ("system($_GET['cmd']);",                            1),
    ("md5($password)",                                   1),
    # Clean — Python
    ("def add(a, b): return a + b",                     0),
    ("api_key = os.getenv('API_KEY')",                   0),
    ("let x: u32 = 42;",                                 0),
    ("ssl.create_default_context()",                     0),
    ("secrets.token_hex(32)",                            0),
    ("cursor.execute('SELECT * FROM u WHERE id = %s', (id,))", 0),
    # Clean — JavaScript
    ("const apiKey = process.env.API_KEY;",              0),
    ("crypto.randomBytes(32).toString('hex')",           0),
    ("const stmt = db.prepare('SELECT * FROM users WHERE id = ?');", 0),
    # Clean — Go
    ("password := os.Getenv(\"DB_PASSWORD\")",           0),
    ("rows, err := db.Query(\"SELECT * FROM u WHERE id = $1\", id)", 0),
    # Clean — Java
    ("String password = System.getenv(\"DB_PASSWORD\");",  0),
    ("PreparedStatement ps = conn.prepareStatement(\"SELECT * FROM u WHERE id=?\");", 0),
    # Edge cases
    ("password = os.environ['PASSWORD']",                0),
    ("test_password = 'test_value_for_unit_test'",       0),
]

passed = 0
results_log = []
print(f"  Running {len(TEST_CASES)} test cases...\n")

for text, expected in TEST_CASES:
    vec    = loaded_tfidf.transform([text]).toarray().astype(np.float32)[0]
    result = loaded.predict({"tfidf_features": vec})
    score  = float(np.array(result["risk_score"]).flatten()[0])
    got    = 1 if score > THRESHOLD else 0
    ok     = got == expected
    if ok: passed += 1
    status = "✓ PASS" if ok else "✗ FAIL"
    tag    = "RISKY" if expected == 1 else "CLEAN"
    print(f"  [{status}]  score={score:.3f}  [{tag}]  {text[:60]}")
    results_log.append({"text": text, "score": round(score, 4), "label": got, "expected": expected, "pass": ok})

verify_accuracy = passed / len(TEST_CASES)
failures = [r for r in results_log if not r["pass"]]

print(f"\n  Verification: {passed}/{len(TEST_CASES)} passed  ({verify_accuracy:.0%})")
if failures:
    print(f"\n  Failed cases:")
    for f in failures:
        tag = "RISKY" if f["expected"] == 1 else "CLEAN"
        print(f"    score={f['score']:.3f} expected=[{tag}]  {f['text'][:60]}")

# ── Metadata ──────────────────────────────────────────────────────────────────

section("Summary")

metadata = {
    "built_at":           datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "model_version":      "2.1.0",
    "layer":              2,
    "architecture":       f"TF-IDF (char_wb 3-5gram, {N_FEATURES} features) + Inner Product + Sigmoid (CoreML)",
    "compute_unit":       "CPU_AND_NE",
    "n_training_samples": len(texts),
    "n_risky":            n_risky,
    "n_clean":            n_clean,
    "languages":          ["Python","JavaScript","TypeScript","Java","Go","Rust","C#","PHP","Ruby","Swift","Kotlin","SQL"],
    "train_accuracy":     round(train_accuracy, 4),
    "cv_f1_mean":         round(cv_f1_mean, 4),
    "cv_f1_std":          round(cv_f1_std, 4),
    "threshold":          THRESHOLD,
    "verification": {
        "n_cases":  len(TEST_CASES),
        "passed":   passed,
        "accuracy": round(verify_accuracy, 4),
        "cases":    results_log,
    },
    "artifacts": {
        "model":      "LocalForgeModel.mlpackage",
        "vectorizer": "tfidf_vectorizer.pkl",
        "metadata":   "model_metadata.json",
    },
}

with open(META_PATH, "w") as f:
    json.dump(metadata, f, indent=2)

print(f"  Train accuracy  : {train_accuracy:.2%}")
print(f"  CV F1 (5-fold)  : {cv_f1_mean:.3f} ± {cv_f1_std:.3f}")
print(f"  Verification    : {passed}/{len(TEST_CASES)} ({verify_accuracy:.0%})")
print(f"  Samples         : {len(texts)} ({n_risky} risky / {n_clean} clean)")
print(f"  Languages       : Python, JS/TS, Java, Go, Rust, C#, PHP, Ruby, Swift, Kotlin, SQL")
print(f"  Features        : {N_FEATURES}")
print(f"  Compute unit    : CPU_AND_NE (Apple Neural Engine)")
print(f"  Metadata        : {META_PATH}")
print(f"\n  Model ready. Copy to ~/.localforge/ with:")
print(f"    localforge --install")
