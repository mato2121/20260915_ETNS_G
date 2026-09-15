import os
from datetime import datetime

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from werkzeug.security import check_password_hash, generate_password_hash

try:
    from supabase import create_client
except ImportError:  # pragma: no cover - 로컬에 supabase 패키지가 없어도 앱은 정상 동작해야 함
    create_client = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)

# Supabase(Postgres) 연결 정보가 환경변수 DATABASE_URL 로 주어지면 그것을 사용하고,
# 없으면 로컬 개발용으로 SQLite 파일을 사용합니다.
database_url = os.environ.get("DATABASE_URL")

if database_url:
    # Supabase/Heroku 등에서 주는 "postgres://" 스킴은 SQLAlchemy 2.x에서 인식하지 못해
    # "postgresql+psycopg2://" 로 바꿔줘야 합니다.
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
elif os.environ.get("VERCEL"):
    # Vercel 서버리스는 배포 디렉터리가 읽기 전용이라 /tmp 에만 쓸 수 있고,
    # 그마저도 인스턴스가 재시작되면 초기화됩니다(DATABASE_URL 미설정 시 임시 동작용).
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:////tmp/todo.db"
else:
    db_path = os.path.join(BASE_DIR, "todo.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# 로그인 세션 쿠키를 서명하는 데 쓰이는 키. Vercel처럼 인스턴스가 여러 개 뜨는 환경에서는
# 반드시 환경변수 SECRET_KEY로 고정값을 줘야 로그인이 유지됩니다(안 주면 매번 랜덤 생성).
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", os.urandom(32))

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = "로그인이 필요합니다."
login_manager.init_app(app)

# ---------------------------------------------------------------------------
# Supabase Data API (REST) 클라이언트
# 할 일 CRUD 자체는 위의 SQLAlchemy(직접 Postgres 연결)로 처리하고,
# 이 클라이언트는 Supabase의 API 방식도 실제로 쓰고 있음을 보여주는 용도입니다.
# SUPABASE_URL / SUPABASE_ANON_KEY 환경변수가 없으면 그냥 비활성 상태로 둡니다.
# ---------------------------------------------------------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_KEY")

supabase_client = None
if create_client and SUPABASE_URL and SUPABASE_ANON_KEY:
    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    except Exception:
        supabase_client = None


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)


class Todo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    done = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


with app.app_context():
    db.create_all()
    # 기존에 user_id 컬럼 없이 만들어졌던 todo 테이블에 로그인 기능 추가로 컬럼을 보강합니다.
    inspector = inspect(db.engine)
    if "todo" in inspector.get_table_names():
        existing_columns = {c["name"] for c in inspector.get_columns("todo")}
        if "user_id" not in existing_columns:
            with db.engine.begin() as conn:
                conn.execute(text("ALTER TABLE todo ADD COLUMN user_id INTEGER"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")

        error = None
        if len(username) < 3:
            error = "아이디는 3자 이상이어야 합니다."
        elif len(password) < 4:
            error = "비밀번호는 4자 이상이어야 합니다."
        elif password != password_confirm:
            error = "비밀번호가 서로 일치하지 않습니다."
        elif User.query.filter_by(username=username).first():
            error = "이미 사용 중인 아이디입니다."

        if error:
            flash(error)
            return render_template("register.html", username=username)

        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for("index"))

    return render_template("register.html", username="")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("index"))

        flash("아이디 또는 비밀번호가 올바르지 않습니다.")
        return render_template("login.html", username=username)

    return render_template("login.html", username="")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    filter_value = request.args.get("filter", "all")

    query = Todo.query.filter_by(user_id=current_user.id).order_by(Todo.created_at.desc())
    if filter_value == "active":
        query = query.filter_by(done=False)
    elif filter_value == "done":
        query = query.filter_by(done=True)

    todos = query.all()
    total = Todo.query.filter_by(user_id=current_user.id).count()
    active_count = Todo.query.filter_by(user_id=current_user.id, done=False).count()
    done_count = Todo.query.filter_by(user_id=current_user.id, done=True).count()

    return render_template(
        "index.html",
        todos=todos,
        filter_value=filter_value,
        total=total,
        active_count=active_count,
        done_count=done_count,
    )


@app.route("/add", methods=["POST"])
@login_required
def add():
    title = request.form.get("title", "").strip()
    if title:
        db.session.add(Todo(title=title, user_id=current_user.id))
        db.session.commit()
    return redirect(url_for("index", filter=request.form.get("filter", "all")))


@app.route("/toggle/<int:todo_id>", methods=["POST"])
@login_required
def toggle(todo_id):
    todo = Todo.query.filter_by(id=todo_id, user_id=current_user.id).first_or_404()
    todo.done = not todo.done
    db.session.commit()
    return redirect(url_for("index", filter=request.args.get("filter", "all")))


@app.route("/edit/<int:todo_id>", methods=["POST"])
@login_required
def edit(todo_id):
    todo = Todo.query.filter_by(id=todo_id, user_id=current_user.id).first_or_404()
    title = request.form.get("title", "").strip()
    if title:
        todo.title = title
        db.session.commit()
    return redirect(url_for("index", filter=request.args.get("filter", "all")))


@app.route("/delete/<int:todo_id>", methods=["POST"])
@login_required
def delete(todo_id):
    todo = Todo.query.filter_by(id=todo_id, user_id=current_user.id).first_or_404()
    db.session.delete(todo)
    db.session.commit()
    return redirect(url_for("index", filter=request.args.get("filter", "all")))


@app.route("/clear_done", methods=["POST"])
@login_required
def clear_done():
    Todo.query.filter_by(user_id=current_user.id, done=True).delete()
    db.session.commit()
    return redirect(url_for("index", filter=request.args.get("filter", "all")))


@app.route("/api-status")
def api_status():
    """Supabase Data API(REST)로 todo 테이블을 직접 조회해보는 확인용 엔드포인트."""
    if not supabase_client:
        return jsonify(
            {
                "api_connected": False,
                "message": "SUPABASE_URL / SUPABASE_ANON_KEY 환경변수가 설정되어 있지 않습니다.",
            }
        ), 200

    try:
        result = supabase_client.table("todo").select("id", count="exact").execute()
        return jsonify(
            {
                "api_connected": True,
                "table": "todo",
                "row_count": result.count,
                "message": "Supabase Data API를 통해 정상적으로 조회했습니다.",
            }
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"api_connected": False, "error": str(exc)}), 500


if __name__ == "__main__":
    app.run(debug=True)
