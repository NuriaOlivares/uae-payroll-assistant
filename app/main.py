"""API: uvicorn app.main:app --reload  then open http://127.0.0.1:8000/docs"""
from fastapi import FastAPI
from pydantic import BaseModel

from app.answer import ask

app = FastAPI(title="UAE Payroll & Employment Assistant")


class Question(BaseModel):
    question: str


@app.post("/ask")
def ask_endpoint(q: Question):
    return ask(q.question)