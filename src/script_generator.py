import json
import re
from pathlib import Path
from google.genai import types

from src.config import (
    INPUT_DIR,
    OUTPUT_DIR,
    get_edition_dir,
    get_genai_client,
    GEMINI_DEFAULT_MODEL,
    MAX_API_RETRIES,
    PODCAST_LANGUAGE_ES,
    PODCAST_LANGUAGE_EN,
    PODCAST_MAX_DURATION_MINUTES,
)


def load_news_data(input_file: Path = None) -> dict:
    """Load news input data from JSON file (defaulting to current_news.json then sample_news.json)."""
    if input_file is None:
        input_file = INPUT_DIR / "current_news.json"
        if not input_file.exists():
            input_file = INPUT_DIR / "sample_news.json"

    if not input_file.exists():
        raise FileNotFoundError(f"Input news file not found at: {input_file}")

    with open(input_file, "r", encoding="utf-8") as f:
        return json.load(f)


def post_process_tts_text(text: str) -> str:
    """Normalize and convert technical terms, numbers, dates, and acronyms into natural Spanish words for TTS."""
    months_es = {
        "01": "enero", "02": "febrero", "03": "marzo", "04": "abril",
        "05": "mayo", "06": "junio", "07": "julio", "08": "agosto",
        "09": "septiembre", "10": "octubre", "11": "noviembre", "12": "diciembre"
    }

    def date_replacer(match):
        year, month, day = match.group(1), match.group(2), match.group(3)
        day_int = int(day)
        month_str = months_es.get(month, "")
        return f"{day_int} de {month_str} de dos mil veintiséis"

    text = re.sub(r'(\d{4})-(\d{2})-(\d{2})', date_replacer, text)

    version_map = {
        "1.5": "uno punto cinco",
        "2.5": "dos punto cinco",
        "3.1": "tres punto uno",
        "3.0": "tres punto cero",
        "4.0": "cuatro punto cero",
        "4.5": "cuatro punto cinco",
    }
    for ver_str, word_str in version_map.items():
        text = text.replace(ver_str, word_str)

    acronym_map = {
        " LLMs": " modelos de lenguaje",
        " LLM": " modelo de lenguaje",
        " APIs": " A P Is",
        " API": " A P I",
        " GUIs": " interfaces gráficas",
        " GUI": " interfaz gráfica",
        " GCP": " Google Cloud",
        " MoE": " mezcla de expertos",
        " PoC": " prueba de concepto",
    }
    for acr, expansion in acronym_map.items():
        text = re.sub(r'\b' + re.escape(acr.strip()) + r'\b', expansion.strip(), text)

    return text


def format_spanish_date(date_str: str) -> str:
    """Convert a YYYY-MM-DD date string into a natural Spanish verbal date string.
    Example: '2026-08-05' -> 'agosto cinco de dos mil veintiséis'
    """
    try:
        from datetime import datetime
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        months = {
            1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
            7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
        }
        day_names = {
            1: "uno", 2: "dos", 3: "tres", 4: "cuatro", 5: "cinco", 6: "seis", 7: "siete",
            8: "ocho", 9: "nueve", 10: "diez", 11: "once", 12: "doce", 13: "trece", 14: "catorce",
            15: "quince", 16: "dieciséis", 17: "diecisiete", 18: "dieciocho", 19: "diecinueve",
            20: "veinte", 21: "veintiuno", 22: "veintidós", 23: "veintitres", 24: "veinticuatro",
            25: "veinticinco", 26: "veintiséis", 27: "veintisiete", 28: "veintiocho", 29: "veintinueve",
            30: "treinta", 31: "treinta y uno"
        }
        day_word = "primero" if dt.day == 1 else day_names.get(dt.day, str(dt.day))
        month_word = months.get(dt.month, "")
        year_word = "dos mil veintiséis" if dt.year == 2026 else str(dt.year)
        return f"{month_word} {day_word} de {year_word}"
    except Exception:
        return date_str


def build_spanish_prompt(news_data: dict) -> str:
    """Build prompt to generate a fast-paced, analytical, and conversational Latin American Spanish monologue script optimized for TTS."""
    items = news_data.get("items", [])
    edition_date = news_data.get("edition_date", "reciente")
    verbal_date = format_spanish_date(edition_date)
    is_slow_week = news_data.get("is_slow_week", False)

    news_text = ""
    for idx, item in enumerate(items, 1):
        news_text += f"\n--- Noticia {idx} ---\n"
        news_text += f"Título: {item.get('title')}\n"
        news_text += f"Categoría: {item.get('category')}\n"
        news_text += f"Resumen: {item.get('summary')}\n"
        news_text += f"Por qué importa: {item.get('why_it_matters', '')}\n"
        takeaways = ", ".join(item.get("key_takeaways", []))
        news_text += f"Puntos clave: {takeaways}\n"

    slow_week_instruction = ""
    if is_slow_week:
        slow_week_instruction = """
NOTA DE SEMANA TRANQUILA: Esta semana ha habido pocos lanzamientos mayores en los laboratorios de IA.
Menciona con agilidad que es una semana de consolidación en la frontera tecnológica y realiza un análisis conciso y dinámico de 1 a 2 minutos sobre las tendencias activas. Mantén el episodio corto y directo.
"""

    prompt = f"""
Eres un locutor y analista experto en Inteligencia Artificial y tecnología de frontera.
Tu tarea es redactar el guion completo para el podcast semanal "Frontier Pulse" en formato MONÓLOGO en ESPAÑOL LATINOAMERICANO.

DATOS DEL PODCAST:
- Nombre del programa: Frontier Pulse
- Fecha de edición: {verbal_date} ({edition_date})
- Idioma: Español latinoamericano (natural, ágil, conversacional).
- Duración máxima: {PODCAST_MAX_DURATION_MINUTES} minutos (aproximadamente 350 a 650 palabras).
- Formato: Monólogo de un solo locutor.
{slow_week_instruction}

NOTICIAS A INCLUIR:
{news_text}

ESTILO Y TONO EDITORIAL:
- Redacta un guion de noticias de tecnología en un estilo rápido, analítico y conversacional.
- Comienza con un gancho de apertura contundente que presente el anuncio o desarrollo como algo sorprendente, estratégicamente decisivo o parte de una carrera tecnológica global.
- Explica las noticias con claridad y respalda el análisis con datos concretos: fechas específicas, benchmarks, porcentajes, precios y comparaciones técnicas.
- Dirígete directamente a la audiencia con preguntas retóricas, oraciones concisas y transiciones fluidas.
- Ve más allá de repetir los hechos: explica lo que cada anuncio significa para las empresas involucradas, sus competidores, la comunidad de desarrolladores y el mercado tecnológico en general.
- Mantén un tono seguro pero equilibrado. Destaca tanto fortalezas como debilidades o limitaciones, evita afirmaciones exageradas y distingue con claridad entre hechos verificados e interpretaciones.
- Incorpora toques sutiles de ironía o humor ligero e inteligente, manteniendo siempre una narración informativa y profesional.
- NO incluyas menciones de patrocinio o publicidad bajo ninguna circunstancia.

ESTRUCTURA DE ORGANIZACIÓN DEL GUION:
1. Gancho de apertura (Opening hook)
2. Anuncio principal y contexto (Main announcement)
3. Rendimiento técnico y detalles del producto o modelo (Technical performance and product details)
4. Comparaciones con competidores clave (Comparisons with competitors)
5. Implicaciones comerciales y estratégicas (Business and strategic implications)
6. Tendencia más amplia de la industria (Broader industry trend)
7. Conclusión concisa y pregunta de reflexión para la audiencia (Concise conclusion and question for the audience)

REGLAS FONÉTICAS Y DE TEXT-TO-SPEECH (TTS):
- Mantén la extensión total entre 380 y 520 palabras para garantizar un ritmo ágil y dinámico (aproximadamente 3 a 4 minutos de locución).
- Escribe TODAS las fechas completamente en letras (ej. "{verbal_date}" o "diecisiete de agosto").
- Escribe los números de versión en palabras (ej. "tres punto siete", "dos punto cinco", "cuatro punto cero").
- Escribe cifras, porcentajes y precios en palabras (ej. "veinte por ciento", "cien millones de dólares", "tres modelos").
- Escribe los años en palabras (ej. "dos mil veintiséis").
- Escribe siglas expandidas o legibles (ej. "inteligencia artificial", "modelos de lenguaje", "A P I", "Google Cloud").
- Escribe ÚNICAMENTE el texto plano que será pronunciado. NO agregues corchetes, paréntesis con efectos de sonido, acotaciones ni etiquetas de locutor.

Genera el guion completo en español latinoamericano a continuación:
"""
    return prompt.strip()


def build_english_prompt(spanish_script: str, news_data: dict) -> str:
    """Build prompt to generate the English transcript matching the Spanish script with identical analytical tone and structure."""
    edition_date = news_data.get("edition_date", "recent")

    prompt = f"""
You are an expert tech journalist, AI communicator, and translator.
Translate and adapt the following Latin American Spanish podcast script for 'Frontier Pulse' (Edition: {edition_date}) into a natural, fast-paced, analytical, and engaging English podcast transcript.

Original Spanish Script:
{spanish_script}

INSTRUCTIONS:
1. Match the fast-paced, analytical, confident, and conversational style of the original script.
2. Maintain the structure: Opening hook, Main announcement, Technical details & benchmarks, Competitor comparisons, Strategic implications, Industry trends, and Concise concluding question.
3. Preserve all specific metrics, benchmarks, dates, percentages, and balanced technical critiques.
4. Do NOT include stage directions, music cues, sound effects, or speaker labels in brackets or parentheses.
5. Provide ONLY the clean spoken English transcript.
"""
    return prompt.strip()


def generate_podcast_script(input_filename: str = None) -> tuple[Path, Path]:
    """Generate both Spanish (Latin America) and English podcast transcripts using Gemini API, normalized for TTS."""
    input_path = None
    if input_filename:
        input_path = INPUT_DIR / input_filename

    news_data = load_news_data(input_path)
    client = get_genai_client()

    # 1. Generate Spanish (Latin America) Script
    print(f"[*] Generating Latin American Spanish podcast script with Gemini ({GEMINI_DEFAULT_MODEL})...")
    es_prompt = build_spanish_prompt(news_data)
    
    es_models = [GEMINI_DEFAULT_MODEL]
    if "gemini-2.5-flash" not in es_models:
        es_models.append("gemini-2.5-flash")
    es_models = es_models[:MAX_API_RETRIES]

    es_response = None
    last_error_es = None
    for attempt_idx, model_name in enumerate(es_models, start=1):
        try:
            es_response = client.models.generate_content(
                model=model_name,
                contents=es_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    top_p=0.9,
                )
            )
            break
        except Exception as e:
            if last_error_es is None or str(e).strip():
                last_error_es = e
            err_summary = str(e).split("\n")[0][:120]
            print(f"[!] Spanish script generation attempt {attempt_idx}/{len(es_models)} ({model_name}) failed: {err_summary}")

    if es_response is None:
        if last_error_es:
            raise last_error_es
        raise RuntimeError("Failed to generate Spanish podcast script after exhausting all retry attempts.")

    raw_script_es = es_response.text.strip()

    # Post-process script to ensure 100% human-readable phonetic text for TTS
    script_es = post_process_tts_text(raw_script_es)

    # Save Spanish script files
    edition_date = news_data.get("edition_date", "recent")
    edition_dir = get_edition_dir(edition_date)
    
    es_txt_path = edition_dir / "podcast_script_es.txt"
    es_txt_path_generic = OUTPUT_DIR / "podcast_script_es.txt"
    with open(es_txt_path, "w", encoding="utf-8") as f:
        f.write(script_es)
    with open(es_txt_path_generic, "w", encoding="utf-8") as f:
        f.write(script_es)

    es_json_path = edition_dir / "podcast_script_es.json"
    es_json_path_generic = OUTPUT_DIR / "podcast_script_es.json"
    es_data = {
        "title": news_data.get("title", "Frontier Pulse Podcast"),
        "edition_date": edition_date,
        "language": PODCAST_LANGUAGE_ES,
        "format": "monologue",
        "word_count": len(script_es.split()),
        "script": script_es,
    }
    with open(es_json_path, "w", encoding="utf-8") as f:
        json.dump(es_data, f, ensure_ascii=False, indent=2)
    with open(es_json_path_generic, "w", encoding="utf-8") as f:
        json.dump(es_data, f, ensure_ascii=False, indent=2)

    print(f"[+] Spanish TTS-normalized script generated successfully ({es_data['word_count']} words).")
    print(f"[+] Saved to: {es_txt_path}")

    # 2. Generate English Transcript
    en_txt_path = edition_dir / "podcast_script_en.txt"
    en_txt_path_generic = OUTPUT_DIR / "podcast_script_en.txt"

    try:
        print(f"[*] Generating English transcript with Gemini ({GEMINI_DEFAULT_MODEL})...")
        en_prompt = build_english_prompt(script_es, news_data)
        
        en_models = [GEMINI_DEFAULT_MODEL]
        if "gemini-2.5-flash" not in en_models:
            en_models.append("gemini-2.5-flash")
        en_models = en_models[:MAX_API_RETRIES]

        en_response = None
        last_error = None
        for attempt_idx, model_name in enumerate(en_models, start=1):
            try:
                en_response = client.models.generate_content(
                    model=model_name,
                    contents=en_prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.5,
                        top_p=0.9,
                    )
                )
                break
            except Exception as e:
                if last_error is None or str(e).strip():
                    last_error = e
                err_summary = str(e).split("\n")[0][:120]
                print(f"[!] English script generation attempt {attempt_idx}/{len(en_models)} ({model_name}) failed: {err_summary}")

        if en_response is None:
            if last_error:
                raise last_error
            raise RuntimeError("English transcript generation failed after all attempts.")
        script_en = en_response.text.strip()

        # Save English script files
        with open(en_txt_path, "w", encoding="utf-8") as f:
            f.write(script_en)
        with open(en_txt_path_generic, "w", encoding="utf-8") as f:
            f.write(script_en)

        en_json_path = edition_dir / "podcast_script_en.json"
        en_json_path_generic = OUTPUT_DIR / "podcast_script_en.json"
        en_data = {
            "title": news_data.get("title", "Frontier Pulse Podcast"),
            "edition_date": edition_date,
            "language": PODCAST_LANGUAGE_EN,
            "format": "monologue",
            "word_count": len(script_en.split()),
            "script": script_en,
        }
        with open(en_json_path, "w", encoding="utf-8") as f:
            json.dump(en_data, f, ensure_ascii=False, indent=2)
        with open(en_json_path_generic, "w", encoding="utf-8") as f:
            json.dump(en_data, f, ensure_ascii=False, indent=2)

        print(f"[+] English transcript generated successfully ({en_data['word_count']} words).")
        print(f"[+] Saved to: {en_txt_path}")

    except Exception as e:
        print(f"[!] Warning: Failed to generate English transcript: {e}")
        print("[*] Proceeding with Spanish-only script/audio flow (FP-013).")
        fallback_msg = f"English transcript generation failed or was skipped for this edition.\nError: {e}"
        with open(en_txt_path, "w", encoding="utf-8") as f:
            f.write(fallback_msg)
        with open(en_txt_path_generic, "w", encoding="utf-8") as f:
            f.write(fallback_msg)

    return es_txt_path, en_txt_path


if __name__ == "__main__":
    generate_podcast_script()
