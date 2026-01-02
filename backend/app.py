import io
import json
import re
import torch
import fitz
import pdfplumber

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from transformers import AutoTokenizer, AutoModelForCausalLM

# ===================== APP =====================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===================== MODEL =====================

MODEL_NAME = "microsoft/Phi-3-mini-4k-instruct"

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    torch_dtype=torch.float16,
    device_map="auto"
)
model.eval()

# Warm-up (important for first request speed)
_ = model.generate(
    **tokenizer("Hello", return_tensors="pt").to(model.device),
    max_new_tokens=5
)

# ===================== HELPERS =====================

def generate(prompt, max_tokens=800, temp=0.7):
    formatted = f"<|user|>\n{prompt}<|end|>\n<|assistant|>\n"
    inputs = tokenizer(formatted, return_tensors="pt").to(model.device)

    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            temperature=temp,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id
        )

    text = tokenizer.decode(out[0], skip_special_tokens=True)
    if "<|assistant|>" in text:
        text = text.split("<|assistant|>")[-1].strip()
    return text.strip()


def extract_json(text):
    if not text:
        return None

    obj = re.search(r'\{.*?\}', text, re.DOTALL)
    if obj:
        try:
            return json.loads(obj.group())
        except:
            pass

    arr = re.search(r'\[.*?\]', text, re.DOTALL)
    if arr:
        try:
            return json.loads(arr.group())
        except:
            pass

    return None


def extract_text_from_pdf(pdf_file):
    text = ""

    try:
        pdf_file.seek(0)
        doc = fitz.open(stream=pdf_file.read(), filetype="pdf")
        for page in doc:
            text += page.get_text()
        doc.close()
    except:
        pass

    try:
        pdf_file.seek(0)
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
    except:
        pass

    return text.strip()


def extract_resume_basic(text):
    data = {
        "name": "Unknown",
        "email": "",
        "phone": "",
        "skills": [],
        "experience": [],
        "projects": []
    }

    email = re.search(r'\b[\w.-]+@[\w.-]+\.\w+\b', text)
    if email:
        data["email"] = email.group()

    phone = re.search(r'[\+\(]?[0-9][0-9 \-\(\)]{8,}', text)
    if phone:
        data["phone"] = phone.group()

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for line in lines[:5]:
        if len(line.split()) <= 4:
            data["name"] = line
            break

    skills_list = [
        "python", "java", "javascript", "react", "sql", "aws",
        "docker", "machine learning", "deep learning", "nlp"
    ]

    text_lower = text.lower()
    data["skills"] = [s.title() for s in skills_list if s in text_lower]

    return data


def extract_resume(pdf_file):
    text = extract_text_from_pdf(pdf_file)
    if not text or len(text) < 30:
        raise ValueError("Could not extract text from resume")

    prompt = f"""
Extract resume info and return ONLY JSON.

{text[:2000]}

Format:
{{
  "name": "",
  "email": "",
  "phone": "",
  "skills": [],
  "experience": [],
  "projects": []
}}
JSON:
"""
    response = generate(prompt, temp=0.1)
    data = extract_json(response)

    if isinstance(data, dict) and data.get("name"):
        return data

    return extract_resume_basic(text)


def gen_questions(resume, num=5):
    prompt = f"""
Generate exactly {num} interview questions based on this resume.

{json.dumps(resume, indent=2)}

Return ONLY JSON array:
[
  {{"id":1,"question":"","focus":""}}
]
JSON:
"""
    response = generate(prompt)
    questions = extract_json(response)

    if isinstance(questions, list):
        for i, q in enumerate(questions):
            q["id"] = i + 1
        return questions[:num]

    return []


def gen_followup(question, answer):
    if len(answer.strip()) < 10:
        return "Could you explain more?"

    prompt = f"""
Generate ONE follow-up question.

Question: {question}
Answer: {answer}

Only the question:
"""
    return generate(prompt, max_tokens=100)


def evaluate(question, answer):
    prompt = f"""
Evaluate the answer and return JSON.

Question: {question}
Answer: {answer}

{{
  "technical_accuracy": 0,
  "completeness": 0,
  "practical_knowledge": 0,
  "communication": 0,
  "total_score": 0,
  "feedback": ""
}}
JSON:
"""
    response = generate(prompt, temp=0.2)
    data = extract_json(response)

    if isinstance(data, dict):
        return data

    return {
        "technical_accuracy": 10,
        "completeness": 10,
        "practical_knowledge": 10,
        "communication": 10,
        "total_score": 40,
        "feedback": "Answer evaluated."
    }


def final_report(evaluations):
    if not evaluations:
        return {"overall_score": 0, "performance_level": "No answers"}

    avg = sum(e["total_score"] for e in evaluations) / len(evaluations)
    level = "Excellent" if avg >= 80 else "Good" if avg >= 60 else "Average"

    return {
        "overall_score": round(avg, 2),
        "performance_level": level,
        "total_questions": len(evaluations)
    }

# ===================== API MODELS =====================

class ResumeInput(BaseModel):
    resume: dict

class AnswerInput(BaseModel):
    question: str
    answer: str

class FinalInput(BaseModel):
    evaluations: list

# ===================== API ENDPOINTS =====================

@app.post("/upload_resume")
async def upload_resume(file: UploadFile = File(...)):
    try:
        pdf_bytes = await file.read()
        pdf_file = io.BytesIO(pdf_bytes)
        resume = extract_resume(pdf_file)
        return {"resume": resume}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/generate_questions")
def generate_questions_api(data: ResumeInput):
    questions = gen_questions(data.resume, num=5)
    return {"questions": questions}


@app.post("/answer")
def answer_api(data: AnswerInput):
    return {
        "followup": gen_followup(data.question, data.answer),
        "evaluation": evaluate(data.question, data.answer)
    }


@app.post("/final_report")
def final_report_api(data: FinalInput):
    return final_report(data.evaluations)
