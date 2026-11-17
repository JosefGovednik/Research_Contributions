from flask import Flask, request, jsonify
from vosk import Model, KaldiRecognizer
from ollama import chat
from pathlib import Path
import wave
import json
import os
import warnings

warnings.filterwarnings("ignore", category=RuntimeWarning)

app = Flask(__name__) #Initialize Flask app.
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 #Set max content length to 16MB.

BASE_DIR = Path(__file__).resolve().parent
VOSK_MODEL_PATH = BASE_DIR / "vosk"
vosk_model = Model(str(VOSK_MODEL_PATH)) #Load Vosk model from the script directory.
PROMPT = """
You are controlling a NAO robot.
Determine the user's current emotion based on what they say, and respond accordingly with only one emotion from below:

explaining | thinking | happy | encouraging | disappointed | correct | incorrect | sorry | confused | waiting | defiant | unsure

, one corresponding action to that emotion from newtt_actions.py, and send a reply. Your reply should acknowledge wht the user said and be consistent with the detected emotion.
If given a question, use its correctness to guide your response and emotion selection.
The reply will be the text answer you provide.

Return ONLY JSON of the emotion, action, and reply. Do not include any other text or explanation.
"""

@app.route('/upload', methods=['POST']) #Tell Flask what URL triggers upload function.
def upload():
    audio = request.files['NAO_audio'] #Get NAO_audio file from HTTP request.
    if not audio.filename.lower().endswith(".wav"): #Ensure the file is a .wav file.
        return jsonify({"error": "Invalid file format. Only .wav accepted."}), 400 #400 is bad request HTTP status code.
    
    with wave.open(audio.stream, "rb") as wf:
        rec = KaldiRecognizer(vosk_model, wf.getframerate())
        rec.SetWords(True)
        rec.AcceptWaveform(wf.readframes(wf.getnframes()))
        transcript = (json.loads(rec.FinalResult())).get("text", "")
        print("Transcript:", transcript)

    try: #Send transcript to LLM to get a reply.
        response = chat(model="llama3", messages=[{ "role": "system", "content": PROMPT }, { "role": "user", "content": transcript }])
        reply = response["message"]["content"]
        
    except Exception as e:
        reply = "Error getting a reply."
        print("LLM error:", e)

    try:
        result = json.loads(reply)
        emotion = result.get("emotion", "neutral")
        action = result.get("action", "idle")
        speech = result.get("reply", "Good")
    
    except Exception as e:
        print("JSON parsing error:", e)
        emotion = "neutral"
        action = "idle"
        speech = reply
        
    return jsonify({
    "emotion": emotion,
    "action": action,
    "reply": speech
    }), 200

if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", "5000"))
    app.run(host=host, port=port)