import json
import os

class InteractionMemory(object):

    def __init__(self, filename="emotion_memory.json"):
        self.filename = filename

        if os.path.exists(filename):
            with open(filename, "r") as f:
                self.memory = json.load(f)
        else:
            self.memory = {
                "conversation_turn": 0,

                "modality_weights": {
                    "speech": 1.0,
                    "vision": 1.0
                },

                "emotion_history": {},

                "animation_stats": {},

                "last_emotion": None,
                "last_action": None
            }

    def save(self):
        with open(self.filename, "w") as f:
            json.dump(self.memory, f, indent=4)

    def increment_turn(self):
        self.memory["conversation_turn"] += 1

    def record_emotion(self, emotion):
        history = self.memory["emotion_history"]
        history[emotion] = history.get(emotion, 0) + 1
        self.memory["last_emotion"] = emotion

    def record_action(self, action):
        self.memory["last_action"] = action