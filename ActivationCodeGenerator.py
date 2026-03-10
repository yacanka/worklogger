from datetime import datetime, timedelta
from base64 import b64decode, b64encode

def encrypt_decrypt(text, key):
    result = []
    key_length = len(key)
    key_as_int = [ord(i) for i in key]
    text_int = [ord(i) for i in text]
    for i in range(len(text_int)):
        value = text_int[i] ^ key_as_int[i % key_length]
        result.append(chr(value))
    return "".join(result)

def stripEquals(text):
    if text.endswith('=='):
        return text.rstrip('=')
    else:
        print("!! ERROR! There are some problems with the activation code !!")
        return ""
    return text

def str_to_base64(str_text):
    byte_metin = str_text.encode('utf-8')
    return b64encode(byte_metin).decode('utf-8')

def base64_to_str(base64_text):
    base64_byte = base64_text.encode('utf-8')
    return b64decode(base64_byte).decode('utf-8')

def CreateCode(day_offset, id):
    future_day = datetime.today() + timedelta(days=day_offset)
    future_str = future_day.strftime("%d.%m.%Y")
   
    code = encrypt_decrypt(str_to_base64(future_str), str_to_base64(id))
    result = stripEquals(str_to_base64(code))

    print(code)
    print(future_str)
    print(str_to_base64(future_str))
    print(str_to_base64(id))
    print(result)

    return result


dayOffset = int(input("Enter day offset: "))
ID = input("Enter identity number: ")
print(CreateCode(dayOffset, ID))
