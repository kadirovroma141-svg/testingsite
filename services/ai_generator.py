"""
AI Test Generator
Supports three backends: openai, gemini, local (Ollama/LM Studio).

Expected JSON output from LLM:
[
  {
    "text": "Вопрос?",
    "type": "single",
    "points": 1,
    "explanation": "...",
    "options": [
      {"text": "Вариант A", "is_correct": false},
      {"text": "Вариант B", "is_correct": true}
    ]
  }
]
"""
from __future__ import annotations
import json
import re
from flask import current_app


SYSTEM_PROMPT_TEMPLATE = (
    "You are an expert educator. Generate a JSON array of quiz questions.\n"
    "Rules:\n"
    '- Return ONLY a valid JSON array, no markdown, no explanations outside JSON.\n'
    '- Each question object must have keys: "text" (string), "type" ("single" or "multiple"), '
    '"points" (integer), "explanation" (string), "options" (array of objects with "text" and "is_correct").\n'
    '- "single" questions must have exactly 1 correct option.\n'
    '- "multiple" questions must have 2 to 4 correct options.\n'
    '- Minimum 4 options per question, maximum 6.\n'
    '- Language: LANG_PLACEHOLDER\n'
)


def _build_system_prompt(language: str) -> str:
    return SYSTEM_PROMPT_TEMPLATE.replace("LANG_PLACEHOLDER", language)


def _build_user_prompt(topic: str, difficulty: str, count: int, language: str) -> str:
    difficulty_map = {
        "easy":   "базового уровня для младших классов",
        "medium": "среднего уровня для старшей школы",
        "hard":   "повышенной сложности / олимпиадного уровня",
    }
    diff_desc = difficulty_map.get(difficulty, "среднего уровня")
    return (
        f"Создай {count} вопросов по теме «{topic}» "
        f"{diff_desc}. "
        f"Ответь строго в формате JSON-массива."
    )


def _extract_json(text: str) -> list:
    """Strip markdown fences and parse JSON."""
    text = text.strip()
    # Remove ```json ... ``` or ``` ... ```
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$",           "", text, flags=re.MULTILINE)
    parsed = json.loads(text)
    # Some models return {"questions": [...]}; unwrap if needed
    if isinstance(parsed, dict):
        if "questions" in parsed:
            parsed = parsed["questions"]
        else:
            parsed = list(parsed.values())[0]
    return parsed


# ------------------------------------------------------------------ OpenAI

def _generate_openai(prompt_user: str, system_prompt: str) -> list:
    from openai import OpenAI
    client = OpenAI(api_key=current_app.config["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model=current_app.config["OPENAI_MODEL"],
        messages=[
            {"role": "system",  "content": system_prompt},
            {"role": "user",    "content": prompt_user},
        ],
        temperature=0.7,
    )
    raw = resp.choices[0].message.content
    return _extract_json(raw)


# ------------------------------------------------------------------ Gemini

def _generate_gemini(prompt_user: str, system_prompt: str) -> list:
    import google.generativeai as genai
    genai.configure(api_key=current_app.config["GEMINI_API_KEY"])
    model = genai.GenerativeModel(
        model_name=current_app.config["GEMINI_MODEL"],
        system_instruction=system_prompt,
    )
    resp = model.generate_content(prompt_user)
    return _extract_json(resp.text)


# ------------------------------------------------------------------ Local LLM (Ollama / LM Studio)

def _generate_local(prompt_user: str, system_prompt: str) -> list:
    import requests
    url   = current_app.config["LOCAL_LLM_URL"]
    model = current_app.config["LOCAL_LLM_MODEL"]
    payload = {
        "model":  model,
        "prompt": system_prompt + "\n\n" + prompt_user,
        "stream": False,
        "format": "json",
    }
    resp = requests.post(url, json=payload, timeout=120)
    resp.raise_for_status()
    raw = resp.json().get("response", resp.text)
    return _extract_json(raw)


# ------------------------------------------------------------------ Public API

def generate_questions_json(
    topic: str,
    difficulty: str = "medium",
    count: int = 10,
    language: str = "ru",
) -> list:
    """
    Generate quiz questions via the configured AI provider.
    Returns a list of question dicts ready to be inserted into the DB.
    """
    provider      = current_app.config.get("AI_PROVIDER", "openai").lower()
    system_prompt = _build_system_prompt(language)
    prompt_user   = _build_user_prompt(topic, difficulty, count, language)

    generators = {
        "openai": _generate_openai,
        "gemini": _generate_gemini,
        "local":  _generate_local,
    }
    fn = generators.get(provider)
    if fn is None:
        raise ValueError(f"Unknown AI provider: {provider!r}. Choose openai/gemini/local.")

    questions = fn(prompt_user, system_prompt)

    if not isinstance(questions, list):
        raise ValueError("AI returned unexpected format (expected JSON array).")

    return questions[:count]
