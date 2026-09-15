import os
from datetime import datetime

from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy

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

db = SQLAlchemy(app)

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


class Todo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    done = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


with app.app_context():
    db.create_all()


@app.route("/")
def index():
    filter_value = request.args.get("filter", "all")

    query = Todo.query.order_by(Todo.created_at.desc())
    if filter_value == "active":
        query = query.filter_by(done=False)
    elif filter_value == "done":
        query = query.filter_by(done=True)

    todos = query.all()
    total = Todo.query.count()
    active_count = Todo.query.filter_by(done=False).count()
    done_count = Todo.query.filter_by(done=True).count()

    return render_template(
        "index.html",
        todos=todos,
        filter_value=filter_value,
        total=total,
        active_count=active_count,
        done_count=done_count,
    )


@app.route("/add", methods=["POST"])
def add():
    title = request.form.get("title", "").strip()
    if title:
        db.session.add(Todo(title=title))
        db.session.commit()
    return redirect(url_for("index", filter=request.form.get("filter", "all")))


@app.route("/toggle/<int:todo_id>", methods=["POST"])
def toggle(todo_id):
    todo = Todo.query.get_or_404(todo_id)
    todo.done = not todo.done
    db.session.commit()
    return redirect(url_for("index", filter=request.args.get("filter", "all")))


@app.route("/edit/<int:todo_id>", methods=["POST"])
def edit(todo_id):
    todo = Todo.query.get_or_404(todo_id)
    title = request.form.get("title", "").strip()
    if title:
        todo.title = title
        db.session.commit()
    return redirect(url_for("index", filter=request.args.get("filter", "all")))


@app.route("/delete/<int:todo_id>", methods=["POST"])
def delete(todo_id):
    todo = Todo.query.get_or_404(todo_id)
    db.session.delete(todo)
    db.session.commit()
    return redirect(url_for("index", filter=request.args.get("filter", "all")))


@app.route("/clear_done", methods=["POST"])
def clear_done():
    Todo.query.filter_by(done=True).delete()
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
