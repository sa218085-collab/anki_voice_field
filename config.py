from pathlib import Path


TARGET_FIELD_NAME = "Lecture Notes"
IMAGE_OCCLUSION_MODEL_HINTS = ("Image Occlusion",)
IMAGE_OCCLUSION_FALLBACK_FIELD_NAME = "Remarks"
DEFAULT_FALLBACK_FIELD_NAMES = ("Back", "Extra", "Back Extra", "Remarks")
HOTKEY = "<f8>"
ANKI_CONNECT_URL = "http://localhost:8765"
CONTROL_SERVER_HOST = "127.0.0.1"
CONTROL_SERVER_PORT = 47866
DRY_RUN_DEFAULT = False
AUDIO_TEMP_FILE = Path(__file__).with_name("voice_note_temp.wav")
LOG_FILE = Path(__file__).with_name("anki_voice_field.log")
VOICE_NOTES_LOG_FILE = Path(__file__).with_name("voice_notes_log.txt")
INSTANCE_LOCK_PORT = 47865
SHOW_TRANSCRIPT_POPUP = True
TRANSCRIPT_POPUP_SECONDS = 8
REVIEW_TRANSCRIPT_BEFORE_WRITE_DEFAULT = True
SAVE_RETRY_ATTEMPTS = 3
POST_SAVE_VERIFY_TIMEOUT_SECONDS = 10.0
POST_SAVE_VERIFY_POLL_SECONDS = 1.0
POST_SAVE_STABLE_SECONDS = 2.0
WAIT_FOR_TARGET_CARD_CHANGE_SECONDS = 5.0
FAST_MODE_WAIT_FOR_CARD_CHANGE_SECONDS = None
WAIT_FOR_TARGET_CARD_CHANGE_POLL_SECONDS = 0.5
FIELDS_THAT_REQUIRE_CARD_CHANGE_BEFORE_SAVE = (
    "Lecture Notes",
    "Remarks",
    "Back",
    "Extra",
    "Back Extra",
)

SAMPLE_RATE = 16_000
CHANNELS = 1

WHISPER_MODEL_SIZE = "base"
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"
WHISPER_LANGUAGE = "en"
WHISPER_BEAM_SIZE = 1
PRELOAD_WHISPER_MODEL = True

MEDICAL_TRANSCRIPTION_MODE = True
MEDICAL_TRANSCRIPTION_PROMPT = (
    "Transcribe this as a medical education note. Prefer accurate medical "
    "terminology, anatomy, physiology, pathology, pharmacology, lab values, "
    "disease names, medication names, and standard clinical abbreviations. "
    "Do not replace medical terms with similar-sounding everyday words."
)
MEDICAL_GLOSSARY = (
    "acetylcholine",
    "acidosis",
    "alkalosis",
    "anemia",
    "angina",
    "arrhythmia",
    "asthma",
    "atrial fibrillation",
    "autoimmune",
    "beta blocker",
    "bicarbonate",
    "bradycardia",
    "calcium",
    "chloride",
    "contraindication",
    "COPD",
    "corticosteroid",
    "creatinine",
    "diabetes mellitus",
    "diabetic ketoacidosis",
    "differential diagnosis",
    "dopamine",
    "epinephrine",
    "GFR",
    "glomerulus",
    "glucose",
    "heart failure",
    "hepatic",
    "hyperkalemia",
    "hypernatremia",
    "hypertension",
    "hypokalemia",
    "hyponatremia",
    "hypotension",
    "infarction",
    "inflammation",
    "insulin",
    "ischemia",
    "jaundice",
    "leukocytosis",
    "mechanism of action",
    "metabolic acidosis",
    "myocardial infarction",
    "nephron",
    "norepinephrine",
    "NSAID",
    "osmolality",
    "pathophysiology",
    "pharmacology",
    "pneumonia",
    "potassium",
    "pulmonary embolism",
    "renal",
    "respiratory acidosis",
    "sepsis",
    "serotonin",
    "sodium",
    "tachycardia",
    "thrombocytopenia",
)
