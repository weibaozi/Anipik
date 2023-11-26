import random
def get_response(message: str) -> str:
    p_message=message.lower() 

    if p_message == "hello":
        return "Hello, how are you?"
    return "I don't understand you"