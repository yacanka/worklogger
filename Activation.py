import os
from base64 import b64decode, b64encode
from datetime import datetime, timedelta

def encrypt_decrypt(text, key):
    result = []
    key_length = len(key)
    key_as_int = [ord(i) for i in key]
    text_int = [ord(i) for i in text]
    for i in range(len(text_int)):
        value = text_int[i] ^ key_as_int[i % key_length]
        result.append(chr(value))
    return "".join(result)

def str_to_base64(str_text):
    byte_metin = str_text.encode('utf-8')
    return b64encode(byte_metin).decode('utf-8')

def base64_to_str(base64_text):
    base64_byte = base64_text.encode('utf-8')
    return b64decode(base64_byte).decode('utf-8')

def ConvertActivationCode(activationCode):
    try:
        activationCode = activationCode + "=="
        key = str_to_base64(os.getlogin())
        rawText = base64_to_str(encrypt_decrypt(base64_to_str(activationCode), key))
        return rawText
    except Exception as e:
        return None

def CheckActivationStatus(date_str):
    try:
        date = datetime.strptime(date_str, "%d.%m.%Y").date()
        today = datetime.today().date()
        diff = date - today
        diff_days = diff.days
        return diff_days
        
    except Exception as e:
        return -1


def main():
    # pure_key = ConvertActivationCode("KS4mDAA+GA0pLgQAAyt0RQ")
    # pure_key = ConvertActivationCode("KS4YDAAAKkYpLgAAAxVeDg")
    pure_key = ConvertActivationCode("KQAEDAAAOkYpLgAAAxVeDg")

    if pure_key:
        diff_key = CheckActivationStatus(pure_key)
        if diff_key >= 0:
            print(f"VALID KEY! {diff_key} days left")
        else:
            print("Expired activation key")
    else:
        print("Invalid activation key")


if __name__ == "__main__":
    main()

    