import urllib2
import json
import socket
import time
import os
import re
import random
from imp import load_source
from naoqi import ALProxy


def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Doesn't need to be reachable, just triggers the local IP logic.
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception as e:
        ip = "127.0.0.1"
        print("Exception during get_ip: {}".format(e))
    finally:
        s.close()
    return ip


def _normalize_action_key(value):
    key = value.lower().strip()
    key = key.replace("animations/", "")
    key = key.replace("boot-config/", "")
    key = key.replace("sleep-reactions/", "")
    key = key.replace("run_dialog_dev/", "")
    key = re.sub(r"[^a-z0-9]+", "_", key).strip("_")
    return key


def load_behavior_dataset():
    data_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "newtt_actions.py",
    )

    data_module = load_source("nao_animations_data", data_path)
    emotions = getattr(data_module, "EMOTIONS", ())
    emotion_aliases = getattr(data_module, "EMOTION_ALIASES", {})
    commands_by_emotion = getattr(data_module, "COMMANDS_BY_EMOTION", {})

    return emotions, emotion_aliases, commands_by_emotion


def build_actions(commands_by_emotion):
    actions = {"idle": None}

    for emotion, commands in commands_by_emotion.items():
        if commands:
            actions[emotion] = list(commands)

        for command in commands:
            actions[command] = command

            normalized_key = _normalize_action_key(command)
            if normalized_key and normalized_key not in actions:
                actions[normalized_key] = command

    return actions


def resolve_action(action, emotion, actions, commands_by_emotion, emotion_aliases):
    if not action:
        action = ""

    if action in actions:
        target = actions[action]
    else:
        normalized_action = _normalize_action_key(action)
        target = actions.get(normalized_action)

    if isinstance(target, (list, tuple)) and target:
        return random.choice(target)
    if isinstance(target, str):
        return target

    # Fallback: map by emotion if action is unknown.
    normalized_emotion = emotion_aliases.get(emotion, emotion)
    emotion_commands = commands_by_emotion.get(normalized_emotion, ())
    if emotion_commands:
        return random.choice(emotion_commands)

    return None


def send_audio_file_and_reply(AUDIO_FILE_PATH, FILE_NAME, TTS, MANAGER):
    print("Sending audio file to Vosk server for transcription.")
    # Prepare the multipart/form-data request to send the audio file.
    BOUNDARY = "WebKitFormBoundary7MA4YWxkTrZu0gW"
    data = []
    data.append("--" + BOUNDARY + "\r\n")
    data.append('Content-Disposition: form-data; name="NAO_audio"; filename="{}"\r\n'.format(FILE_NAME))
    data.append("Content-Type: audio/wav\r\n\r\n")
    with open(AUDIO_FILE_PATH, 'rb') as file:
        data.append(file.read())
    data.append("\r\n--" + BOUNDARY + "--\r\n")

    body = "".join(data)  # Join the parts into a single request body.

    # Send the audio file to Flask and get a reply from the LLM.
    req = urllib2.Request(
        "http://192.168.1.8:5000/upload",
        data=body,
        headers={
            "Content-Type": "multipart/form-data; boundary={}".format(BOUNDARY),
            "Content-Length": str(len(body))
        }
    )

    try:
        response = urllib2.urlopen(req)
        result = json.loads(response.read())
        emotion = result.get("emotion", "neutral")
        action = result.get("action", "idle")
        reply = result.get("reply", "No reply found from LLM.")

    except Exception as e:
        emotion = "neutral"
        action = "idle"
        reply = "Error contacting Flask host."
        print("Exception: {}".format(e))

    print("Emotion: {}".format(emotion))
    print("Action: {}".format(action))
    print("Reply: {}".format(reply))

    selected_behavior = resolve_action(
        action,
        emotion,
        ACTIONS,
        COMMANDS_BY_EMOTION,
        EMOTION_ALIASES,
    )

    if selected_behavior:
        print("Selected behavior: {}".format(selected_behavior))
        MANAGER.post.runBehavior(selected_behavior)

    TTS.say(str(reply))


def SR_start(SR, MEM, NAO_NAME, VOCABULARY):
    print("Listening for the word(s):", VOCABULARY)
    SR.subscribe(NAO_NAME)
    MEM.insertData("WordRecognized", [])  # Clear previous recognized word.


def run_animation(command, MANAGER):
    if command not in ANIMATIONS:
        return False

    animation = ANIMATIONS[command]
    MANAGER.runBehavior(animation)
    return True


if __name__ == "__main__":
    NAO_NAME = "megatron"
    FILE_NAME = "LLM_prompt.wav"
    NAO_IP = get_ip()  # Get the local IP address.
    NAO_PORT = 9559
    VOCABULARY = ["exit", NAO_NAME, "hello", "show me kung fu", "there's a fly", "dance", "give a tour", "show your muscles", "happy birthday", "goodbye"]
    TTS = ALProxy("ALTextToSpeech", NAO_IP, NAO_PORT)
    SR = ALProxy("ALSpeechRecognition", NAO_IP, NAO_PORT)
    MEM = ALProxy("ALMemory", NAO_IP, NAO_PORT)
    MANAGER = ALProxy("ALBehaviorManager", NAO_IP, NAO_PORT)
    SR.setLanguage("English")

    ANIMATIONS = {
        "hello": "animations/Stand/Emotions/Neutral/Hello_1",
        "show me kung fu": "animations/Stand/Waiting/KungFu_1",
        "there's a fly": "animations/Stand/Gestures/CatchFly_2",
        "dance": "animations/Stand/Waiting/FunnyDancer_1",
        "give a tour": "animations/Stand/Emotions/Positive/Shy_2",
        "show your muscles": "animations/Stand/Waiting/ShowMuscles_1",
        "happy birthday": "animations/Stand/Waiting/HappyBirthday_1",
        "goodbye": "animations/Stand/Emotions/Neutral/Hello_1"
    }

    EMOTIONS, EMOTION_ALIASES, COMMANDS_BY_EMOTION = load_behavior_dataset()
    ACTIONS = build_actions(COMMANDS_BY_EMOTION)
    ACTIONS.setdefault("idle", None)

    total_commands = sum(len(commands) for commands in COMMANDS_BY_EMOTION.values())
    print("Loaded {} commands across {} emotions.".format(total_commands, len(EMOTIONS)))

    try:  # Unsubscribe from any previous subscription to avoid conflicts.
        SR.unsubscribe(NAO_NAME)
    except:
        pass

    SR.pause(True)
    SR.setWordListAsVocabulary(VOCABULARY)  # NAO listens for these wake/command words first.
    SR.pause(False)
    SR_start(SR, MEM, NAO_NAME, VOCABULARY)

    try:
        while True:
            word = MEM.getData("WordRecognized")
            if word and len(word) >= 2 and word[1] > .3:
                if word[0] in ANIMATIONS:
                    print("Animation command detected: {}".format(word[0]))
                    run_animation(word[0], MANAGER)
                    MEM.insertData("WordRecognized", [])

                elif word[0] == NAO_NAME:
                    # Start recording audio to a file so we can send it to the LLM.
                    AUDIO_FILE_PATH = "/home/nao/recordings/audio/{}".format(FILE_NAME)
                    print("Starting audio recording. Say your prompt after the 'listening'")
                    AUDIO = ALProxy("ALAudioRecorder", NAO_IP, NAO_PORT)
                    TTS.say("Listening")
                    AUDIO.startMicrophonesRecording(AUDIO_FILE_PATH, "wav", 16000, [0, 0, 1, 0])
                    time.sleep(.75)
                    silence_duration = 0.0
                    total_audio_duration = 0.0

                    while True:
                        if MEM.getData("SpeechDetected"):
                            silence_duration = 0.0
                        else:
                            silence_duration += .2
                            if silence_duration >= 2.0:
                                AUDIO.stopMicrophonesRecording()
                                SR.unsubscribe(NAO_NAME)
                                print("Audio recording stopped. Sending request to LLM.")
                                send_audio_file_and_reply(AUDIO_FILE_PATH, FILE_NAME, TTS, MANAGER)
                                break

                            total_audio_duration += .2
                            if total_audio_duration >= 30.0:
                                AUDIO.stopMicrophonesRecording()
                                SR.unsubscribe(NAO_NAME)
                                print("Audio recording stopped, too long of an audio.")
                                break

                        time.sleep(.2)

                    SR_start(SR, MEM, NAO_NAME, VOCABULARY)

                elif word[0] == "exit":
                    break

    except KeyboardInterrupt:
        print("KeyboardInterrupt received, exiting.")
    finally:
        try:
            SR.unsubscribe(NAO_NAME)
        except:
            pass

        print("Unsubscribed from speech recognition.")
        TTS.say("Goodbye!")
        print("Exiting program.")
