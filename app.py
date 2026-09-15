from datetime import datetime

from flask import Flask, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///todo.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


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


if __name__ == "__main__":
    app.run(debug=True)
