"""API di esempio con FastAPI: una lista di cose da fare, tenuta in memoria.

Avvio: python -m uvicorn main:app --reload   poi apri http://127.0.0.1:8000/docs
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="La mia API")


class NewTodo(BaseModel):
    text: str


class Todo(NewTodo):
    id: int
    done: bool = False


todos: dict[int, Todo] = {}


@app.get("/")
def home() -> dict[str, str]:
    return {"message": "Ciao! Apri /docs per provare l'API"}


@app.get("/todos")
def list_todos() -> list[Todo]:
    return list(todos.values())


@app.post("/todos", status_code=201)
def add_todo(item: NewTodo) -> Todo:
    todo = Todo(id=max(todos, default=0) + 1, text=item.text)
    todos[todo.id] = todo
    return todo


@app.post("/todos/{todo_id}/done")
def complete_todo(todo_id: int) -> Todo:
    if todo_id not in todos:
        raise HTTPException(status_code=404, detail="cosa da fare non trovata")
    todos[todo_id].done = True
    return todos[todo_id]
